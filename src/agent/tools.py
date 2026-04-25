"""
Repair tools available to the planning agent.

The agent's job is to choose which of these to call (and in what order) when
the harness reports low confidence. Each tool is a small, focused operation
that mirrors one rung of the deterministic ladder. The agent can also call
inspect_catalog() to gather evidence before committing to a repair, and
report_unfixable() to terminate the loop when no strategy looks promising.

Every tool returns a plain dict so the planner can serialize the result back
into the LLM's next-turn context.
"""

from typing import Any, Dict, List, Optional, Tuple

from src.recommender import recommend_songs, SCORING_MODES
from src.harness.confidence import compute_confidence


TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "try_mode",
        "description": (
            "Re-score the catalog using a different scoring mode and return "
            "the new top-5 plus a fresh confidence breakdown. Use this when "
            "the current mode under- or over-weights a feature relative to "
            "what the user actually cares about."
        ),
        "args": {
            "mode": (
                f"Required. One of: {', '.join(SCORING_MODES.keys())}. "
                "Must differ from the current_mode in state."
            ),
        },
    },
    {
        "name": "enable_diversity",
        "description": (
            "Re-rank with the diversity penalty turned on (artist -2.0, "
            "genre -1.5). Use when the top-5 is dominated by one artist or "
            "genre and the user would benefit from variety."
        ),
        "args": {},
    },
    {
        "name": "drop_preference",
        "description": (
            "Re-score after removing one categorical preference from the "
            "user profile. Use when inspect_catalog showed that the "
            "preference has zero or near-zero matches, so removing it lets "
            "the continuous-feature scoring do useful work."
        ),
        "args": {
            "field": "Required. Either 'genre' or 'mood'.",
        },
    },
    {
        "name": "inspect_catalog",
        "description": (
            "Count how many songs match a given categorical value. Use "
            "before drop_preference to confirm a preference is unmatched. "
            "Does NOT change the recommendation; pure information-gathering."
        ),
        "args": {
            "field": "Required. Either 'genre' or 'mood'.",
            "value": "Required. The string to count (e.g., 'jazz' or 'sad').",
        },
    },
    {
        "name": "report_unfixable",
        "description": (
            "Terminate the loop when no further repair is worth attempting "
            "(e.g., catalog has zero matches for the user's preferences and "
            "all repairs have been tried). Returns the best result found "
            "so far. Use this rather than spinning on hopeless cases."
        ),
        "args": {
            "reason": "Required. One short sentence explaining why repair is hopeless.",
        },
    },
]


def tool_specs_as_text() -> str:
    """Format the tool catalog as a string for inclusion in the LLM system prompt."""
    blocks = []
    for spec in TOOL_SPECS:
        block = [f"- {spec['name']}: {spec['description']}"]
        if spec["args"]:
            block.append("  args:")
            for k, v in spec["args"].items():
                block.append(f"    {k}: {v}")
        else:
            block.append("  args: (none)")
        blocks.append("\n".join(block))
    return "\n".join(blocks)


def execute_tool(
    name: str,
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run one tool. Returns a dict with at least:
      - 'observation' : human-readable summary the agent will see next turn
      - 'state_updates': dict of state-fields to merge after the call
                         (may include 'current_results', 'current_report_dict',
                          'current_confidence', 'current_mode',
                          'current_diversity', 'current_user_prefs')
    """
    if name == "try_mode":
        return _exec_try_mode(args, state)
    if name == "enable_diversity":
        return _exec_enable_diversity(args, state)
    if name == "drop_preference":
        return _exec_drop_preference(args, state)
    if name == "inspect_catalog":
        return _exec_inspect_catalog(args, state)
    if name == "report_unfixable":
        return _exec_report_unfixable(args, state)
    return {
        "observation": f"unknown tool '{name}'; valid: {[s['name'] for s in TOOL_SPECS]}",
        "state_updates": {},
        "error": True,
    }


# ----- individual tool implementations -----

def _format_top(results: List[Tuple[Dict[str, Any], float, str]], n: int = 5) -> str:
    rows = []
    for i, (song, score, _) in enumerate(results[:n], start=1):
        rows.append(f"  {i}. {song['title']} ({song['genre']}/{song['mood']}) {score:.2f}")
    return "\n".join(rows) if rows else "  (no results)"


def _run_strategy(
    user_prefs: Dict[str, Any],
    songs: List[Dict[str, Any]],
    k: int,
    mode: str,
    diversity: bool,
) -> Tuple[List[Tuple[Dict[str, Any], float, str]], Dict[str, Any]]:
    results = recommend_songs(user_prefs, songs, k=k, mode=mode, diversity=diversity)
    confidence = compute_confidence(results, user_prefs)
    return results, confidence


def _exec_try_mode(args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode")
    if mode not in SCORING_MODES:
        return {
            "observation": f"invalid mode '{mode}'; valid modes: {list(SCORING_MODES.keys())}",
            "state_updates": {},
            "error": True,
        }
    if mode == state["current_mode"]:
        return {
            "observation": f"mode '{mode}' is already current; pick a different mode",
            "state_updates": {},
            "error": True,
        }
    results, confidence = _run_strategy(
        state["current_user_prefs"], state["songs"], state["k"],
        mode=mode, diversity=state["current_diversity"],
    )
    obs = (
        f"try_mode({mode}): confidence {confidence['overall']:.2f} "
        f"(was {state['current_confidence']:.2f}). new top-5:\n{_format_top(results)}"
    )
    return {
        "observation": obs,
        "state_updates": {
            "current_results": results,
            "current_confidence": confidence["overall"],
            "current_confidence_dict": confidence,
            "current_mode": mode,
        },
    }


def _exec_enable_diversity(args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    if state["current_diversity"]:
        return {
            "observation": "diversity is already enabled; pick another tool",
            "state_updates": {},
            "error": True,
        }
    results, confidence = _run_strategy(
        state["current_user_prefs"], state["songs"], state["k"],
        mode=state["current_mode"], diversity=True,
    )
    obs = (
        f"enable_diversity(): confidence {confidence['overall']:.2f} "
        f"(was {state['current_confidence']:.2f}). new top-5:\n{_format_top(results)}"
    )
    return {
        "observation": obs,
        "state_updates": {
            "current_results": results,
            "current_confidence": confidence["overall"],
            "current_confidence_dict": confidence,
            "current_diversity": True,
        },
    }


def _exec_drop_preference(args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    field = args.get("field")
    if field not in ("genre", "mood"):
        return {
            "observation": f"invalid field '{field}'; must be 'genre' or 'mood'",
            "state_updates": {},
            "error": True,
        }
    new_prefs = dict(state["current_user_prefs"])
    if field not in new_prefs:
        return {
            "observation": f"field '{field}' is already absent from the profile; nothing to drop",
            "state_updates": {},
            "error": True,
        }
    dropped_value = new_prefs.pop(field)
    results, confidence = _run_strategy(
        new_prefs, state["songs"], state["k"],
        mode=state["current_mode"], diversity=state["current_diversity"],
    )
    obs = (
        f"drop_preference({field}={dropped_value!r}): confidence "
        f"{confidence['overall']:.2f} (was {state['current_confidence']:.2f}). "
        f"new top-5:\n{_format_top(results)}"
    )
    return {
        "observation": obs,
        "state_updates": {
            "current_results": results,
            "current_confidence": confidence["overall"],
            "current_confidence_dict": confidence,
            "current_user_prefs": new_prefs,
            "relaxed_preferences": state.get("relaxed_preferences", []) + [field],
        },
    }


def _exec_inspect_catalog(args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    field = args.get("field")
    value = args.get("value")
    if field not in ("genre", "mood"):
        return {
            "observation": f"invalid field '{field}'; must be 'genre' or 'mood'",
            "state_updates": {},
            "error": True,
        }
    matches = sum(1 for s in state["songs"] if s.get(field) == value)
    total = len(state["songs"])
    obs = (
        f"inspect_catalog({field}={value!r}): {matches}/{total} songs match "
        f"({100 * matches / total:.0f}%)."
    )
    return {"observation": obs, "state_updates": {}}


def _exec_report_unfixable(args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    reason = args.get("reason", "no reason given")
    return {
        "observation": f"report_unfixable(reason={reason!r}): terminating loop.",
        "state_updates": {"agent_terminated": True, "termination_reason": reason},
    }
