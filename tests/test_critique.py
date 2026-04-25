"""Tests for the self-critique loop in src.harness.critique."""

import pytest

from src.harness import recommend_with_harness, HarnessError
from src.recommender import load_songs


@pytest.fixture(scope="module")
def full_catalog():
    return load_songs("data/songs.csv")


def test_happy_path_no_fallback(full_catalog, basic_user_prefs):
    results, report = recommend_with_harness(basic_user_prefs, full_catalog, k=5)
    assert len(results) == 5
    assert report.fallback_triggered is False
    assert report.confidence_initial == report.confidence_final
    assert len(report.rungs_attempted) == 1


def test_conflicting_profile_triggers_fallback(full_catalog):
    profile = {
        "label": "Conflicting",
        "genre": "ambient",
        "mood": "sad",  # not present in dataset
        "energy": 0.9,
        "target_valence": 0.2,
        "likes_acoustic": True,
    }
    results, report = recommend_with_harness(profile, full_catalog, k=5)
    assert report.fallback_triggered is True
    assert len(report.rungs_attempted) > 1
    # ladder must have attempted at least one alternative strategy
    assert any("rung 1" in r or "rung 2" in r or "rung 3" in r for r in report.rungs_attempted)


def test_ladder_records_relaxed_preferences(full_catalog):
    profile = {
        "label": "All-Mismatch",
        "genre": "reggaeton",  # not in catalog
        "mood": "sad",         # not in catalog
        "energy": 0.5,
    }
    results, report = recommend_with_harness(profile, full_catalog, k=5)
    assert report.fallback_triggered is True
    # rung 3 should have attempted a relaxation
    assert report.relaxed_preferences  # non-empty


def test_invalid_profile_raises(full_catalog):
    with pytest.raises(HarnessError):
        recommend_with_harness({"genre": "pop"}, full_catalog, k=5)  # missing energy + mood


def test_returns_results_even_when_ladder_exhausts(full_catalog):
    """Even when no rung clears the threshold, harness still returns the best run."""
    profile = {
        "label": "Hopeless",
        "genre": "reggaeton",
        "mood": "sad",
        "energy": 0.5,
    }
    results, report = recommend_with_harness(profile, full_catalog, k=5)
    assert len(results) == 5
    # all entries should still be valid (no NaN, no duplicates)
    seen_ids = {r[0]["id"] for r in results}
    assert len(seen_ids) == 5
