"""Angle, metric and quality-gate tests.

These pin the geometry contract the whole engine is built on: angles come out
of the construction the fixtures use, and anything unmeasurable returns ``None``
rather than a number.
"""

import math

import pytest

from fixtures import TORSO, person
from reproom.geometry import (
    LEFT_ANKLE,
    LEFT_HIP,
    LEFT_KNEE,
    LEFT_SHOULDER,
    PoseFrame,
    RIGHT_ANKLE,
    RIGHT_HIP,
    RIGHT_KNEE,
    RIGHT_SHOULDER,
    angle_at,
    assess_quality,
    elbow_angle,
    knee_angle,
    side_mean,
    spine_angle,
    torso_lean,
)


def test_standing_leg_measures_close_to_straight():
    pose = person(0.0, theta=178.0, lean=0.0)
    assert knee_angle(pose, "left") == pytest.approx(178.0, abs=0.5)


def test_knee_angle_matches_the_fixture_parameter():
    for theta in (150.0, 120.0, 95.0, 70.0):
        pose = person(0.0, theta=theta, lean=10.0)
        assert knee_angle(pose, "left") == pytest.approx(theta, abs=1.0)
        assert knee_angle(pose, "right") == pytest.approx(theta, abs=1.0)


def test_torso_lean_is_the_declared_lean():
    for lean in (0.0, 15.0, 40.0, 65.0):
        pose = person(0.0, theta=170.0, lean=lean)
        assert torso_lean(pose) == pytest.approx(lean, abs=1.0)


def test_spine_angle_tracks_hip_and_knee_placement():
    pose = person(0.0, theta=176.0, lean=8.0)
    assert spine_angle(pose) == pytest.approx(176.0, abs=10.0)


def test_elbow_angle_matches_its_parameter():
    for elbow in (170.0, 120.0, 75.0, 45.0):
        pose = person(0.0, elbow=elbow, alpha=0.0, arm_only=True)
        assert elbow_angle(pose, "left") == pytest.approx(elbow, abs=1.0)
        assert elbow_angle(pose, "right") == pytest.approx(elbow, abs=1.0)


def test_torso_length_is_scale_invariant():
    pose = person(0.0, theta=120.0, lean=30.0)
    assert pose.torso_length == pytest.approx(TORSO, rel=1e-6)


def test_missing_landmark_yields_none_not_zero():
    """A joint that cannot be seen is reported as absent, never as 0 degrees."""
    pose = person(0.0, theta=120.0, visibility=0.2)
    assert knee_angle(pose, "left") is None
    assert torso_lean(pose) is None


def test_side_mean_falls_back_to_one_side_and_reports_no_asymmetry():
    mean, gap = side_mean(100.0, None)
    assert mean == 100.0
    assert gap is None
    mean, gap = side_mean(100.0, 140.0)
    assert mean == 120.0
    assert gap == 40.0
    assert side_mean(None, None) == (None, None)


def test_quality_gate_rejects_a_body_that_is_not_really_there():
    pose = person(0.0, theta=120.0, visibility=0.1)
    quality = assess_quality(pose)
    assert quality.ok is False
    assert any("shoulders and hips" in reason for reason in quality.reasons)


def test_quality_gate_rejects_a_subject_too_far_from_the_camera():
    """Collapse the body to a tenth of its size: same shape, unusable detail."""
    pose = person(0.0, theta=120.0, lean=10.0)
    shrunk = PoseFrame(
        landmarks=[
            type(lm)(0.5 + (lm.x - 0.5) * 0.1, 0.5 + (lm.y - 0.5) * 0.1, lm.z, lm.visibility, lm.presence)
            for lm in pose.landmarks
        ],
        timestamp_ms=0.0,
    )
    quality = assess_quality(shrunk)
    assert quality.ok is False
    assert any("too small" in reason for reason in quality.reasons)


def test_landmarks_are_coerced_from_tuples_and_objects():
    class Loose:
        def __init__(self, x, y):
            self.x, self.y = x, y

    points = [Loose(0.5, 0.5) for _ in range(33)]
    points[LEFT_HIP] = Loose(0.5, 0.5)
    points[LEFT_KNEE] = (0.5, 0.65)
    pose = PoseFrame(landmarks=points, timestamp_ms=1.0)
    assert pose.lm(LEFT_KNEE).y == pytest.approx(0.65)


def test_pose_frame_rejects_a_short_landmark_list():
    with pytest.raises(ValueError):
        PoseFrame(landmarks=[(0.5, 0.5)] * 20, timestamp_ms=0.0)
