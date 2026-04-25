"""
Input and output guardrails for the Resonance Selector harness.

Three entry points:
- validate_user_profile(profile)   — checks the user's preference dict before scoring.
- validate_catalog(songs)          — checks the song list loaded from CSV.
- validate_recommendations(...)    — checks the scorer's output before display.

Each returns (cleaned_object, warnings: list[str]). Hard failures raise HarnessError.
The intent is "clamp and warn" for soft errors (out-of-range numerics, missing optional
fields) and "fail fast" only for catastrophic problems (empty catalog, missing required
fields, fundamentally wrong types).
"""

import math
from typing import Dict, List, Tuple, Any


class HarnessError(ValueError):
    """Raised when input cannot be safely repaired (missing required field, empty catalog, etc.)."""


REQUIRED_PROFILE_KEYS = ("genre", "mood", "energy")

REQUIRED_SONG_KEYS = (
    "id", "title", "artist", "genre", "mood",
    "energy", "tempo_bpm", "valence", "danceability", "acousticness",
    "popularity", "release_decade", "detailed_mood_tag",
    "instrumentalness", "language",
)

UNIT_INTERVAL_PROFILE_KEYS = (
    "energy", "target_valence", "target_danceability", "target_instrumentalness",
)
UNIT_INTERVAL_SONG_KEYS = (
    "energy", "valence", "danceability", "acousticness", "instrumentalness",
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def validate_user_profile(profile: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Validate and repair a user profile dict.

    Hard fails if required keys are missing or fundamentally mistyped.
    Clamps out-of-range numerics with a warning. Returns a cleaned copy
    so the caller's dict is not mutated.
    """
    if not isinstance(profile, dict):
        raise HarnessError(f"profile must be a dict, got {type(profile).__name__}")

    cleaned: Dict[str, Any] = dict(profile)
    warnings: List[str] = []

    missing = [k for k in REQUIRED_PROFILE_KEYS if k not in cleaned]
    if missing:
        raise HarnessError(f"profile missing required key(s): {missing}")

    for key in ("genre", "mood"):
        if not isinstance(cleaned[key], str) or not cleaned[key].strip():
            raise HarnessError(f"profile['{key}'] must be a non-empty string")

    try:
        cleaned["energy"] = float(cleaned["energy"])
    except (TypeError, ValueError):
        raise HarnessError(f"profile['energy'] must be numeric, got {cleaned['energy']!r}")

    for key in UNIT_INTERVAL_PROFILE_KEYS:
        if key in cleaned and cleaned[key] is not None:
            try:
                v = float(cleaned[key])
            except (TypeError, ValueError):
                warnings.append(f"{key}={cleaned[key]!r} is not numeric; dropping")
                cleaned.pop(key)
                continue
            if not (0.0 <= v <= 1.0):
                clamped = _clamp(v, 0.0, 1.0)
                warnings.append(f"{key}={v} out of [0,1]; clamped to {clamped}")
                v = clamped
            cleaned[key] = v

    if "target_tempo" in cleaned and cleaned["target_tempo"] is not None:
        try:
            t = float(cleaned["target_tempo"])
        except (TypeError, ValueError):
            warnings.append(f"target_tempo={cleaned['target_tempo']!r} is not numeric; dropping")
            cleaned.pop("target_tempo")
        else:
            if not (60 <= t <= 200):
                clamped = _clamp(t, 60, 200)
                warnings.append(f"target_tempo={t} out of [60,200]; clamped to {clamped}")
                t = clamped
            cleaned["target_tempo"] = t

    if "target_popularity" in cleaned and cleaned["target_popularity"] is not None:
        try:
            p = float(cleaned["target_popularity"])
        except (TypeError, ValueError):
            warnings.append(f"target_popularity={cleaned['target_popularity']!r} is not numeric; dropping")
            cleaned.pop("target_popularity")
        else:
            if not (0 <= p <= 100):
                clamped = _clamp(p, 0, 100)
                warnings.append(f"target_popularity={p} out of [0,100]; clamped to {clamped}")
                p = clamped
            cleaned["target_popularity"] = int(p)

    if "preferred_decade" in cleaned and cleaned["preferred_decade"] is not None:
        try:
            d = int(cleaned["preferred_decade"])
        except (TypeError, ValueError):
            warnings.append(f"preferred_decade={cleaned['preferred_decade']!r} is not an int; dropping")
            cleaned.pop("preferred_decade")
        else:
            if d not in (1990, 2000, 2010, 2020):
                warnings.append(f"preferred_decade={d} not in known set {{1990,2000,2010,2020}}; keeping anyway")
            cleaned["preferred_decade"] = d

    if "likes_acoustic" in cleaned and not isinstance(cleaned["likes_acoustic"], bool):
        warnings.append(
            f"likes_acoustic={cleaned['likes_acoustic']!r} is not a bool; coerced to {bool(cleaned['likes_acoustic'])}"
        )
        cleaned["likes_acoustic"] = bool(cleaned["likes_acoustic"])

    return cleaned, warnings


def validate_catalog(songs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Validate the song catalog. Drops malformed rows with a warning.
    Hard fails on an empty catalog or duplicate IDs.
    """
    if not isinstance(songs, list):
        raise HarnessError(f"catalog must be a list, got {type(songs).__name__}")
    if not songs:
        raise HarnessError("catalog is empty; nothing to recommend")

    cleaned: List[Dict[str, Any]] = []
    warnings: List[str] = []
    seen_ids = set()

    for idx, song in enumerate(songs):
        if not isinstance(song, dict):
            warnings.append(f"row {idx}: not a dict ({type(song).__name__}); dropping")
            continue
        missing = [k for k in REQUIRED_SONG_KEYS if k not in song]
        if missing:
            warnings.append(f"row {idx}: missing keys {missing}; dropping")
            continue

        song_id = song.get("id")
        if song_id in seen_ids:
            raise HarnessError(f"duplicate song id {song_id!r} in catalog (row {idx})")
        seen_ids.add(song_id)

        bad_numeric = False
        for key in UNIT_INTERVAL_SONG_KEYS:
            try:
                v = float(song[key])
            except (TypeError, ValueError):
                warnings.append(f"row {idx} (id={song_id}): {key}={song[key]!r} is not numeric; dropping row")
                bad_numeric = True
                break
            if math.isnan(v) or math.isinf(v):
                warnings.append(f"row {idx} (id={song_id}): {key}={v} is not finite; dropping row")
                bad_numeric = True
                break
        if bad_numeric:
            continue

        cleaned.append(song)

    if not cleaned:
        raise HarnessError("catalog has no valid rows after validation")

    return cleaned, warnings


def validate_recommendations(
    results: List[Tuple[Dict[str, Any], float, str]],
    k: int,
    catalog_size: int,
) -> Tuple[List[Tuple[Dict[str, Any], float, str]], List[str]]:
    """
    Validate the scorer's output before display.

    - Drops entries with non-finite scores.
    - Deduplicates by song id (keeps the first/highest-scoring occurrence).
    - Sorts descending by score, with deterministic tiebreak on ascending id.
    - Truncates to min(k, catalog_size).
    """
    warnings: List[str] = []
    seen_ids = set()
    filtered: List[Tuple[Dict[str, Any], float, str]] = []

    for entry in results:
        if not (isinstance(entry, tuple) and len(entry) == 3):
            warnings.append(f"malformed result entry (not a 3-tuple); dropping")
            continue
        song, score, explanation = entry
        if not isinstance(song, dict) or "id" not in song:
            warnings.append("result missing song dict or song id; dropping")
            continue
        try:
            s = float(score)
        except (TypeError, ValueError):
            warnings.append(f"score={score!r} is not numeric for id={song.get('id')}; dropping")
            continue
        if math.isnan(s) or math.isinf(s):
            warnings.append(f"score={s} is not finite for id={song.get('id')}; dropping")
            continue
        if song["id"] in seen_ids:
            warnings.append(f"duplicate song id={song['id']} in results; dropping later occurrence")
            continue
        seen_ids.add(song["id"])
        filtered.append((song, s, explanation if isinstance(explanation, str) else str(explanation)))

    filtered.sort(key=lambda t: (-t[1], t[0]["id"]))

    target_len = min(k, catalog_size)
    if len(filtered) > target_len:
        filtered = filtered[:target_len]
    elif len(filtered) < target_len:
        warnings.append(
            f"only {len(filtered)} valid recommendations available, expected {target_len}"
        )

    return filtered, warnings
