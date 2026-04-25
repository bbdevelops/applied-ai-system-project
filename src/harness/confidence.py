"""
Confidence scoring for a top-k recommendation set.

Combines three signals into one overall score in [0, 1]:
  - gap_score:               how far the top result is above the rest of top-k
  - categorical_match_pct:   fraction of top-k that match the user's genre or mood
  - diversity_score:         how varied the top-k is across artist + genre

overall = 0.5 * gap_score + 0.3 * categorical_match_pct + 0.2 * diversity_score

The default threshold for the harness fallback is 0.4.
"""

from typing import Dict, List, Tuple, Any


# A song that perfectly matches all weights in balanced mode would land near
# this score. We use it to normalize gap_score into [0, 1] without depending
# on the SCORING_MODES dict directly (keeps confidence module mode-agnostic).
MAX_REFERENCE_SCORE = 14.0

GAP_WEIGHT = 0.5
CATEGORICAL_WEIGHT = 0.3
DIVERSITY_WEIGHT = 0.2


def compute_confidence(
    results: List[Tuple[Dict[str, Any], float, str]],
    user_prefs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute confidence metrics for a ranked recommendation list.

    Returns a dict with:
      - gap_score              float in [0, 1]
      - categorical_match_pct  float in [0, 1]
      - diversity_score        float in [0, 1]
      - overall                weighted sum, float in [0, 1]
      - flags                  list[str] human-readable issues
    """
    flags: List[str] = []

    if not results:
        return {
            "gap_score": 0.0,
            "categorical_match_pct": 0.0,
            "diversity_score": 0.0,
            "overall": 0.0,
            "flags": ["empty result list"],
        }

    scores = [score for _, score, _ in results]
    top_score = scores[0]

    if len(scores) > 1:
        rest = scores[1:]
        mean_rest = sum(rest) / len(rest)
        raw_gap = top_score - mean_rest
        gap_score = max(0.0, min(1.0, raw_gap / MAX_REFERENCE_SCORE))
    else:
        gap_score = max(0.0, min(1.0, top_score / MAX_REFERENCE_SCORE))

    if top_score < 1.0:
        flags.append(f"top score is low ({top_score:.2f})")

    user_genre = user_prefs.get("genre")
    user_mood = user_prefs.get("mood")
    matches = 0
    for song, _, _ in results:
        if (user_genre and song.get("genre") == user_genre) or (
            user_mood and song.get("mood") == user_mood
        ):
            matches += 1
    categorical_match_pct = matches / len(results)
    if categorical_match_pct < 0.4:
        flags.append(
            f"only {matches}/{len(results)} top results match user's genre or mood"
        )

    artists = [song.get("artist") for song, _, _ in results]
    genres = [song.get("genre") for song, _, _ in results]
    n = len(results)
    if n > 1:
        dup_artists = n - len(set(artists))
        dup_genres = n - len(set(genres))
        diversity_score = max(0.0, 1.0 - (dup_artists + dup_genres) / (2 * n))
    else:
        diversity_score = 1.0
    if diversity_score < 0.5:
        flags.append("low diversity: top results cluster on artist/genre")

    overall = (
        GAP_WEIGHT * gap_score
        + CATEGORICAL_WEIGHT * categorical_match_pct
        + DIVERSITY_WEIGHT * diversity_score
    )

    return {
        "gap_score": round(gap_score, 4),
        "categorical_match_pct": round(categorical_match_pct, 4),
        "diversity_score": round(diversity_score, 4),
        "overall": round(overall, 4),
        "flags": flags,
    }
