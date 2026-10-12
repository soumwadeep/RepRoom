"""Form-grading tests: what the TV is allowed to claim about a rep.

Two rules run through this file. A rep can be counted and still be graded
harshly -- counting and grading are separate questions. And a check the camera
cannot support is reported as ``not_measurable`` and kept out of the quality
score, so nobody gets a green tick they did not earn.
"""

import pytest

from fixtures import curl_arc, find_check, press_arc, pushup_arc, squat_arc
from reproom import RepEngine
from reproom.exercises import CATALOGUE, VIEW_FRONT, VIEW_SIDE, catalogue_summary

SIDE, FRONT = VIEW_SIDE, VIEW_FRONT


def run(key, frames, view=SIDE, **kw):
    engine = RepEngine(key, view=view, **kw)
    for frame in frames:
        engine.feed(frame, frame.timestamp_ms)
    return engine


def last_rep(engine):
    assert engine.reps, "expected at least one counted rep"
    return engine.summary().per_rep[-1]


# ------------------------------------------------------------------- squat
def test_deep_squat_passes_depth():
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=95.0)))
    depth = find_check(rep, "depth")
    assert depth.status == "pass"
    assert depth.measured is not None and depth.measured <= 0.15


def test_squat_that_stops_high_is_failed_on_depth_not_silently_passed():
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=108.0)))
    depth = find_check(rep, "depth")
    assert depth.status == "fail"
    assert depth.measured > depth.threshold
    assert rep.quality < 1.0


def test_depth_is_reported_as_unmeasurable_from_a_front_camera():
    """A front-on shot cannot see depth, and says so instead of guessing."""
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=95.0), view=FRONT))
    depth = find_check(rep, "depth")
    assert depth.status == "not_measurable"
    assert depth.measured is None
    assert "front" in depth.detail


def test_knee_tracking_is_measurable_from_the_front_and_fails_on_collapse():
    clean = last_rep(run("squat", squat_arc(reps=1, bottom=95.0), view=FRONT))
    assert find_check(clean, "knee_track").status == "pass"
    collapsed = last_rep(
        run("squat", squat_arc(reps=1, bottom=95.0, knee_in=0.03), view=FRONT)
    )
    track = find_check(collapsed, "knee_track")
    assert track.status == "fail"
    assert track.measured > track.threshold


def test_leaning_the_torso_past_the_limit_fails_back_angle():
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=95.0, lean=75.0)))
    lean = find_check(rep, "torso_lean")
    assert lean.status == "fail"
    assert lean.measured > 60.0


def test_one_leg_working_harder_than_the_other_fails_balance():
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=90.0, asym=25.0)))
    balance = find_check(rep, "asymmetry")
    assert balance.status == "fail"
    assert balance.measured == pytest.approx(25.0, abs=3.0)


def test_a_rushed_rep_is_counted_and_flagged():
    """Faster than the tempo floor but a real arc: counted *and* criticised.

    This is the distinction the discard rule cannot make on its own.
    """
    engine = run("squat", squat_arc(reps=2, step_ms=85.0))
    assert engine.reps == 2
    for rep in engine.summary().per_rep:
        assert find_check(rep, "tempo").status == "fail"


# ---------------------------------------------------------------- upper body
def test_pushup_with_a_sagging_hip_fails_the_body_line():
    rep = last_rep(run("pushup", pushup_arc(reps=1, spine=140.0)))
    line = find_check(rep, "body_line")
    assert line.status == "fail"
    assert line.severity == "critical"


def test_pushup_with_a_strong_line_passes_it():
    rep = last_rep(run("pushup", pushup_arc(reps=1, spine=176.0)))
    assert find_check(rep, "body_line").status == "pass"


def test_press_that_finishes_short_of_overhead_fails_lockout():
    rep = last_rep(run("overhead_press", press_arc(reps=1, elbow_top=168.0, alpha_top=105.0)))
    lockout = find_check(rep, "overhead")
    assert lockout.status == "fail"
    assert lockout.measured < lockout.threshold


def test_press_with_a_full_lockout_passes_it():
    rep = last_rep(run("overhead_press", press_arc(reps=1)))
    lockout = find_check(rep, "overhead")
    assert lockout.status == "pass"
    assert lockout.measured > 0.45


def test_curl_with_elbows_drifting_off_the_ribs_is_flagged():
    rep = last_rep(run("bicep_curl", curl_arc(reps=1, alpha_top=45.0), view=FRONT))
    assert find_check(rep, "elbow_position").status == "fail"


def test_curl_with_anchored_elbows_is_not_flagged():
    rep = last_rep(run("bicep_curl", curl_arc(reps=1), view=FRONT))
    assert find_check(rep, "elbow_position").status == "pass"


def test_curl_elbow_position_is_not_measured_from_a_side_camera():
    """The side view cannot see a lateral drift, and must not pretend to."""
    rep = last_rep(run("bicep_curl", curl_arc(reps=1, alpha_top=45.0), view=SIDE))
    assert find_check(rep, "elbow_position").status == "not_measurable"


# ------------------------------------------------------------- honesty rules
def test_quality_only_counts_checks_that_actually_ran():
    """Unmeasurable checks leave the denominator instead of inflating the score."""
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=95.0), view=FRONT))
    scored = [c for c in rep.checks if c.status != "not_measurable"]
    assert rep.checks_run == len(scored)
    assert rep.quality == pytest.approx(
        sum(1 for c in scored if c.ok) / len(scored)
    )
    assert any(c.status == "not_measurable" for c in rep.checks)


def test_a_perfect_rep_scores_one_and_a_failed_check_lowers_it():
    clean = last_rep(run("squat", squat_arc(reps=1, bottom=95.0)))
    assert clean.quality == 1.0
    bad = last_rep(run("squat", squat_arc(reps=1, bottom=108.0)))
    assert 0.0 < bad.quality < 1.0
    assert "depth" in bad.failed


def test_every_check_result_carries_a_status_and_a_severity():
    arcs = {
        "squat": squat_arc(reps=1, bottom=95.0),
        "pushup": pushup_arc(reps=1),
        "overhead_press": press_arc(reps=1),
        "bicep_curl": curl_arc(reps=1),
        "lunge": squat_arc(reps=1, bottom=100.0),
    }
    graded = 0
    for key, frames in arcs.items():
        engine = run(key, frames)
        for rep in engine.summary().per_rep:
            graded += 1
            for check in rep.checks:
                assert check.status in ("pass", "fail", "not_measurable")
                assert check.severity in ("critical", "posture", "tempo")
                if check.status == "pass":
                    assert check.measured is not None, (
                        f"{key}/{check.key} passed without a measurement"
                    )
    assert graded >= 5, "every exercise in the catalogue should have graded a rep"


def test_unmeasurable_checks_never_claim_to_have_passed():
    rep = last_rep(run("squat", squat_arc(reps=1, bottom=95.0), view=FRONT))
    for check in rep.checks:
        if check.status == "not_measurable":
            assert check.ok is False
            assert check.measured is None


def test_adaptive_depth_relaxes_toward_the_subject_and_says_so():
    engine = run("squat", squat_arc(reps=4, bottom=108.0), adaptive_depth=True)
    state = engine.state()
    assert state["depth_threshold_source"].startswith("adaptive")
    assert state["depth_threshold"] == pytest.approx(0.211 + 0.08, abs=0.02)


def test_depth_threshold_is_absolute_and_published_by_default():
    state = run("squat", squat_arc(reps=2, bottom=108.0)).state()
    assert state["depth_threshold_source"] == "absolute"
    assert state["depth_threshold"] == 0.15


def test_weakest_check_names_what_to_fix_first():
    engine = run("squat", squat_arc(reps=3, bottom=108.0))
    assert engine.weakest_check == "Depth"


def test_catalogue_declares_a_view_and_guidance_for_every_exercise():
    summary = catalogue_summary()
    assert len(summary) == len(CATALOGUE) >= 4
    for entry in summary:
        assert entry["view"] in (SIDE, FRONT)
        assert entry["guidance"]
        assert entry["checks"]


def test_checks_for_shows_the_ui_what_this_camera_can_grade():
    spec = CATALOGUE["squat"]
    side_keys = {c.key for c in spec.checks_for(SIDE)}
    front_keys = {c.key for c in spec.checks_for(FRONT)}
    assert "depth" in side_keys and "depth" not in front_keys
    assert "knee_track" in front_keys and "knee_track" not in side_keys
