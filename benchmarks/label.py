#!/usr/bin/env python
"""Create and validate the sidecar labels the benchmark reads.

Counting reps by hand from a video is the slow part of building a corpus, and
the failure mode is silent: a sidecar whose `reps` was typed from memory rather
than from the clip produces a precision number that means nothing. This tool
removes the two easiest mistakes -- it measures the clip's real duration and
frame rate, and it refuses a label file that does not match the video it
describes.

    .venv/bin/python benchmarks/label.py benchmarks/clips/squats_set1.mp4
    .venv/bin/python benchmarks/label.py benchmarks/clips --verify

Writing the sidecar is still a human judgement: watch the clip, count the reps,
note which reps had which fault. Nothing here guesses at them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "packages", "rep-engine"))

from reproom.exercises import CATALOGUE, VIEW_FRONT, VIEW_SIDE  # noqa: E402

SIDECAR_KEYS = (
    "exercise",
    "view",
    "reps",
    "expected_fail",
    "labelled_by",
    "notes",
)


def probe(path: str) -> Dict[str, Any]:
    """Measured properties of the clip. No decoding of content, just metadata."""
    import cv2

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise SystemExit(f"cv2 could not open {path!r} -- is it a video this build can decode?")
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    capture.release()
    duration_ms = (frames / fps * 1000.0) if fps else 0.0
    return {
        "fps": round(fps, 3),
        "frames": frames,
        "duration_ms": round(duration_ms),
        "width": width,
        "height": height,
    }


def ask(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def label_one(path: str, force: bool = False) -> Optional[str]:
    sidecar = os.path.splitext(path)[0] + ".json"
    if os.path.exists(sidecar) and not force:
        print(f"{sidecar} already exists; pass --force to overwrite")
        return sidecar

    meta = probe(path)
    print(f"\n{os.path.basename(path)}")
    print(
        f"  {meta['width']}x{meta['height']} @ {meta['fps']} fps, "
        f"{meta['frames']} frames, {meta['duration_ms'] / 1000:.1f} s"
    )
    print("  Count the reps from the clip itself. Do not fill this in from memory.\n")

    keys = ", ".join(sorted(CATALOGUE))
    while True:
        exercise = ask("exercise", "squat")
        if exercise in CATALOGUE:
            break
        print(f"  unknown exercise; choose one of {keys}")

    spec = CATALOGUE[exercise]
    views = (VIEW_SIDE, VIEW_FRONT)
    while True:
        view = ask(f"camera view ({'/'.join(views)})", spec.recommended_view)
        if view in views:
            break

    while True:
        raw = ask("reps counted by a human")
        try:
            reps = int(raw)
            break
        except ValueError:
            print("  needs a whole number")

    print(f"  checks this exercise grades: {', '.join(c.key for c in spec.checks)}")
    raw_checks = ask("expected_fail (comma separated, blank if none)")
    expected = [c.strip() for c in raw_checks.split(",") if c.strip()]
    unknown = [c for c in expected if c not in {chk.key for chk in spec.checks}]
    if unknown:
        print(f"  note: {', '.join(unknown)} is not a check of {exercise}; kept anyway")

    payload: Dict[str, Any] = {
        "exercise": exercise,
        "view": view,
        "reps": reps,
        "expected_fail": expected,
        "labelled_by": ask("labelled_by", os.environ.get("USER", "unknown")),
        "notes": ask("notes"),
        # Recorded so a later reader can tell a 1080p60 side-on clip from a
        # 480p15 phone clip, and so --verify can catch a re-encoded video.
        "clip": {"path": os.path.basename(path), **meta},
    }
    with open(sidecar, "w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(f"  wrote {os.path.relpath(sidecar, ROOT)}")
    return sidecar


def verify_one(path: str) -> List[str]:
    """Re-measure the clip against the metadata its label claims."""
    sidecar = os.path.splitext(path)[0] + ".json"
    problems: List[str] = []
    if not os.path.exists(sidecar):
        return [f"{os.path.basename(path)}: no sidecar"]

    with open(sidecar) as handle:
        label = json.load(handle)

    missing = [key for key in ("exercise", "view", "reps") if key not in label]
    if missing:
        problems.append(f"{os.path.basename(path)}: sidecar missing {', '.join(missing)}")
    if label.get("exercise") not in CATALOGUE:
        problems.append(f"{os.path.basename(path)}: unknown exercise {label.get('exercise')!r}")
    if not isinstance(label.get("reps"), int) or label.get("reps", 0) <= 0:
        problems.append(f"{os.path.basename(path)}: reps must be a positive integer")

    recorded = label.get("clip", {})
    if recorded:
        try:
            meta = probe(path)
        except SystemExit as exc:
            return problems + [f"{os.path.basename(path)}: {exc}"]
        for key in ("fps", "frames", "duration_ms"):
            if abs(float(recorded.get(key, 0)) - float(meta[key])) > max(2.0, abs(float(meta[key])) * 0.02):
                problems.append(
                    f"{os.path.basename(path)}: {key} is {meta[key]}, labelled {recorded.get(key)}"
                )
    else:
        problems.append(
            f"{os.path.basename(path)}: sidecar has no measured clip metadata; "
            "re-run label.py --force so duration and fps are on the record"
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="a clip, or a directory with --verify")
    parser.add_argument("--verify", action="store_true", help="check labels against the videos")
    parser.add_argument("--force", action="store_true", help="overwrite an existing sidecar")
    args = parser.parse_args()

    if not args.target:
        parser.print_help()
        return 2

    videos: List[str] = []
    if os.path.isdir(args.target):
        videos = sorted(
            os.path.join(args.target, name)
            for name in os.listdir(args.target)
            if name.lower().endswith((".mp4", ".mov", ".m4v", ".avi", ".mkv"))
        )
    else:
        videos = [args.target]

    if not videos:
        print(f"no video files in {args.target}", file=sys.stderr)
        return 2

    if args.verify:
        problems: List[str] = []
        for video in videos:
            problems.extend(verify_one(video))
        if problems:
            print("label problems found:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print(f"{len(videos)} clips labelled consistently")
        return 0

    for video in videos:
        label_one(video, force=args.force)
    print("\nnow run: .venv/bin/python benchmarks/bench_clips.py <clips-dir>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
