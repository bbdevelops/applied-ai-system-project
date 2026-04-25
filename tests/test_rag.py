"""Tests for the RAG retriever and enricher (offline; no API calls)."""

import os
from unittest.mock import patch

import pytest

from src.rag.retriever import Retriever, _slug
from src.rag.enricher import (
    enrich_recommendations,
    _parse_response,
    _build_user_payload,
    _build_system_prompt,
    list_personas,
    PERSONAS,
)


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
    # Override only the key var, not the whole environment, so other modules can
    # still resolve $HOME/$USERPROFILE during import. load_dotenv won't override
    # an already-set env var by default, so this stays empty even if .env has a key.
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        out = enrich_recommendations(basic_user_prefs, results)
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


def test_all_personas_registered():
    expected = {"default", "analytical", "enthusiast", "historian"}
    assert set(list_personas()) >= expected
    for name in expected:
        assert PERSONAS[name]["instruction"], f"persona {name} missing instruction"


def test_persona_prompts_diverge():
    """Each persona must produce a meaningfully different system prompt so
    output style can measurably differ from baseline."""
    prompts = {p: _build_system_prompt(p) for p in list_personas()}
    pairs = [
        ("default", "analytical"),
        ("default", "enthusiast"),
        ("default", "historian"),
        ("analytical", "enthusiast"),
    ]
    for a, b in pairs:
        assert prompts[a] != prompts[b], f"{a} and {b} prompts are identical"
    # analytical should mention musical-theory vocabulary
    assert any(term in prompts["analytical"].lower() for term in ("harmonic", "instrumentation", "modal"))
    # enthusiast should mention casual vibe
    assert any(term in prompts["enthusiast"].lower() for term in ("casual", "vibe", "fan", "exclamation"))
    # historian should mention lineage/era
    assert any(term in prompts["historian"].lower() for term in ("lineage", "era", "tradition", "historian"))


def test_unknown_persona_falls_back_to_default():
    fallback_prompt = _build_system_prompt("totally-made-up")
    default_prompt = _build_system_prompt("default")
    assert fallback_prompt == default_prompt
