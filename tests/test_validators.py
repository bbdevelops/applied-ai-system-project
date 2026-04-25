"""Tests for input/output guardrails in src.harness.validators."""

import math

import pytest

from src.harness.validators import (
    HarnessError,
    validate_user_profile,
    validate_catalog,
    validate_recommendations,
)


def test_valid_profile_passes_with_no_warnings(basic_user_prefs):
    cleaned, warnings = validate_user_profile(basic_user_prefs)
    assert warnings == []
    assert cleaned["genre"] == "pop"
    assert cleaned["energy"] == 0.8


def test_missing_required_field_raises():
    profile = {"genre": "pop", "mood": "happy"}  # no energy
    with pytest.raises(HarnessError, match="energy"):
        validate_user_profile(profile)


def test_out_of_range_energy_is_clamped_with_warning(basic_user_prefs):
    basic_user_prefs["energy"] = 1.5
    cleaned, warnings = validate_user_profile(basic_user_prefs)
    assert cleaned["energy"] == 1.0
    assert any("energy" in w and "clamped" in w for w in warnings)


def test_negative_valence_is_clamped(basic_user_prefs):
    basic_user_prefs["target_valence"] = -0.3
    cleaned, warnings = validate_user_profile(basic_user_prefs)
    assert cleaned["target_valence"] == 0.0
    assert any("target_valence" in w for w in warnings)


def test_non_numeric_energy_raises(basic_user_prefs):
    basic_user_prefs["energy"] = "high"
    with pytest.raises(HarnessError, match="energy"):
        validate_user_profile(basic_user_prefs)


def test_empty_catalog_raises():
    with pytest.raises(HarnessError, match="empty"):
        validate_catalog([])


def test_duplicate_song_id_raises(small_songs_dicts):
    dup = dict(small_songs_dicts[0])
    songs = small_songs_dicts + [dup]
    with pytest.raises(HarnessError, match="duplicate"):
        validate_catalog(songs)


def test_catalog_drops_malformed_row(small_songs_dicts):
    bad = dict(small_songs_dicts[0])
    bad["id"] = 99
    bad["energy"] = float("nan")
    cleaned, warnings = validate_catalog(small_songs_dicts + [bad])
    assert len(cleaned) == 2
    assert any("nan" in w.lower() or "finite" in w.lower() for w in warnings)


def test_recommendations_drop_nan_score(small_songs_dicts):
    s1 = small_songs_dicts[0]
    s2 = small_songs_dicts[1]
    results = [(s1, 5.0, "ok"), (s2, float("nan"), "bad")]
    cleaned, warnings = validate_recommendations(results, k=5, catalog_size=2)
    assert len(cleaned) == 1
    assert cleaned[0][0]["id"] == s1["id"]
    assert any("not finite" in w or "nan" in w.lower() for w in warnings)


def test_recommendations_dedupe_by_id(small_songs_dicts):
    s1 = small_songs_dicts[0]
    results = [(s1, 5.0, "first"), (s1, 4.0, "duplicate")]
    cleaned, warnings = validate_recommendations(results, k=5, catalog_size=1)
    assert len(cleaned) == 1
    assert any("duplicate" in w.lower() for w in warnings)


def test_recommendations_sorted_descending_with_id_tiebreak(small_songs_dicts):
    s1 = small_songs_dicts[0]  # id=1
    s2 = small_songs_dicts[1]  # id=2
    results = [(s2, 5.0, "b"), (s1, 5.0, "a")]
    cleaned, _ = validate_recommendations(results, k=5, catalog_size=2)
    assert cleaned[0][0]["id"] == 1  # tiebreak picks lower id first
    assert cleaned[1][0]["id"] == 2
