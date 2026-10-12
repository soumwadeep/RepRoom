"""Counting, presence and session-total tests.

The claims under test here are the ones a viewer would call a lie over: a rep
that never happened must not be counted, an interrupted arc must not be counted,
and a rep flushed in half a second must be reported as a discard rather than
quietly dropped.
"""

import json

import pytest

from fixtures import (
    curl_arc,
    interrupted_squat,
    person,
    press_arc,
    pushup_arc,
    run_arc,
    squat_arc,
)
from reproom import RepEngine
from reproom.exercises import VIEW_FRONT, VIEW_SIDE


def drive(engine, frames):
    updates = [engine.feed(frame, frame.timestamp_ms) for frame in frames]
    return updates


def test_three_full_squats_count_three_reps():
    engine = RepEngine("squat", view=VIEW_SIDE)
    updates = drive(engine, squat_arc(reps=3))
    assert engine.reps == 3
    assert engine.no_reps == 0
    assert max(u.reps for u in updates) == 3


def test_the_rep_counter_is_monotonic_and_matches_the_last_update():
    engine = RepEngine("squat", view=VIEW_SIDE)
    updates = drive(engine, squat_arc(reps=4))
    counts = [u.reps for u in updates]
    assert counts == sorted(counts)
    assert counts[-1] == engine.reps == 4


def test_a_rep_that_does_not_reach_depth_is_never_started():
    """Standing-half-way is not a shallow squat; it is not a squat at all.

    The engine never arms, so nothing is counted and nothing is discarded:
    ``no_reps`` stays at zero because no arc was ever begun.
    """
    engine = RepEngine("squat", view=VIEW_SIDE)
    drive(engine, squat_arc(reps=3, bottom=140.0))
    assert engine.reps == 0
    assert engine.no_reps == 0


def test_a_flushed_rep_is_discarded_and_says_so():
    fast = squat_arc(reps=2, step_ms=55.0)
    engine = RepEngine("squat", view=VIEW_SIDE)
    updates = drive(engine, fast)
    assert engine.reps == 0
    assert engine.no_reps == 2
    assert any(u.discarded is not None for u in updates)
    assert not any(u.completed is not None for u in updates)
    assert engine.summary().to_dict()["reps"] == 0


def test_coming_back_up_halfway_does_not_finish_the_rep():
    stand = {"theta": 175.0}
    mid = {"theta": 135.0}
    deep = {"theta": 95.0}
    frames = run_arc(0.0, 150.0, [(stand, 2), (mid, 4), (deep, 6), (mid, 6), (stand, 2)])
    engine = RepEngine("squat", view=VIEW_SIDE)
    updates = drive(engine, frames)
    assert engine.reps == 0
    assert updates[-1].phase.value in ("setup", "descending", "ascending", "bottom")


def test_leaving_the_frame_pauses_and_forgets_the_partial_rep():
    engine = RepEngine("squat", view=VIEW_SIDE)
    updates = drive(engine, interrupted_squat())
    assert engine.reps == 0
    assert any(u.presence == "lost" for u in updates)
    state = engine.state()
    assert state["pause_ms"] > 0


def test_the_arc_resumes_cleanly_after_a_pause():
    """After the subject returns, the next genuine rep must still count."""
    frames = interrupted_squat() + squat_arc(4000.0, reps=2)
    engine = RepEngine("squat", view=VIEW_SIDE)
    drive(engine, frames)
    assert engine.reps == 2
    assert engine.no_reps == 0
    assert engine.abandoned_arcs == 1


def test_fps_and_cadence_are_measured_from_the_supplied_timestamps():
    engine = RepEngine("squat", view=VIEW_SIDE)
    drive(engine, squat_arc(reps=3, step_ms=150.0))
    assert engine.fps == pytest.approx(1000.0 / 150.0, rel=0.05)
    assert engine.cadence_upm == pytest.approx(60000.0 / 1350.0, rel=0.35)


def test_cadence_is_none_before_any_rep_is_counted():
    engine = RepEngine("squat", view=VIEW_SIDE)
    assert engine.cadence_upm is None
    assert engine.mean_quality is None
    assert engine.summary().to_dict()["cadence_upm"] is None


def test_each_exercise_counts_its_own_arc():
    cases = {
        "squat": squat_arc(reps=3),
        "pushup": pushup_arc(reps=2),
        "overhead_press": press_arc(reps=2),
        "bicep_curl": curl_arc(reps=2),
    }
    for key, frames in cases.items():
        engine = RepEngine(key, view=VIEW_SIDE)
        drive(engine, frames)
        assert engine.reps >= 1, f"{key} counted {engine.reps} reps"


def test_summary_and_state_are_json_serialisable():
    """The TV polls a JSON endpoint; nothing here may contain a numpy scalar."""
    engine = RepEngine("squat", view=VIEW_SIDE)
    drive(engine, squat_arc(reps=2))
    payload = json.dumps(engine.state())
    assert "rep_log" in payload
    assert json.loads(payload)["reps"] == 2


def test_update_to_dict_carries_the_phase_and_presence():
    engine = RepEngine("squat", view=VIEW_SIDE)
    update = engine.feed(person(0.0, theta=175.0), 0.0)
    payload = update.to_dict()
    assert payload["reps"] == 0
    assert payload["presence"] in ("locked", "searching")
    assert payload["completed"] is None


def test_engine_rejects_an_unknown_exercise_with_the_list_of_valid_ones():
    with pytest.raises(KeyError) as exc:
        RepEngine("deadlift")
    assert "squat" in str(exc.value)
