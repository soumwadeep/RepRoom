# Benchmarks

The unit suite in `packages/rep-engine/tests` proves the counting and grading
logic against synthetic arcs. **It proves nothing about real cameras**, and this
directory is where that gap gets closed or admitted.

## Status: UNVERIFIED

No accuracy number in this repository is measured yet. There is no clip corpus
here, so `bench_clips.py` exits with code 2 and says so. Until real footage is
labelled and run, the honest claim about detection accuracy is: unknown.

## Recording a corpus

1. `scripts/dev.sh` (or `scripts/with-tls.sh` to use a phone as the camera).
2. Open `https://<host>:8420/capture`, pick the exercise and view, and record
   the session screen plus the source frames.
3. Drop the clip in `benchmarks/clips/` next to a sidecar of the same basename:

```json
{
  "exercise": "squat",
  "view": "side",
  "reps": 12,
  "expected_fail": ["depth"],
  "labelled_by": "soumwadeep",
  "notes": "reps 7-9 stopped above parallel on purpose"
}
```

`reps` is what a human counted from the recording, not what the engine said.
Include deliberate failures in `expected_fail` so the form checks are graded too,
not just the counter.

## Running it

```bash
.venv/bin/python benchmarks/bench_clips.py benchmarks/clips --fps 10
```

Reports per clip: counted, discarded, abandoned arcs, count error, missing
expected flags, measured ms/frame, pose detection rate. Aggregates: exact-match
rate, within-one rate, mean absolute error, bias, rep-level precision and recall.

## What the numbers may and may not say

Every published figure must ship with its conditions -- frame rate, model,
exercise mix, clip count, who was on camera. They describe that corpus only.
They are not a claim about other exercises, cameras, lighting, body types or
clothing than the ones recorded, and a README that implies otherwise is a bug.
