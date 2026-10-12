# RepRoom

Camera-coached reps on the living-room television. A phone or laptop webcam is
the sensor, a FastAPI service measures the movement, and a Fire TV app running
on Vega OS shows the count, the tempo and the form verdicts from across the sofa.

Built for the [Amazon Developer Hackathon 2026](https://amazonappdev2026.devpost.com/)
Fire TV track, with the AWS Builder and Open Source mini challenges.

```
companion camera  --JPEG-->  session API  --pose landmarks-->  rep engine
        |                                                          |
        └──────────── TV polls /session/{id} <── JSON state ───────┘
```

## Why the camera is not on the TV

A Vega OS or Fire OS application has no camera API to call. The Fire TV Cube has
a physical camera, and third-party apps cannot open it. So the sensor is whatever
device is already in the room, and the television is a display for measurements
made somewhere else. That is the whole architecture, and it is the direct
consequence of a gap that is written up in `docs/friction-log.md`.

## Quickstart

```bash
scripts/setup.sh                      # venv, deps, pose models (~14 MB)
.venv/bin/python -m pytest packages services   # 68 tests
node --test apps/fire-tv                      # 19 tests, no browser needed

scripts/dev.sh                        # API on http://localhost:8420
open http://localhost:8420/capture    # camera page; press Start, do squats
```

Using a phone as the camera needs TLS, because a browser only grants
`getUserMedia` to a secure origin and `http://192.168.x.x` is not one:

```bash
scripts/with-tls.sh                   # https://<lan-ip>:8420/capture
```

The Fire TV app lives in `apps/fire-tv` and needs the Vega Developer Tools
(`curl -fsSL https://sdk-installer.vega.labcollab.net/get_vvm.sh | bash`), which
run on macOS or Ubuntu only.

## What is verified, and what is not

| Claim | State | Evidence |
|---|---|---|
| Rep counting, discards, pause and resume | Verified | 52 engine tests on synthetic landmark arcs |
| Form checks flag the fault they target | Verified | same suite; each check has a passing and a failing fixture |
| MediaPipe recovers a pose from a JPEG | Verified | 4 integration tests, 20–100 ms/frame measured on Apple M1 |
| The API serves that over HTTP | Verified | 16 service tests plus a live uvicorn smoke run |
| The HUD refuses to render unmeasured numbers | Verified | 19 app tests |
| **Rep counts a real person matches a human's count** | **UNVERIFIED** | no labelled clip corpus exists yet; `benchmarks/bench_clips.py` exits rather than invent one |
| The app runs in the Vega Virtual Device | In progress | see `docs/status.md` |

## The rule the codebase is organised around

Nothing on screen is allowed to be a guess.

A form check that the camera view cannot support is reported as
`not_measurable` and dropped from the quality denominator. It does not count as
a pass. A rep that was interrupted by the subject walking off is reported as an
abandoned arc, not a failed rep and not a rep at all. A feed slower than 4 fps
shows a dash where tempo and cadence would go, because those two numbers are
derived from frame timing and the timing is not good enough.

Two clocks are kept apart for the same reason. Rep duration, tempo and cadence
come from the capture device's monotonic clock (`X-Capture-Ms`). The server's
arrival time is reported separately as `arrival_gap_ms`. They live on different
machines with no shared origin, so no cross-device latency figure is published,
because that number would be a fiction about clock synchronisation.

## Layout

```
packages/rep-engine/  reproom -- counts reps and grades form from pose
                                 landmarks. Standard library only. The piece
                                 meant to be reused. Apache-2.0.
services/session-api/ FastAPI service: frames in, session state out.
services/capture/     Companion-device camera page, served from the API origin.
apps/fire-tv/         Vega OS React Native app: 10-foot HUD, D-pad focus.
benchmarks/           Labelled-clip harness. Where the accuracy claim is earned
                      or withheld.
docs/                 Measurements, friction log, feature requests, status.
scripts/              setup, dev, TLS.
```

## Exercise catalogue

| Exercise | Measured on | Counted rep | Graded checks |
|---|---|---|---|
| Bodyweight squat | knee angle | 175° → ≤109° → back | depth, back angle, knee tracking, balance, tempo |
| Push-up | elbow angle | 172° → ≤97° → back | body line, balance, tempo |
| Overhead press | elbow angle | 175° → ≤92° → back | lockout overhead, bar path, balance, tempo |
| Bicep curl | elbow angle | 60° → ≥150° | elbow position, lean, balance, tempo |
| Split squat / lunge | knee angle | 175° → ≤114° → back | back angle, balance, tempo |

Thresholds carry a hysteresis band and the angle is smoothed over five frames
before anything is compared, so a joint sitting on a threshold cannot fire a
hundred reps. `docs/measurements.md` explains what each ratio means and where
single-camera geometry stops being enough.

## Test assets

`assets_test_pose.jpg` is the sample photograph published in Google's
MediaPipe assets bucket and is used by the detector integration tests. The
synthetic poses in `packages/rep-engine/tests/fixtures.py` are generated from
joint angles, not recorded from a person, and they validate the state machine
rather than the detector.

## License

Apache-2.0. See `LICENSE`.
