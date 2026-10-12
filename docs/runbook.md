# Runbook

Reproduces exactly what `docs/status.md` claims, in order. Verified on Apple M1,
macOS, Node 22, Python 3.13.2, Vega CLI 1.4.4, Vega SDK 0.24.12112.

**The project path must not contain a space.** See
[friction log entry 1](friction-log.md#1-a-project-in-a-folder-with-a-space-cannot-be-built).

## 1. Engine, service, tests

```bash
cd RepRoom
scripts/setup.sh                                   # venv + deps + pose models
.venv/bin/python -m pytest packages services -q    # 70 tests
```

## 2. Start the API

```bash
scripts/dev.sh            # http://localhost:8420, real MediaPipe detector
curl -s localhost:8420/health
# {"status":"ok","detected_by":"mediapipe-pose-landmarker","exercises":5,...}
```

## 3. Build the TV app

```bash
cd apps/fire-tv
npm install
npx jest --ci                       # 44 tests
npx tsc --noEmit && npx eslint src test --ext .ts,.tsx
export PATH="$HOME/vega/bin:$PATH"
vega build                                       # native artifacts
npx react-native build-vega --build-type Release # .vpkg per architecture
```

## 4. Run it on the virtual device

```bash
vega virtual-device start --gui -t 300     # ~30 s on Apple Silicon
vega device list                           # VirtualDevice : tv - aarch64
vega run-app build/aarch64-release/reproomtv_aarch64.vpkg
vega device running-apps | grep reproom    # com.reproom.tv.main
```

The app needs to reach the API. Either forward the port, or point it at the
Mac's LAN address from the on-screen keypad:

```bash
# device 127.0.0.1:8420  ->  host 8420. Note the direction: --forward FALSE.
vega device start-port-forwarding --port 8420 --forward false
vega device is-port-forwarded --port 8420 --forward false     # true
```

Confirm the app really is talking to the service rather than assuming it: the
API's access log should show the device's own probes after a relaunch.

```bash
vega device terminate-app --appName com.reproom.tv.main
vega device launch-app    --appName com.reproom.tv.main
# then in the terminal running scripts/dev.sh:
#   INFO: 127.0.0.1:49725 - "GET /health HTTP/1.1" 200 OK
#   INFO: 127.0.0.1:49725 - "GET /exercises HTTP/1.1" 200 OK
```

## 5. Drive a session

The VVD window has an on-screen remote and these keyboard bindings: `Esc` back,
`F1` home, `F2` menu, `F3` rewind, `F4` play/pause, `F5` fast-forward. Arrow keys
move focus, the centre button selects. There is no CLI key injection, so this
step is manual.

1. On the TV setup screen, arrow to an exercise tile and press select. The TV
   opens a session and shows its pairing code.
2. On the same machine, open `http://localhost:8420/capture?session=<code>` and
   press Start, allowing camera access. `localhost` is a secure origin, so the
   browser will grant it; a phone on the LAN needs `scripts/with-tls.sh`.
3. Stand where the camera can see shoulders and hips, and squat. The count,
   phase, tempo and per-rep form checks update on the television.

## 6. Record the benchmark

Nothing above proves accuracy against a human count. That needs labelled clips:
see `benchmarks/README.md`, then

```bash
.venv/bin/python benchmarks/bench_clips.py benchmarks/clips --fps 10
```

## Stopping

```bash
vega virtual-device stop
pkill -f "uvicorn app:app"
```
