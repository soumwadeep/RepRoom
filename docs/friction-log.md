# Friction log

Every entry is a task that was actually attempted while building RepRoom for the
Fire TV track on macOS, in the order it was hit. Severity is how much of the
project it cost: **blocker** stopped work, **major** forced a redesign,
**minor** cost an hour, **cosmetic** cost attention.

## 1. A project in a folder with a space cannot be built

- **Task:** `npx react-native build-vega --build-type Release`
- **Steps:** generated a helloWorld project, ran `vega build` (succeeded), then
  the RN bundle step.
- **Expected:** a `.vpkg`.
- **Actual:**
  ```
  /bin/sh: /Volumes/SoumwadeepSSD/Github: is a directory
  error Unable to generate a manifest: Error: Command failed:
    .../kepler-module-manifest-builder/dist/src/cli.js build -d /Volumes/SoumwadeepSSD/Github Repos/... -p ./package.json -s
  ```
  The project directory is interpolated into a shell command without quoting, so
  the first space terminates the argument. `vega build` passes; only the JS
  bundle stage fails, which is the worse possible place for it — you get a
  plausible-looking native package with no app inside.
- **Severity:** blocker. macOS users routinely keep repos under folders with
  spaces, and the error names a directory that exists, so it reads like a
  permissions problem rather than a quoting bug.
- **Workaround:** moved the whole project to a space-free path.
- **Suggestion:** use `execFile`/`spawn` with an argument array instead of
  building a shell string. If a shell is unavoidable, quote. A one-line
  preflight — "project path contains whitespace" — would have saved an evening,
  and would be findable in a `vega project doctor` run.

## 2. The VDT installer aborts when it is not attached to a terminal

- **Task:** install the Vega Developer Tools headlessly.
- **Steps:** `curl -fsSL .../get_vvm.sh | bash` with stdin closed, as the docs'
  own command line suggests a CI system would run.
- **Expected:** the documented defaults to apply, since the installer prints
  "(press Enter to keep current)".
- **Actual:** the CLI installed fine, then
  `Error: failed to get SDK path: failed to read input: EOF` → `Vega CLI not set
  up` → `Exiting...`, and the pipeline still reported success because the exit
  code was 0. `vega sdk list-installed` then showed nothing.
- **Severity:** major. The failure is silent at the process level, and the
  recovery (`vega sdk install`) is not mentioned in the error.
- **Workaround:** ran `vega sdk install` separately, which needed no prompt.
- **Suggestion:** when `read` fails on a non-tty, take the default you already
  computed and continue; exit non-zero if you truly cannot proceed. Also print
  the recovery command in the error text.

## 3. `vega project generate --outputDir` writes into the directory, not a subdirectory

- **Task:** generate the app into `apps/fire-tv`.
- **Steps:** `vega project generate --template helloWorld --name reproomtv --outputDir .../apps`.
- **Expected:** `.../apps/reproomtv/`, matching the help text "Create a new
  application project named exampleProject in the current directory" and
  matching every other scaffolder.
- **Actual:** the project's files landed directly in `.../apps`. A second run in
  a different location would have silently overwritten the first.
- **Severity:** major for anyone scripting this. `mv` recovered it here.
- **Workaround:** moved the files into `apps/fire-tv` by hand.
- **Suggestion:** create `$outputDir/$name`, or rename the flag
  `--into`/`--dest` so it does not promise a directory layout it does not
  produce. Refuse to write into a non-empty directory unless `--force` is given.

## 4. Project names reject hyphens, so folder and project diverge

- **Task:** name the project `fire-tv`.
- **Actual:** `fire-tv is not a valid project name — Allowed characters:
  [a-zA-Z0-9]`, while npm conventions and the generated
  `@amazon-devices/<name>` package encourage kebab-case.
- **Severity:** minor.
- **Workaround:** project `reproomtv`, folder `fire-tv`.
- **Suggestion:** accept `-` and map it to the identifier form internally, the
  way every npm tooling does.

## 5. The virtual device has no screen capture and no input injection

- **Task:** prove the app rendered correctly, and drive the D-pad from a script.
- **Steps:** `vega device run-cmd --command 'screencap -p /data/local/tmp/x.png'`;
  `vda shell input keyevent 23`.
- **Actual:** `/bin/sh: screencap: command not found`, `/bin/sh: input: command
  not found`. The device shell is a minimal busybox without the two commands
  that make a TV emulator scriptable.
- **Severity:** major. A hackathon entry is judged on a demo video, and a
  screenshot is also the only cheap way to catch a layout regression. I ended up
  verifying render by watching the API access log for the app's own health
  probe, which proves execution but not pixels.
- **Workaround:** OS-level screen capture of the emulator window; the on-screen
  remote for input.
- **Suggestion:** `vega device screenshot --out path.png`, and
  `vega device send-key --key DPAD_CENTER`. Both are table stakes for Android's
  emulator and both would make Vega testable in CI.

## 6. `--forward true` is the direction you almost never want

- **Task:** let the app on the VVD reach the API on the host.
- **Steps:** `vega device start-port-forwarding --port 8420 --forward true`,
  then `wget http://127.0.0.1:8420/health` from inside the device.
- **Expected:** a response, because "forward" is the word used for
  "make a host port reachable from the device" in most developer mental models.
- **Actual:** connection refused. `--forward false` is the direction that works,
  and the help text's own examples are garbled by line wrapping so both readings
  look plausible.
- **Severity:** minor, but it cost a full debug cycle at the worst moment.
- **Workaround:** `--forward false`, and separately confirmed the device can
  also reach the host's LAN address directly.
- **Suggestion:** replace the boolean with `--direction device-to-host` /
  `host-to-device`.

## 7. Build output paths contain a literal `undefined`

- **Task:** locate the built package.
- **Actual:**
  `build/private/kepler/@amazon-devices/reproomtv/undefined/vega/aarch64/Release/...vpkg`
  — one path segment is the string `undefined`, so a version field is missing
  somewhere in the native build.
- **Severity:** cosmetic, but it makes the path awkward to script and reads like
  a bug, which is corrosive in a tool that is otherwise impressive.
- **Workaround:** used the clean `build/<arch>-release/*.vpkg` copies.
- **Suggestion:** fall back to `untagged` or omit the segment.

## 8. `Pressable` reports `pressed` but not `focused`

- **Task:** draw a focus ring, which on a television is the cursor.
- **Steps:** `style={({focused}) => ...}`, the standard React Native TV idiom.
- **Actual:** TypeScript error — `Property 'focused' does not exist on type
  'PressableStateCallbackType'` — and no runtime focus state either.
- **Severity:** minor for me, structural for the platform: every TV app has to
  hand-roll focus state, and the ones that don't will ship invisible cursors.
- **Workaround:** local `useState` driven by `onFocus`/`onBlur` in three
  components.
- **Suggestion:** add `focused` to the state callback. It costs nothing where
  there is no focus system and removes a whole class of unusable-on-a-TV UI.

## 9. `vega virtual-device status` leads with warnings

- **Task:** ask whether the emulator is running.
- **Actual:** four `WARN vvman command not found or failed` lines before the
  fallback succeeds and prints `{"running":true,...}`.
- **Severity:** cosmetic. It makes a working system look broken in logs, which
  is how people end up ignoring the first warning that matters.
- **Suggestion:** log the fallback at debug level.

## 10. The helloWorld template ships with diff markers in it

- **Task:** read `metro.config.js` in a freshly generated project.
- **Actual:**
  ```js
  /**
  + * Metro configuration
  + * https://facebook.github.io/metro/docs/configuration
   */
  ```
  The `+` characters are git-diff artefacts left in the template. It parses, so
  nothing fails — it is just the first file a newcomer opens.
- **Severity:** cosmetic.
- **Workaround:** rewrote the file.

## Outside Amazon's stack, for completeness

MediaPipe 1.1 renamed `min_pose_tracking_confidence` to `min_tracking_confidence`
and dropped `Image.data`. Both broke code written against the 0.10 docs; the
renames are not in a changelog that was easy to find. This project now has a test
that constructs the detector for real, because a stub could never catch it.

## What worked well, because the brief asked

- Installing the SDK and the virtual device was one command each and both
  actually worked the second time; the VVD boots in about 30 seconds on an M1
  and is genuinely fast enough to develop against.
- `vega device` covering install, launch, running-apps, log stream and
  `run-cmd` meant I never needed a hidden adb.
- The manifest validation output is unusually good: `manifest.toml is valid`,
  zero errors, plus an actionable info about the missing icon.
- React Native on Vega needed no shim or polyfill to run plain RN components, and
  the `TVFocusGuideView` and `hasTVPreferredFocus` behaviour matched what the
  docs claimed.
- `vega project doctor` catching OS-version compatibility is the right idea, and
  is where the preflight checks described above belong.
