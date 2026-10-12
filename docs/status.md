# Build status — 12 October 2026

Everything below was run on the machine used to build this (Apple M1, macOS,
Node 22, Python 3.13.2, Vega SDK 0.24.12112, Vega CLI 1.4.4). Reproduced with
the commands in [runbook.md](runbook.md).

## Verified

| | How it was proven |
|---|---|
| Pose detection runs locally | MediaPipe `pose_landmarker_full` recovers 33 landmarks from a real photo; 20–100 ms/frame measured. 4 integration tests in `packages/rep-engine/tests/test_detector_real.py` |
| Rep counting and form grading | 52 engine tests over synthetic landmark arcs: hysteresis, five-frame smoothing, discard windows, pause/abandon, adaptive depth |
| Session API serves it over HTTP | 18 service tests, plus a live `uvicorn` boot where a real JPEG posted to `/session/{id}/frame` returned a measured knee angle |
| The Vega app builds | `npx react-native build-vega --build-type Release` → signed `reproomtv_{armv7,x86_64,aarch64}.vpkg` |
| The Vega app runs on the simulator | `vega virtual-device start` → "Virtual device ready"; `vega run-app` → `com.reproom.tv.main is running`; `vega device running-apps` lists it |
| The app's JavaScript executes and reaches the API | With reverse port forwarding on, the API access log shows `GET /health 200` and `GET /exercises 200` arriving from the device after the app was relaunched. The emulator window shows the exercise list and "API reachable" |
| The device can reach a LAN host directly too | `wget http://192.168.29.2:8420/health` from `vega device run-cmd` returned the live payload |
| App logic and screen flow | 44 jest tests: pairing code on screen, live reps rendered, unmeasurable check drawn as a dash, stale veil, summary read back from the server |

## Not verified

- **Rep-count accuracy against a human counting real reps.** No labelled clip
  corpus exists. `benchmarks/bench_clips.py` exits with a message rather than
  producing a number, and no README or demo claim may quote one until it runs.
- **The camera path on a phone.** `scripts/with-tls.sh` is written and the
  insecure-origin warning is implemented, but the TLS pairing flow has not been
  exercised from a handset. The Mac's own camera at `localhost` is the tested
  route.
- **Form-check agreement with a trainer's judgement.** The checks are
  deterministic and tested against fixtures that reproduce each fault; nobody
  has yet confirmed that the faults they flag are the ones a coach would call.
- **On-device behaviour.** There is no physical Fire TV here. Everything about
  the television is emulator-derived, including the demo recording.

## Known rough edges

- The VVD has no `screencap` and no `input`, so screenshots come from the OS and
  the remote is driven by hand. See the friction log.
- `kepler` builds only from a path without spaces. This project was moved to
  `/Volumes/SoumwadeepSSD/Repos/RepRoom` for that reason.
- The `helloWorld` template's `metro.config.js` ships with git-diff `+` markers
  in its header comment; corrected here.
