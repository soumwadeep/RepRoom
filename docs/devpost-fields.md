# Devpost fields — copy each block into the matching box

Entry: https://devpost.com/submit-to/30992-build-ship-shape-amazon-developer-hackathon/manage/submissions

Ordered the way the submission form asks. Each fenced block is the literal
answer; nothing in it needs editing except the two marked `<< >>`.

**Before you paste anything:** the existing entry's URL slug is
`…/submissions/1211873-jio-tv-plus/…`. If that entry was created for a different
idea, start a new submission instead of overwriting it. If it is this project's
entry, change **Project name** to `RepRoom` first — a submission titled after
another company's product is both confusing to a judge and a trademark problem in
its own right.

---

## Project name

```
RepRoom
```

## Tagline

```
Camera-coached reps on the television — no wearable, no app to hold.
```

## Project description

```
RepRoom counts your repetitions and grades your form on the biggest screen in the house. You prop a phone or laptop where it can see you, do a set, and the television shows the rep count, the tempo, and per-rep verdicts on depth, body line and left/right balance, live, from across the sofa.

The architecture starts from a constraint: a Vega OS or Fire OS app has no camera it can open. The Fire TV Cube has one, and third-party apps cannot use it. So the sensor is whatever device is already in the room, and the television is a display for measurements made elsewhere. A companion browser page streams one JPEG at a time to a FastAPI service; MediaPipe pose estimation recovers 33 landmarks per frame in 20-100 ms on an M1; a deterministic engine turns that stream into reps and form verdicts; the TV polls a JSON endpoint and renders it. Amazon Bedrock supplies the one sentence of coaching, built only from the measurements the engine produced.

The counter is a hysteresis state machine over a smoothed joint angle, so a joint sitting on a threshold cannot fire a hundred reps. A rep that was too short or too fast is counted as a discard, and an arc interrupted by the subject walking off frame is counted as abandoned - both shown separately from the total, because "12 reps" and "12 of 15 attempts counted" are different claims.

The design rule the whole codebase is organised around is that nothing on screen may be a guess. A form check the camera view cannot support - squat depth from a front-on phone, for instance - is reported as not measurable and excluded from the quality score rather than passing by default. Tempo and cadence are withheld below 4 fps. Rep duration is measured on the capture device's monotonic clock while server arrival time is kept separate, because merging two unsynchronised clocks would make every tempo number fiction.

Built for the Fire TV track in React Native on Vega OS, running on the Vega Virtual Device. 157 tests, Apache-2.0, and the rep engine is packaged as a standalone library with no runtime dependencies.
```

## Source code URL

```
https://github.com/soumwadeep/RepRoom
```

Public repository, Apache-2.0 license at the root (GitHub's detector reports
`Apache-2.0`). No private-repo collaborator invitations are needed.

## Demo video URL

```
<< paste your YouTube link here >>
```

Required and not yet recorded. Under 3 minutes, public, English. Shot list is in
`docs/submission.md` §6 of the repo — 2:40, leads with someone squatting.

## Which track are you entering?

**Primary track:** Fire TV

```
Fire TV track. A React Native application targeting Vega OS, built with the Vega Developer Tools to a signed .vpkg for armv7, x86_64 and aarch64, installed and running on the Vega Virtual Device. The demo video shows the app running on the simulator, which is the only Fire TV surface available for this build.
```

**Mini challenges:** AWS Builder, Open Source

Note for your own records: the rules allow one track prize and one mini-challenge
prize per project, so entering both mini challenges is extra coverage, not extra
stacked prizes.

## Product feedback (required)

```
What I used, and for what: the Vega Developer Tools for the whole build loop (vega project generate, vega build, npx react-native build-vega, vega virtual-device start, vega run-app), the vega device command set for install/launch/running-apps/run-cmd/port-forwarding, React Native 0.83 on Vega via @amazon-devices/react-native-kepler 4.0 for the app, and Amazon Bedrock for the coaching sentence.

What worked well: installing the SDK and booting the virtual device were one command each, and the VVD is fast - about 30 seconds to "Virtual device ready" on Apple Silicon and smooth enough to develop against all evening. vega build validating manifest.toml and printing "manifest validation found 0 errors" plus an actionable note about the missing icon is the right shape for a build tool. The helloWorld template was genuinely a working starting point, and TVFocusGuideView and hasTVPreferredFocus behaved as documented, which is more than I can say for most TV SDKs. React Native needed no shim to run plain components on Vega.

What needs work, in the order it cost me time:

1. BLOCKER - a project in a folder whose name contains a space cannot be built. The Kepler manifest builder interpolates the project directory into a shell command unquoted, so the bundle step dies with "/bin/sh: /Volumes/.../Github: is a directory". vega build succeeds first, which leaves a plausible-looking package with no app inside. I moved my whole project to a space-free path before I understood that was the cause. Fix: pass an argument array instead of a shell string, and add a whitespace preflight to `vega project doctor`.

2. MAJOR - the virtual device has no screen capture and no key injection. screencap and input are both absent from the device shell, so I could not screenshot the app from a script and could not press a D-pad button from a script. For a competition judged on a demo video, and for anyone wanting UI tests in CI, this is the biggest gap versus the Android emulator. I ended up proving the app ran by watching my own API's access log for the health probe the app issues.

3. MINOR - "--forward true" is the direction you almost never want. Letting an app on the emulator reach a service on the host needs --forward false, and the help text's examples wrap so that both readings look plausible. --direction device-to-host|host-to-device would remove the guesswork.

Also: the CLI installer aborts SDK setup when stdin is not a terminal while still exiting 0; vega project generate --outputDir writes the project into the directory rather than a subdirectory named after it; project names reject hyphens so the folder and project diverge; build paths contain a literal "undefined" segment; and the helloWorld template ships metro.config.js with git-diff "+" markers in its header comment.

How onboarding felt: the docs got me from nothing to a running app on the emulator in one evening, which is the correct outcome for a first-time device SDK. The friction was concentrated where the docs could not be blamed - the space-in-path failure and the port-forward direction - and in the two things I most wanted to automate having no CLI surface.

Would I build with it again: yes, and I would budget for the path-name constraint up front and for hand-driven UI testing. The platform is in open beta and behaves like it: the shape is right and the edges are sharp.
```

## AWS Builder — which services and how

```
Amazon Bedrock.

What it does: exactly one thing - it turns a set of measurements into a single sentence of coaching. It is deliberately outside the counting path and outside the form-grading path, because a rep count has to be reproducible for the benchmark to mean anything, and a generative model should not be the thing deciding whether a repetition happened.

How it is integrated: services/coach/coach.py calls bedrock-runtime Converse with a system prompt that forbids introducing any figure not present in the input (temperature 0.3, 160 max tokens). The prompt payload is produced by session_facts(), which drops every form check whose status is "not_measurable" so the model is never handed a null and invited to interpret it. Model selection is discovered at runtime rather than hardcoded, because Bedrock availability is per account and per region and cross-region inference profiles have their own identifiers: discover() calls bedrock ListInferenceProfiles, and when an account has no profile it falls through to ListFoundationModels plus GetFoundationModelAvailability and reports a PENDING agreement as what it actually is - the one-time Anthropic use-case form - rather than as a permissions mystery.

Honest status of the claim: the cue endpoint, the caching, the provenance labelling and the failure paths are tested and the failure path was exercised against the live AWS endpoint (an invalid-credential probe reached bedrock and returned UnrecognizedClientException, which the service surfaced as the cue's reason and degraded to a labelled rules line). A successful model completion has not been run, because the account's Bedrock API key was not configured on the build machine. No number in this submission is attributed to Bedrock.

Design detail that matters for cost and for the demo: every cue carries its source and the television renders it - "COACH · BEDROCK · <model id>" versus "COACH · BUILT-IN RULES". A rule assembled from an if-statement and a generated sentence are not the same claim, and the viewer is entitled to know which one is on the wall. Caching is per (exercise, rep count, failed checks), so a TV polling several times a second does not spend a model call per poll.

Permissions requested for the integration are in infra/bedrock-cue-policy.json: bedrock read actions for discovery, bedrock-runtime InvokeModel scoped to anthropic models and inference profiles, and the three aws-marketplace actions Bedrock needs the first time a model is enabled in an account.
```

## Open Source — required fields

**Repository URL**

```
https://github.com/soumwadeep/RepRoom
```

**GitHub username**

```
soumwadeep
```

**What you did, how it works, why it matters**

```
RepRoom is published as a new open-source project for this hackathon, under Apache-2.0 with the canonical license text at the repository root.

Inside it, packages/rep-engine is separately packaged as reproom-rep-engine: a library that counts repetitions and grades exercise form from pose landmarks. The split is deliberate. reproom.geometry computes joint angles from 33-point landmarks; reproom.exercises declares each movement's arc thresholds and its form checks; reproom.engine is a hysteresis state machine that turns a stream of poses into counted reps, discards, abandoned arcs and per-rep check results. The core imports nothing outside the Python standard library - MediaPipe sits behind an optional "detect" extra - so it can be embedded in a server, an edge device or a test fixture without carrying a vision runtime.

Why it matters: rep counting is usually shipped as a black box that returns a number. This one reports what it could not measure, and keeps that distinction all the way to the screen. A check the camera angle cannot support is excluded from the quality score rather than passing by default; a rep interrupted by the subject leaving frame is counted as abandoned rather than as a failed rep or silently dropped; tempo and cadence are withheld when the feed is too slow for the timing to mean anything. Anyone building a camera-based movement feature inherits that behaviour and the 52 tests that pin it.

Contribution URL: << optional - see below >>
```

On that last line: the mini challenge accepts either a new open-source project or
a contribution. The new project is done. A PR is cheap here and would make the
entry unambiguous — `AmazonAppDev/react-native-multi-tv-app-sample` and
`AmazonAppDev/vega-video-sample` are the two official samples, and both the
`metro.config.js` diff markers and the space-in-path build failure are small,
real, upstream-fixable defects. Filing one before the deadline is roughly 20
minutes of work.

## Prior work statement

```
This project did not exist before the submission window. The repository's first commit is 12 October 2026, inside the 31 August - 23 October period, and the entire history is inside it. No code was reused from any earlier project of mine; what carried over was judgement, not files - specifically, the discipline of never letting an unmeasured quantity appear as a number.
```

## Feature requests (optional, but free)

Paste from `docs/feature-requests.md`. Lead with the camera one and mark it
critical: third-party Fire TV apps cannot open the Cube's camera, which is the
constraint that forced a companion device to become the sensor for every
computer-vision-on-the-TV idea.

## Friction log (optional, up to 10% judging bonus)

Upload or paste `docs/friction-log.md` — ten entries, each with the task
attempted, steps taken, expected vs actual, a severity rating, the workaround,
and an actionable suggestion. This is the highest-value thing in the whole
submission and it is already written.

---

## What is genuinely not ready

| Item | State |
|---|---|
| Demo video | **Missing.** Required. ~10 minutes: start the API + emulator, screen-record the window, follow the 2:40 shot list, upload to YouTube as public. |
| Labelled clip benchmark | **Missing.** Accuracy against a human count stays UNVERIFIED. `scripts/verify-bedrock.sh`'s equivalent for vision is `benchmarks/label.py` + `benchmarks/bench_clips.py`. |
| Bedrock live call | **Not run.** The text above says so explicitly rather than implying otherwise. |
| Entry title | Says `jio-tv-plus`. Rename to RepRoom, or start a fresh submission. |
