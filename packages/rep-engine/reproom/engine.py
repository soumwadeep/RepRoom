"""The repetition state machine.

Feed it poses, it tells you where the subject is in a rep, when a rep
completes, and what the form did at the bottom. It is deliberately small,
synchronous and free of any vision dependency -- MediaPipe is only one way to
produce a :class:`~reproom.geometry.PoseFrame`, and tests, recorded sessions and
synthetic fixtures can all drive the same engine.

Counting rules, in the order they are applied
---------------------------------------------
1. A frame only counts if the body is detected well enough to measure
   (``assess_quality``). Frames that fail put the session into ``searching``
   or ``lost`` and never advance the arc.
2. The primary joint angle is smoothed over a short window before it is
   compared to anything, so a single noisy landmark cannot start or finish a
   rep.
3. A rep is counted when the smoothed angle leaves the working end of the arc
   and returns to the extended end, crossing both thresholds plus the
   hysteresis band.
4. A counted rep is discarded if its range of motion or duration falls outside
   the exercise's declared window. Discards are reported as ``no_reps``, not
   silently dropped.
5. Form checks run against the frame captured at the relevant end of the arc.
   A check that cannot run in the current camera view is reported as
   ``not_measurable`` and excluded from the quality score.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from .exercises import ExerciseSpec, VIEW_SIDE, get_spec
from .geometry import PoseFrame, PoseQuality, assess_quality
from .models import (
    CheckResult,
    Phase,
    RepRecord,
    RepStats,
    SessionSummary,
)

#: Consecutive unmeasurable frames tolerated before the session pauses.
DEFAULT_PAUSE_AFTER_MS = 900.0
#: Samples used to smooth the primary joint angle.
DEFAULT_SMOOTHING = 5


@dataclass
class RepUpdate:
    """Everything the UI needs about one fed frame."""

    reps: int
    phase: Phase
    angle: Optional[float]
    presence: str  # 'locked' | 'searching' | 'lost'
    reason: str = ""
    completed: Optional[RepRecord] = None
    discarded: Optional[RepRecord] = None
    cadence_upm: Optional[float] = None
    quality: Optional[float] = None
    fps: Optional[float] = None
    live_checks: List[CheckResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reps": self.reps,
            "phase": self.phase.value,
            "angle": None if self.angle is None else round(self.angle, 1),
            "presence": self.presence,
            "reason": self.reason,
            "completed": self.completed.to_dict() if self.completed else None,
            "discarded": self.discarded.to_dict() if self.discarded else None,
            "cadence_upm": None if self.cadence_upm is None else round(self.cadence_upm, 1),
            "session_quality": None if self.quality is None else round(self.quality, 3),
            "fps": None if self.fps is None else round(self.fps, 1),
            "live_checks": [c.to_dict() for c in self.live_checks],
        }


class RepEngine:
    """Count reps and grade form for one exercise at a time.

    Parameters
    ----------
    exercise:
        Key into :data:`reproom.exercises.CATALOGUE`, or an
        :class:`~reproom.exercises.ExerciseSpec`.
    view:
        Where the camera sits relative to the subject -- ``"side"`` or
        ``"front"``. This decides which form checks are honest to run.
    adaptive_depth:
        When true, the squat depth threshold relaxes toward the subject's own
        deepest measured rep after calibration, so a beginner is graded against
        their range rather than an absolute parallel line. The threshold in use
        and where it came from are always published in
        :attr:`depth_threshold_source`; it never changes invisibly.
    """

    def __init__(
        self,
        exercise: Any,
        view: str = VIEW_SIDE,
        *,
        pause_after_ms: float = DEFAULT_PAUSE_AFTER_MS,
        smoothing: int = DEFAULT_SMOOTHING,
        adaptive_depth: bool = False,
    ) -> None:
        self.spec: ExerciseSpec = exercise if isinstance(exercise, ExerciseSpec) else get_spec(exercise)
        self.view = view
        self.pause_after_ms = pause_after_ms
        self.adaptive_depth = adaptive_depth

        self._window: Deque[float] = deque(maxlen=max(1, smoothing))
        self._stats: Optional[RepStats] = None
        self._in_work_range = False
        self._reps: List[RepRecord] = []
        self._no_reps: List[RepRecord] = []
        self._abandoned = 0
        self._started_ms: Optional[float] = None
        self._last_ms: Optional[float] = None
        self._missing_since: Optional[float] = None
        self._paused_since: Optional[float] = None
        self._paused_total_ms = 0.0
        self._frames = 0
        self._low_confidence_frames = 0
        self._best_depth: Optional[float] = None
        self._depth_threshold = 0.15
        self._depth_source = "absolute"

    # ------------------------------------------------------------- properties
    @property
    def reps(self) -> int:
        return len(self._reps)

    @property
    def no_reps(self) -> int:
        return len(self._no_reps)

    @property
    def abandoned_arcs(self) -> int:
        """Arcs that started and were cut short by the subject leaving the frame.

        Counted separately from ``no_reps`` on purpose. "You did not go deep
        enough" and "you walked off mid-rep" are different facts, and lumping
        them together would make the session report read like a judgement about
        effort when it is mostly about the camera losing sight of you.
        """
        return self._abandoned

    @property
    def depth_threshold_source(self) -> str:
        return self._depth_source

    @property
    def phase(self) -> Phase:
        if self._stats is None:
            return Phase.SETUP
        return self._stats.phase

    # ------------------------------------------------------------------ input
    def feed(self, pose: PoseFrame, now_ms: Optional[float] = None) -> RepUpdate:
        """Advance the engine by one measured pose."""
        now = pose.timestamp_ms if now_ms is None else now_ms
        if self._started_ms is None:
            self._started_ms = now
        dt = None
        if self._last_ms is not None and now > self._last_ms:
            dt = now - self._last_ms
        self._last_ms = now
        self._frames += 1

        quality: PoseQuality = assess_quality(pose)
        if not quality.ok:
            return self._on_missing(now, quality)

        raw = self.spec.primary(pose)
        if raw is None:
            self._low_confidence_frames += 1
            if self._stats is not None:
                self._stats.low_confidence_frames = getattr(
                    self._stats, "low_confidence_frames", 0
                ) + 1
            return RepUpdate(
                reps=self.reps,
                phase=self.phase,
                angle=None,
                presence="searching",
                reason="joint not measurable in this frame",
                cadence_upm=self.cadence_upm,
                quality=self.mean_quality,
                fps=self.fps,
            )

        self._resume(now)
        self._window.append(raw)
        angle = self._smoothed()

        if self._stats is None:
            if self.spec.is_down(angle):
                self._begin_rep(now, angle, pose)
            return RepUpdate(
                reps=self.reps,
                phase=Phase.SETUP if not self._in_work_range else Phase.DESCENDING,
                angle=angle,
                presence="locked",
                cadence_upm=self.cadence_upm,
                quality=self.mean_quality,
                fps=self.fps,
            )

        self._stats.observe(angle, pose, now)
        completed = None
        discarded = None
        phase = self._stats.phase

        if not self._in_work_range:
            if self.spec.is_down(angle):
                self._in_work_range = True
                phase = Phase.DESCENDING
        elif self.spec.is_up(angle):
            phase = Phase.LOCKOUT
            record = self._finish_rep(now)
            completed, discarded = self._validate(record)
            self._stats = None
            self._in_work_range = False
        elif self.spec.is_down(angle):
            phase = Phase.BOTTOM
        else:
            phase = Phase.ASCENDING

        if self._stats is not None:
            self._stats.phase = phase

        return RepUpdate(
            reps=self.reps,
            phase=phase,
            angle=angle,
            presence="locked",
            completed=completed,
            discarded=discarded,
            cadence_upm=self.cadence_upm,
            quality=self.mean_quality,
            fps=self.fps,
        )

    # ------------------------------------------------------------- rep arc
    def _begin_rep(self, now: float, angle: float, pose: PoseFrame) -> None:
        self._stats = RepStats(start_ms=now, last_ms=now, phase=Phase.DESCENDING)
        self._stats.observe(angle, pose, now)
        self._in_work_range = True

    def _finish_rep(self, now: float) -> RepRecord:
        stats = self._stats
        assert stats is not None
        checks = self._run_checks(stats)
        record = RepRecord(
            index=len(self._reps) + len(self._no_reps) + 1,
            exercise=self.spec.key,
            started_ms=stats.start_ms,
            duration_ms=max(0.0, now - stats.start_ms),
            primary_min=stats.primary_min,
            primary_max=stats.primary_max,
            range_of_motion=stats.range_of_motion,
            checks=checks,
            low_confidence_frames=getattr(stats, "low_confidence_frames", 0),
        )
        record.duration_ms = stats.duration_ms
        return record

    def _validate(self, record: RepRecord) -> Tuple[Optional[RepRecord], Optional[RepRecord]]:
        """Accept a rep only if it moved through a real, controlled arc."""
        rom = record.range_of_motion
        if rom is None or rom < self.spec.min_rom:
            self._no_reps.append(record)
            return None, record
        if record.duration_ms < self.spec.min_duration_ms:
            self._no_reps.append(record)
            return None, record
        if record.duration_ms > self.spec.max_duration_ms:
            self._no_reps.append(record)
            return None, record
        self._reps.append(record)
        self._track_depth(record)
        return record, None

    def _track_depth(self, record: RepRecord) -> None:
        """Roll the subject's own deepest measured rep into the depth gate."""
        depth = next((c for c in record.checks if c.key == "depth" and c.measured is not None), None)
        if depth is None:
            return
        value = depth.measured
        if self._best_depth is None or value < self._best_depth:
            self._best_depth = value
        if self.adaptive_depth and len(self._reps) >= 3 and self._best_depth is not None:
            relaxed = max(0.15, self._best_depth + 0.08)
            if abs(relaxed - self._depth_threshold) > 1e-9:
                self._depth_threshold = relaxed
                self._depth_source = "adaptive:personal-best+0.08"

    def _run_checks(self, stats: RepStats) -> List[CheckResult]:
        """Grade every declared check, and say plainly which ones could not run.

        A check that is invalid for the current camera view is recorded as
        ``not_measurable`` rather than being filtered out. The TV then shows
        "not measured from this angle" instead of implying a pass the camera
        never earned.
        """
        out: List[CheckResult] = []
        for check in self.spec.checks:
            if self.view not in check.views:
                out.append(
                    CheckResult.unmeasurable(
                        check.key,
                        check.label,
                        f"not valid from a {self.view} camera",
                        severity=check.severity,
                    )
                )
                continue
            pose = stats.extreme_pose if check.applies_to == "bottom" else stats.max_pose
            result = check.evaluate(pose, stats)
            if result is None:
                out.append(
                    CheckResult.unmeasurable(
                        check.key, check.label, f"not valid from a {self.view} camera"
                    )
                )
                continue
            if result.key == "depth":
                result = _rethreshold(result, self._depth_threshold)
            out.append(result)
        return out

    # ------------------------------------------------------------- presence
    def _on_missing(self, now: float, quality: PoseQuality) -> RepUpdate:
        reason = "; ".join(quality.reasons) or "body not detected"
        if self._paused_since is not None:
            return RepUpdate(
                reps=self.reps,
                phase=Phase.HOLDING,
                angle=None,
                presence="lost",
                reason=reason,
                cadence_upm=self.cadence_upm,
                quality=self.mean_quality,
                fps=self.fps,
            )
        if self._missing_since is None:
            self._missing_since = now
        elif now - self._missing_since >= self.pause_after_ms:
            self._paused_since = now
            # An arc interrupted by the subject leaving the frame is not a rep.
            if self._stats is not None:
                self._abandoned += 1
            self._stats = None
            self._in_work_range = False
            self._window.clear()
            return RepUpdate(
                reps=self.reps,
                phase=Phase.HOLDING,
                angle=None,
                presence="lost",
                reason=f"paused: {reason}",
                cadence_upm=self.cadence_upm,
                quality=self.mean_quality,
                fps=self.fps,
            )
        return RepUpdate(
            reps=self.reps,
            phase=self.phase,
            angle=None,
            presence="searching",
            reason=reason,
            cadence_upm=self.cadence_upm,
            quality=self.mean_quality,
            fps=self.fps,
        )

    def _resume(self, now: float) -> None:
        self._missing_since = None
        if self._paused_since is not None:
            self._paused_total_ms += now - self._paused_since
            self._paused_since = None

    # ------------------------------------------------------------- readouts
    @property
    def fps(self) -> Optional[float]:
        """Measured feed rate, derived from the timestamps actually supplied.

        The UI prints this next to tempo and cadence because those two numbers
        are only as trustworthy as this one.
        """
        if self._started_ms is None or self._last_ms is None or self._frames < 2:
            return None
        span = self._last_ms - self._started_ms
        if span <= 0:
            return None
        return (self._frames - 1) * 1000.0 / span

    @property
    def cadence_upm(self) -> Optional[float]:
        """Reps per minute over the last five counted reps."""
        recent = self._reps[-5:]
        if not recent:
            return None
        mean_ms = sum(r.duration_ms for r in recent) / len(recent)
        if mean_ms <= 0:
            return None
        return 60000.0 / mean_ms

    @property
    def mean_quality(self) -> Optional[float]:
        scored = [r for r in self._reps if r.checks_run]
        if not scored:
            return None
        return sum(r.quality for r in scored) / len(scored)

    @property
    def weakest_check(self) -> Optional[str]:
        """The form check that fails most often, for the coaching cue."""
        counts: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for rep in self._reps:
            for check in rep.checks:
                if check.status != "fail":
                    continue
                counts[check.key] = counts.get(check.key, 0) + 1
                labels[check.key] = check.label
        if not counts:
            return None
        key = max(counts.items(), key=lambda kv: kv[1])[0]
        return labels[key]

    def _smoothed(self) -> float:
        return sum(self._window) / len(self._window)

    def summary(self) -> SessionSummary:
        reps = self._reps
        return SessionSummary(
            exercise=self.spec.key,
            started_ms=self._started_ms or 0.0,
            reps=len(reps),
            cadence_upm=self.cadence_upm,
            mean_quality=self.mean_quality,
            mean_tempo_ms=(
                sum(r.duration_ms for r in reps) / len(reps) if reps else None
            ),
            total_active_ms=(self._last_ms or 0.0) - (self._started_ms or 0.0) - self._paused_total_ms,
            pause_ms=self._paused_total_ms,
            lowest_check=self.weakest_check,
            per_rep=list(reps),
        )

    def state(self) -> Dict[str, Any]:
        """Full session state, including the honesty fields."""
        summary = self.summary().to_dict()
        summary.update(
            {
                "no_reps": self.no_reps,
                "abandoned_arcs": self.abandoned_arcs,
                "frames": self._frames,
                "low_confidence_frames": self._low_confidence_frames,
                "view": self.view,
                "fps_estimate": None if self.fps is None else round(self.fps, 1),
                "depth_threshold": round(self._depth_threshold, 3),
                "depth_threshold_source": self._depth_source,
                "exercise": {
                    "name": self.spec.name,
                    "focus": self.spec.focus,
                    "primary_label": self.spec.primary_label,
                    "up_angle": self.spec.up_angle,
                    "down_angle": self.spec.down_angle,
                    "guidance": self.spec.camera_guidance,
                },
            }
        )
        return summary


def _rethreshold(result: CheckResult, threshold: float) -> CheckResult:
    """Re-grade a depth measurement against the threshold currently in force."""
    if result.measured is None:
        return result
    ok = result.measured <= threshold
    return CheckResult(
        key=result.key,
        label=result.label,
        ok=ok,
        severity=result.severity,
        measured=result.measured,
        threshold=threshold,
        unit=result.unit,
        status="pass" if ok else "fail",
        detail=result.detail if ok else "above the depth target",
    )
