"""
Command line runner for the Music Recommender Simulation.

Run from the project root with:
    python -m src.main                                                  # default: High-Energy Pop, balanced
    python -m src.main --profile chill_lofi                            # specific profile
    python -m src.main --all                                            # all profiles in sequence
    python -m src.main --mode genre-first                               # genre-first scoring mode
    python -m src.main --profile chill_lofi --mode mood-first          # profile + mode combined
    python -m src.main --all --mode energy-focused                      # all profiles, energy-focused mode
    python -m src.main --diversity                                      # enable diversity penalty
    python -m src.main --all --diversity --mode genre-first             # all profiles with diversity
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

from src.recommender import load_songs, recommend_songs, SCORING_MODES


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


def display_table(recommendations: list) -> None:
    """Render recommendations as a color-coded table with per-song scoring reasons."""
    if _HAS_RICH:
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
        for rank, (song, score, explanation) in enumerate(recommendations, start=1):
            print(f"{rank}. {song['title']} by {song['artist']}  [Score: {score:.2f}]")
            reasons = "\n   ".join(explanation.split(" | "))
            print(f"   Because:\n   {reasons}")
            print()


def run_profile(user_prefs: dict, songs: list, mode: str = "balanced", diversity: bool = False) -> None:
    """Print top-5 recommendations for a single user profile."""
    label = user_prefs.get("label", "Unknown Profile")
    diversity_label = "  [diversity ON]" if diversity else ""
    print(f"\n{'=' * 50}")
    print(f"  Profile: {label}  |  Mode: {mode}{diversity_label}")
    print(f"{'=' * 50}")

    recommendations = recommend_songs(user_prefs, songs, k=5, mode=mode, diversity=diversity)

    print("\nTop recommendations:\n")
    display_table(recommendations)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Music Recommender Simulation",
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
    args = parser.parse_args()

    songs = load_songs("data/songs.csv")
    print(f"Loaded {len(songs)} songs.")

    if args.all:
        profiles_to_run = list(PROFILES.values())
    elif args.profile:
        profiles_to_run = [PROFILES[args.profile]]
    else:
        profiles_to_run = [PROFILES["high_energy_pop"]]

    for user_prefs in profiles_to_run:
        run_profile(user_prefs, songs, mode=args.mode, diversity=args.diversity)


if __name__ == "__main__":
    main()
