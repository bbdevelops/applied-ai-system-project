"""Tests for the LLM planning agent in src.agent.planner.

These run offline by injecting a scripted Decider — no Gemini API calls.
"""

import json

import pytest

from src.agent.planner import (
    agentic_recommend,
    _parse_decision,
    CONFIDENCE_THRESHOLD,
)
from src.recommender import load_songs


@pytest.fixture(scope="module")
def full_catalog():
    return load_songs("data/songs.csv")


@pytest.fixture
def low_conf_profile():
    """Same conflicting profile that drives the deterministic ladder past rung 0."""
    return {
        "label": "Conflicting",
        "genre": "ambient",
        "mood": "sad",  # not in dataset
        "energy": 0.9,
        "target_valence": 0.2,
        "likes_acoustic": True,
    }


def _scripted_decider(decisions):
    """Return a Decider that yields each scripted decision in order, then raises."""
    iterator = iter(decisions)

    def call(_system, _user):
        try:
            d = next(iterator)
        except StopIteration:
            raise AssertionError("decider called more times than scripted")
        return d if isinstance(d, str) else json.dumps(d)

    return call


def test_high_confidence_short_circuits(full_catalog, basic_user_prefs):
    """If baseline confidence already clears threshold, agent must not call decider."""
    def never_call(_s, _u):
        raise AssertionError("decider should not be called when baseline clears threshold")
    results, trace = agentic_recommend(
        basic_user_prefs, full_catalog, k=5, decider=never_call
    )
    assert len(results) == 5
    assert trace.terminated_reason == "confidence_met"
    assert len(trace.steps) == 1
    assert trace.steps[0].tool_name == "baseline"


def test_planning_loop_records_each_tool_call(full_catalog, low_conf_profile):
    """Scripted try_mode then enable_diversity then drop_preference should each show up."""
    decisions = [
        {"reasoning": "try a different scoring mode first",
         "tool": "try_mode", "args": {"mode": "mood-first"}},
        {"reasoning": "now try diversity to spread artists",
         "tool": "enable_diversity", "args": {}},
        {"reasoning": "drop the unmatched mood preference",
         "tool": "drop_preference", "args": {"field": "mood"}},
        {"reasoning": "give up if still bad",
         "tool": "report_unfixable", "args": {"reason": "exhausted options"}},
    ]
    results, trace = agentic_recommend(
        low_conf_profile, full_catalog, k=5,
        decider=_scripted_decider(decisions),
    )
    assert len(results) == 5
    tool_sequence = [s.tool_name for s in trace.steps]
    assert tool_sequence[0] == "baseline"
    # at least one of the scripted tools must appear before termination
    assert "try_mode" in tool_sequence


def test_max_steps_guard_terminates_loop(full_catalog, low_conf_profile):
    """Agent that loops on inspect_catalog (no state change) must hit the max-steps cap."""
    looping = [
        {"reasoning": "just looking",
         "tool": "inspect_catalog", "args": {"field": "genre", "value": "ambient"}}
    ] * 10
    _results, trace = agentic_recommend(
        low_conf_profile, full_catalog, k=5,
        decider=_scripted_decider(looping),
        max_steps=3,
    )
    assert trace.terminated_reason == "max_steps"
    # baseline + 3 planning steps
    assert len(trace.steps) == 4


def test_report_unfixable_terminates_immediately(full_catalog, low_conf_profile):
    decisions = [
        {"reasoning": "nothing to do here",
         "tool": "report_unfixable", "args": {"reason": "catalog has no ambient/sad songs"}},
    ]
    _results, trace = agentic_recommend(
        low_conf_profile, full_catalog, k=5,
        decider=_scripted_decider(decisions),
    )
    assert trace.terminated_reason == "report_unfixable"
    assert trace.steps[-1].tool_name == "report_unfixable"


def test_malformed_json_retries_then_terminates(full_catalog, low_conf_profile):
    """First response is gibberish; second is also gibberish — terminate with error."""
    bad_decisions = ["not json at all", "still not json {{"]
    _results, trace = agentic_recommend(
        low_conf_profile, full_catalog, k=5,
        decider=_scripted_decider(bad_decisions),
    )
    assert trace.terminated_reason == "error"
    assert trace.steps[-1].error is True


def test_malformed_json_then_valid_recovers(full_catalog, low_conf_profile):
    """First response gibberish, retry produces a valid decision — loop continues."""
    decisions = [
        "garbage",
        {"reasoning": "after retry", "tool": "try_mode", "args": {"mode": "mood-first"}},
        {"reasoning": "stop", "tool": "report_unfixable", "args": {"reason": "done"}},
    ]
    _results, trace = agentic_recommend(
        low_conf_profile, full_catalog, k=5,
        decider=_scripted_decider(decisions),
    )
    tool_sequence = [s.tool_name for s in trace.steps]
    assert "try_mode" in tool_sequence
    assert trace.terminated_reason == "report_unfixable"


def test_unknown_tool_is_caught_by_validator():
    decision, err = _parse_decision('{"reasoning": "x", "tool": "make_coffee", "args": {}}')
    assert decision is None
    assert "unknown tool" in err


def test_parse_decision_strips_code_fence():
    raw = '```json\n{"reasoning": "x", "tool": "try_mode", "args": {"mode": "balanced"}}\n```'
    decision, err = _parse_decision(raw)
    assert err is None
    assert decision["tool"] == "try_mode"


def test_parse_decision_rejects_non_object_args():
    decision, err = _parse_decision('{"reasoning": "x", "tool": "try_mode", "args": "not-a-dict"}')
    assert decision is None
    assert "args" in err.lower()


def test_threshold_constant_matches_ladder():
    """Agent must use the same confidence threshold as the deterministic harness."""
    from src.harness.critique import recommend_with_harness
    import inspect
    sig = inspect.signature(recommend_with_harness)
    assert sig.parameters["confidence_threshold"].default == CONFIDENCE_THRESHOLD
