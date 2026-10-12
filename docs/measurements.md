# What each number means, and where it stops being true

Everything the HUD shows is derived from 2D joint positions recovered by a
monocular camera. That single sentence is the source of most of the caveats
below, and it is why this file exists: an on-screen percentage looks authoritative
even when the geometry underneath it cannot support the claim.

## Coordinate system

Landmarks arrive normalised to the frame with the origin at the top-left, so
`y` grows downwards. `z` is a network estimate of relative depth with respect to
the hip centre. It is not metric and nothing in this repository uses it for a
measurement -- every angle is computed in the image plane.

## Joint angles

`angle_at(pose, vertex, a, b)` is the interior angle at `vertex`, in degrees,
between the two segments to `a` and `b`. It returns `None` when any of the three
landmarks is detected below 0.5 visibility. `None` propagates: it is never
converted to zero, and a rep whose defining joint went unmeasurable on a frame
is counted in `low_confidence_frames` on that rep's record.

| Call | Landmarks | Standing | Working end |
|---|---|---|---|
| `knee_angle` | hip–knee–ankle | ~180 | 90–115 |
| `hip_angle` | knee–hip–ankle | ~170 | hip flexion |
| `elbow_angle` | shoulder–elbow–wrist | ~175 | 60–95 |
| `shoulder_angle` | elbow–shoulder–wrist | ~60 | abduction |
| `spine_angle` | shoulder–hip–knee | ~178 | straight line |
| `torso_lean` | shoulder-to-hip line vs vertical | ~5 | forward/back lean |

Angles are capped at 180 by construction, because they come from an arc cosine of
a dot product. A leg hyperextended past straight does not report 190; it reports
170 and starts looking bent the other way. Thresholds are set inside the range
where this cannot happen.

## Scale invariance

Every ratio is normalised against a body measurement rather than pixels, so the
same judgement applies whether the subject stands 1 m or 4 m from the lens.

`torso_length` is shoulder-centre to hip-centre distance. `shoulder_width` is
left-to-right shoulder distance. Depth and knee tracking use `torso_length` on
purpose: a knee that collapses inward drags the hips with it, so a shoulder-width
denominator shrinks at exactly the moment the numerator grows, and the ratio can
only ever flatter the rep. That was a real bug in the first version of
`check_knee_track`, found by a fixture that reproduced a knock-in collapse.

## Why camera view is part of the contract

An angle measured in the image plane is only the true joint angle when the joint
rotates roughly parallel to that plane.

- From a **side** camera, the knee and hip arcs are visible. Squat depth and
  forward torso lean are measurable. Lateral knee collapse is nearly invisible.
- From a **front** camera, knee tracking and bar path are measurable. Forward
  lean is invisible -- the torso can tilt 40° toward the floor and the shoulder
  to hip line stays vertical in the image.

Each form check declares the views it is valid in. A check that is invalid for
the current view is emitted as `not_measurable` with a reason, and is excluded
from both the numerator and denominator of the quality score.

The consequence, stated plainly: a squat filmed from the front has no depth
measurement in this build. Not "a weak one" -- none. The screen says so.

## Derived numbers and their gates

| Field | Definition | Gate |
|---|---|---|
| `reps` | Arcs that crossed both thresholds plus hysteresis | requires `min_rom` and `min_duration_ms` |
| `no_reps` | Arcs that began and finished but failed a validity window | always reported |
| `abandoned_arcs` | Arcs killed by the subject leaving the frame | separate from `no_reps` deliberately |
| `quality` | Passed measurable checks / measurable checks | no measurable checks yields no score |
| `duration_ms` | Pose-clock time between arming and lockout | `clock_source` says which clock |
| `cadence_upm` | 60 000 / mean duration of the last five counted reps | hidden below 4 fps |
| `fps_estimate` | Frames fed per second over the session | printed next to tempo |

## What has not been established

This document describes how measurements are computed. It is not evidence that
they are right about a human body. Rep-count agreement with a human counting
real reps is measured by `benchmarks/bench_clips.py` against a labelled corpus,
and until that corpus exists the accuracy of this build is
[UNVERIFIED](../benchmarks/README.md).

Known structural limits, independent of any benchmark:

- Occlusion. A far-side limb behind the torso in a side view is estimated, not
  seen, and MediaPipe's visibility score is the only signal available.
- Clothing and low light degrade landmark stability before they degrade the
  counter, which means the count can stay plausible while the form verdicts stop
  being one.
- A subject who genuinely moves asymmetrically can pass `asymmetry` if the
  camera only resolves one side well, which is why single-side measurement sets
  the gap to `None` instead of zero.
