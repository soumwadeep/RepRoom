"""HTTP contract tests for the session API.

These drive the real request path -- start, frame, poll, stop -- with the stub
detector and synthetic poses, so what is under test is the service, the session
store and the JSON shape the TV parses. Detection quality is measured in
``benchmarks/``, not here; the stub is declared in every response as
``detected_by: stub-no-camera-input`` so a test can never be mistaken for a demo.
"""

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "packages", "rep-engine"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "packages", "rep-engine", "tests"))

os.environ["REPROOM_DETECTOR"] = "stub"

from app import app  # noqa: E402
from fixtures import squat_arc  # noqa: E402


def frame_payload(pose) -> bytes:
    return json.dumps(
        {
            "landmarks": [
                [lm.x, lm.y, lm.z, lm.visibility, lm.presence] for lm in pose.landmarks
            ]
        }
    ).encode("utf-8")


def post_frame(client, session_id, pose, capture_ms=None):
    """Send one pose over the same path a real camera client uses."""
    header = pose.timestamp_ms if capture_ms is None else capture_ms
    response = client.post(
        f"/session/{session_id}/frame",
        content=frame_payload(pose),
        headers={"content-type": "application/json", "X-Capture-Ms": str(header)},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def start(client, exercise="squat", view="side", **kw):
    response = client.post("/session", json={"exercise": exercise, "view": view, **kw})
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_health_names_the_detector_that_is_actually_running(client):
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["detected_by"] == "stub-no-camera-input"
    assert payload["exercises"] >= 4


def test_capture_page_is_served_from_the_api_origin(client):
    """Same-origin matters: a phone only grants the camera to a secure context."""
    response = client.get("/capture")
    assert response.status_code == 200
    assert "getUserMedia" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_exercises_endpoint_lists_a_view_and_guidance_per_exercise(client):
    rows = client.get("/exercises").json()
    assert {row["key"] for row in rows} >= {"squat", "pushup", "overhead_press"}
    assert all(row["guidance"] and row["view"] in ("side", "front") for row in rows)


def test_unknown_exercise_is_a_400_with_the_valid_choices(client):
    response = client.post("/session", json={"exercise": "yoga"})
    assert response.status_code == 400
    assert "squat" in response.json()["detail"]


def test_a_set_of_frames_produces_counted_reps_over_http(client):
    session_id = start(client, "squat", "side")
    poses = squat_arc(reps=3)
    updates = [post_frame(client, session_id, pose) for pose in poses]
    assert updates[-1]["reps"] == 3
    assert any(u["completed"] for u in updates)
    assert updates[-1]["clock_source"] == "sender-monotonic"
    state = client.get(f"/session/{session_id}").json()
    assert state["reps"] == 3
    assert state["frames"] == {"received": len(poses), "with_pose": len(poses)}


def test_every_frame_response_declares_where_the_pose_came_from(client):
    session_id = start(client)
    response = post_frame(client, session_id, squat_arc(reps=1)[0])
    assert response["detected_by"] == "stub-no-camera-input"
    assert "detect_ms" in response


def test_tempo_comes_from_the_capture_clock_not_the_arrival_rate(client):
    """The same clip replayed instantly still reports a two-second rep.

    If the session used the server's arrival time, a fast client would make
    every rep look flushed -- the count would survive and the tempo would be
    fiction.
    """
    session_id = start(client)
    poses = squat_arc(reps=1)
    updates = [post_frame(client, session_id, pose) for pose in poses]
    completed = next(u for u in updates if u["completed"])
    assert completed["completed"]["duration_ms"] == pytest.approx(1500.0, rel=0.3)


def test_a_sender_clock_that_runs_backwards_is_degraded_not_trusted(client):
    session_id = start(client)
    pose = squat_arc(reps=1)[0]
    assert post_frame(client, session_id, pose, capture_ms=5000.0)["clock_source"] == "sender-monotonic"
    later = squat_arc(reps=1, start_ms=100.0)[1]
    response = post_frame(client, session_id, later, capture_ms=4000.0)
    assert response["clock_source"] == "server-arrival"
    assert client.get(f"/session/{session_id}").json()["clock_degraded"] is True


def test_arrival_gap_is_reported_separately_from_pose_time(client):
    session_id = start(client)
    pose = squat_arc(reps=1)[0]
    first = post_frame(client, session_id, pose)
    second = post_frame(client, session_id, pose)
    assert first["arrival_gap_ms"] is None
    assert isinstance(second["arrival_gap_ms"], (int, float))


def test_bytes_that_are_not_a_pose_are_answered_not_crashed(client):
    session_id = start(client)
    response = client.post(
        f"/session/{session_id}/frame",
        content=b"not a jpeg and not json",
        headers={"content-type": "image/jpeg"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["presence"] == "searching"
    assert payload["reps"] == 0
    assert payload["reason"] == "no pose in frame"


def test_an_empty_body_is_a_400(client):
    session_id = start(client)
    response = client.post(f"/session/{session_id}/frame", content=b"")
    assert response.status_code == 400


def test_state_reports_the_view_mismatch_instead_of_silently_grading(client):
    """A press set up with a side camera is allowed, but it is flagged."""
    session_id = start(client, "overhead_press", "side")
    state = client.get(f"/session/{session_id}").json()
    assert state["view_matches"] is False
    assert state["recommended_view"] == "front"


def test_stopping_a_session_freezes_it_and_later_frames_are_refused(client):
    session_id = start(client)
    pose = squat_arc(reps=1)[0]
    post_frame(client, session_id, pose)
    assert client.post(f"/session/{session_id}/stop").json()["finished"] is True
    response = client.post(
        f"/session/{session_id}/frame",
        content=frame_payload(pose),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 409


def test_unknown_session_is_a_404(client):
    assert client.get("/session/doesnotexist").status_code == 404
    assert client.delete("/session/doesnotexist").status_code == 404


def test_deleting_a_session_removes_it_from_health_counts(client):
    session_id = start(client)
    before = client.get("/health").json()["sessions_open"]
    client.delete(f"/session/{session_id}")
    assert client.get("/health").json()["sessions_open"] == before - 1


def test_form_checks_travel_to_the_tv_with_honest_statuses(client):
    session_id = start(client, "squat", "front")
    for pose in squat_arc(reps=1, bottom=95.0):
        response = post_frame(client, session_id, pose)
        if response["completed"]:
            statuses = {c["status"] for c in response["completed"]["checks"]}
            assert statuses <= {"pass", "fail", "not_measurable"}
            assert "not_measurable" in statuses, "depth cannot be measured from the front"
            break
    else:
        pytest.fail("no rep was completed over HTTP")
