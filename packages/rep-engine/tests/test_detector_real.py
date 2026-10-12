"""Integration tests for the MediaPipe bridge.

Skipped when MediaPipe or the ``.task`` bundle is absent, so the dependency-free
core can still be tested anywhere. These are the only tests that touch a real
model, and they exist because the option names changed under us once already:
``min_pose_tracking_confidence`` does not exist in MediaPipe 1.1, and a stub
could not have caught that.
"""

import os

import pytest

mp = pytest.importorskip("mediapipe")

from reproom.detector import PoseDetector  # noqa: E402
from reproom.geometry import LEFT_KNEE, PoseFrame  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODEL = os.path.join(REPO, "models", "pose_landmarker_full.task")
SAMPLE = os.path.join(REPO, "assets_test_pose.jpg")

pytestmark = [
    pytest.mark.skipif(not os.path.exists(MODEL), reason="pose model not downloaded"),
    pytest.mark.skipif(not os.path.exists(SAMPLE), reason="no sample photo present"),
]


def test_a_real_photo_becomes_a_pose_frame():
    with PoseDetector(MODEL, running_mode="image") as detector:
        pose = detector.detect_file(SAMPLE)
    assert isinstance(pose, PoseFrame)
    assert len(pose.landmarks) == 33
    assert pose.person_present
    # A real photo should produce an angle, and it should be a plausible one.
    knee = pose.lm(LEFT_KNEE)
    assert 0.0 <= knee.x <= 1.0
    assert 0.0 <= knee.y <= 1.0


def test_video_mode_needs_timestamps_and_beats_one():
    import cv2

    frame = cv2.cvtColor(cv2.imread(SAMPLE), cv2.COLOR_BGR2RGB)
    with PoseDetector(MODEL, running_mode="video") as detector:
        with pytest.raises(ValueError):
            detector.detect(frame, None)
        first = detector.detect(frame, 0)
        second = detector.detect(frame, 33)
    assert first is not None and second is not None
    assert first.lm(LEFT_KNEE).x == pytest.approx(second.lm(LEFT_KNEE).x, abs=0.05)


def test_an_empty_frame_yields_no_pose_rather_than_a_confident_lie():
    import numpy as np

    blank = np.full((480, 640, 3), 255, dtype=np.uint8)
    with PoseDetector(MODEL, running_mode="image") as detector:
        assert detector.detect(blank) is None


def test_detection_time_on_this_machine_is_recorded_not_assumed():
    """The number the demo video quotes for latency comes from here, not a guess."""
    import time

    import cv2

    frame = cv2.cvtColor(cv2.imread(SAMPLE), cv2.COLOR_BGR2RGB)
    with PoseDetector(MODEL, running_mode="image") as detector:
        detector.detect(frame)  # warm the graph
        started = time.perf_counter()
        detector.detect(frame)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert elapsed_ms < 250.0, f"single-frame detection took {elapsed_ms:.0f} ms"
    print(f"\nmeasured pose detection: {elapsed_ms:.1f} ms/frame on this machine")
