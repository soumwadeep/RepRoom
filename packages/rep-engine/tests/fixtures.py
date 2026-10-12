"""Synthetic pose fixtures.

These build :class:`reproom.geometry.PoseFrame` objects from joint angles
directly, with no vision model involved. That distinction matters when reading
the results: this suite proves the *counting and grading* logic. Whether the
angles are recovered accurately from real pixels is a separate question,
measured over labelled clips in ``benchmarks/`` -- never asserted here.

Geometry conventions, all in normalised image units with y increasing downwards
-------------------------------------------------------------------------------
thigh and shank are 0.15 long, torso 0.22, upper arm and forearm 0.12. The hip
is placed from the knee by the interior knee angle ``theta``::

    hip = knee + L_thigh * (sin theta, cos theta)

so theta=180 puts the hip directly above the knee (standing) and smaller angles
swing it forward and down. ``lean`` is exactly the value
:func:`reproom.geometry.torso_lean` reports. Arms are placed by an upper-arm
direction ``alpha`` (0 hangs at the side, 90 points forward, 180 overhead) and
an interior elbow angle.

The arc builders hold each extreme for several frames on purpose. The engine
smooths the measured angle over a five-frame window, so an arc that reverses in
one frame never crosses a threshold at all -- and no person moves like that
either. Each sequence is written at a tempo a real rep would take.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from reproom.geometry import (
    LEFT_ANKLE,
    LEFT_ELBOW,
    LEFT_FOOT_INDEX,
    LEFT_HEEL,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    NUM_LANDMARKS,
    RIGHT_ANKLE,
    RIGHT_ELBOW,
    RIGHT_FOOT_INDEX,
    RIGHT_HEEL,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    Landmark,
    PoseFrame,
)

THIGH = 0.15
SHANK = 0.15
TORSO = 0.22
UPPER_ARM = 0.12
FOREARM = 0.12

Point = Tuple[float, float]


def _rot(beta_deg: float, vector: Point) -> Point:
    beta = math.radians(beta_deg)
    x, y = vector
    return (x * math.cos(beta) - y * math.sin(beta), x * math.sin(beta) + y * math.cos(beta))


def _leg_points(theta: float, lean: float, ankle: Point, knee_shift: float = 0.0) -> Dict[str, Point]:
    knee = (ankle[0] + knee_shift, ankle[1] - SHANK)
    hip = (knee[0] + THIGH * math.sin(math.radians(theta)), knee[1] + THIGH * math.cos(math.radians(theta)))
    shoulder = (hip[0] + TORSO * math.sin(math.radians(lean)), hip[1] - TORSO * math.cos(math.radians(lean)))
    return {
        "knee": knee,
        "hip": hip,
        "shoulder": shoulder,
        "ankle": ankle,
        "heel": (ankle[0] - 0.01, ankle[1] + 0.01),
        "toe": (ankle[0] + 0.04, ankle[1] + 0.02),
    }


def _arm_points(shoulder: Point, alpha: float, elbow_angle: float) -> Tuple[Point, Point]:
    d1 = (math.sin(math.radians(alpha)), math.cos(math.radians(alpha)))
    elbow = (shoulder[0] + UPPER_ARM * d1[0], shoulder[1] + UPPER_ARM * d1[1])
    d2 = _rot(elbow_angle, (-d1[0], -d1[1]))
    return elbow, (elbow[0] + FOREARM * d2[0], elbow[1] + FOREARM * d2[1])


def person(
    timestamp_ms: float,
    theta: float = 175.0,
    lean: float = 8.0,
    *,
    asym: float = 0.0,
    ankle_spread: float = 0.10,
    knee_in: float = 0.0,
    alpha: float = 0.0,
    elbow: float = 170.0,
    elbow_asym: float = 0.0,
    visibility: float = 1.0,
    arm_only: bool = False,
    source: str = "fixture",
) -> PoseFrame:
    """Build a full 33-point pose.

    ``arm_only`` locks the legs out and is what a curl or press fixture uses --
    those exercises do not move the knees, and a fixture that drifted them would
    quietly test a different joint than the one under review.
    """
    pts: List[Optional[Point]] = [None] * NUM_LANDMARKS
    center_x = 0.5
    leg_theta = 178.0 if arm_only else theta
    leg_lean = 2.0 if arm_only else lean

    left = _leg_points(leg_theta, leg_lean, (center_x - ankle_spread / 2.0, 0.85), knee_in)
    right = _leg_points(leg_theta + asym, leg_lean, (center_x + ankle_spread / 2.0, 0.85), -knee_in)

    for body, hip_i, knee_i, ankle_i, heel_i, toe_i, sho_i, elb_i, wri_i, side in (
        (left, LEFT_HIP, LEFT_KNEE, LEFT_ANKLE, LEFT_HEEL, LEFT_FOOT_INDEX, LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST, 0),
        (right, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE, RIGHT_HEEL, RIGHT_FOOT_INDEX, RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST, 1),
    ):
        pts[hip_i] = body["hip"]
        pts[knee_i] = body["knee"]
        pts[ankle_i] = body["ankle"]
        pts[heel_i] = body["heel"]
        pts[toe_i] = body["toe"]
        pts[sho_i] = body["shoulder"]
        pts[elb_i], pts[wri_i] = _arm_points(body["shoulder"], alpha, elbow + (elbow_asym if side else 0.0))

    shoulder_center = pts[LEFT_SHOULDER]
    pts[NOSE] = (shoulder_center[0], shoulder_center[1] - 0.16)

    landmarks = [
        Landmark(p[0], p[1], 0.0, visibility, visibility) if p else Landmark(0.5, 0.5, 0.0, 0.0, 0.0)
        for p in pts
    ]
    return PoseFrame(landmarks=landmarks, timestamp_ms=timestamp_ms, source=source)


# --------------------------------------------------------------------- arcs
def run_arc(start_ms: float, step_ms: float, sequence: Sequence[Tuple[dict, int]]) -> List[PoseFrame]:
    """Emit ``sequence`` as ``(person kwargs, frame count)`` steps at ``step_ms``."""
    frames: List[PoseFrame] = []
    now = start_ms
    for kwargs, count in sequence:
        for _ in range(count):
            frames.append(person(now, **kwargs))
            now += step_ms
    return frames


def squat_arc(
    start_ms: float = 0.0,
    reps: int = 3,
    *,
    top: float = 175.0,
    bottom: float = 95.0,
    step_ms: float = 150.0,
    down_frames: int = 4,
    hold_frames: int = 8,
    up_frames: int = 4,
    **kw,
) -> List[PoseFrame]:
    stand = {"theta": top, **kw}
    deep = {"theta": bottom, **kw}
    sequence: List[Tuple[dict, int]] = [(stand, 3)]
    for _ in range(reps):
        mid = top + (bottom - top) / 2.0
        sequence.append(({"theta": mid, **kw}, down_frames))
        sequence.append((deep, hold_frames))
        sequence.append(({"theta": mid, **kw}, up_frames))
        # Five frames at the top, not two: the engine smooths over a five-frame
        # window, so a shorter plateau leaves the smoothed angle still climbing
        # when the sequence ends and the rep never appears to finish.
        sequence.append((stand, 5))
    return run_arc(start_ms, step_ms, sequence)


def interrupted_squat(start_ms: float = 0.0, gap_ms: float = 1500.0, **kw) -> List[PoseFrame]:
    """Descend past the arming threshold, leave the frame, come back standing.

    The rep must not be credited: the engine watched an arc that never finished,
    interrupted by a subject who was not in shot at all.
    """
    stand = dict(theta=175.0, **kw)
    mid = dict(theta=135.0, **kw)
    deep = dict(theta=95.0, **kw)
    frames = run_arc(
        start_ms,
        150.0,
        [(stand, 2), (mid, 4), (deep, 6)],
    )
    gone_from = frames[-1].timestamp_ms
    now = gone_from + 150.0
    blind_kw = {k: v for k, v in kw.items() if k not in ("theta", "bottom", "top")}
    while now - gone_from < gap_ms:
        frames.append(person(now, theta=95.0, visibility=0.05, **blind_kw))
        now += 150.0
    frames.append(person(now, **stand))
    return frames


def press_arc(
    start_ms: float = 0.0,
    reps: int = 2,
    *,
    elbow_top: float = 175.0,
    alpha_top: float = 175.0,
    elbow_bottom: float = 90.0,
    step_ms: float = 180.0,
    hold_frames: int = 5,
    **kw,
) -> List[PoseFrame]:
    """Overhead press. ``alpha_top`` sets how high the arms actually finish.

    A shallow lockout (``alpha_top`` around 105) still moves through a valid
    elbow range, so the rep *is* counted and the lockout check then fails on the
    measured wrist height. That separates "a rep happened" from "the rep was
    done well", which are two different claims to put on a screen.
    """
    low = {"alpha": 0.0, "elbow": elbow_bottom, "arm_only": True, **kw}
    high = {"alpha": alpha_top, "elbow": elbow_top, "arm_only": True, **kw}
    mid = {"alpha": max(0.0, alpha_top / 2.0), "elbow": (elbow_top + elbow_bottom) / 2.0, "arm_only": True, **kw}
    sequence: List[Tuple[dict, int]] = [(high, 3)]
    for _ in range(reps):
        sequence.append((mid, 3))
        sequence.append((low, hold_frames))
        sequence.append((mid, 3))
        sequence.append((high, hold_frames))
    return run_arc(start_ms, step_ms, sequence)


def curl_arc(
    start_ms: float = 0.0,
    reps: int = 2,
    *,
    elbow_top: float = 60.0,
    alpha_top: float = 0.0,
    elbow_bottom: float = 170.0,
    step_ms: float = 200.0,
    hold_frames: int = 5,
    **kw,
) -> List[PoseFrame]:
    """Bicep curl. ``alpha_top`` away from 0 is elbows drifting off the ribs."""
    down = {"alpha": 0.0, "elbow": elbow_bottom, "arm_only": True, **kw}
    up = {"alpha": alpha_top, "elbow": elbow_top, "arm_only": True, **kw}
    mid = {"alpha": alpha_top / 2.0, "elbow": (elbow_top + elbow_bottom) / 2.0, "arm_only": True, **kw}
    sequence: List[Tuple[dict, int]] = [(down, 3)]
    for _ in range(reps):
        sequence.append((mid, 2))
        sequence.append((up, hold_frames))
        sequence.append((mid, 2))
        sequence.append((down, hold_frames))
    return run_arc(start_ms, step_ms, sequence)


def pushup_arc(
    start_ms: float = 0.0,
    reps: int = 2,
    *,
    spine: float = 176.0,
    elbow_top: float = 172.0,
    elbow_bottom: float = 88.0,
    step_ms: float = 160.0,
    hold_frames: int = 5,
    **kw,
) -> List[PoseFrame]:
    """Push-up, with ``spine`` as the shoulder-hip-knee line.

    Dropping ``spine`` past the 155 deg limit reproduces a hip that sags toward
    the floor mid-rep -- the exact failure the body-line check exists for.
    """
    top = {"theta": spine, "alpha": 0.0, "elbow": elbow_top, **kw}
    bottom = {"theta": spine, "alpha": 0.0, "elbow": elbow_bottom, **kw}
    mid = {"theta": spine, "alpha": 0.0, "elbow": (elbow_top + elbow_bottom) / 2.0, **kw}
    sequence: List[Tuple[dict, int]] = [(top, 3)]
    for _ in range(reps):
        sequence.append((mid, 3))
        sequence.append((bottom, hold_frames))
        sequence.append((mid, 3))
        sequence.append((top, hold_frames))
    return run_arc(start_ms, step_ms, sequence)


def find_check(rep, key: str):
    return next((c for c in rep.checks if c.key == key), None)
