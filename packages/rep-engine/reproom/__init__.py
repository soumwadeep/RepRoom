"""RepRoom rep engine: count repetitions and grade form from pose landmarks.

The package is split so that the part worth reusing has no dependency on any
vision runtime::

    reproom.geometry     -- landmarks, joint angles, body metrics (stdlib only)
    reproom.models       -- rep/session data classes
    reproom.exercises    -- the exercise catalogue and its form checks
    reproom.engine       -- the repetition state machine
    reproom.detector     -- OPTIONAL: MediaPipe -> PoseFrame bridge (pip .[detect])

Typical use::

    from reproom import RepEngine
    from reproom.detector import PoseDetector

    engine = RepEngine("squat", view="side")
    detector = PoseDetector("models/pose_landmarker_full.task")

    for timestamp_ms, frame in camera:
        pose = detector.detect(frame, timestamp_ms)
        if pose is None:
            continue
        update = engine.feed(pose, timestamp_ms)
        print(update.reps, update.phase, update.presence)

See ``docs/measurements.md`` for what each reported number means and what the
single-camera limitations are.
"""

from .engine import RepEngine, RepUpdate
from .exercises import (
    CATALOGUE,
    ExerciseSpec,
    FormCheck,
    VIEW_FRONT,
    VIEW_SIDE,
    catalogue_summary,
    get_spec,
)
from .geometry import (
    Landmark,
    PoseFrame,
    PoseQuality,
    assess_quality,
    elbow_angle,
    hip_angle,
    knee_angle,
    shoulder_angle,
    spine_angle,
    torso_lean,
)
from .models import (
    CheckResult,
    Phase,
    RepRecord,
    RepStats,
    SessionSummary,
)

__version__ = "0.1.0"

__all__ = [
    "RepEngine",
    "RepUpdate",
    "CATALOGUE",
    "ExerciseSpec",
    "FormCheck",
    "VIEW_FRONT",
    "VIEW_SIDE",
    "catalogue_summary",
    "get_spec",
    "Landmark",
    "PoseFrame",
    "PoseQuality",
    "assess_quality",
    "elbow_angle",
    "hip_angle",
    "knee_angle",
    "shoulder_angle",
    "spine_angle",
    "torso_lean",
    "CheckResult",
    "Phase",
    "RepRecord",
    "RepStats",
    "SessionSummary",
    "__version__",
]
