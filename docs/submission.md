# Submission — Build, Ship, Shape: Amazon Developer Hackathon 2026

Deadline: **Friday 23 October 2026, 12:00 PT.** Fill the Devpost fields from the
blocks below; anything in `[[double brackets]]` needs a real value first.

---

## 1. Open items before submitting

| # | Item | Who |
|---|---|---|
| 1 | Create the public GitHub repo and push (commands in §7) | you |
| 2 | `aws configure` on this machine, then I run `/coach/status` and one real `converse()` call so the AWS Builder claim is verified rather than stubbed | you, then me |
| 3 | Record ~15 labelled squats on your phone so the accuracy number stops being UNVERIFIED | you, then me |
| 4 | Screen-record the demo (script in §6) and upload unlisted-public to YouTube | you |
| 5 | Decide whether to also file the upstream PR for the Open Source field (§5 optional line) | you |

Items 2 and 3 change what can honestly be written in the feedback and
description fields, so do them before pasting §2 and §4 if possible.

---

## 2. Project description

> **RepRoom — camera-coached reps on the television**
>
> RepRoom counts your repetitions and grades your form on the biggest screen in
> the house. You prop a phone or laptop where it can see you, do a set, and the
> television shows the rep count, the tempo, and per-rep verdicts on depth, body
> line and left/right balance, live, from across the sofa.
>
> The architecture starts from a constraint: a Vega OS or Fire OS app has no
> camera it can open. The Fire TV Cube has one, and third-party apps cannot use
> it. So the sensor is whatever device is already in the room, and the television
> is a display for measurements made elsewhere. A companion browser page streams
> one JPEG at a time to a FastAPI service; MediaPipe pose estimation recovers 33
> landmarks per frame in 20–100 ms on an M1; a deterministic engine turns the
> landmark stream into reps and form verdicts; the TV polls a JSON endpoint and
> renders it. Amazon Bedrock supplies the one sentence of coaching, built only
> from the measurements the engine produced.
>
> The counter is a hysteresis state machine over a smoothed joint angle, so a
> joint sitting on a threshold cannot fire a hundred reps. A rep that was too
> short or too fast is counted as a discard, and an arc interrupted by the
> subject walking off frame is counted as abandoned — both are shown separately
> from the total, because "12 reps" and "12 of 15 attempts counted" are different
> claims.
>
> The design rule the whole codebase is organised around is that nothing on
> screen may be a guess. A form check the camera view cannot support — squat
> depth from a front-on phone, for instance — is reported as *not measurable* and
> excluded from the quality score rather than passing by default. Tempo and
> cadence are withheld below 4 fps. Rep duration is measured on the capture
> device's monotonic clock while server arrival time is kept separate, because
> merging two unsynchronised clocks would make every tempo number fiction.
>
> Built for the Fire TV track in React Native on Vega OS, running on the Vega
> Virtual Device. 146 tests, Apache-2.0, and the rep engine is packaged as a
> standalone library with no runtime dependencies.

**Word count:** ~350. Devpost's description box is generous; trim from the last
two paragraphs if it complains.

---

## 3. Tracks and mini challenges

- **Primary track:** Fire TV. React Native app targeting Vega OS, built to a
  signed `.vpkg`, installed and running in the Vega Virtual Device (no physical
  Fire TV was available; the simulator is the demo surface).
- **Mini challenge:** AWS Builder — Amazon Bedrock `converse()` generates the
  coaching cue; model selection discovered via `bedrock:ListInferenceProfiles`.
  Documented integration in `docs/bedrock.md`, code in `services/coach/coach.py`.
- **Mini challenge:** Open Source — the repository is public under Apache-2.0,
  and `packages/rep-engine` is a separately installable package
  (`reproom-rep-engine`) with a standard-library-only core.

Understanding of the rules: one track prize and one mini-challenge prize per
project, so entering both mini challenges is for coverage, not for stacking.

---

## 4. Product feedback (required field)

**What I used it for.** The Vega Developer Tools for the whole build loop:
`vega project generate`, `vega build`, `npx react-native build-vega`,
`vega virtual-device start`, `vega run-app`, and `vega device` for install,
launch, running-apps, `run-cmd` and port forwarding. React Native on Vega via
`@amazon-devices/react-native-kepler` 4.0 with RN 0.83 for the app. Amazon
Bedrock for the coaching sentence.

**What worked well.** Installing the SDK and booting the virtual device were one
command each and the VVD is fast — roughly 30 seconds to "Virtual device ready"
on Apple Silicon, and smooth enough to develop against all evening. `vega build`
validating the manifest and printing `manifest validation found 0 errors` plus an
actionable note about the missing icon is the right shape for a build tool. The
`helloWorld` template was genuinely a working starting point, and
`TVFocusGuideView` / `hasTVPreferredFocus` behaved as documented, which is more
than I can say for most TV SDKs. React Native needed no shim to run plain
components on Vega.

**What needs work.** Ten entries with severity, reproduction steps and a
suggested fix are in `docs/friction-log.md`. The three that cost the most:

1. **A project in a folder whose name contains a space cannot be built.** The
   Kepler manifest builder interpolates the project path into a shell command
   unquoted, so the bundle step dies with `/bin/sh: /Volumes/.../Github: is a
   directory`. `vega build` succeeds first, which produces a plausible-looking
   package with no app inside. I moved my project to a space-free path before I
   understood that was the cause. Fix: pass an argument array instead of a shell
   string, and add a whitespace preflight to `vega project doctor`.
2. **The virtual device has no screen capture and no key injection.** `screencap`
   and `input` are both absent from the device shell, so I could not screenshot
   the app from a script and could not press a D-pad button from a script. For a
   competition judged on a demo video, and for anyone wanting UI tests in CI,
   this is the biggest gap versus the Android emulator. I ended up proving the
   app ran by watching my own API's access log for the health probe the app
   issues.
3. **`--forward true` is the direction you almost never want.** Making an app on
   the emulator reach a service on the host needs `--forward false`, and the help
   text's examples wrap in a way that makes both readings look plausible.
   `--direction device-to-host|host-to-device` would remove the guesswork.

Also: the CLI installer aborts SDK setup when stdin is not a terminal while still
exiting 0; `vega project generate --outputDir` writes the project *into* the
directory rather than into a subdirectory named after it; project names reject
hyphens; `build/.../undefined/...` appears in package paths; and the template's
`metro.config.js` ships with git-diff `+` markers in its header comment.

**How onboarding felt.** The docs got me from nothing to a running app on the
emulator in one evening, which is the correct outcome for a first-time device-SDK
experience. The friction was concentrated in places the docs could not be blamed
for — the space-in-path failure and the port-forward direction — and in the fact
that the two things I most wanted to automate (screenshot, key press) have no
CLI surface.

**Would I build with it again.** Yes, for a TV app, and I would budget for the
path-name constraint up front and for hand-driven UI testing. The platform is in
open beta and it behaves like it: the shape is right and the edges are sharp.

**AWS services used.** Amazon Bedrock, `bedrock-runtime.converse()` for the
coaching cue and `bedrock:ListInferenceProfiles` to discover which Anthropic
profile the account will actually serve, since availability is per account and
region and cross-region inference profiles have their own identifiers. Design
note: Bedrock is deliberately outside the counting path — a rep count has to be
reproducible for the benchmark to mean anything — and every cue carries its
provenance on screen, with a deterministic rule-based fallback labelled as such
when the model is unreachable.

`[[If item 2 in §1 is done, add the measured model ID, the real latency of a cue
call, and the region. If it is not done, keep the sentence above and say in the
video that the coach is running on its rule-based fallback.]]`

---

## 5. Open Source mini challenge (required field)

- **Repo URL:** `[[https://github.com/USERNAME/RepRoom]]`
- **GitHub username:** `[[soumwadeepguha]]`
- **License:** Apache-2.0 (`LICENSE` at the repo root).
- **What I did:** RepRoom is published as a new open-source project for this
  hackathon. Inside it, `packages/rep-engine` is separately packaged as
  `reproom-rep-engine` — a dependency-free library that counts repetitions and
  grades exercise form from pose landmarks, with an optional MediaPipe bridge
  under a `detect` extra.
- **How it works:** `reproom.geometry` computes joint angles from 33-point
  landmarks; `reproom.exercises` declares each movement's arc thresholds and its
  form checks; `reproom.engine` is a hysteresis state machine that turns a stream
  of poses into counted reps, discards, abandoned arcs and per-rep check results.
  The core imports nothing outside the standard library, so it can be embedded in
  a server, an edge device or a test fixture without a vision runtime.
- **Why it matters:** rep counting is usually shipped as a black box that returns
  a number. This one reports what it could not measure, and it keeps that
  distinction all the way to the screen — a check the camera angle cannot support
  is excluded from the quality score rather than passing by default. Anyone
  building a camera-based movement feature inherits that behaviour and the 52
  tests that pin it.
- **Contribution URL (optional, stronger claim):** `[[not filed — see note
  below]]`

**Note on the optional line.** The mini challenge accepts either a new
open-source project *or* a contribution. The new project is done. A PR is also
cheap here: `AmazonAppDev/react-native-multi-tv-app-sample` and
`AmazonAppDev/vega-video-sample` are the two official samples, and the
`metro.config.js` diff markers plus the space-in-path failure are both small,
real, upstream-fixable defects. Filing one PR before the deadline would make the
Open Source entry unambiguous rather than dependent on my own repo being noticed.

---

## 6. Demo video script — target 2:40 of 3:00

Public or unlisted on YouTube, English, no copyrighted music or third-party
footage. Record the VVD window with QuickTime (`⌘⇧5`, pick the window). Keep the
terminal beside it so the commands are visible.

| Time | Shot | Say / show |
|---|---|---|
| 0:00–0:15 | The television screen, someone squatting, the counter climbing | "RepRoom counts your reps and grades your form on the TV — no wearable, no app to hold." |
| 0:15–0:30 | Pull back: phone propped on books, TV across the room | "It has to work this way. A Fire TV app cannot open a camera — the Cube has one and third-party apps can't use it. So the room's existing devices are the sensor and the TV is the display." |
| 0:30–0:50 | Terminal: `vega virtual-device start` → "Virtual device ready", `vega run-app`, app appears | "This is a React Native app on Vega OS, built with the Vega Developer Tools and running on the Vega Virtual Device." Show `vega device running-apps` listing `com.reproom.tv.main`. |
| 0:50–1:15 | TV setup screen: keypad, enter the API address, exercise tiles, "API reachable" | "The TV opens the session and shows a code; the camera joins it." Show the capture page at `/capture?session=CODE` and press Start. |
| 1:15–1:50 | Live set, 6–8 squats, HUD updating | Narrate the count. Then deliberately do two shallow reps: "Those two didn't reach depth — they're counted as discards, not as reps." Walk out of frame mid-rep: "And that arc was abandoned, which is a different fact." |
| 1:50–2:10 | Close on the checks panel with a front-on camera | "Filmed from the front, depth is not measurable at all — so it says *not measured* and leaves it out of the score instead of showing a green tick it didn't earn." |
| 2:10–2:25 | Cue line on screen | "The coaching sentence comes from Amazon Bedrock, built only from these measurements — and when the model isn't reachable it says so and uses a rule instead." Show the label. |
| 2:25–2:40 | Terminal: `pytest` + `jest` totals; repo with license | "146 tests, Apache-2.0, and the rep engine is its own package. What I haven't measured yet is accuracy against a human count — there's no labelled corpus, so the repo says UNVERIFIED rather than guessing." |

**Do not** show a number for accuracy, latency-to-display, or model latency unless
it was actually measured by then. The closing line above is a feature: a hackathon
demo that admits what it hasn't proven is the rarest thing in the format.

---

## 7. Publishing the repo

No `gh` CLI on this machine; HTTPS push via the keychain works.

```bash
# 1. Create an empty PUBLIC repo named RepRoom at https://github.com/new
#    (do not add a README, .gitignore or license — the local ones win)
cd "/Volumes/SoumwadeepSSD/Repos/RepRoom"
git remote add origin https://github.com/[[USERNAME]]/RepRoom.git
git branch -M main
git push -u origin main
```

Because the repo is public and carries an Apache-2.0 license, the
`testing@devpost.com` and Amazon-collaborator invitations are **not needed** —
that step only applies to private repos.

Sanity-check before pushing:

```bash
git ls-files | wc -l          # ~60 files
du -sh .git                   # under 1 MB; models and node_modules are ignored
git ls-files | grep -E "\.task|node_modules|\.vpkg" || echo "clean"
```

---

## 8. Field-by-field checklist

- [ ] Text description — §2
- [ ] GitHub repo — public, Apache-2.0, pushed (§7)
- [ ] Demo video under 3 minutes, public, English (§6)
- [ ] Product feedback — §4
- [ ] Tracks entered — Fire TV; AWS Builder; Open Source — §3
- [ ] AWS Builder extra field — Bedrock `converse` + `ListInferenceProfiles`, `docs/bedrock.md` — §4 last paragraph
- [ ] Open Source extra field — repo URL, username, what/how/why — §5
- [ ] Prior-work statement — RepRoom did not exist before the submission window; the repository's first commit is 12 October 2026, inside the 31 August – 23 October period. No code was reused from any earlier project.
- [ ] Feature requests (optional) — `docs/feature-requests.md`, five items, camera access marked critical
- [ ] Friction log (optional, up to 10% bonus) — `docs/friction-log.md`, ten entries with severity, workaround and suggested fix
