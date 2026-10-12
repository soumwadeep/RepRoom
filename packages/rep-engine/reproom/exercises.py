"""Exercise catalogue: what counts as one rep, and what form to grade.

Each exercise declares the joint angle its repetition is measured on, the
thresholds that define the contracted and extended ends of that arc, and the
form checks that run on the frames captured at those extremes.

Camera view matters, and is part of the contract rather than an afterthought.
All angles here are measured in the 2D image plane from a single monocular
camera, so a check is only valid from a view where the joint actually rotates
in that plane. Every check declares the views it is valid in; anything not
declared for the current view is reported as ``not_measurable`` and is excluded
from the quality score. A squat filmed from the front produces a genuine
``not_measurable`` on depth instead of a fabricated green tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .geometry import (
    LEFT_ANKLE,
    LEFT_ELBOW,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_ANKLE,
    RIGHT_ELBOW,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    PoseFrame,
    angle_at,
    elbow_angle,
    hip_angle,
    knee_angle,
    side_mean,
    spine_angle,
    torso_lean,
)
from .models import (
    CheckResult,
    RepStats,
    SEVERITY_CRITICAL,
    SEVERITY_POSTURE,
    SEVERITY_TEMP,
)

VIEW_SIDE = "side"
VIEW_FRONT = "front"
VIEWS_ANY = (VIEW_SIDE, VIEW_FRONT)


@dataclass(frozen=True)
class FormCheck:
    """One graded aspect of a repetition.

    ``evaluate`` receives the pose captured at the relevant end of the arc and
    the rep's accumulated stats. It returns ``None`` when the check cannot run
    in the current view -- the engine turns that into ``not_measurable``.
    """

    key: str
    label: str
    severity: str
    views: Tuple[str, ...]
    applies_to: str  # 'bottom' (min angle) or 'lockout' (max angle)
    evaluate: Callable[[Optional[PoseFrame], RepStats], Optional[CheckResult]]
    cue: str = ""


def _torso_scale(pose: PoseFrame) -> float:
    scale = pose.torso_length
    return scale if scale > 1e-6 else 0.0


# --------------------------------------------------------------------- checks
def check_squat_depth(views_ok: bool):
    """Hip dropped to (or below) the knee, measured at the bottom of the squat.

    ``(knee_y - hip_y) / torso_length`` is ~1.0 standing and approaches 0 at
    parallel, so the threshold is an upper bound on how much thigh is still
    above the hip. Scale-invariant: it behaves the same whether the subject is
    1 m or 4 m from the lens.
    """

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None or not views_ok:
            return None
        if not pose.visible(LEFT_HIP, RIGHT_HIP, LEFT_KNEE, RIGHT_KNEE):
            return CheckResult.unmeasurable(
                "depth", "Depth", "hip or knee landmarks lost at the bottom"
            )
        scale = _torso_scale(pose)
        if scale <= 0:
            return CheckResult.unmeasurable("depth", "Depth", "no torso to scale against")
        knee_y = max(pose.lm(LEFT_KNEE).y, pose.lm(RIGHT_KNEE).y)
        hip_y = pose.hip_center.y
        measured = (knee_y - hip_y) / scale
        threshold = 0.15
        ok = measured <= threshold
        return CheckResult(
            key="depth",
            label="Depth",
            ok=ok,
            severity=SEVERITY_CRITICAL,
            measured=measured,
            threshold=threshold,
            unit="ratio",
            status="pass" if ok else "fail",
            detail="hips at or below parallel" if ok else "stopped above parallel",
        )

    return evaluate


def check_torso_lean(limit: float, label: str = "Back angle", views=(VIEW_SIDE,)):
    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None or not any(v in views for v in (VIEW_SIDE, VIEW_FRONT)):
            return None
        lean = torso_lean(pose)
        if lean is None:
            return CheckResult.unmeasurable(
                "torso_lean", label, "shoulders or hips not detected"
            )
        ok = lean <= limit
        return CheckResult(
            key="torso_lean",
            label=label,
            ok=ok,
            severity=SEVERITY_POSTURE,
            measured=lean,
            threshold=limit,
            unit="deg",
            status="pass" if ok else "fail",
            detail="torso within range" if ok else f"{limit:.0f} deg limit exceeded",
        )

    return evaluate


def check_knee_track(max_drift: float = 0.10):
    """Knee stays over the ankle column, measured from a frontal view.

    This flags the knee travelling away from the foot in *either* direction --
    valgus collapse and varus push-out look the same to a single 2D camera, and
    saying so is more honest than naming one.

    Drift is normalised by torso length, not shoulder width. That choice is the
    whole point: a collapsing knee drags the hips inward with it, so a
    shoulder-width scale shrinks toward zero at the same moment the numerator
    grows, and the ratio can only ever flatter the rep.
    """

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None:
            return None
        if not pose.visible(LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE):
            return CheckResult.unmeasurable(
                "knee_track", "Knee tracking", "knee or ankle landmarks lost"
            )
        scale = _torso_scale(pose)
        if scale <= 0:
            return CheckResult.unmeasurable(
                "knee_track", "Knee tracking", "no torso to scale against"
            )
        left_drift = abs(pose.lm(LEFT_KNEE).x - pose.lm(LEFT_ANKLE).x)
        right_drift = abs(pose.lm(RIGHT_KNEE).x - pose.lm(RIGHT_ANKLE).x)
        measured = max(left_drift, right_drift) / scale
        ok = measured <= max_drift
        return CheckResult(
            key="knee_track",
            label="Knee tracking",
            ok=ok,
            severity=SEVERITY_POSTURE,
            measured=measured,
            threshold=max_drift,
            unit="ratio",
            status="pass" if ok else "fail",
            detail="knees stacked over feet" if ok else "knees drifted off the foot column",
        )

    return evaluate


def check_asymmetry(limit: float, name: str):
    """Left and right sides move through the same arc.

    Only meaningful when both sides were measurable; a single visible limb is
    reported as unmeasurable rather than as perfect symmetry.
    """

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None:
            return None
        left, right, gap = _side_gap(pose, name)
        if gap is None:
            return CheckResult.unmeasurable(
                "asymmetry", "Left/right balance", "only one side was measurable"
            )
        ok = gap <= limit
        return CheckResult(
            key="asymmetry",
            label="Left/right balance",
            ok=ok,
            severity=SEVERITY_POSTURE,
            measured=gap,
            threshold=limit,
            unit="deg",
            status="pass" if ok else "fail",
            detail="both sides matched" if ok else f"{gap:.0f} deg apart",
        )

    return evaluate


def _side_gap(pose: PoseFrame, name: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if name == "knee":
        left, right = knee_angle(pose, "left"), knee_angle(pose, "right")
    elif name == "elbow":
        left, right = elbow_angle(pose, "left"), elbow_angle(pose, "right")
    elif name == "hip":
        left, right = hip_angle(pose, "left"), hip_angle(pose, "right")
    else:
        return None, None, None
    mean, gap = side_mean(left, right)
    return left, right, gap


def check_body_line(min_angle: float = 155.0):
    """Shoulder-hip-knee stays straight under load: no hip sag, no pike."""

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None:
            return None
        line = spine_angle(pose)
        if line is None:
            return CheckResult.unmeasurable(
                "body_line", "Body line", "spine landmarks lost at the bottom"
            )
        ok = line >= min_angle
        return CheckResult(
            key="body_line",
            label="Body line",
            ok=ok,
            severity=SEVERITY_CRITICAL,
            measured=line,
            threshold=min_angle,
            unit="deg",
            status="pass" if ok else "fail",
            detail="straight line shoulder to knee" if ok else "hips sagged or piked",
        )

    return evaluate


def check_overhead(min_clear: float = 0.45):
    """Wrists finish clearly above the shoulder line at lockout."""

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None:
            return None
        if not pose.visible(LEFT_WRIST, RIGHT_WRIST, LEFT_SHOULDER, RIGHT_SHOULDER):
            return CheckResult.unmeasurable(
                "overhead", "Lockout overhead", "wrists or shoulders lost"
            )
        scale = _torso_scale(pose)
        if scale <= 0:
            return CheckResult.unmeasurable("overhead", "Lockout overhead", "no torso to scale against")
        wrist_y = (pose.lm(LEFT_WRIST).y + pose.lm(RIGHT_WRIST).y) / 2.0
        measured = (pose.shoulder_center.y - wrist_y) / scale
        ok = measured >= min_clear
        return CheckResult(
            key="overhead",
            label="Lockout overhead",
            ok=ok,
            severity=SEVERITY_CRITICAL,
            measured=measured,
            threshold=min_clear,
            unit="ratio",
            status="pass" if ok else "fail",
            detail="arms finished overhead" if ok else "stopped short of lockout",
        )

    return evaluate


def check_wrist_path(max_offset: float = 0.20):
    """Wrists travel over the shoulder line instead of drifting forward."""

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None:
            return None
        if not pose.visible(LEFT_WRIST, RIGHT_WRIST, LEFT_SHOULDER, RIGHT_SHOULDER):
            return CheckResult.unmeasurable("wrist_path", "Bar path", "wrists or shoulders lost")
        width = pose.shoulder_width
        if width <= 1e-6:
            return CheckResult.unmeasurable("wrist_path", "Bar path", "no shoulder width to scale against")
        wrist_x = (pose.lm(LEFT_WRIST).x + pose.lm(RIGHT_WRIST).x) / 2.0
        measured = abs(wrist_x - pose.shoulder_center.x) / width
        ok = measured <= max_offset
        return CheckResult(
            key="wrist_path",
            label="Bar path",
            ok=ok,
            severity=SEVERITY_POSTURE,
            measured=measured,
            threshold=max_offset,
            unit="ratio",
            status="pass" if ok else "fail",
            detail="wrists stacked over shoulders" if ok else "wrists drifted off centre",
        )

    return evaluate


def check_elbow_at_side(max_drift: float = 0.45):
    """Elbow does not drift out or forward during a curl."""

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        if pose is None:
            return None
        if not pose.visible(LEFT_ELBOW, RIGHT_ELBOW, LEFT_SHOULDER, RIGHT_SHOULDER):
            return CheckResult.unmeasurable(
                "elbow_position", "Elbow position", "elbows or shoulders lost"
            )
        width = pose.shoulder_width
        if width <= 1e-6:
            return CheckResult.unmeasurable(
                "elbow_position", "Elbow position", "no shoulder width to scale against"
            )
        left_drift = abs(pose.lm(LEFT_ELBOW).x - pose.lm(LEFT_SHOULDER).x)
        right_drift = abs(pose.lm(RIGHT_ELBOW).x - pose.lm(RIGHT_SHOULDER).x)
        measured = max(left_drift, right_drift) / width
        ok = measured <= max_drift
        return CheckResult(
            key="elbow_position",
            label="Elbow position",
            ok=ok,
            severity=SEVERITY_POSTURE,
            measured=measured,
            threshold=max_drift,
            unit="ratio",
            status="pass" if ok else "fail",
            detail="elbows stayed anchored" if ok else "elbows wandered",
        )

    return evaluate


def check_tempo(min_ms: float):
    """A rep that is flushed in under ``min_ms`` was not controlled."""

    def evaluate(pose: Optional[PoseFrame], stats: RepStats) -> Optional[CheckResult]:
        measured = stats.duration_ms
        ok = measured >= min_ms
        return CheckResult(
            key="tempo",
            label="Tempo",
            ok=ok,
            severity=SEVERITY_TEMP,
            measured=measured,
            threshold=min_ms,
            unit="ms",
            status="pass" if ok else "fail",
            detail="controlled through the arc" if ok else "rep was rushed",
        )

    return evaluate


# ------------------------------------------------------------------ exercises
@dataclass(frozen=True)
class ExerciseSpec:
    key: str
    name: str
    focus: str
    #: Returns the joint angle the repetition is counted on, averaged over both
    #: sides when both are measurable. ``None`` means this frame cannot be used.
    primary: Callable[[PoseFrame], Optional[float]]
    primary_label: str
    #: Angle at the top of the movement (fully extended / start position).
    up_angle: float
    #: Angle at the working end of the movement (bottom of a squat, squeeze of
    #: a curl). A rep counts when the measured angle crosses this and comes back.
    down_angle: float
    #: Guard band around both thresholds so a joint oscillating on the line is
    #: not counted as a hundred reps.
    hysteresis: float
    min_rom: float
    min_duration_ms: float
    max_duration_ms: float
    recommended_view: str
    camera_guidance: str
    checks: Sequence[FormCheck] = ()

    def is_down(self, angle: Optional[float]) -> bool:
        return angle is not None and angle <= self.down_angle - self.hysteresis

    def is_up(self, angle: Optional[float]) -> bool:
        return angle is not None and angle >= self.up_angle - self.hysteresis

    def checks_for(self, view: str) -> List[FormCheck]:
        return [c for c in self.checks if view in c.views]


_SQUAT = ExerciseSpec(
    key="squat",
    name="Bodyweight squat",
    focus="Quads, glutes, core",
    primary=lambda p: side_mean(knee_angle(p, "left"), knee_angle(p, "right"))[0],
    primary_label="Knee angle",
    up_angle=165.0,
    down_angle=115.0,
    hysteresis=6.0,
    min_rom=25.0,
    # Anything under this is not a rep at all and is reported as a discard.
    min_duration_ms=700.0,
    max_duration_ms=8000.0,
    recommended_view=VIEW_SIDE,
    camera_guidance="Prop the phone to the side, about 3 m back, lens level with your hips.",
    checks=(
        FormCheck("depth", "Depth", SEVERITY_CRITICAL, (VIEW_SIDE,), "bottom", check_squat_depth(True)),
        FormCheck("torso_lean", "Back angle", SEVERITY_POSTURE, (VIEW_SIDE,), "bottom", check_torso_lean(60.0)),
        FormCheck("knee_track", "Knee tracking", SEVERITY_POSTURE, (VIEW_FRONT,), "bottom", check_knee_track()),
        FormCheck("asymmetry", "Left/right balance", SEVERITY_POSTURE, VIEWS_ANY, "bottom", check_asymmetry(12.0, "knee")),
        # The tempo floor sits above the discard floor on purpose: a rep can be
        # real and still rushed, and those are two different messages.
        FormCheck("tempo", "Tempo", SEVERITY_TEMP, VIEWS_ANY, "lockout", check_tempo(1100.0)),
    ),
)

_PUSHUP = ExerciseSpec(
    key="pushup",
    name="Push-up",
    focus="Chest, triceps, core",
    primary=lambda p: side_mean(elbow_angle(p, "left"), elbow_angle(p, "right"))[0],
    primary_label="Elbow angle",
    up_angle=160.0,
    down_angle=105.0,
    hysteresis=8.0,
    min_rom=30.0,
    min_duration_ms=500.0,
    max_duration_ms=12000.0,
    recommended_view=VIEW_SIDE,
    camera_guidance="Set the phone on the floor to your side so it can see shoulder, hip and knee.",
    checks=(
        FormCheck("body_line", "Body line", SEVERITY_CRITICAL, (VIEW_SIDE,), "bottom", check_body_line(155.0)),
        FormCheck("asymmetry", "Left/right balance", SEVERITY_POSTURE, VIEWS_ANY, "bottom", check_asymmetry(15.0, "elbow")),
        FormCheck("tempo", "Tempo", SEVERITY_TEMP, VIEWS_ANY, "lockout", check_tempo(500.0)),
    ),
)

_OVERHEAD_PRESS = ExerciseSpec(
    key="overhead_press",
    name="Overhead press",
    focus="Shoulders, triceps",
    primary=lambda p: side_mean(elbow_angle(p, "left"), elbow_angle(p, "right"))[0],
    primary_label="Elbow angle",
    up_angle=168.0,
    down_angle=100.0,
    hysteresis=8.0,
    min_rom=40.0,
    min_duration_ms=700.0,
    max_duration_ms=10000.0,
    recommended_view=VIEW_FRONT,
    camera_guidance="Face the phone squarely and stand far enough back that your hands clear your head at the top.",
    checks=(
        FormCheck("overhead", "Lockout overhead", SEVERITY_CRITICAL, VIEWS_ANY, "lockout", check_overhead(0.45)),
        FormCheck("wrist_path", "Bar path", SEVERITY_POSTURE, (VIEW_FRONT,), "lockout", check_wrist_path()),
        FormCheck("asymmetry", "Left/right balance", SEVERITY_POSTURE, VIEWS_ANY, "lockout", check_asymmetry(15.0, "elbow")),
        FormCheck("tempo", "Tempo", SEVERITY_TEMP, VIEWS_ANY, "lockout", check_tempo(700.0)),
    ),
)

_BICEP_CURL = ExerciseSpec(
    key="bicep_curl",
    name="Bicep curl",
    focus="Biceps",
    primary=lambda p: side_mean(elbow_angle(p, "left"), elbow_angle(p, "right"))[0],
    primary_label="Elbow angle",
    up_angle=160.0,
    down_angle=80.0,
    hysteresis=10.0,
    min_rom=40.0,
    min_duration_ms=800.0,
    max_duration_ms=10000.0,
    recommended_view=VIEW_FRONT,
    camera_guidance="Face the phone; frame from hips to overhead so both elbows stay in shot.",
    checks=(
        FormCheck("elbow_position", "Elbow position", SEVERITY_POSTURE, (VIEW_FRONT,), "bottom", check_elbow_at_side()),
        FormCheck("torso_lean", "No lean-back", SEVERITY_POSTURE, (VIEW_SIDE,), "bottom", check_torso_lean(20.0)),
        FormCheck("asymmetry", "Left/right balance", SEVERITY_POSTURE, VIEWS_ANY, "bottom", check_asymmetry(15.0, "elbow")),
        FormCheck("tempo", "Tempo", SEVERITY_TEMP, VIEWS_ANY, "lockout", check_tempo(800.0)),
    ),
)

_LUNGE = ExerciseSpec(
    key="lunge",
    name="Split squat / lunge",
    focus="Quads, glutes, balance",
    primary=lambda p: side_mean(knee_angle(p, "left"), knee_angle(p, "right"))[0],
    primary_label="Knee angle",
    up_angle=160.0,
    down_angle=120.0,
    hysteresis=6.0,
    min_rom=20.0,
    min_duration_ms=900.0,
    max_duration_ms=9000.0,
    recommended_view=VIEW_SIDE,
    camera_guidance="Side view again, and frame wide enough to keep both feet in shot as you drop.",
    checks=(
        FormCheck("torso_lean", "Back angle", SEVERITY_POSTURE, (VIEW_SIDE,), "bottom", check_torso_lean(35.0)),
        FormCheck("asymmetry", "Left/right balance", SEVERITY_POSTURE, VIEWS_ANY, "bottom", check_asymmetry(25.0, "knee")),
        FormCheck("tempo", "Tempo", SEVERITY_TEMP, VIEWS_ANY, "lockout", check_tempo(900.0)),
    ),
)

CATALOGUE: Dict[str, ExerciseSpec] = {
    spec.key: spec
    for spec in (_SQUAT, _PUSHUP, _OVERHEAD_PRESS, _BICEP_CURL, _LUNGE)
}


def get_spec(key: str) -> ExerciseSpec:
    try:
        return CATALOGUE[key]
    except KeyError:
        raise KeyError(
            f"unknown exercise {key!r}; known: {', '.join(sorted(CATALOGUE))}"
        ) from None


def catalogue_summary() -> List[Dict[str, Any]]:
    """Machine-readable catalogue for the TV's exercise picker."""
    return [
        {
            "key": spec.key,
            "name": spec.name,
            "focus": spec.focus,
            "view": spec.recommended_view,
            "guidance": spec.camera_guidance,
            "checks": [c.key for c in spec.checks],
        }
        for spec in CATALOGUE.values()
    ]
