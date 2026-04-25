"""
RAG enrichment via the Google Gemini API.

For one profile run, we collect the user's preferences plus retrieved
documents for each of the top-K songs, batch them into a single Gemini call,
and replace each song's deterministic explanation string with a grounded
natural-language paragraph.

Behavior:
  - If GEMINI_API_KEY is missing: print a warning and return results unchanged.
  - If the SDK is not installed: print a warning and return results unchanged.
  - If the API call raises: print the error and return results unchanged.

The deterministic explanation is preserved by appending a separator and the
generated paragraph, so the user can always see the underlying scoring
reasons even when enrichment is on.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from src.rag.retriever import Retriever, Document


GEMINI_MODEL = "gemini-2.5-flash"
SEPARATOR = "\n\nRAG note: "

SYSTEM_PROMPT = (
    "You are a music critic helping someone understand why a recommender "
    "selected specific songs. For each song, you will receive: the user's "
    "preferences, the song's metadata, the deterministic scoring reasons, "
    "and 1-3 retrieved reference documents about its genre and mood. "
    "Write a single short paragraph (2-3 sentences, max ~50 words) per song "
    "that grounds the recommendation in the retrieved documents. Reference "
    "specific phrases or concepts from the documents. Do not invent facts "
    "outside the documents and the song metadata. Do not use markdown formatting."
)


def _format_doc(doc: Document) -> str:
    return f"### {doc.category}: {doc.key}\n{doc.text.strip()}"


def _build_user_payload(
    user_prefs: Dict[str, Any],
    items: List[Tuple[Dict[str, Any], float, str, List[Document]]],
) -> str:
    lines = []
    lines.append("USER PREFERENCES")
    safe_prefs = {k: v for k, v in user_prefs.items() if k != "label"}
    lines.append(json.dumps(safe_prefs, indent=2))
    lines.append("")
    lines.append(f"SONGS TO EXPLAIN ({len(items)})")
    for i, (song, score, explanation, docs) in enumerate(items, start=1):
        lines.append(f"\n--- Song {i} (id={song['id']}) ---")
        lines.append(f"Title: {song['title']}")
        lines.append(f"Artist: {song['artist']}")
        lines.append(f"Genre: {song['genre']}, Mood: {song['mood']}, Detailed mood: {song.get('detailed_mood_tag', '')}")
        lines.append(f"Score: {score:.2f}")
        lines.append(f"Deterministic reasons: {explanation}")
        if docs:
            lines.append("Retrieved documents:")
            for d in docs:
                lines.append(_format_doc(d))
        else:
            lines.append("(no relevant documents retrieved)")
    lines.append("")
    lines.append(
        "Output JSON only, with no surrounding prose. Schema: "
        '{"notes": [{"id": <song_id>, "note": "<paragraph>"}, ...]} '
        f"with one entry per song in the same order, exactly {len(items)} entries."
    )
    return "\n".join(lines)


def _parse_response(text: str, expected_ids: List[int]) -> Dict[int, str]:
    """Best-effort JSON parse; tolerates ```json fences and trailing prose."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return {}
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return {}

    notes = data.get("notes", [])
    out: Dict[int, str] = {}
    for entry in notes:
        sid = entry.get("id")
        note = entry.get("note", "")
        if isinstance(sid, int) and isinstance(note, str) and sid in expected_ids:
            out[sid] = note.strip()
    return out


def _try_load_key() -> Optional[str]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.environ.get("GEMINI_API_KEY") or None


def enrich_recommendations(
    user_prefs: Dict[str, Any],
    results: List[Tuple[Dict[str, Any], float, str]],
    retriever: Optional[Retriever] = None,
    model_name: str = GEMINI_MODEL,
) -> List[Tuple[Dict[str, Any], float, str]]:
    """
    Enrich each result's explanation with a RAG-grounded paragraph.

    Returns a new list with the same shape; each explanation is augmented
    by appending a separator and the generated paragraph. If enrichment
    cannot run (missing key, SDK, or API failure), returns the input
    list unchanged with a printed warning.
    """
    if not results:
        return results

    api_key = _try_load_key()
    if not api_key:
        print("[RAG] GEMINI_API_KEY not set; skipping enrichment. "
              "Copy .env.example to .env and add your key (free at https://aistudio.google.com/app/apikey).")
        return results

    try:
        import google.generativeai as genai
    except ImportError:
        print("[RAG] google-generativeai not installed; run `pip install -r requirements.txt`.")
        return results

    if retriever is None:
        retriever = Retriever()

    items: List[Tuple[Dict[str, Any], float, str, List[Document]]] = []
    for song, score, explanation in results:
        docs = retriever.retrieve(song)
        items.append((song, score, explanation, docs))

    expected_ids = [song["id"] for song, _, _, _ in items]
    user_payload = _build_user_payload(user_prefs, items)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(
            user_payload,
            generation_config={
                "temperature": 0.4,
                "response_mime_type": "application/json",
            },
        )
        text = response.text or ""
    except Exception as exc:
        print(f"[RAG] Gemini API call failed ({type(exc).__name__}: {exc}); returning unchanged results.")
        return results

    notes = _parse_response(text, expected_ids)
    if not notes:
        print("[RAG] Could not parse Gemini response as JSON; returning unchanged results.")
        return results

    enriched: List[Tuple[Dict[str, Any], float, str]] = []
    for song, score, explanation in results:
        note = notes.get(song["id"], "")
        if note:
            new_explanation = f"{explanation}{SEPARATOR}{note}"
        else:
            new_explanation = explanation
        enriched.append((song, score, new_explanation))

    return enriched
