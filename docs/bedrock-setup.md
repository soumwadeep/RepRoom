---
name: bedrock-setup
description: How to give this build access to Amazon Bedrock from the Mumbai region, and what to expect
---

# Giving RepRoom access to Bedrock

Region matters here. This project was developed against **ap-south-1 (Mumbai)**,
where Anthropic Claude is served through **global cross-region inference
profiles** (`global.anthropic.claude-…`) rather than a regional `us.…` profile.
A model ID copied from a US tutorial will fail in Mumbai with an error that looks
like a permissions problem.

## Step 1 -- one-time Anthropic use-case form

Model access on Bedrock is now mostly automatic, with one exception: **Anthropic
requires a first-time-use form once per account** (or once at the AWS Organization
management account). Until it clears, every invoke returns `AccessDeniedException`.

In the Bedrock console:

1. **Discover → Model catalog**, search `Claude`, open a **Sonnet** model.
   Sonnet is the right choice; Opus costs several times more for a 60-token answer.
2. Choose **Use in Playground** -- this is what surfaces the use-case form.
3. Fill it in. A personal GitHub profile is explicitly accepted where a company
   website is asked for, for individual developers and students.
4. Submit. Access is normally granted immediately; if it enters a pending state,
   invoking keeps returning `AccessDeniedException` until AWS emails you.

To check the state without waiting, ask the account directly:

```bash
aws bedrock get-foundation-model-availability \
  --model-id anthropic.claude-sonnet-4-5-… --region ap-south-1
# agreementAvailability.status: AVAILABLE | PENDING | NOT_AVAILABLE | ERROR
```

That call is what `discover()` uses when an account has no inference profile, so
a pending form shows up in `/coach/status` as `PENDING the one-time use-case
form` rather than as a mystery failure.

## Step 2 -- find the profile ID for Mumbai

**Infer → Inference profiles**, filter to Anthropic, and note the exact ID --
in ap-south-1 it will begin `global.anthropic.`.

## Step 3 -- hand it to this build. Two ways.

### Option A -- Bedrock API key (recommended)

**Discover → API keys**, create one. It is scoped to the Bedrock runtime, is
revocable in one click, and grants no IAM or account access at all.

```bash
export AWS_REGION=ap-south-1
export AWS_BEARER_TOKEN_BEDROCK='bs_…'          # the key from the console
export REPROOM_BEDROCK_MODEL='global.anthropic.claude-…'   # from step 2
```

Verified on this machine: `boto3` accepts that environment for `converse()` -- a
deliberately malformed key produced a client-side `Invalid API Key format` error,
which means the bearer path is the one being taken.

The one thing this option cannot do is discovery: an API key does not sign
control-plane calls, so `ListInferenceProfiles` is unavailable and the model ID
must be supplied. That is what `REPROOM_BEDROCK_MODEL` is for.

### Option B -- IAM user access key (full discovery)

Create an IAM user and attach `infra/bedrock-cue-policy.json`, which allows:

| Statement | Why |
|---|---|
| `bedrock:ListInferenceProfiles`, `ListFoundationModels`, `GetFoundationModelAvailability` | discovery, so the app can find a usable model without being told |
| `bedrock-runtime:InvokeModel` on `anthropic.*` and inference profiles | the cue itself. `Converse` is covered by `InvokeModel` |
| `aws-marketplace:Subscribe`, `ViewSubscriptions` | only needed the first time a model is enabled in the account |

```bash
aws configure                      # put the keys in ~/.aws/credentials yourself
```

**Do not paste an access key into the chat.** It would be stored in the
conversation transcript, which is a wider audience than an IAM secret should
ever have. Writing it to `~/.aws/credentials` with `aws configure` gives this
build the same access without that exposure.

## Step 4 -- verify

```bash
scripts/verify-bedrock.sh
```

It probes `/coach/status`, then makes one real cue call and prints the model that
answered, the latency, and the sentence. If it degrades to `built-in rules`, the
reason line says why -- that is the same path the television shows, so the script
is testing the product and not a separate code path.

## Cost

A set of 12 reps is about a dozen calls of roughly 250 input and 60 output
tokens. On Sonnet that is a fraction of a cent per set. The account still needs a
valid payment method, which Bedrock's automatic Marketplace subscription requires.
