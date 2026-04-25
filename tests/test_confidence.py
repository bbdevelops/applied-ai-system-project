"""Tests for src.harness.confidence."""

from src.harness.confidence import compute_confidence


def _result(song_id: int, genre: str, mood: str, artist: str, score: float):
    return ({"id": song_id, "genre": genre, "mood": mood, "artist": artist}, score, "")


def test_empty_results_returns_zero_confidence():
    out = compute_confidence([], {"genre": "pop", "mood": "happy"})
    assert out["overall"] == 0.0
    assert "empty" in out["flags"][0].lower()


def test_high_confidence_case():
    results = [
        _result(1, "pop", "happy", "A", 12.5),
        _result(2, "pop", "happy", "B", 9.0),
        _result(3, "pop", "happy", "C", 8.0),
        _result(4, "pop", "happy", "D", 7.5),
        _result(5, "pop", "happy", "E", 7.0),
    ]
    out = compute_confidence(results, {"genre": "pop", "mood": "happy"})
    assert out["categorical_match_pct"] == 1.0
    assert out["diversity_score"] >= 0.5  # all same genre, but artists are unique
    assert out["overall"] > 0.5


def test_low_confidence_when_no_categorical_matches():
    results = [
        _result(1, "ambient", "calm", "A", 4.0),
        _result(2, "lofi", "chill", "B", 3.0),
        _result(3, "ambient", "calm", "A", 2.5),
    ]
    out = compute_confidence(results, {"genre": "rock", "mood": "intense"})
    assert out["categorical_match_pct"] == 0.0
    assert out["overall"] < 0.4


def test_low_diversity_flagged():
    results = [
        _result(1, "pop", "happy", "Same Artist", 10.0),
        _result(2, "pop", "happy", "Same Artist", 9.0),
        _result(3, "pop", "happy", "Same Artist", 8.0),
        _result(4, "pop", "happy", "Same Artist", 7.0),
    ]
    out = compute_confidence(results, {"genre": "pop", "mood": "happy"})
    assert out["diversity_score"] < 1.0
    assert any("diversity" in f.lower() or "cluster" in f.lower() for f in out["flags"])


def test_single_result_does_not_crash():
    results = [_result(1, "pop", "happy", "A", 8.0)]
    out = compute_confidence(results, {"genre": "pop", "mood": "happy"})
    assert 0.0 <= out["overall"] <= 1.0
