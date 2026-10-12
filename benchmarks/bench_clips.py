#!/usr/bin/env python
"""Measure the engine against labelled clips, and print what actually happened.

The unit suite proves the state machine on synthetic arcs. Nothing in this
repository claims that the *detector* counts a real person's reps accurately
until this script has been run over real footage with human labels.

    .venv/bin/python benchmarks/bench_clips.py benchmarks/clips --fps 10

Each clip is a video file with a sidecar of the same name::

    squats_set1.mp4
    squats_set1.json      {"exercise": "squat", "view": "side", "reps": 12,
                           "expected_fail": ["depth"], "labelled_by": "me",
                           "notes": "stopped high on reps 7-9"}

Reported per clip: counted reps, discarded reps, abandoned arcs, count error,
whether every expected form flag appeared, and the measured cost per frame.
Aggregated: exact-match rate, mean absolute error, and a count-level
precision/recall -- with the frame rate, model, exercise and clip count stated
next to it, because a number without its conditions is not a measurement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "packages", "rep-engine"))

from reproom import CATALOGUE, RepEngine  # noqa: E402


@dataclass
class ClipResult:
    clip: str
    exercise: str
    view: str
    labelled_reps: int
    counted_reps: int
    discarded: int
    abandoned: int
    frames: int
    with_pose: int
    ms_per_frame: float
    flags_seen: List[str] = field(default_factory=list)
    expected_missing: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def detection_rate(self) -> float:
        return self.with_pose / self.frames if self.frames else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip": self.clip,
            "exercise": self.exercise,
            "view": self.view,
            "labelled_reps": self.labelled_reps,
            "counted_reps": self.counted_reps,
            "count_error": self.counted_reps - self.labelled_reps,
            "discarded": self.discarded,
            "abandoned_arcs": self.abandoned,
            "frames": self.frames,
            "pose_detection_rate": round(self.detection_rate, 3),
            "ms_per_frame": round(self.ms_per_frame, 1),
            "flags_seen": self.flags_seen,
            "expected_flags_missing": self.expected_missing,
            "error": self.error,
        }


def iter_frames(path: str, target_fps: float, sample_fps: float = 30.0):
    """Yield (timestamp_ms, rgb) at ``target_fps`` from any decodable video."""
    import cv2

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise RuntimeError(f"cv2 could not open {path}")
    native = capture.get(cv2.CAP_PROP_FPS) or sample_fps
    stride = max(1, round(native / target_fps))
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % stride == 0:
            yield index * 1000.0 / native, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        index += 1
    capture.release()


def run_clip(path: str, label: Dict[str, Any], detector, target_fps: float) -> ClipResult:
    exercise = label.get("exercise", "squat")
    view = label.get("view", "side")
    if exercise not in CATALOGUE:
        raise SystemExit(f"{path}: unknown exercise {exercise!r}")
    engine = RepEngine(exercise, view=view)
    frames = with_pose = 0
    started = time.perf_counter()
    for timestamp_ms, rgb in iter_frames(path, target_fps):
        frames += 1
        pose = detector.detect(rgb, timestamp_ms)
        if pose is None:
            continue
        with_pose += 1
        engine.feed(pose, timestamp_ms)
    elapsed = time.perf_counter() - started
    cost = (elapsed * 1000.0 / frames) if frames else 0.0

    seen = sorted({c.key for rep in engine.summary().per_rep for c in rep.checks if c.status == "fail"})
    expected = sorted(label.get("expected_fail", []))
    return ClipResult(
        clip=os.path.basename(path),
        exercise=exercise,
        view=view,
        labelled_reps=int(label.get("reps", 0)),
        counted_reps=engine.reps,
        discarded=engine.no_reps,
        abandoned=engine.abandoned_arcs,
        frames=frames,
        with_pose=with_pose,
        ms_per_frame=cost,
        flags_seen=seen,
        expected_missing=[k for k in expected if k not in seen],
    )


def aggregate(results: List[ClipResult], args) -> Dict[str, Any]:
    usable = [r for r in results if r.error is None]
    exact = [r for r in usable if r.counted_reps == r.labelled_reps]
    within_one = [r for r in usable if abs(r.counted_reps - r.labelled_reps) <= 1]
    errors = [r.counted_reps - r.labelled_reps for r in usable]
    labelled_total = sum(r.labelled_reps for r in usable)
    counted_total = sum(r.counted_reps for r in usable)
    # Rep-level agreement: how many counted reps the labels support, and how
    # many labelled reps the engine found at all.
    tp = sum(min(r.counted_reps, r.labelled_reps) for r in usable)
    return {
        "clips": len(usable),
        "clips_that_failed_to_run": len(results) - len(usable),
        "exercise_breakdown": {
            key: sum(1 for r in usable if r.exercise == key) for key in sorted({r.exercise for r in usable})
        },
        "exact_match_rate": round(len(exact) / len(usable), 3) if usable else None,
        "within_one_rep_rate": round(len(within_one) / len(usable), 3) if usable else None,
        "mean_absolute_error_reps": (
            round(sum(abs(e) for e in errors) / len(errors), 2) if errors else None
        ),
        "bias_reps": round(sum(errors) / len(errors), 2) if errors else None,
        "rep_level_precision": round(tp / counted_total, 3) if counted_total else None,
        "rep_level_recall": round(tp / labelled_total, 3) if labelled_total else None,
        "median_ms_per_frame": round(sorted(r.ms_per_frame for r in usable)[len(usable) // 2], 1) if usable else None,
        "mean_pose_detection_rate": (
            round(sum(r.detection_rate for r in usable) / len(usable), 3) if usable else None
        ),
        "expected_flags_missing_in": [
            r.clip for r in usable if r.expected_missing
        ],
        "sample_fps": args.fps,
        "model": os.path.basename(args.model),
        "caveat": (
            "Rep-count agreement with human labels on the clips in this corpus. "
            "Not a claim about accuracy on other exercises, cameras, lighting, "
            "body types or clothing than the ones recorded here."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips_dir", nargs="?", default=os.path.join(ROOT, "benchmarks", "clips"))
    parser.add_argument("--fps", type=float, default=10.0, help="frames per second to analyse")
    parser.add_argument(
        "--model",
        default=os.path.join(ROOT, "models", "pose_landmarker_full.task"),
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()

    if not os.path.isdir(args.clips_dir):
        print(
            f"no clip corpus at {args.clips_dir}.\n"
            "Record labelled clips there (see benchmarks/README.md). Until then the "
            "detection accuracy of this build is UNVERIFIED, and no number derived "
            "from it belongs in a README.",
            file=sys.stderr,
        )
        return 2

    from reproom.detector import PoseDetector

    clips = sorted(
        f for f in os.listdir(args.clips_dir)
        if f.lower().endswith((".mp4", ".mov", ".mk4", ".avi", ".m4v"))
    )
    if not clips:
        print(f"no video files in {args.clips_dir}", file=sys.stderr)
        return 2

    results: List[ClipResult] = []
    with PoseDetector(args.model, running_mode="video") as detector:
        for name in clips:
            label_path = os.path.splitext(os.path.join(args.clips_dir, name))[0] + ".json"
            if not os.path.exists(label_path):
                results.append(ClipResult(name, "-", "-", 0, 0, 0, 0, 0, 0, 0.0, error="no sidecar label"))
                continue
            with open(label_path) as handle:
                label = json.load(handle)
            try:
                detector_reset = detector  # MediaPipe carries tracking state across clips
                results.append(run_clip(os.path.join(args.clips_dir, name), label, detector_reset, args.fps))
            except Exception as exc:  # a clip that will not decode is a result too
                results.append(ClipResult(name, "-", "-", 0, 0, 0, 0, 0, 0, 0.0, error=str(exc)))

    summary = aggregate(results, args)
    if args.json:
        print(json.dumps({"clips": [r.to_dict() for r in results], "summary": summary}, indent=2))
    else:
        for result in results:
            print(json.dumps(result.to_dict()))
        print("\n--- summary ---")
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
