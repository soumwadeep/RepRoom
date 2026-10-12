"""Coach tests. No AWS calls: every Bedrock interaction is a stub client.

The behaviour under test is the honesty of the provenance, not the quality of
the prose. A cue that came from a rule must be labelled a rule, and a cue built
from measurements must not contain a number the engine never produced.
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "packages", "rep-engine")))

from coach import (  # noqa: E402
    Coach,
    Discovery,
    build_messages,
    discover,
    rep_key,
    rules_cue,
    session_facts,
)


def state(**overrides):
    base = {
        "exercise": {"name": "Bodyweight squat"},
        "view": "side",
        "reps": 6,
        "no_reps": 1,
        "abandoned_arcs": 0,
        "cadence_upm": 38.0,
        "mean_tempo_ms": 1500.0,
        "mean_quality": 0.83,
        "lowest_check": "Depth",
        "rep_log": [
            {
                "index": 6,
                "checks": [
                    {"label": "Depth", "status": "fail", "measured": 0.21, "threshold": 0.15},
                    {"label": "Tempo", "status": "pass", "measured": 1500, "threshold": 1100},
                    {
                        "label": "Knee tracking",
                        "status": "not_measurable",
                        "measured": None,
                        "threshold": None,
                    },
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class StubRuntime:
    def __init__(self, text="Drop deeper before you drive up.", error=None):
        self.text = text
        self.error = error
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


class StubControl:
    def __init__(self, profiles=None, error=None):
        self.profiles = profiles if profiles is not None else []
        self.error = error

    def list_inference_profiles(self, **kwargs):
        if self.error:
            raise self.error
        return {"inferenceProfileSummaryList": self.profiles}


# --------------------------------------------------------------------- facts
def test_session_facts_pass_only_measured_checks_to_the_model():
    facts = session_facts(state())
    labels = [c["check"] for c in facts["last_rep_checks"]]
    assert "Knee tracking" not in labels, "an unmeasurable check must not be offered as a fact"
    assert labels == ["Depth", "Tempo"]
    assert facts["checks_not_measurable"] == 1


def test_session_facts_survive_a_session_with_no_reps():
    facts = session_facts({"rep_log": [], "reps": 0})
    assert facts["last_rep_checks"] == []
    assert facts["reps_counted"] == 0


def test_build_messages_carries_the_rules_and_the_json():
    messages = build_messages(state())
    assert messages[0]["role"] == "system"
    assert "never invent a metric" in messages[0]["content"][0]["text"]
    user_text = messages[1]["content"][0]["text"]
    payload = json.loads(user_text.split("JSON:\n", 1)[1].rsplit("\n", 1)[0])
    assert payload["reps_counted"] == 6
    assert payload["mean_tempo_ms"] == 1500.0


# --------------------------------------------------------------------- rules
def test_rules_cue_before_the_first_rep_says_so():
    assert "full range" in rules_cue(state(reps=0, rep_log=[]))


def test_rules_cue_names_the_failing_check():
    line = rules_cue(state())
    assert "Depth" in line


def test_rules_cue_celebrates_a_clean_set_without_inventing_a_fault():
    clean = state(
        reps=12,
        no_reps=0,
        mean_quality=1.0,
        lowest_check=None,
        rep_log=[{"index": 12, "checks": [{"label": "Depth", "status": "pass", "measured": 0.05, "threshold": 0.15}]}],
    )
    line = rules_cue(clean)
    assert "12 clean reps" in line
    assert "Depth" not in line


def test_rules_cue_calls_out_a_camera_that_cannot_see_the_movement():
    line = rules_cue(state(reps=0, rep_log=[], view="front", recommended_view="side", view_matches=False))
    assert "side view" in line
    assert "cannot be measured" in line


def test_rules_cue_does_not_blame_the_camera_when_it_is_placed_correctly():
    line = rules_cue(state(reps=0, rep_log=[], view="side", recommended_view="side", view_matches=True))
    assert "full range" in line


# ------------------------------------------------------------------- coach
def test_cue_falls_back_to_rules_when_no_region_is_configured():
    coach = Coach(region=None)
    cue = coach.cue(state())
    assert cue.source == "rules"
    assert "region" in cue.reason


def test_cue_uses_bedrock_and_labels_it():
    runtime = StubRuntime("Sit until your hips pass your knees.")
    coach = Coach(region="us-east-1", model_id="us.anthropic.claude-sonnet-x", runtime_client=runtime)
    cue = coach.cue(state())
    assert cue.source == "bedrock"
    assert cue.model == "us.anthropic.claude-sonnet-x"
    assert cue.text == "Sit until your hips pass your knees."
    assert cue.latency_ms is not None
    assert runtime.calls == 1
    assert runtime.last_kwargs["inferenceConfig"]["temperature"] == 0.3


def test_a_bedrock_failure_degrades_to_rules_with_the_reason_kept():
    runtime = StubRuntime(error=RuntimeError("AccessDeniedException: not entitled to this model"))
    coach = Coach(region="us-east-1", model_id="anthropic.claude-nope", runtime_client=runtime)
    cue = coach.cue(state())
    assert cue.source == "rules"
    assert "AccessDeniedException" in cue.reason
    assert "Depth" in cue.text


def test_a_model_that_returns_nothing_is_not_passed_through():
    runtime = StubRuntime(text="")
    coach = Coach(region="us-east-1", model_id="m", runtime_client=runtime)
    cue = coach.cue(state())
    assert cue.source == "rules"
    assert "no text" in cue.reason


def test_the_same_situation_does_not_spend_two_bedrock_calls():
    runtime = StubRuntime()
    coach = Coach(region="us-east-1", model_id="m", runtime_client=runtime)
    first = coach.cue(state())
    second = coach.cue(state())
    assert runtime.calls == 1
    assert "cached" in second.reason
    assert first.text == second.text


def test_a_new_rep_is_a_new_situation_and_gets_its_own_cue():
    runtime = StubRuntime()
    coach = Coach(region="us-east-1", model_id="m", runtime_client=runtime)
    coach.cue(state())
    coach.cue(state(reps=7))
    assert runtime.calls == 2


def test_rep_key_changes_when_the_failing_check_changes():
    before = rep_key(state())
    after = rep_key(state(rep_log=[{"index": 6, "checks": [{"label": "Tempo", "status": "fail", "measured": 400, "threshold": 1100}]}]))
    assert before != after


# ---------------------------------------------------------------- discovery
def test_discovery_prefers_an_enabled_sonnet_profile():
    control = StubControl(
        profiles=[
            {"inferenceProfileId": "global.anthropic.claude-haiku", "models": []},
            {"inferenceProfileId": "us.anthropic.claude-sonnet-4", "models": []},
            {"inferenceProfileId": "us.meta.llama", "models": []},
        ]
    )
    result = discover("us-east-1", control)
    assert result.ok
    assert result.model_id == "us.anthropic.claude-sonnet-4"
    assert "us.meta.llama" not in result.candidates


def test_discovery_reports_no_access_rather_than_guessing_a_model():
    result = discover("us-east-1", StubControl(profiles=[{"inferenceProfileId": "us.meta.llama", "models": []}]))
    assert not result.ok
    assert "Model catalog" in result.reason


def test_discovery_needs_a_region():
    result = discover(None, StubControl())
    assert not result.ok
    assert "region" in result.reason


def test_discovery_surfaces_a_control_plane_failure_as_a_reason():
    result = discover("eu-west-1", StubControl(error=RuntimeError("Unable to locate credentials")))
    assert not result.ok
    assert "credentials" in result.reason


def test_discovery_result_shape_is_serialisable():
    payload = Discovery(ok=False, reason="x").__dict__
    assert payload["candidates"] == []


# ------------------------------------------------------------------- status
def test_health_status_does_not_probe_aws():
    control = StubControl(profiles=[{"inferenceProfileId": "us.anthropic.claude-sonnet-4", "models": []}])
    coach = Coach(region="us-east-1", control_client=control)
    status = coach.status(probe=False)
    assert status["ready"] is False
    assert status["probed"] is False
    assert status["reason"] == "not probed"


def test_explicit_probe_resolves_a_model_and_marks_ready():
    control = StubControl(profiles=[{"inferenceProfileId": "us.anthropic.claude-sonnet-4", "models": []}])
    coach = Coach(region="us-east-1", control_client=control)
    status = coach.status(probe=True)
    assert status["ready"] is True
    assert status["model_id"] == "us.anthropic.claude-sonnet-4"
