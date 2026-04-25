"""
Command line runner for Resonance Selector 2.0.

Run from the project root with:
    python -m src.main                                                  # default: High-Energy Pop, balanced
    python -m src.main --profile chill_lofi                            # specific profile
    python -m src.main --all                                            # all profiles in sequence
    python -m src.main --mode genre-first                               # genre-first scoring mode
    python -m src.main --profile chill_lofi --mode mood-first          # profile + mode combined
    python -m src.main --all --mode energy-focused                      # all profiles, energy-focused mode
    python -m src.main --diversity                                      # enable diversity penalty
    python -m src.main --all --diversity --mode genre-first             # all profiles with diversity
    python -m src.main --explain-harness                                # print self-critique report under each table
    python -m src.main --no-harness                                     # legacy path: bypass guardrails + fallback
    python -m src.main --rag --profile chill_lofi                       # RAG-enriched explanations (requires GEMINI_API_KEY)
    python -m src.main --agent --profile conflicting_moods              # LLM planning agent on a low-confidence profile
    python -m src.main --help                                           # list available profiles and modes
"""

import argparse

try:
    from rich.console import Console as _Console
    from rich.table import Table as _Table
    from rich import box as _box
    _RICH_CONSOLE = _Console()
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


def _say(text: str = "", *, style: str = "") -> None:
    """Print a line through rich (with optional style) when available, else plain.

    `markup=False` keeps literal brackets in messages like '[ERROR]' from being
    parsed as rich markup tags. Styling is applied via the `style` kwarg instead.
    """
    if _HAS_RICH:
        _RICH_CONSOLE.print(text, style=style or None, markup=False)
    else:
        print(text)

from src.recommender import load_songs, recommend_songs, SCORING_MODES
from src.harness import recommend_with_harness, HarnessReport, HarnessError
from src.harness.logging_utils import write_run_log
from src.rag.enricher import list_personas as _list_personas
from src.agent import agentic_recommend, AgentTrace


PROFILES = {
    "high_energy_pop": {
        "label": "High-Energy Pop",
        "genre": "pop",
        "mood": "happy",
        "energy": 0.80,
        "likes_acoustic": False,
        "target_valence": 0.82,
        "target_tempo": 120,
        "target_danceability": 0.80,
        "target_popularity": 85,
        "preferred_decade": 2020,
        "favorite_detailed_mood": "euphoric",
        "target_instrumentalness": 0.05,
        "preferred_language": "english",
    },
    "chill_lofi": {
        "label": "Chill Lofi",
        "genre": "lofi",
        "mood": "chill",
        "energy": 0.30,
        "likes_acoustic": True,
        "target_valence": 0.45,
        "target_tempo": 75,
        "target_danceability": 0.35,
        "target_popularity": 60,
        "preferred_decade": 2020,
        "favorite_detailed_mood": "peaceful",
        "target_instrumentalness": 0.80,
        "preferred_language": "instrumental",
    },
    "deep_intense_rock": {
        "label": "Deep Intense Rock",
        "genre": "rock",
        "mood": "intense",
        "energy": 0.92,
        "likes_acoustic": False,
        "target_valence": 0.35,
        "target_tempo": 160,
        "target_danceability": 0.50,
        "target_popularity": 65,
        "preferred_decade": 2010,
        "favorite_detailed_mood": "aggressive",
        "target_instrumentalness": 0.08,
        "preferred_language": "english",
    },
    "conflicting_moods": {
        "label": "Conflicting Moods (Edge Case)",
        "genre": "ambient",
        "mood": "sad",      # mood not in dataset — tests graceful degradation
        "energy": 0.90,     # high energy + sad = contradictory combination
        "likes_acoustic": True,
        "target_valence": 0.20,
        "target_tempo": 140,
        "target_danceability": 0.60,
        "target_popularity": 75,
        "preferred_decade": 2010,
        "favorite_detailed_mood": "romantic",
        "target_instrumentalness": 0.30,
        "preferred_language": "english",
    },
    "focused_jazz": {
        "label": "Focused Jazz",
        "genre": "jazz",
        "mood": "focused",
        "energy": 0.45,
        "likes_acoustic": True,
        "target_valence": 0.55,
        "target_tempo": 95,
        "target_danceability": 0.42,
        "target_popularity": 55,
        "preferred_decade": 2000,
        "favorite_detailed_mood": "nostalgic",
        "target_instrumentalness": 0.50,
        "preferred_language": "english",
    },
}


def display_table(recommendations: list, report: HarnessReport | None = None) -> None:
    """Render recommendations as a color-coded table with per-song scoring reasons.

    If a HarnessReport is provided and a fallback was triggered, a yellow note is
    printed above the table summarizing how the system adjusted its strategy.
    """
    if _HAS_RICH:
        if report is not None and report.fallback_triggered:
            note_lines = [
                f"[bold yellow]Self-critique fallback triggered.[/bold yellow]",
                f"  Initial confidence: {report.confidence_initial:.2f} (threshold {report.confidence_threshold:.2f})",
                f"  Final confidence:   {report.confidence_final:.2f}",
                f"  Final strategy:     mode='{report.final_mode}', diversity={report.final_diversity}",
            ]
            if report.relaxed_preferences:
                note_lines.append(
                    f"  Relaxed:            {', '.join(report.relaxed_preferences)}"
                )
            for line in note_lines:
                _RICH_CONSOLE.print(line)
            _RICH_CONSOLE.print()

        table = _Table(box=_box.ROUNDED, show_lines=True, highlight=True)
        table.add_column("#",             style="bold cyan",  justify="center", width=3)
        table.add_column("Title",         style="bold white")
        table.add_column("Artist",        style="magenta")
        table.add_column("Genre",         style="yellow")
        table.add_column("Score",         justify="right", width=7)
        table.add_column("Why (Reasons)", overflow="fold")

        for rank, (song, score, explanation) in enumerate(recommendations, start=1):
            if score >= 10:
                score_str = f"[bold green]{score:.2f}[/bold green]"
            elif score >= 5:
                score_str = f"[yellow]{score:.2f}[/yellow]"
            else:
                score_str = f"[red]{score:.2f}[/red]"

            colored_reasons = []
            for reason in explanation.split(" | "):
                if "penalty" in reason:
                    colored_reasons.append(f"[dim red]{reason}[/dim red]")
                elif "match" in reason:
                    colored_reasons.append(f"[green]{reason}[/green]")
                elif "closeness" in reason or "fit" in reason:
                    colored_reasons.append(f"[cyan]{reason}[/cyan]")
                else:
                    colored_reasons.append(reason)

            row_style = "bold" if rank == 1 else ""
            table.add_row(
                str(rank),
                song["title"],
                song["artist"],
                song["genre"],
                score_str,
                "\n".join(colored_reasons),
                style=row_style,
            )

        _RICH_CONSOLE.print(table)

    else:
        if report is not None and report.fallback_triggered:
            print(f"[Self-critique fallback triggered] "
                  f"conf {report.confidence_initial:.2f} -> {report.confidence_final:.2f}, "
                  f"final mode='{report.final_mode}', diversity={report.final_diversity}")
            if report.relaxed_preferences:
                print(f"  Relaxed: {', '.join(report.relaxed_preferences)}")

        for rank, (song, score, explanation) in enumerate(recommendations, start=1):
            print(f"{rank}. {song['title']} by {song['artist']}  [Score: {score:.2f}]")
            reasons = "\n   ".join(explanation.split(" | "))
            print(f"   Because:\n   {reasons}")
            print()


def print_harness_report(report: HarnessReport) -> None:
    """Print the full HarnessReport detail (for --explain-harness)."""
    if _HAS_RICH:
        _RICH_CONSOLE.print()
        _RICH_CONSOLE.print(f"[bold]Harness report — {report.profile_label}[/bold]")
        _RICH_CONSOLE.print(f"  initial:  mode='{report.initial_mode}', diversity={report.initial_diversity}, conf={report.confidence_initial:.3f}")
        _RICH_CONSOLE.print(f"  final:    mode='{report.final_mode}', diversity={report.final_diversity}, conf={report.confidence_final:.3f}")
        _RICH_CONSOLE.print(f"  threshold: {report.confidence_threshold:.2f}")
        _RICH_CONSOLE.print(f"  fallback triggered: {report.fallback_triggered}")
        if report.relaxed_preferences:
            _RICH_CONSOLE.print(f"  relaxed preferences: {', '.join(report.relaxed_preferences)}")
        _RICH_CONSOLE.print("  rungs attempted:")
        for r in report.rungs_attempted:
            _RICH_CONSOLE.print(f"    - {r}")
        if report.flags:
            _RICH_CONSOLE.print("  flags:")
            for f in report.flags:
                _RICH_CONSOLE.print(f"    - [yellow]{f}[/yellow]")
        if report.warnings:
            _RICH_CONSOLE.print("  warnings:")
            for w in report.warnings:
                _RICH_CONSOLE.print(f"    - [dim]{w}[/dim]")
    else:
        print(f"\nHarness report — {report.profile_label}")
        print(f"  initial: mode='{report.initial_mode}', conf={report.confidence_initial:.3f}")
        print(f"  final:   mode='{report.final_mode}', conf={report.confidence_final:.3f}")
        print(f"  fallback triggered: {report.fallback_triggered}")
        for r in report.rungs_attempted:
            print(f"    - {r}")


def print_agent_trace(trace: AgentTrace) -> None:
    """Render the AgentTrace step-by-step so the planning chain is visible."""
    if _HAS_RICH:
        _RICH_CONSOLE.print()
        _RICH_CONSOLE.print(
            f"[bold magenta]Agent planning trace -- {trace.profile_label}[/bold magenta]"
        )
        _RICH_CONSOLE.print(
            f"  initial: mode='{trace.initial_mode}', diversity={trace.initial_diversity}, "
            f"conf={trace.initial_confidence:.3f}"
        )
        _RICH_CONSOLE.print(
            f"  final:   mode='{trace.final_mode}', diversity={trace.final_diversity}, "
            f"conf={trace.final_confidence:.3f}"
        )
        _RICH_CONSOLE.print(f"  terminated: [bold]{trace.terminated_reason}[/bold]")
        if trace.relaxed_preferences:
            _RICH_CONSOLE.print(f"  relaxed: {', '.join(trace.relaxed_preferences)}")
        _RICH_CONSOLE.print("  steps:")
        for s in trace.steps:
            color = "red" if s.error else "cyan"
            _RICH_CONSOLE.print(
                f"    [{color}]step {s.step_num}[/{color}] tool=[bold]{s.tool_name}[/bold] "
                f"args={s.tool_args} -> conf={s.confidence_after:.3f}"
            )
            if s.reasoning:
                _RICH_CONSOLE.print(f"      reasoning: [italic]{s.reasoning}[/italic]")
            if s.observation:
                first_line = s.observation.split("\n")[0]
                _RICH_CONSOLE.print(f"      observation: [dim]{first_line}[/dim]")
        if trace.warnings:
            _RICH_CONSOLE.print("  warnings:")
            for w in trace.warnings:
                _RICH_CONSOLE.print(f"    - [dim]{w}[/dim]")
    else:
        print(f"\nAgent planning trace -- {trace.profile_label}")
        print(f"  initial conf={trace.initial_confidence:.3f}; "
              f"final conf={trace.final_confidence:.3f}; "
              f"terminated={trace.terminated_reason}")
        for s in trace.steps:
            print(f"  step {s.step_num}: tool={s.tool_name} args={s.tool_args} "
                  f"-> conf={s.confidence_after:.3f}")
            if s.reasoning:
                print(f"    reasoning: {s.reasoning}")


def run_profile(
    user_prefs: dict,
    songs: list,
    mode: str = "balanced",
    diversity: bool = False,
    use_harness: bool = True,
    explain_harness: bool = False,
    use_rag: bool = False,
    persona: str = "default",
    use_agent: bool = False,
) -> None:
    """Print top-5 recommendations for a single user profile."""
    label = user_prefs.get("label", "Unknown Profile")
    diversity_label = "  [diversity ON]" if diversity else ""
    if use_agent:
        harness_label = "  [AGENT MODE]"
    elif not use_harness:
        harness_label = "  [HARNESS BYPASSED]"
    else:
        harness_label = ""
    _say(f"\n{'=' * 50}", style="cyan")
    _say(f"  Profile: {label}  |  Mode: {mode}{diversity_label}{harness_label}", style="bold")
    _say(f"{'=' * 50}", style="cyan")

    report = None
    trace: AgentTrace | None = None
    if use_agent:
        try:
            recommendations, trace = agentic_recommend(
                user_prefs, songs, k=5, mode=mode, diversity=diversity
            )
        except HarnessError as exc:
            _say(f"[ERROR] agent rejected this run: {exc}", style="bold red")
            return
        except RuntimeError as exc:
            _say(f"[ERROR] agent could not start: {exc}", style="bold red")
            return
    elif use_harness:
        try:
            recommendations, report = recommend_with_harness(
                user_prefs, songs, k=5, mode=mode, diversity=diversity
            )
        except HarnessError as exc:
            _say(f"[ERROR] harness rejected this run: {exc}", style="bold red")
            return
        write_run_log(report, recommendations)
    else:
        recommendations = recommend_songs(user_prefs, songs, k=5, mode=mode, diversity=diversity)

    if use_rag and recommendations:
        try:
            from src.rag.enricher import enrich_recommendations
            recommendations = enrich_recommendations(
                user_prefs, recommendations, persona=persona
            )
        except Exception as exc:
            _say(f"[RAG] enrichment failed ({exc}); falling back to deterministic explanations.", style="yellow")

    _say("\nTop recommendations:\n", style="bold")
    display_table(recommendations, report=report)

    if explain_harness and report is not None:
        print_harness_report(report)
    if trace is not None:
        print_agent_trace(trace)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resonance Selector 2.0 — music recommender with self-critique harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available profiles:\n  " + "\n  ".join(PROFILES.keys()) +
            "\n\nAvailable modes:\n  " + "\n  ".join(SCORING_MODES.keys())
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--profile",
        choices=list(PROFILES.keys()),
        metavar="PROFILE",
        help=f"Profile to run. Choices: {', '.join(PROFILES.keys())}",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run all profiles in sequence",
    )
    parser.add_argument(
        "--mode",
        choices=list(SCORING_MODES.keys()),
        default="balanced",
        metavar="MODE",
        help=f"Scoring mode. Choices: {', '.join(SCORING_MODES.keys())} (default: balanced)",
    )
    parser.add_argument(
        "--diversity",
        action="store_true",
        help="Apply diversity penalty: reduce scores for songs whose artist or genre is already in the top results.",
    )
    parser.add_argument(
        "--no-harness",
        action="store_true",
        help="Bypass the reliability harness and self-critique loop. Useful for direct A/B comparison demos.",
    )
    parser.add_argument(
        "--explain-harness",
        action="store_true",
        help="Print the full HarnessReport (rung trace, flags, warnings) under each profile's table.",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        help="Enrich explanations with RAG-grounded natural language paragraphs (requires GEMINI_API_KEY in .env).",
    )
    parser.add_argument(
        "--persona",
        choices=_list_personas(),
        default="default",
        metavar="PERSONA",
        help=(
            f"RAG voice persona. Choices: {', '.join(_list_personas())} "
            "(default: default). Each persona constrains tone, vocabulary, "
            "and focus area. Only takes effect with --rag."
        ),
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help=(
            "Use the LLM planning agent instead of the deterministic fallback "
            "ladder. The agent picks repair tools (try_mode, enable_diversity, "
            "drop_preference, inspect_catalog, report_unfixable) one step at a "
            "time and prints its reasoning. Requires GEMINI_API_KEY."
        ),
    )
    args = parser.parse_args()
    if args.agent and args.no_harness:
        parser.error("--agent and --no-harness are mutually exclusive")

    songs = load_songs("data/songs.csv")

    if args.all:
        profiles_to_run = list(PROFILES.values())
    elif args.profile:
        profiles_to_run = [PROFILES[args.profile]]
    else:
        profiles_to_run = [PROFILES["high_energy_pop"]]

    for user_prefs in profiles_to_run:
        run_profile(
            user_prefs,
            songs,
            mode=args.mode,
            diversity=args.diversity,
            use_harness=not args.no_harness,
            explain_harness=args.explain_harness,
            use_rag=args.rag,
            persona=args.persona,
            use_agent=args.agent,
        )


if __name__ == "__main__":
    main()
