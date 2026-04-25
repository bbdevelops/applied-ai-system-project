"""
Shared pytest fixtures for the Resonance Selector test suite.
"""

import pytest

from src.recommender import Song, Recommender


def _small_song_list():
    return [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]


@pytest.fixture
def small_songs_dicts():
    """Two-song catalog as dicts (matches load_songs format)."""
    return [vars(s) for s in _small_song_list()]


@pytest.fixture
def small_recommender():
    """Two-song Recommender instance."""
    return Recommender(_small_song_list())


@pytest.fixture
def basic_user_prefs():
    """A well-formed user preference dict that should validate without warnings."""
    return {
        "label": "Test Pop",
        "genre": "pop",
        "mood": "happy",
        "energy": 0.8,
        "likes_acoustic": False,
        "target_valence": 0.9,
        "target_tempo": 120,
        "target_danceability": 0.8,
        "target_popularity": 70,
        "preferred_decade": 2020,
        "favorite_detailed_mood": "euphoric",
        "target_instrumentalness": 0.05,
        "preferred_language": "english",
    }
