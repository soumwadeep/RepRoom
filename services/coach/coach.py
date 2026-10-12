"""Coaching cues: Amazon Bedrock when it is reachable, deterministic rules when
it is not, and never a sentence about which one happened.

The design constraint is that a cue is allowed to be wrong but not allowed to be
invented. Everything the model is given is a measured number from the session
engine, and the prompt forbids introducing figures that were not supplied. When
there are no credentials, no model access, a throttle or a timeout, the caller
gets a rule-based line instead and `source` says `rules` -- the television
renders that label, so a fallback is never mistaken for generative coaching.

Model selection is discovered at runtime rather than hardcoded. Bedrock model
availability is per account and per region, cross-region inference profiles have
their own identifiers (`us.anthropic....`), and access has to be requested in the
console before a call will succeed. Guessing an ID produces a 400 that looks like
a code bug; asking the account what it has enabled produces a truthful answer.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_MAX_TOKENS = 160
CUE_CACHE_VERSION = 1

#: Preferred families, most capable first. Matched against what the account has
#: actually enabled, so an entry here is a preference and not an assumption.
PREFERRED_FAMILIES: Sequence[str] = (
    "anthropic.claude-sonnet",
    "anthropic.claude-haiku",
    "anthropic.claude-opus",
)

SYSTEM_PROMPT = (
    "You are the on-screen coach in a computer-vision workout app running on a "
    "television. You are given measurements from a pose-estimation engine about "
    "the repetitions the person just performed. Reply with ONE short sentence of "
    "coaching, at most 140 characters, in second person, naming the single most "
    "consequential issue and the concrete correction. Rules you must not break: "
    "use only the numbers and checks present in the input; never invent a metric, "
    "a body-weight, a rep count or a range that was not given; if the input says a "
    "check was not measurable, do not comment on it; if everything passed, say what "
    "to hold onto rather than inventing a fault; no markdown, no emoji, no preamble."
)


@dataclass
class Cue:
    """A coaching line plus the provenance the UI has to display."""

    text: str
    source: str  # 'bedrock' | 'rules'
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    reason: str = ""
    rep_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["label"] = "Bedrock" if self.source == "bedrock" else "built-in rules"
        return payload


@dataclass
class Discovery:
    """What this account and region will actually serve."""

    ok: bool
    model_id: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    region: Optional[str] = None
    reason: str = ""


class CoachUnavailable(Exception):
    """Raised internally when Bedrock cannot serve this call; triggers the fallback."""


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def session_facts(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a session payload to the measured facts a cue may be built from.

    Anything `not_measurable` is dropped rather than passed through as a null, so
    the model is never invited to reason about a check the camera could not run.
    """
    reps = state.get("rep_log") or []
    last = reps[-1] if reps else {}
    checks = [
        {
            "check": c.get("label"),
            "status": c.get("status"),
            "measured": c.get("measured"),
            "threshold": c.get("threshold"),
        }
        for c in (last.get("checks") or [])
        if c.get("status") in ("pass", "fail")
    ]
    return {
        "exercise": (state.get("exercise") or {}).get("name"),
        "camera_view": state.get("view"),
        "recommended_camera_view": state.get("recommended_view"),
        "camera_view_matches": state.get("view_matches"),
        "reps_counted": state.get("reps"),
        "reps_discarded": state.get("no_reps"),
        "arcs_abandoned": state.get("abandoned_arcs"),
        "cadence_reps_per_min": state.get("cadence_upm"),
        "mean_tempo_ms": state.get("mean_tempo_ms"),
        "mean_form_quality": state.get("mean_quality"),
        "checks_not_measurable": sum(
            1
            for r in reps
            for c in (r.get("checks") or [])
            if c.get("status") == "not_measurable"
        ),
        "last_rep_checks": checks,
        "weakest_check": state.get("lowest_check"),
    }


def build_messages(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The Converse API message list for one cue request."""
    facts = session_facts(state)
    payload = json.dumps(facts, separators=(",", ":"), default=str)
    return [
        {"role": "system", "content": [{"text": SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "Measurements from the engine, JSON:\n"
                        + payload
                        + "\nGive the one-sentence correction now."
                    )
                }
            ],
        },
    ]


def rules_cue(state: Dict[str, Any]) -> str:
    """A deterministic line from the same facts, with no model in the loop.

    This is not a placeholder. It is the behaviour of the product when there is
    no network, and it is deliberately the thing a viewer can check by hand.
    """
    facts = session_facts(state)
    reps = facts["reps_counted"] or 0
    failed = [c["check"] for c in facts["last_rep_checks"] if c["status"] == "fail"]

    if reps == 0:
        if facts["camera_view_matches"] is False and facts["recommended_camera_view"]:
            return (
                f"Move the camera to a {facts['recommended_camera_view']} view -- "
                "the checks for this exercise cannot be measured from the current angle."
            )
        return "Keep moving through the full range so the first rep can be counted."
    if failed:
        priority = next(
            (f for f in failed if f in ("Depth", "Body line", "Lockout overhead")),
            failed[0],
        )
        return f"{priority} is the one to fix: slow the lowering phase and stop until the target is met."
    if (facts["mean_form_quality"] or 1) >= 0.999:
        return f"Hold that: {reps} clean reps with every measurable check met."
    return f"Form slipped on {reps} counted reps -- keep the tempo you had at the start."


def rep_key(state: Dict[str, Any]) -> str:
    """Identity of the situation a cue was written for, used to cache."""
    facts = session_facts(state)
    failed = ",".join(sorted(c["check"] or "" for c in facts["last_rep_checks"] if c["status"] == "fail"))
    return f"v{CUE_CACHE_VERSION}:{facts['exercise']}:{facts['reps_counted']}:{failed}"


def discover(region: Optional[str] = None, control_client: Any = None) -> Discovery:
    """Ask this account which Anthropic model it will actually serve.

    Two shapes have to be handled, because Amazon changed the first one in the
    lifetime of this project. Cross-region inference profiles are the answer in
    regions where a provider model is served from elsewhere; in regions where the
    model is offered directly, the account may have no profile at all but still be
    entitled to the foundation model. Guessing either way produces a 400 that reads
    like a bug in the caller, so both are asked.
    """
    region = region or _env("AWS_REGION") or _env("AWS_DEFAULT_REGION") or _env("REPROOM_AWS_REGION")
    if not region:
        return Discovery(ok=False, reason="no AWS region configured (set AWS_REGION)")
    if control_client is None:
        try:
            import boto3

            control_client = boto3.client("bedrock", region_name=region)
        except Exception as exc:  # missing boto3, no credentials, bad config
            return Discovery(ok=False, reason=f"bedrock control plane unavailable: {exc}", region=region)

    profiles_error: Optional[str] = None
    try:
        profiles = (control_client.list_inference_profiles(maxResults=100) or {}).get(
            "inferenceProfileSummaryList", []
        )
    except Exception as exc:
        profiles = []
        profiles_error = _brief(exc)

    enabled = [(p.get("inferenceProfileId") or "", p.get("models") or []) for p in profiles]
    candidates = [pid for pid, models in enabled if _is_anthropic(pid, models)]
    if candidates:
        preferred = next(
            (
                c
                for family in PREFERRED_FAMILIES
                for c in candidates
                if family in c and not c.startswith("global.")
            ),
            candidates[0],
        )
        return Discovery(ok=True, model_id=preferred, candidates=candidates, region=region)

    # No profile: the account may still be entitled to the model directly.
    direct = discover_foundation_models(region, control_client)
    if direct.ok or direct.reason:
        return direct
    return Discovery(
        ok=False,
        region=region,
        candidates=[],
        reason=(
            "no Anthropic inference profile and no Anthropic foundation model "
            "reported; "
            + (profiles_error and f"profile listing failed: {profiles_error}; " or "")
            + "submit the one-time Anthropic use-case form in the Bedrock console"
        ),
    )


def discover_foundation_models(region: str, control_client: Any) -> Discovery:
    """Check direct foundation-model entitlement, and its agreement status.

    Anthropic models need a first-time-use form per account or management account.
    Until that clears, the status is ``PENDING`` and every invoke returns
    ``AccessDeniedException`` -- so the status is reported rather than assumed,
    and a pending agreement is told apart from an absent one.
    """
    try:
        listing = control_client.list_foundation_models()
    except Exception as exc:
        return Discovery(ok=False, region=region, reason=f"list_foundation_models failed: {_brief(exc)}")

    anthropic = [
        m.get("modelId")
        for m in (listing or {}).get("modelSummaries", [])
        if "anthropic" in str(m.get("modelArn", "")).lower()
    ]
    anthropic = [m for m in anthropic if m]
    if not anthropic:
        return Discovery(ok=False, region=region, reason="no Anthropic model offered in this region")

    ordered = sorted(
        anthropic,
        key=lambda mid: next((i for i, f in enumerate(PREFERRED_FAMILIES) if f in mid), len(PREFERRED_FAMILIES)),
    )
    statuses: Dict[str, str] = {}
    for model_id in ordered:
        try:
            availability = control_client.get_foundation_model_availability(modelId=model_id)
        except Exception as exc:
            statuses[model_id] = f"error: {_brief(exc)}"
            continue
        status = ((availability or {}).get("agreementAvailability") or {}).get("status")
        statuses[model_id] = str(status)
        if status == "AVAILABLE":
            return Discovery(ok=True, model_id=model_id, candidates=anthropic, region=region)

    pending = [m for m, s in statuses.items() if s == "PENDING"]
    return Discovery(
        ok=False,
        region=region,
        candidates=anthropic,
        reason=(
            "Anthropic model access is "
            + ("PENDING the one-time use-case form" if pending else "not granted")
            + f"; statuses: {json.dumps(statuses)}"
        ),
    )


def _is_anthropic(profile_id: str, models: List[Dict[str, Any]]) -> bool:
    if "anthropic" in profile_id:
        return True
    return any("anthropic" in str(m.get("modelArn", "")).lower() for m in models)


class Coach:
    """Bedrock-backed cue generator with a cached, labelled rule fallback."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        runtime_client: Any = None,
        control_client: Any = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.region = region or _env("AWS_REGION") or _env("AWS_DEFAULT_REGION") or _env("REPROOM_AWS_REGION")
        self.model_id = model_id or _env("REPROOM_BEDROCK_MODEL")
        self._runtime = runtime_client
        self._control = control_client
        self.max_tokens = max_tokens
        self._cache: Dict[str, Cue] = {}
        self._discovery: Optional[Discovery] = None

    # -- runtime client ------------------------------------------------------
    def runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        import boto3

        self._runtime = boto3.client("bedrock-runtime", region_name=self.region)
        return self._runtime

    def status(self, probe: bool = False) -> Dict[str, Any]:
        """Reported on `/health` (cheap) and `/coach/status` (probe=True).

        `/health` is polled by the television on every address change, so it must
        not make a network call to AWS. Discovery happens on the first cue, or on
        demand through the explicit probe.
        """
        if probe and not self.model_id:
            self._discovery = discover(self.region, self._control)
            if self._discovery.ok:
                self.model_id = self._discovery.model_id
        return {
            "provider": "amazon-bedrock",
            "region": self.region,
            "model_id": self.model_id,
            "ready": bool(self.model_id) and bool(self.region),
            "probed": self._discovery is not None,
            "reason": (self._discovery.reason if self._discovery else "not probed"),
            "candidates": (self._discovery.candidates if self._discovery else []),
        }

    # -- cue -----------------------------------------------------------------
    def cue(self, state: Dict[str, Any]) -> Cue:
        key = rep_key(state)
        cached = self._cache.get(key)
        if cached is not None:
            return Cue(**{**asdict(cached), "reason": cached.reason + " (cached)"})

        if not self.region:
            return self._store(key, self._fallback(state, "no AWS region configured"))
        try:
            cue = self._bedrock_cue(state, key)
        except Exception as exc:  # any Bedrock failure degrades, loudly labelled
            cue = self._fallback(state, f"bedrock unavailable: {_brief(exc)}")
        return self._store(key, cue)

    def _store(self, key: str, cue: Cue) -> Cue:
        cue.rep_key = key
        # One cue per situation, and situations are cheap: keep the last few.
        if len(self._cache) > 8:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = cue
        return cue

    def _bedrock_cue(self, state: Dict[str, Any], key: str) -> Cue:
        if not self.model_id:
            self._discovery = self._discovery or discover(self.region, self._control)
            if not self._discovery.ok:
                raise CoachUnavailable(self._discovery.reason)
            self.model_id = self._discovery.model_id

        started = time.perf_counter()
        response = self.runtime().converse(
            modelId=self.model_id,
            messages=build_messages(state),
            inferenceConfig={
                "maxTokens": self.max_tokens,
                "temperature": 0.3,
            },
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        text = _extract_text(response)
        if not text:
            raise CoachUnavailable("model returned no text")
        return Cue(
            text=text,
            source="bedrock",
            model=self.model_id,
            latency_ms=round(latency_ms, 1),
            reason="generated from measured session facts",
        )

    def _fallback(self, state: Dict[str, Any], reason: str) -> Cue:
        return Cue(text=rules_cue(state), source="rules", reason=reason)


def _extract_text(response: Dict[str, Any]) -> str:
    output = response.get("output") or {}
    parts = output.get("message", {}).get("content") or []
    chunks = [str(p.get("text", "")) for p in parts if isinstance(p, dict)]
    text = " ".join(c for c in chunks if c).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:220]


def _brief(exc: Exception) -> str:
    text = str(exc).strip().replace("\n", " ")
    return text[:180]
