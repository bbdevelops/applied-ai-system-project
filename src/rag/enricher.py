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

# Base instruction shared by every persona. Persona-specific text is appended
# below to constrain tone, vocabulary, and focus area while keeping the JSON
# contract unchanged.
_BASE_INSTRUCTION = (
    "You are explaining to a listener why a recommender selected specific songs. "
    "For each song you will receive: the user's preferences, the song's metadata, "
    "the deterministic scoring reasons, and 1-3 retrieved reference documents "
    "about its genre and mood. Ground each explanation in those documents — "
    "reference specific phrases or concepts from them. Do not invent facts "
    "outside the documents and the song metadata. Do not use markdown formatting. "
    "Output JSON only, with one entry per song, in the order they were given."
)

PERSONAS: Dict[str, Dict[str, str]] = {
    "default": {
        "label": "Default music critic",
        "instruction": (
            "Write 2-3 sentences (max ~50 words) per song in a clear, neutral "
            "music-critic voice. Aim for informative concision."
        ),
        "fewshot": "",
    },
    "analytical": {
        "label": "Analytical musician",
        "instruction": (
            "Write 2-3 sentences (max ~60 words) per song from the perspective "
            "of an analytical musician. Focus on instrumentation, harmonic "
            "language (mode, tonality, key tendencies), production texture, "
            "and structural elements. Use specific musical terminology drawn "
            "from the retrieved documents (e.g., 'minor harmony', 'syncopation', "
            "'gated reverb', 'sidechained bassline'). Avoid emotional language "
            "and avoid hyping the song."
        ),
        "fewshot": (
            "Example output style:\n"
            "  \"The track's modal-major harmony and gated-reverb drum signature "
            "place it firmly in the synthwave lineage; sidechained bass and "
            "arpeggiated leads reinforce the retrofuturist palette the genre "
            "document describes. Tempo and danceability cluster within the "
            "90-120 BPM band typical of the form.\""
        ),
    },
    "enthusiast": {
        "label": "Energetic enthusiast",
        "instruction": (
            "Write 2-3 sentences (max ~50 words) per song with an upbeat, "
            "casual fan voice. Use exclamation, conversational vocabulary, "
            "and focus on vibe, feel, and listening context (when to play it, "
            "what mood it lands in). Still ground claims in the retrieved "
            "documents but reframe them as recommendations a friend would "
            "make. Avoid clinical or academic vocabulary."
        ),
        "fewshot": (
            "Example output style:\n"
            "  \"This one's a perfect chill-mode pick — the lofi doc nails it "
            "with 'as ignorable as it is interesting,' and that's exactly the "
            "energy here. Throw it on for studying or a slow Sunday and let "
            "it just sit in the background while you do your thing.\""
        ),
    },
    "historian": {
        "label": "Genre historian",
        "instruction": (
            "Write 2-3 sentences (max ~60 words) per song from the perspective "
            "of a genre historian. Anchor each explanation to lineage, era, "
            "and stylistic influences as described in the retrieved documents. "
            "Mention the genre's origin period, key precedents, and how this "
            "track sits within the tradition. Use historical framing ('rooted "
            "in', 'descended from', 'echoes of') rather than emotional or "
            "instrumental analysis."
        ),
        "fewshot": (
            "Example output style:\n"
            "  \"The track sits in a tradition the genre document traces to "
            "Brian Eno's 1970s work — the 'as ignorable as it is interesting' "
            "ethos shows in the slow harmonic motion and absence of beat. It "
            "carries the lineage of ambient electronic into a contemporary "
            "production context.\""
        ),
    },
}

DEFAULT_PERSONA = "default"


def _build_system_prompt(persona: str) -> str:
    config = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])
    parts = [_BASE_INSTRUCTION, "", config["instruction"]]
    if config["fewshot"]:
        parts.extend(["", config["fewshot"]])
    return "\n".join(parts)


def list_personas() -> List[str]:
    return list(PERSONAS.keys())


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
        f"with one entry per song in the same order, exactly {len(items)} entries. "
        "Each note must follow the persona's instructed style."
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
    persona: str = DEFAULT_PERSONA,
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
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        print("[RAG] google-genai not installed; run `pip install -r requirements.txt`.")
        return results

    if retriever is None:
        retriever = Retriever()

    items: List[Tuple[Dict[str, Any], float, str, List[Document]]] = []
    for song, score, explanation in results:
        docs = retriever.retrieve(song)
        items.append((song, score, explanation, docs))

    expected_ids = [song["id"] for song, _, _, _ in items]
    user_payload = _build_user_payload(user_prefs, items)

    if persona not in PERSONAS:
        print(f"[RAG] unknown persona '{persona}'; falling back to '{DEFAULT_PERSONA}'.")
        persona = DEFAULT_PERSONA
    system_prompt = _build_system_prompt(persona)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=user_payload,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                response_mime_type="application/json",
            ),
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
