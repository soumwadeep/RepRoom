"""RepRoom session API.

A companion device (phone browser, laptop webcam, or any camera that can POST a
JPEG) is the sensor. This service runs pose detection, feeds the rep engine,
and hands the Fire TV app a small JSON document it can poll. That split exists
because a Vega/Fire OS app has no camera API to call -- see
``docs/friction-log.md``.

Run it with::

    uvicorn app:app --host 0.0.0.0 --port 8420

Every number this service returns was measured on a frame that actually
arrived. There is no seeded demo data, no synthetic "average quality", and no
session state that survives a restart: if the service is restarted mid-set the
TV sees the session disappear, which is the truth.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ENGINE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "packages", "rep-engine")
)
if ENGINE_ROOT not in sys.path:
    sys.path.insert(0, ENGINE_ROOT)

from reproom import CATALOGUE, RepEngine, catalogue_summary  # noqa: E402
from reproom.exercises import VIEW_FRONT, VIEW_SIDE  # noqa: E402
from reproom.geometry import PoseFrame  # noqa: E402


class Detector(Protocol):
    """Anything that turns pixels into a pose. Injected so tests need no model."""

    name: str

    def detect(self, image_bytes: bytes, timestamp_ms: float) -> Optional[PoseFrame]: ...

    def close(self) -> None: ...


class MediaPipeDetector:
    """The production detector: MediaPipe pose landmarker over decoded JPEG."""

    name = "mediapipe-pose-landmarker"

    def __init__(self, model_path: Optional[str] = None) -> None:
        from reproom.detector import PoseDetector

        path = model_path or os.environ.get(
            "REPROOM_MODEL",
            os.path.join(
                os.path.dirname(__file__), "..", "..", "models", "pose_landmarker_full.task"
            ),
        )
        self._running_ms = 0.0
        self._inner = PoseDetector(path, running_mode="video")

    def detect(self, image_bytes: bytes, timestamp_ms: float) -> Optional[PoseFrame]:
        import cv2
        import numpy as np

        array = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pose = self._inner.detect(rgb, timestamp_ms)
        return pose

    def close(self) -> None:
        self._inner.close()


@dataclass
class Session:
    id: str
    exercise: str
    view: str
    engine: RepEngine
    created_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)
    frames_received: int = 0
    frames_detected: int = 0
    detect_ms_last: float = 0.0
    detect_ms_mean: float = 0.0
    last_arrival_ms: Optional[float] = None
    last_pose_ms: Optional[float] = None
    clock_degraded: bool = False
    last_update: Dict[str, Any] = field(default_factory=dict)
    clock_origin_ms: float = field(default_factory=lambda: time.monotonic() * 1000.0)
    finished: bool = False

    def next_timestamp_ms(self) -> float:
        return time.monotonic() * 1000.0 - self.clock_origin_ms


def build_detector() -> Detector:
    """Environment-selected detector.

    ``REPROOM_DETECTOR=stub`` uses the synthetic detector the test suite drives;
    it is loud about it, because a screen fed by a stub detector is not a
    workout.
    """
    if os.environ.get("REPROOM_DETECTOR") == "stub":
        return StubDetector()
    return MediaPipeDetector()


class StubDetector:
    """Returns whatever pose the test put in the payload; never used in demo runs.

    The payload is the JSON list of landmarks, so the HTTP path can be exercised
    without a model. Anything the stub "sees" is marked ``detected_by`` so it can
    never be mistaken for a camera measurement.
    """

    name = "stub-no-camera-input"

    def detect(self, image_bytes: bytes, timestamp_ms: float) -> Optional[PoseFrame]:
        import json

        try:
            payload = json.loads(image_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        landmarks = payload.get("landmarks")
        if not landmarks:
            return None
        return PoseFrame(landmarks=landmarks, timestamp_ms=timestamp_ms, source=self.name)

    def close(self) -> None:
        return None


app = FastAPI(
    title="RepRoom session API",
    version="0.1.0",
    description="Camera-in on a companion device, reps-and-form out for the TV.",
)

_sessions: Dict[str, Session] = {}
_sessions_lock = threading.Lock()


def get_detector() -> Detector:
    """Detector singleton, created on first use and reused across sessions."""
    if not hasattr(app.state, "detector"):
        app.state.detector = build_detector()
    return app.state.detector


class StartSession(BaseModel):
    exercise: str = "squat"
    view: str = VIEW_SIDE
    adaptive_depth: bool = False
    pause_after_ms: float = Field(default=900.0, ge=200.0, le=10000.0)
    smoothing: int = Field(default=5, ge=1, le=15)


class SessionRef(BaseModel):
    session_id: str
    exercise: str
    view: str
    state: Dict[str, Any]


def require_session(session_id: str) -> Session:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no such session")
    return session


@app.get("/health")
def health(detector: Detector = Depends(get_detector)) -> Dict[str, Any]:
    """Liveness plus which detector is really wired in.

    ``detected_by: stub-no-camera-input`` is a warning, not a status: it means
    the numbers on the TV are not coming from a camera.
    """
    return {
        "status": "ok",
        "detected_by": detector.name,
        "exercises": len(CATALOGUE),
        "sessions_open": len(_sessions),
        "engine_root": ENGINE_ROOT,
    }


@app.get("/exercises")
def exercises() -> List[Dict[str, Any]]:
    """Picker data for the TV: name, focus, camera view, and what gets graded."""
    return catalogue_summary()


@app.get("/capture", include_in_schema=False)
def capture_page() -> FileResponse:
    """The companion camera page, served from the same origin as the session API.

    Same origin matters: a browser only hands the camera to a secure context, so
    serving both from one place means localhost works on the laptop and a TLS
    terminator is the only extra step for a phone.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "capture", "index.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="capture page not installed")
    return FileResponse(path, media_type="text/html")


@app.post("/session", response_model=SessionRef)
def start_session(body: StartSession) -> SessionRef:
    if body.exercise not in CATALOGUE:
        raise HTTPException(
            status_code=400,
            detail=f"unknown exercise; choose one of {', '.join(sorted(CATALOGUE))}",
        )
    if body.view not in (VIEW_SIDE, VIEW_FRONT):
        raise HTTPException(status_code=400, detail="view must be 'side' or 'front'")
    spec = CATALOGUE[body.exercise]
    session = Session(
        id=uuid.uuid4().hex[:12],
        exercise=body.exercise,
        view=body.view,
        engine=RepEngine(
            spec,
            view=body.view,
            pause_after_ms=body.pause_after_ms,
            smoothing=body.smoothing,
            adaptive_depth=body.adaptive_depth,
        ),
        created_at=time.time(),
    )
    with _sessions_lock:
        _sessions[session.id] = session
    state = session.engine.state()
    state["recommended_view"] = spec.recommended_view
    state["view_matches"] = spec.recommended_view == body.view
    session.last_update = state
    return SessionRef(session_id=session.id, exercise=body.exercise, view=body.view, state=state)


@app.post("/session/{session_id}/frame")
async def ingest_frame(
    request: Request,
    session_id: str,
    x_capture_ms: Optional[str] = Header(default=None),
    detector: Detector = Depends(get_detector),
) -> Dict[str, Any]:
    """Accept one frame from the companion camera and advance the session.

    Two clocks are kept apart, because conflating them is how a tempo number
    becomes fiction. The pose timestamp comes from the *capture device's*
    monotonic clock (``X-Capture-Ms``) and drives rep duration, tempo and
    cadence -- a monotonic clock cannot jump backwards the way a wall clock can.
    The server's arrival time is kept separately as ``arrival_gap_ms``, which is
    the only honest measure of feed rate from here. The two clocks live on
    different machines with no shared origin, so no cross-device latency number
    is reported, only the gap the server can actually observe.

    A body that is not a JPEG is answered with the same shape and
    ``presence: searching`` rather than a 500, because the TV is polling this in
    a render loop.
    """
    session = require_session(session_id)
    if session.finished:
        raise HTTPException(status_code=409, detail="session already finished")
    body_bytes = await request.body()
    if not body_bytes:
        raise HTTPException(status_code=400, detail="empty frame body")

    arrival_ms = session.next_timestamp_ms()
    pose_ms, clock_source = _pose_clock(session, x_capture_ms, arrival_ms)
    started = time.perf_counter()
    with session.lock:
        pose = detector.detect(body_bytes, pose_ms)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        session.frames_received += 1
        arrival_gap = (
            arrival_ms - session.last_arrival_ms if session.last_arrival_ms else None
        )
        session.last_arrival_ms = arrival_ms
        session.detect_ms_last = round(elapsed_ms, 1)
        n = session.frames_received
        session.detect_ms_mean = round(
            (session.detect_ms_mean * (n - 1) + elapsed_ms) / n, 1
        )
        if pose is None:
            update = RepUpdateShorthand(session.engine.reps, "searching", "no pose in frame")
        else:
            session.frames_detected += 1
            update = session.engine.feed(pose, pose_ms).to_dict()
        update["arrival_gap_ms"] = None if arrival_gap is None else round(arrival_gap, 1)
        update["clock_source"] = clock_source
        update["detect_ms"] = session.detect_ms_last
        update["detected_by"] = detector.name
        update["frames"] = {
            "received": session.frames_received,
            "with_pose": session.frames_detected,
        }
        session.last_update = update
    return update


def _pose_clock(session: Session, header_value: Optional[str], arrival_ms: float):
    """Prefer the capture device's monotonic clock; fall back to the server's."""
    if header_value:
        try:
            value = float(header_value)
        except ValueError:
            return arrival_ms, "server-arrival"
        if session.last_pose_ms is None or value >= session.last_pose_ms:
            session.last_pose_ms = value
            return value, "sender-monotonic"
        # A sender whose clock went backwards mid-set would fabricate negative
        # durations, so the rest of the session is clocked from here instead.
        session.clock_degraded = True
    return arrival_ms, "server-arrival"


class RepUpdateShorthand(dict):
    """A frame with nothing in it still has to answer with the same shape."""

    def __init__(self, reps: int, presence: str, reason: str) -> None:  # noqa: D107
        super().__init__(
            {
                "reps": reps,
                "phase": "setup",
                "angle": None,
                "presence": presence,
                "reason": reason,
                "completed": None,
                "discarded": None,
                "cadence_upm": None,
                "session_quality": None,
                "fps": None,
                "live_checks": [],
            }
        )


@app.get("/session/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    session = require_session(session_id)
    with session.lock:
        state = session.engine.state()
        spec = CATALOGUE[session.exercise]
        state["recommended_view"] = spec.recommended_view
        state["view_matches"] = spec.recommended_view == session.view
        state["frames"] = {"received": session.frames_received, "with_pose": session.frames_detected}
        state["detect_ms"] = {"last": session.detect_ms_last, "mean": session.detect_ms_mean}
        state["clock_degraded"] = session.clock_degraded
        state["finished"] = session.finished
        return state


@app.post("/session/{session_id}/stop")
def stop_session(session_id: str) -> Dict[str, Any]:
    session = require_session(session_id)
    with session.lock:
        session.finished = True
        state = session.engine.state()
    state["finished"] = True
    return state


@app.delete("/session/{session_id}")
def discard_session(session_id: str) -> Dict[str, Any]:
    """Forget a session outright, e.g. the set was recorded by accident."""
    with _sessions_lock:
        existed = _sessions.pop(session_id, None) is not None
    if not existed:
        raise HTTPException(status_code=404, detail="no such session")
    return {"discarded": session_id}
