"""
LLM-driven planning agent that drives the repair tools in src.agent.tools.

This module is a parallel pathway to the deterministic ladder in
src.harness.critique. The ladder remains the default and powers the 40/40
golden regression matrix; the agent is opt-in via --agent and exists to
satisfy the "multi-step reasoning with tool-calls, planning steps, or a
decision-making chain ... intermediate steps observable" rubric line.

Public entry point: agentic_recommend(). Every loop iteration is captured
as an AgentStep so the CLI can print the agent's reasoning chain.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.harness.validators import (
    validate_user_profile,
    validate_catalog,
    validate_recommendations,
)
from src.agent.tools import (
    TOOL_SPECS,
    execute_tool,
    tool_specs_as_text,
    _run_strategy,
)


CONFIDENCE_THRESHOLD = 0.4
DEFAULT_MAX_STEPS = 6
DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass
class AgentStep:
    """One iteration of the planner loop."""
    step_num: int
    reasoning: str
    tool_name: str
    tool_args: Dict[str, Any]
    observation: str
    confidence_after: float
    error: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentTrace:
    """Full record of an agentic_recommend() call."""
    profile_label: str
    initial_mode: str
    initial_diversity: bool
    initial_confidence: float
    final_mode: str
    final_diversity: bool
    final_confidence: float
    relaxed_preferences: List[str] = field(default_factory=list)
    steps: List[AgentStep] = field(default_factory=list)
    terminated_reason: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


# A "decider" is the LLM seam: given a prompt, return raw JSON text. The real
# implementation calls Gemini; tests inject a callable that returns scripted
# decisions, so the planner can be exercised offline.
Decider = Callable[[str, str], str]


def _build_decider_prompt(
    user_prefs: Dict[str, Any],
    state: Dict[str, Any],
    history: List[AgentStep],
) -> Tuple[str, str]:
    """
    Returns (system_prompt, user_payload) for one planner turn.

    The system prompt explains the role, the JSON contract, and the tool
    catalog. The user payload carries the live state and step history.
    """
    system = (
        "You are a planning agent for a music recommender. The deterministic "
        "scorer produced a low-confidence top-5 for a user. Your job is to "
        "pick ONE tool to call next that is most likely to raise confidence "
        "above the threshold of "
        f"{CONFIDENCE_THRESHOLD}. Valid tools:\n\n"
        f"{tool_specs_as_text()}\n\n"
        "Strategy hints:\n"
        " - Before drop_preference, use inspect_catalog to confirm the "
        "preference has zero or near-zero matches in the catalog.\n"
        " - Do not repeat a tool call that already failed in history.\n"
        " - If you have tried the available repairs and confidence is still "
        "below threshold, call report_unfixable with a one-sentence reason.\n\n"
        "Output JSON only, no prose, no code fences, with this exact schema:\n"
        '  {"reasoning": "<one sentence>", "tool": "<tool_name>", '
        '"args": {<arg_name>: <arg_value>}}\n'
    )

    history_blob = []
    for s in history:
        history_blob.append(
            f"step {s.step_num}: tool={s.tool_name} args={json.dumps(s.tool_args)} "
            f"-> confidence={s.confidence_after:.2f}; observation: {s.observation}"
        )
    history_text = "\n".join(history_blob) if history_blob else "(no steps yet)"

    safe_prefs = {k: v for k, v in user_prefs.items() if k != "label"}
    user_payload = (
        "CURRENT USER PREFERENCES:\n"
        f"{json.dumps(safe_prefs, indent=2)}\n\n"
        "CURRENT STATE:\n"
        f"  mode: {state['current_mode']}\n"
        f"  diversity: {state['current_diversity']}\n"
        f"  confidence: {state['current_confidence']:.2f} "
        f"(threshold {CONFIDENCE_THRESHOLD})\n"
        f"  relaxed_preferences: {state.get('relaxed_preferences', [])}\n"
        f"  catalog_size: {len(state['songs'])}\n\n"
        "STEP HISTORY:\n"
        f"{history_text}\n\n"
        "Pick the next tool call. JSON only."
    )
    return system, user_payload


def _parse_decision(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse LLM output into (decision_dict, error_msg). One of the two is None."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return None, "could not find JSON object in agent response"
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            return None, f"JSON parse error: {exc}"

    if not isinstance(data, dict):
        return None, "agent response is not a JSON object"
    tool = data.get("tool")
    args = data.get("args", {})
    reasoning = data.get("reasoning", "")
    if not isinstance(tool, str) or not tool:
        return None, "missing or invalid 'tool' field"
    if not isinstance(args, dict):
        return None, "'args' must be an object"
    valid_tools = {spec["name"] for spec in TOOL_SPECS}
    if tool not in valid_tools:
        return None, f"unknown tool '{tool}'; valid: {sorted(valid_tools)}"
    return {"reasoning": str(reasoning), "tool": tool, "args": args}, None


def _gemini_decider(model_name: str = DEFAULT_MODEL) -> Decider:
    """Build a Decider that calls the real Gemini API. Lazy-imports the SDK."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    api_key = os.environ.get("GEMINI_API_KEY") or None
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set; copy .env.example to .env and add your key."
        )
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise RuntimeError(
            "google-genai not installed; run `pip install -r requirements.txt`."
        ) from exc

    client = genai.Client(api_key=api_key)

    def call(system_prompt: str, user_payload: str) -> str:
        response = client.models.generate_content(
            model=model_name,
            contents=user_payload,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        return response.text or ""

    return call


def agentic_recommend(
    user_prefs: Dict[str, Any],
    songs: List[Dict[str, Any]],
    k: int = 5,
    *,
    mode: str = "balanced",
    diversity: bool = False,
    max_steps: int = DEFAULT_MAX_STEPS,
    decider: Optional[Decider] = None,
) -> Tuple[List[Tuple[Dict[str, Any], float, str]], AgentTrace]:
    """
    Run the LLM planning loop and return (validated_results, AgentTrace).

    The first action is always a deterministic baseline run; if confidence
    already clears the threshold the loop short-circuits with a single step.
    Otherwise the decider is consulted up to max_steps times.
    """
    cleaned_profile, profile_warnings = validate_user_profile(user_prefs)
    cleaned_songs, catalog_warnings = validate_catalog(songs)

    label = cleaned_profile.get("label", cleaned_profile.get("genre", "unknown"))
    results, confidence = _run_strategy(cleaned_profile, cleaned_songs, k, mode, diversity)
    initial_overall = confidence["overall"]

    trace = AgentTrace(
        profile_label=str(label),
        initial_mode=mode,
        initial_diversity=diversity,
        initial_confidence=initial_overall,
        final_mode=mode,
        final_diversity=diversity,
        final_confidence=initial_overall,
        warnings=profile_warnings + catalog_warnings,
    )
    trace.steps.append(AgentStep(
        step_num=0,
        reasoning="deterministic baseline run; agent only engages if confidence is below threshold",
        tool_name="baseline",
        tool_args={"mode": mode, "diversity": diversity},
        observation=f"baseline confidence {initial_overall:.2f}",
        confidence_after=initial_overall,
    ))

    if initial_overall >= CONFIDENCE_THRESHOLD:
        trace.terminated_reason = "confidence_met"
        validated, val_warnings = validate_recommendations(results, k, len(cleaned_songs))
        trace.warnings.extend(val_warnings)
        return validated, trace

    if decider is None:
        decider = _gemini_decider()

    state: Dict[str, Any] = {
        "songs": cleaned_songs,
        "k": k,
        "current_user_prefs": dict(cleaned_profile),
        "current_mode": mode,
        "current_diversity": diversity,
        "current_results": results,
        "current_confidence": initial_overall,
        "current_confidence_dict": confidence,
        "relaxed_preferences": [],
    }
    best_results = results
    best_confidence = initial_overall

    for step_num in range(1, max_steps + 1):
        system_prompt, user_payload = _build_decider_prompt(
            cleaned_profile, state, trace.steps[1:]
        )

        decision: Optional[Dict[str, Any]] = None
        parse_error: Optional[str] = None
        for attempt in range(2):
            raw = decider(system_prompt, user_payload)
            decision, parse_error = _parse_decision(raw)
            if decision is not None:
                break
            user_payload = (
                user_payload
                + f"\n\nPREVIOUS RESPONSE WAS INVALID: {parse_error}. "
                "Output JSON only with the schema {reasoning, tool, args}."
            )
        if decision is None:
            trace.steps.append(AgentStep(
                step_num=step_num,
                reasoning="(agent response unparseable after retry)",
                tool_name="(none)",
                tool_args={},
                observation=parse_error or "unknown parse error",
                confidence_after=state["current_confidence"],
                error=True,
            ))
            trace.terminated_reason = "error"
            break

        tool_result = execute_tool(decision["tool"], decision["args"], state)
        observation = tool_result.get("observation", "")
        updates = tool_result.get("state_updates", {})
        is_error = bool(tool_result.get("error"))

        state.update(updates)
        if "current_results" in updates and updates["current_confidence"] > best_confidence:
            best_results = updates["current_results"]
            best_confidence = updates["current_confidence"]

        trace.steps.append(AgentStep(
            step_num=step_num,
            reasoning=decision["reasoning"],
            tool_name=decision["tool"],
            tool_args=decision["args"],
            observation=observation,
            confidence_after=state["current_confidence"],
            error=is_error,
        ))

        if state.get("agent_terminated"):
            trace.terminated_reason = "report_unfixable"
            break
        if state["current_confidence"] >= CONFIDENCE_THRESHOLD:
            trace.terminated_reason = "confidence_met"
            break
    else:
        trace.terminated_reason = "max_steps"

    trace.final_mode = state["current_mode"]
    trace.final_diversity = state["current_diversity"]
    trace.final_confidence = best_confidence
    trace.relaxed_preferences = list(state.get("relaxed_preferences", []))

    if best_confidence < CONFIDENCE_THRESHOLD:
        trace.warnings.append(
            f"agent loop ended below threshold; best confidence {best_confidence:.2f} "
            f"vs threshold {CONFIDENCE_THRESHOLD:.2f}"
        )

    validated, val_warnings = validate_recommendations(best_results, k, len(cleaned_songs))
    trace.warnings.extend(val_warnings)
    return validated, trace
