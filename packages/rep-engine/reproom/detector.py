"""Optional MediaPipe bridge: pixels in, :class:`PoseFrame` out.

Import this module only when you actually want to run detection. The rest of
``reproom`` -- the angles, the exercises, the state machine -- never touches a
vision runtime, which is what lets the engine be unit tested, replayed from a
recorded session, or embedded somewhere without 90 MB of model files.

Requires ``pip install reproom-rep-engine[detect]`` and one of the MediaPipe
pose-landmarker ``.task`` bundles:
https://storage.googleapis.com/mediapipe-models/pose_landmarker/
``pose_landmarker_{lite,full,heavy}/float16/1/pose_landmarker_*.task``
"""

from __future__ import annotations

import os
from typing import Optional, Union

from .geometry import NUM_LANDMARKS, Landmark, PoseFrame

ArrayLike = Union[str, "object"]

MODEL_ASSETS = {
    "lite": "pose_landmarker_lite",
    "full": "pose_landmarker_full",
    "heavy": "pose_landmarker_heavy",
}

_MODEL_BASE = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "{name}/float16/1/{name}.task"
)


class DetectorUnavailable(RuntimeError):
    """MediaPipe is not installed in this interpreter."""


def _require_mediapipe():
    try:  # pragma: no cover - import guard
        import mediapipe  # noqa: F401
        from mediapipe.tasks import python as _tasks_python
        from mediapipe.tasks.python import vision as _tasks_vision
    except ImportError as exc:  # pragma: no cover
        raise DetectorUnavailable(
            "MediaPipe is required for reproom.detector: "
            "pip install 'reproom-rep-engine[detect]'"
        ) from exc
    return mediapipe, _tasks_python, _tasks_vision


class PoseDetector:
    """Wrap a MediaPipe pose landmarker behind the engine's own frame type.

    ``running_mode`` is ``"video"`` by default so MediaPipe's internal tracking
    carries across frames, which is both faster and stabler than re-detecting
    every frame as a still. Pass monotonically increasing ``timestamp_ms`` --
    the timestamp is what makes tempo and cadence mean anything downstream.
    """

    def __init__(
        self,
        model_path: str,
        *,
        running_mode: str = "video",
        num_poses: int = 1,
        min_pose_detection_confidence: float = 0.5,
        min_pose_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        mp, tasks_python, tasks_vision = _require_mediapipe()
        self._mp = mp
        self._vision = tasks_vision
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"pose model not found at {model_path!r}. Download it from "
                + _MODEL_BASE.format(name="pose_landmarker_full")
            )
        base = tasks_python.BaseOptions(model_asset_path=model_path)
        mode = (
            tasks_vision.RunningMode.VIDEO
            if running_mode == "video"
            else tasks_vision.RunningMode.IMAGE
        )
        options = tasks_vision.PoseLandmarkerOptions(
            base_options=base,
            running_mode=mode,
            num_poses=num_poses,
            min_pose_detection_confidence=min_pose_detection_confidence,
            min_pose_presence_confidence=min_pose_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._mode = running_mode
        self._delegate = tasks_vision.PoseLandmarker.create_from_options(options)

    # ------------------------------------------------------------------ setup
    @classmethod
    def from_asset(cls, name: str = "full", models_dir: str = "models", **kw) -> "PoseDetector":
        """Open ``<models_dir>/pose_landmarker_<name>.task``."""
        if name not in MODEL_ASSETS:
            raise ValueError(f"unknown model {name!r}; pick one of {sorted(MODEL_ASSETS)}")
        asset = MODEL_ASSETS[name]
        return cls(os.path.join(models_dir, f"{asset}.task"), **kw)

    def close(self) -> None:
        self._delegate.close()

    def __enter__(self) -> "PoseDetector":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # ------------------------------------------------------------------- infer
    def detect(self, rgb, timestamp_ms: Optional[float] = None) -> Optional[PoseFrame]:
        """Return the most confident pose in the frame, or ``None``.

        ``None`` is a real answer and means "no person was detected well enough
        to measure". Callers should surface it as such -- the engine treats a
        missing frame and a bad frame identically, by not counting anything.
        """
        array = self._as_contiguous(rgb)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=array)
        if self._mode == "video":
            if timestamp_ms is None:
                raise ValueError("video mode needs a timestamp_ms")
            result = self._delegate.detect_for_video(image, int(round(timestamp_ms)))
        else:
            result = self._delegate.detect(image)
        if not result.pose_landmarks:
            return None
        landmarks = [
            Landmark(
                lm.x,
                lm.y,
                getattr(lm, "z", 0.0),
                float(getattr(lm, "visibility", 1.0) or 1.0),
                float(getattr(lm, "presence", 1.0) or 1.0),
            )
            for lm in result.pose_landmarks[0]
        ]
        if len(landmarks) < NUM_LANDMARKS:
            return None
        return PoseFrame(
            landmarks=landmarks,
            timestamp_ms=0.0 if timestamp_ms is None else timestamp_ms,
        )

    def detect_file(self, path: str) -> Optional[PoseFrame]:
        image = self._mp.Image.create_from_file(path)
        result = self._delegate.detect(image)
        if not result.pose_landmarks:
            return None
        landmarks = [
            Landmark(
                lm.x,
                lm.y,
                getattr(lm, "z", 0.0),
                float(getattr(lm, "visibility", 1.0) or 1.0),
                float(getattr(lm, "presence", 1.0) or 1.0),
            )
            for lm in result.pose_landmarks[0]
        ]
        return PoseFrame(landmarks=landmarks, timestamp_ms=0.0)

    @staticmethod
    def _as_contiguous(rgb):
        try:
            import numpy as np
        except ImportError:  # pragma: no cover
            return rgb
        array = np.asarray(rgb)
        if array.dtype != np.uint8:
            raise ValueError("expected an 8-bit RGB array")
        if array.ndim == 2:  # greyscale is not a pose input
            raise ValueError("expected 3 channels, got a greyscale frame")
        if not array.flags["C_CONTIGUOUS"]:
            array = np.ascontiguousarray(array)
        return array


def download_model(name: str = "full", dest_dir: str = "models") -> str:
    """Fetch a hosted ``.task`` bundle. Returns the local path."""
    import urllib.request

    if name not in MODEL_ASSETS:
        raise ValueError(f"unknown model {name!r}")
    asset = MODEL_ASSETS[name]
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{asset}.task")
    if os.path.exists(dest):
        return dest
    url = _MODEL_BASE.format(name=asset)
    urllib.request.urlretrieve(url, dest)  # noqa: S310 - fixed https host above
    return dest
