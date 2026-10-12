# Feature requests

Ordered by how much of a class of projects each one unlocks. Each says what it
would be used for rather than what to build, since the platform teams know their
constraints better than a hackathon entrant does.

## 1. Camera access for Fire TV apps — critical

**What:** a way for a third-party app to receive frames from the Fire TV Cube
camera, with an explicit user consent gate and a shutter indicator.

**Why it matters:** this is the constraint that decided RepRoom's architecture.
The television is the one screen in the house that is already calibrated to the
room, already renders at a distance, and already has a wide-angle camera pointed
at the person using it. A fitness form check, a sign-language captioner, a
posture reminder for a child sitting two feet from the panel, and a "who is in
the room" accessibility mode all want that camera and currently cannot have it.

So the sensor became a phone propped against a book, streaming JPEGs to a
server, with the TV polling JSON. That works, and it is honest about what it is,
but it means every one of those ideas requires the user to place a second device
before the product does anything.

**Urgency:** critical for computer-vision-on-the-TV, which the track brief lists
as a priority category. If a full camera API is not on the table, a
low-resolution, frame-rate-limited, consent-gated stream would still unlock the
category.

## 2. Screen capture and key injection for the virtual device — important

**What:** `vega device screenshot --out file.png` and a way to send remote keys
from the CLI.

**Why:** the demo video is a required deliverable and the emulator is the only
device most entrants have. Today a screenshot means capturing the whole desktop
and cropping, and there is no way to script a D-pad press at all, so UI
regressions cannot be caught by a test. Both are standard in the Android
emulator and their absence is the single biggest difference in day-to-day
developer feel between the two.

**Urgency:** important. It affects every submission's polish, not just CV apps.

## 3. A pairing primitive — important

**What:** a QR/barcode component, or a documented "second screen joins this
session" flow with a short code and a device-local display name.

**Why:** RepRoom needs a phone to join a session the TV opened, and the only
input on a television is a D-pad. So the app renders a code and an address that
a person has to type on a phone. A barcode component in the UI kit turns that
into one camera tap. This is a common shape — casting, second-screen, kiosk,
kids' profiles — and every one of them currently reinvents it.

**Urgency:** important, and cheap.

## 4. A first-party HTTP/WebSocket data hook for TV state — nice to have

**What:** a React hook in the Kepler package for polling with focus-aware
pausing, backoff and a stale flag.

**Why:** every TV app here is a thin client over some service, and the pieces I
had to write — backoff on failure, "the picture is old" signalling, not
re-rendering when the screen loses focus — are the same ones the next app will
write. RepRoom's version is tested and could be donated upstream if it is
useful.

**Urgency:** nice to have.

## 5. Manifest validation for the missing icon at submission time — nice to have

**What:** the build already reports `[package.icon] Icon is not defined. System
default will be used.` as an info.

**Why:** for a store submission that becomes a generic tile among real apps. A
warning that blocks Live App Testing, or a template icon to start from, would
make the gap visible at the moment it is cheap to fix.

**Urgency:** nice to have.
