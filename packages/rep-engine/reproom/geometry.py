"""Pose geometry: landmarks, joint angles and body metrics.

Pure Python and standard library only, so this module can be embedded in any
runtime -- a FastAPI service, an edge device, or a test fixture -- without
pulling in a vision stack.

Coordinate system (matches MediaPipe / BlazePose output)
-------------------------------------------------------
``x`` and ``y`` are normalised to the frame, origin at the **top-left** corner,
so ``y`` *increases downwards*. ``z`` is the relative depth of a landmark with
respect to the hip centre; it is a network estimate, is not metric, and is only
used here as a weak tie-breaker. All angle math in this package is done in the
2D image plane, which has one important consequence documented throughout: a
joint angle measured from a camera that is not roughly perpendicular to the
plane the joint moves in is compressed toward 180 degrees. The engine therefore
reports ``low_confidence`` rather than inventing a measurement.

Landmark indices are the 33-point BlazePose set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator, Optional, Sequence, Tuple

# --- BlazePose 33-point landmark indices ------------------------------------
NOSE = 0
LEFT_EYE = 2
RIGHT_EYE = 5
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_PINKY = 17
RIGHT_PINKY = 18
LEFT_INDEX = 19
RIGHT_INDEX = 20
LEFT_THUMB = 21
RIGHT_THUMB = 22
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32

NUM_LANDMARKS = 33

#: Visibility below which a landmark is treated as unusable for measurement.
MIN_VISIBILITY = 0.5


@dataclass(frozen=True)
class Landmark:
    """One body landmark in normalised image coordinates."""

    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0
    presence: float = 1.0

    def as_point(self) -> Tuple[float, float]:
        return (self.x, self.y)


def _as_landmark(value) -> Landmark:
    """Accept Landmark, a (x, y[, z]) tuple, or an object with .x/.y/.z."""
    if isinstance(value, Landmark):
        return value
    if hasattr(value, "x") and hasattr(value, "y"):
        z = getattr(value, "z", 0.0)
        visibility = getattr(value, "visibility", 1.0)
        presence = getattr(value, "presence", 1.0)
        try:
            visibility = float(visibility)
        except (TypeError, ValueError):
            visibility = 1.0
        try:
            presence = float(presence)
        except (TypeError, ValueError):
            presence = 1.0
        return Landmark(float(value.x), float(value.y), float(z), visibility, presence)
    parts = tuple(value)
    if len(parts) < 2:
        raise ValueError("a landmark needs at least x and y")
    z = float(parts[2]) if len(parts) > 2 else 0.0
    return Landmark(float(parts[0]), float(parts[1]), z)


@dataclass
class PoseFrame:
    """A single measured pose.

    ``timestamp_ms`` is monotonic session time, not wall-clock, and every
    duration reported by the engine is derived from it. If you feed the engine
    frames at a rate you have not measured, the rep *counts* stay correct but
    tempo and cadence will not be -- the engine reports ``fps_estimate`` so the
    UI can say which of its numbers are trustworthy.
    """

    landmarks: Sequence[Landmark]
    timestamp_ms: float
    frame_index: int = 0
    #: Identifier of the camera or capture device that produced this frame.
    source: str = "unknown"

    def __post_init__(self) -> None:
        self.landmarks = tuple(_as_landmark(lm) for lm in self.landmarks)
        if len(self.landmarks) < NUM_LANDMARKS:
            raise ValueError(
                f"expected {NUM_LANDMARKS} landmarks, got {len(self.landmarks)}"
            )

    def lm(self, index: int) -> Landmark:
        return self.landmarks[index]

    def __iter__(self) -> Iterator[Landmark]:
        return iter(self.landmarks)

    # -- availability ---------------------------------------------------------
    def visible(self, *indices: int, min_visibility: float = MIN_VISIBILITY) -> bool:
        """True when every listed landmark is detected well enough to measure."""
        for index in indices:
            lm = self.landmarks[index]
            if lm.visibility < min_visibility:
                return False
        return True

    @property
    def person_present(self) -> bool:
        """A person is in frame well enough to attempt a measurement.

        Requires both shoulders and both hips. Deliberately strict: half a body
        in shot is enough to keep counting a curl, but the exercise specs in
        :mod:`reproom.exercises` need the lower body too, and a session should
        pause rather than emit a silent wrong answer.
        """
        return self.visible(LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP)

    # -- derived geometry -----------------------------------------------------
    def midpoint(self, a: int, b: int) -> Landmark:
        la, lb = self.landmarks[a], self.landmarks[b]
        return Landmark(
            (la.x + lb.x) / 2.0,
            (la.y + lb.y) / 2.0,
            (la.z + lb.z) / 2.0,
            min(la.visibility, lb.visibility),
        )

    @property
    def hip_center(self) -> Landmark:
        return self.midpoint(LEFT_HIP, RIGHT_HIP)

    @property
    def shoulder_center(self) -> Landmark:
        return self.midpoint(LEFT_SHOULDER, RIGHT_SHOULDER)

    @property
    def torso_length(self) -> float:
        """Normalised shoulder-centre to hip-centre distance.

        Used as a scale reference (so metrics survive the subject standing at a
        different distance from the camera) and as a proximity quality gate --
        a torso shorter than ~0.10 of frame height means the subject is too far
        away or occluded for the angles to be dependable.
        """
        h, s = self.hip_center, self.shoulder_center
        return math.hypot(h.x - s.x, h.y - s.y)

    @property
    def shoulder_width(self) -> float:
        """Left-to-right shoulder distance in normalised frame units.

        A second scale reference alongside :attr:`torso_length`. Width
        compresses as the subject rotates away from the camera, so checks that
        use it are declared for the frontal view only.
        """
        if not self.visible(LEFT_SHOULDER, RIGHT_SHOULDER):
            return 0.0
        return abs(self.lm(LEFT_SHOULDER).x - self.lm(RIGHT_SHOULDER).x)

    @property
    def body_center_x(self) -> float:
        return self.hip_center.x

    @property
    def in_frame_center(self) -> bool:
        """Rough check that the subject is not hugging an edge of the shot."""
        return 0.12 <= self.body_center_x <= 0.88


def angle_at(
    pose: PoseFrame,
    vertex: int,
    a: int,
    b: int,
    min_visibility: float = MIN_VISIBILITY,
) -> Optional[float]:
    """Interior angle in degrees at ``vertex``, formed with ``a`` and ``b``.

    Returns ``None`` -- never a guess -- when any of the three landmarks is too
    poorly detected to measure, so callers can surface ``low_confidence``
    instead of a number that looks plausible and is not.
    """
    if not pose.visible(vertex, a, b, min_visibility=min_visibility):
        return None
    v = pose.lm(vertex).as_point()
    pa = pose.lm(a).as_point()
    pb = pose.lm(b).as_point()
    v1 = (pa[0] - v[0], pa[1] - v[1])
    v2 = (pb[0] - v[0], pb[1] - v[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return None
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def knee_angle(pose: PoseFrame, side: str = "left") -> Optional[float]:
    """Hip-knee-ankle angle. ~180 standing, ~90 at parallel squat depth."""
    if side == "left":
        return angle_at(pose, LEFT_KNEE, LEFT_HIP, LEFT_ANKLE)
    return angle_at(pose, RIGHT_KNEE, RIGHT_HIP, RIGHT_ANKLE)


def elbow_angle(pose: PoseFrame, side: str = "left") -> Optional[float]:
    """Shoulder-elbow-wrist angle. ~180 arm straight, ~40 fully flexed."""
    if side == "left":
        return angle_at(pose, LEFT_ELBOW, LEFT_SHOULDER, LEFT_WRIST)
    return angle_at(pose, RIGHT_ELBOW, RIGHT_SHOULDER, RIGHT_WRIST)


def shoulder_angle(pose: PoseFrame, side: str = "left") -> Optional[float]:
    """Elbow-shoulder-wrist angle: arm abduction from the torso, in degrees."""
    if side == "left":
        return angle_at(pose, LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST)
    return angle_at(pose, RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST)


def hip_angle(pose: PoseFrame, side: str = "left") -> Optional[float]:
    """Knee-hip-ankle angle: hip flexion. ~180 upright, smaller as you sit back."""
    if side == "left":
        return angle_at(pose, LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
    return angle_at(pose, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)


def spine_angle(pose: PoseFrame) -> Optional[float]:
    """Shoulder-hip-knee angle. ~180 on a neutral torso, hinged as you fold."""
    return angle_at(pose, LEFT_HIP, LEFT_SHOULDER, LEFT_KNEE)


def torso_lean(pose: PoseFrame) -> Optional[float]:
    """Tilt of the shoulder-to-hip line away from vertical, in degrees.

    0 means perfectly upright. Measured in the image plane, so from a *side*
    camera this reads forward lean; from a *front* camera it reads lateral
    tilt and says nothing about forward lean at all. Exercise specs pick the
    view each check is valid in rather than pretending one camera fits both.
    """
    if not pose.visible(LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP):
        return None
    h, s = pose.hip_center, pose.shoulder_center
    dx = s.x - h.x
    dy = s.y - h.y  # negative: shoulders sit above hips in image coords
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    # Angle between the torso vector and straight up (0, -1).
    cos = (-dy) / length
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def side_mean(
    left: Optional[float],
    right: Optional[float],
    max_asymmetry: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Combine a left/right pair.

    Returns ``(mean, asymmetry)``. When either side is missing the mean falls
    back to the side that *is* measured and asymmetry stays ``None`` -- the
    engine reports which happened instead of quietly averaging one limb with
    nothing.
    """
    sides = [v for v in (left, right) if v is not None]
    if not sides:
        return None, None
    if len(sides) == 1:
        return sides[0], None
    return sum(sides) / 2.0, abs(left - right)


@dataclass
class PoseQuality:
    """Why a frame was usable or not. Surfaced to the UI verbatim."""

    ok: bool
    reasons: list = field(default_factory=list)
    torso_length: float = 0.0
    center_x: float = 0.5


def assess_quality(pose: PoseFrame, min_torso: float = 0.09) -> PoseQuality:
    """Gate a frame before any measurement is attempted."""
    reasons: list[str] = []
    if not pose.person_present:
        reasons.append("shoulders and hips not both detected")
    torso = pose.torso_length if pose.person_present else 0.0
    if torso < min_torso:
        reasons.append("subject too small in frame to measure angles reliably")
    if not pose.in_frame_center:
        reasons.append("subject near the edge of the frame")
    return PoseQuality(
        ok=not reasons,
        reasons=reasons,
        torso_length=torso,
        center_x=pose.body_center_x,
    )
