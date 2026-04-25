"""Tests for the RAG retriever and enricher (offline; no API calls)."""

import os
from unittest.mock import patch

import pytest

from src.rag.retriever import Retriever, _slug
from src.rag.enricher import enrich_recommendations, _parse_response, _build_user_payload


def test_retriever_loads_docs():
    r = Retriever()
    stats = r.stats()
    # we shipped 17 genres + 13 moods + 8 detailed_moods
    assert stats["genre"] >= 10
    assert stats["mood"] >= 10
    assert stats["detailed_mood"] >= 5


def test_retriever_returns_genre_mood_for_known_song():
    r = Retriever()
    song = {"genre": "lofi", "mood": "chill", "detailed_mood_tag": "peaceful"}
    docs = r.retrieve(song)
    keys = {(d.category, d.key) for d in docs}
    assert ("genre", "lofi") in keys
    assert ("mood", "chill") in keys
    assert ("detailed_mood", "peaceful") in keys


def test_retriever_handles_unknown_genre_gracefully():
    r = Retriever()
    song = {"genre": "reggaeton", "mood": "happy", "detailed_mood_tag": ""}
    docs = r.retrieve(song)
    # only happy mood doc retrievable; genre and detailed_mood absent
    keys = {(d.category, d.key) for d in docs}
    assert ("mood", "happy") in keys
    assert not any(c == "genre" for c, _ in keys)


def test_slug_normalizes_special_chars():
    assert _slug("R&B") == "r_b"
    assert _slug("indie pop") == "indie_pop"
    assert _slug("hip-hop") == "hip_hop"


def test_enricher_returns_unchanged_when_no_api_key(small_songs_dicts, basic_user_prefs):
    results = [(s, 5.0, "deterministic reason") for s in small_songs_dicts]
    with patch.dict(os.environ, {}, clear=True):
        out = enrich_recommendations(basic_user_prefs, results)
    # without key, results pass through unchanged
    assert out == results


def test_enricher_parses_response_with_json_fence():
    text = '```json\n{"notes": [{"id": 1, "note": "Great song."}]}\n```'
    parsed = _parse_response(text, expected_ids=[1])
    assert parsed == {1: "Great song."}


def test_enricher_parses_response_with_trailing_prose():
    text = 'Sure, here it is: {"notes": [{"id": 7, "note": "Nice."}]} hope this helps!'
    parsed = _parse_response(text, expected_ids=[7])
    assert parsed == {7: "Nice."}


def test_enricher_filters_unknown_ids():
    text = '{"notes": [{"id": 99, "note": "wrong id"}, {"id": 3, "note": "right id"}]}'
    parsed = _parse_response(text, expected_ids=[3])
    assert parsed == {3: "right id"}


def test_enricher_payload_includes_user_prefs_and_documents(small_songs_dicts, basic_user_prefs):
    from src.rag.retriever import Retriever
    r = Retriever()
    items = [(small_songs_dicts[0], 5.0, "reason1", r.retrieve(small_songs_dicts[0]))]
    payload = _build_user_payload(basic_user_prefs, items)
    assert "USER PREFERENCES" in payload
    assert "Test Pop Track" in payload
    assert "JSON" in payload  # schema instruction
