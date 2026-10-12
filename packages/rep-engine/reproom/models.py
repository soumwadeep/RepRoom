"""Data models shared by the rep engine and its consumers.

Every number that reaches the TV is produced here, and every field documents
whether it was measured or not. ``None`` means "not measured" and is preserved
all the way to the UI -- it is never replaced by a zero or a plausible guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Phase(str, Enum):
    """Where in a repetition the subject currently is."""

    SETUP = "setup"
    DESCENDING = "descending"
    BOTTOM = "bottom"
    ASCENDING = "ascending"
    LOCKOUT = "lockout"
    HOLDING = "holding"


#: Severity drives both the colour on the TV and the order of coaching cues.
SEVERITY_CRITICAL = "critical"  # the rep did not happen as intended
SEVERITY_POSTURE = "posture"  # joint position that risks a load going wrong
SEVERITY_TEMP = "tempo"  # pacing, not safety


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one form check for one rep.

    ``measured`` is ``None`` whenever the camera geometry made the check
    unmeasurable. That is reported as ``not_measurable`` rather than as a pass,
    because "the check could not run" and "the check passed" are different
    claims and the subject deserves to know which one they are being shown.
    """

    key: str
    label: str
    ok: bool
    severity: str
    measured: Optional[float] = None
    threshold: Optional[float] = None
    unit: str = "deg"
    detail: str = ""
    status: str = "pass"  # pass | fail | not_measurable

    @classmethod
    def passed(cls, key: str, label: str, **kw: Any) -> "CheckResult":
        return cls(key=key, label=label, ok=True, severity=kw.pop("severity", SEVERITY_POSTURE), status="pass", **kw)

    @classmethod
    def failed(cls, key: str, label: str, **kw: Any) -> "CheckResult":
        return cls(key=key, label=label, ok=False, severity=kw.pop("severity", SEVERITY_POSTURE), status="fail", **kw)

    @classmethod
    def unmeasurable(cls, key: str, label: str, detail: str, severity: str = SEVERITY_POSTURE) -> "CheckResult":
        return cls(
            key=key,
            label=label,
            ok=False,
            severity=severity,
            status="not_measurable",
            detail=detail,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "ok": self.ok,
            "severity": self.severity,
            "measured": self.measured,
            "threshold": self.threshold,
            "unit": self.unit,
            "detail": self.detail,
            "status": self.status,
        }


@dataclass
class RepStats:
    """Measurements accumulated while one repetition is in progress."""

    start_ms: float
    last_ms: float
    phase: Phase = Phase.SETUP
    primary_min: Optional[float] = None
    primary_max: Optional[float] = None
    #: The pose captured at the decision point of the rep (bottom of a squat,
    #: squeeze of a curl). Form checks run against this frame, not a random one.
    extreme_pose: Optional[Any] = None
    extreme_ms: Optional[float] = None
    #: The pose captured at the other end of the arc -- the lockout of an
    #: overhead press or the top of a push-up, where a different set of checks
    #: applies.
    max_pose: Optional[Any] = None
    max_ms: Optional[float] = None
    samples: int = 0
    #: Frames inside this rep where the graded joint could not be measured.
    low_confidence_frames: int = 0

    def observe(self, value: Optional[float], pose: Any, now_ms: float) -> None:
        self.samples += 1
        self.last_ms = now_ms
        if value is None:
            return
        if self.primary_min is None or value < self.primary_min:
            self.primary_min, self.extreme_pose, self.extreme_ms = value, pose, now_ms
        if self.primary_max is None or value > self.primary_max:
            self.primary_max, self.max_pose, self.max_ms = value, pose, now_ms

    @property
    def range_of_motion(self) -> Optional[float]:
        if self.primary_min is None or self.primary_max is None:
            return None
        return self.primary_max - self.primary_min

    @property
    def duration_ms(self) -> float:
        return self.last_ms - self.start_ms


@dataclass
class RepRecord:
    """A completed repetition, ready to be serialised."""

    index: int
    exercise: str
    started_ms: float
    duration_ms: float
    primary_min: Optional[float]
    primary_max: Optional[float]
    range_of_motion: Optional[float]
    checks: List[CheckResult] = field(default_factory=list)
    #: Frames where the engine could not measure the joint it needed.
    low_confidence_frames: int = 0

    @property
    def quality(self) -> float:
        """Fraction of *measurable* form checks that passed.

        Unmeasurable checks are excluded from both numerator and denominator,
        so a subject standing too far from the camera lowers ``checks_run``
        rather than inflating this score.
        """
        scored = [c for c in self.checks if c.status != "not_measurable"]
        if not scored:
            return 0.0
        return sum(1 for c in scored if c.ok) / len(scored)

    @property
    def checks_run(self) -> int:
        return sum(1 for c in self.checks if c.status != "not_measurable")

    @property
    def failed(self) -> List[str]:
        return [c.key for c in self.checks if c.status == "fail"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "exercise": self.exercise,
            "duration_ms": round(self.duration_ms),
            "primary_min": _r1(self.primary_min),
            "primary_max": _r1(self.primary_max),
            "range_of_motion": _r1(self.range_of_motion),
            "quality": round(self.quality, 3),
            "checks_run": self.checks_run,
            "failed": self.failed,
            "low_confidence_frames": self.low_confidence_frames,
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class SessionSummary:
    """Rolling totals for the whole session."""

    exercise: str
    started_ms: float
    reps: int = 0
    cadence_upm: Optional[float] = None
    mean_quality: Optional[float] = None
    mean_tempo_ms: Optional[float] = None
    total_active_ms: float = 0.0
    pause_ms: float = 0.0
    lowest_check: Optional[str] = None
    per_rep: List[RepRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exercise": self.exercise,
            "reps": self.reps,
            "elapsed_ms": round(self.total_active_ms),
            "pause_ms": round(self.pause_ms),
            "cadence_upm": _r1(self.cadence_upm),
            "mean_quality": None if self.mean_quality is None else round(self.mean_quality, 3),
            "mean_tempo_ms": None if self.mean_tempo_ms is None else round(self.mean_tempo_ms),
            "lowest_check": self.lowest_check,
            "rep_log": [r.to_dict() for r in self.per_rep],
        }


def _r1(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 1)
