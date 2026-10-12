# Amazon Bedrock integration

## What it does, narrowly

Bedrock has exactly one job in RepRoom: turn a set of measurements into one
sentence of coaching. It is not in the counting path, not in the form-grading
path, and no number on the screen depends on it. If the model is unreachable the
session continues to work and says so.

That boundary is deliberate. A generative model should not be the thing deciding
whether a rep counted, because that decision has to be reproducible for the
benchmark in `benchmarks/` to mean anything.

## Where it lives

| Piece | Location |
|---|---|
| Cue generation, discovery, fallback | `services/coach/coach.py` |
| `GET /session/{id}/cue` | `services/session-api/app.py` |
| `GET /coach/status`, coach block in `/health` | same |
| Polling, caching per rep-count change | `apps/fire-tv/src/sessionClient.ts` |
| Provenance label on screen | `apps/fire-tv/src/format.ts` (`coachLine`) |

The call is `bedrock-runtime.converse()` with a system prompt that forbids
introducing any figure not present in the input, temperature 0.3, 160 max tokens.
The payload it is given is produced by `session_facts()`, which **drops every
check whose status is `not_measurable`** -- the model is never handed a null and
invited to interpret it.

## Why the model ID is discovered, not written down

Bedrock model availability depends on the account, the region, and whether
access was requested in the console. Cross-region inference profiles have their
own identifiers (`us.anthropic.…`, `global.anthropic.…`) and a bare model ARN
will 400 in a region that requires a profile. Hardcoding an ID produces a failure
that looks like a bug in the caller.

So `discover()` calls `bedrock:ListInferenceProfiles`, filters to Anthropic
profiles, prefers Sonnet over Haiku over Opus and a regional profile over a
`global.` one, and reports the candidates. If nothing matches, the reason it
returns names the console step rather than raising. `REPROOM_BEDROCK_MODEL`
overrides the choice when you want a specific model.

## Setup

```bash
# 1. Credentials for the account (any one of these works)
aws configure                       # or export AWS_ACCESS_KEY_ID / _SECRET_KEY
export AWS_REGION=us-east-1         # the region you will call Bedrock in

# 2. Model access, once per account+region
#    Bedrock console -> Model catalog -> an Anthropic model -> submit the use-case form
#    Access is granted immediately after submission.

# 3. Permissions for the principal
#    bedrock:ListInferenceProfiles        (control plane, for discovery)
#    bedrock-runtime:InvokeModel          (for converse)

# 4. Ask the running service what it can see
curl -s localhost:8420/coach/status | python3 -m json.tool
```

`/coach/status` answers with `ready`, the resolved `model_id`, the candidate list,
or the reason it could not proceed -- `no AWS region configured`, `Unable to
locate credentials`, or `no Anthropic inference profile enabled in this account and
region`. `/health` reports the coach block without making any AWS call, because
the television polls it on every address change.

## Verification status

**Not yet run against a live account.** This build machine has no AWS
credentials, so the Bedrock path has been exercised only against stub clients.

What that means precisely:

| | State |
|---|---|
| Prompt construction, and that unmeasurable checks are excluded | Verified -- 22 tests in `services/coach/test_coach.py` |
| Fallback to rules when there is no region, no access, no credentials, a throttle, or an empty response | Verified, with the reason preserved in the response |
| Cue cached per (exercise, rep count, failed checks) so polling does not spend a call per poll | Verified |
| The TV labels the source of every cue it shows | Verified -- 51 app tests, including the on-screen `COACH · BUILT-IN RULES` label |
| A real `converse()` call returning a real sentence | **UNVERIFIED** until run against the account |
| Which model this account will serve | **UNVERIFIED** -- `discover()` answers this at runtime |

The rules fallback is not a mock: it is the shipped behaviour without a network,
and it is what has actually been demonstrated end to end on the emulator so far.

## Cost and latency

One cue per change in situation, not per poll. A 400 ms poll interval against a
session of 12 reps is roughly a dozen `converse` calls per set, each on the order
of a few hundred milliseconds to a second. The television keeps showing the last
cue while the next one is in flight, and hides the line entirely if the request
fails -- a stale sentence presented as current advice is the failure mode worth
avoiding here.
