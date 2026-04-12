"""
Command line runner for the Music Recommender Simulation.

Run from the project root with:
    python -m src.main                          # default: High-Energy Pop
    python -m src.main --profile chill_lofi     # specific profile
    python -m src.main --all                    # all profiles in sequence
    python -m src.main --help                   # list available profiles
"""

import argparse

from src.recommender import load_songs, recommend_songs


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


def run_profile(user_prefs: dict, songs: list) -> None:
    """Print top-5 recommendations for a single user profile."""
    label = user_prefs.get("label", "Unknown Profile")
    print(f"\n{'=' * 50}")
    print(f"  Profile: {label}")
    print(f"{'=' * 50}")

    recommendations = recommend_songs(user_prefs, songs, k=5)

    print("\nTop recommendations:\n")
    for rank, (song, score, explanation) in enumerate(recommendations, start=1):
        print(f"{rank}. {song['title']} by {song['artist']}  [Score: {score:.2f}]")
        print(f"   Because: {explanation}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Music Recommender Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Available profiles:\n  " + "\n  ".join(PROFILES.keys()),
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
        run_profile(user_prefs, songs)


if __name__ == "__main__":
    main()
