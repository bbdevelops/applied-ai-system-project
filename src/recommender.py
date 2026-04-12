import csv
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float
    popularity: int = 50
    release_decade: int = 2010
    detailed_mood_tag: str = ""
    instrumentalness: float = 0.5
    language: str = "english"

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool
    target_popularity: int = 70
    preferred_decade: int = 2010
    favorite_detailed_mood: str = ""
    target_instrumentalness: float = 0.5
    preferred_language: str = "english"

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5, mode: str = "balanced", diversity: bool = False) -> List[Song]:
        """Returns the top k songs ranked by score for the given user profile."""
        user_prefs = {
            'genre': user.favorite_genre,
            'mood': user.favorite_mood,
            'energy': user.target_energy,
            'likes_acoustic': user.likes_acoustic,
            'target_popularity': user.target_popularity,
            'preferred_decade': user.preferred_decade,
            'favorite_detailed_mood': user.favorite_detailed_mood,
            'target_instrumentalness': user.target_instrumentalness,
            'preferred_language': user.preferred_language,
        }
        song_dicts = [vars(s) for s in self.songs]
        results = recommend_songs(user_prefs, song_dicts, k, mode=mode, diversity=diversity)
        song_map = {s.id: s for s in self.songs}
        return [song_map[r[0]['id']] for r in results]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Returns a human-readable explanation of why a song was recommended."""
        user_prefs = {
            'genre': user.favorite_genre,
            'mood': user.favorite_mood,
            'energy': user.target_energy,
            'likes_acoustic': user.likes_acoustic,
            'target_popularity': user.target_popularity,
            'preferred_decade': user.preferred_decade,
            'favorite_detailed_mood': user.favorite_detailed_mood,
            'target_instrumentalness': user.target_instrumentalness,
            'preferred_language': user.preferred_language,
        }
        _, reasons = score_song(user_prefs, vars(song))
        return " | ".join(reasons) if reasons else "No strong match found."

SCORING_MODES = {
    "balanced": {
        "genre": 2.5,  "mood": 1.5,  "energy": 2.0,  "valence": 1.5,
        "acousticness": 1.0, "tempo": 0.75, "danceability": 0.5,
        "popularity": 0.75, "decade": 0.75, "detailed_mood": 1.0,
        "instrumentalness": 1.0, "language": 0.75,
    },
    "genre-first": {
        "genre": 5.0,  "mood": 0.75, "energy": 1.0,  "valence": 0.75,
        "acousticness": 0.5, "tempo": 0.4,  "danceability": 0.25,
        "popularity": 0.4,  "decade": 0.4,  "detailed_mood": 0.5,
        "instrumentalness": 0.5, "language": 0.4,
    },
    "mood-first": {
        "genre": 1.25, "mood": 3.0,  "energy": 1.0,  "valence": 1.5,
        "acousticness": 0.5, "tempo": 0.4,  "danceability": 0.4,
        "popularity": 0.4,  "decade": 0.4,  "detailed_mood": 2.0,
        "instrumentalness": 0.5, "language": 0.4,
    },
    "energy-focused": {
        "genre": 1.25, "mood": 0.75, "energy": 4.0,  "valence": 0.75,
        "acousticness": 0.5, "tempo": 1.5,  "danceability": 1.0,
        "popularity": 0.4,  "decade": 0.4,  "detailed_mood": 0.5,
        "instrumentalness": 0.5, "language": 0.4,
    },
}

def load_songs(csv_path: str) -> List[Dict]:
    """Loads songs from a CSV file and returns a list of dicts with typed values."""
    songs = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            songs.append({
                'id':                int(row['id']),
                'title':             row['title'],
                'artist':            row['artist'],
                'genre':             row['genre'],
                'mood':              row['mood'],
                'energy':            float(row['energy']),
                'tempo_bpm':         float(row['tempo_bpm']),
                'valence':           float(row['valence']),
                'danceability':      float(row['danceability']),
                'acousticness':      float(row['acousticness']),
                'popularity':        int(row['popularity']),
                'release_decade':    int(row['release_decade']),
                'detailed_mood_tag': row['detailed_mood_tag'],
                'instrumentalness':  float(row['instrumentalness']),
                'language':          row['language'],
            })
    print(f"Loaded {len(songs)} songs from {csv_path}")
    return songs

def score_song(user_prefs: Dict, song: Dict, weights: Dict = None) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences using the weighted closeness model.

    Categorical features (genre, mood) award fixed bonus points on a match.
    Continuous features score (1 - |song_value - user_value|) * weight,
    rewarding proximity to the user's target rather than just high or low values.

    Pass a weights dict (from SCORING_MODES) to use a non-default scoring mode.
    Returns a (score, reasons) tuple where reasons is a list of strings
    explaining each contribution to the total.
    """
    if weights is None:
        weights = SCORING_MODES["balanced"]

    score = 0.0
    reasons = []

    # --- Categorical matches (binary) ---

    if 'genre' in user_prefs and song['genre'] == user_prefs['genre']:
        score += weights["genre"]
        reasons.append(f"genre match: {song['genre']} (+{weights['genre']:.2f})")

    if 'mood' in user_prefs and song['mood'] == user_prefs['mood']:
        score += weights["mood"]
        reasons.append(f"mood match: {song['mood']} (+{weights['mood']:.2f})")

    # --- Continuous feature closeness ---

    # Energy — strongest predictor of vibe
    if 'energy' in user_prefs:
        closeness = 1 - abs(song['energy'] - user_prefs['energy'])
        pts = closeness * weights["energy"]
        score += pts
        reasons.append(f"energy closeness: {closeness:.2f} (+{pts:.2f})")

    # Valence — emotional positivity
    if 'target_valence' in user_prefs:
        closeness = 1 - abs(song['valence'] - user_prefs['target_valence'])
        pts = closeness * weights["valence"]
        score += pts
        reasons.append(f"valence closeness: {closeness:.2f} (+{pts:.2f})")

    # Acousticness — target depends on likes_acoustic preference
    if 'likes_acoustic' in user_prefs:
        target = 1.0 if user_prefs['likes_acoustic'] else 0.0
        closeness = 1 - abs(song['acousticness'] - target)
        pts = closeness * weights["acousticness"]
        score += pts
        reasons.append(f"acousticness fit: {closeness:.2f} (+{pts:.2f})")

    # Tempo — normalized to 0–1 over the 60–200 BPM range
    if 'target_tempo' in user_prefs:
        norm_song = (song['tempo_bpm'] - 60) / 140
        norm_user = (user_prefs['target_tempo'] - 60) / 140
        closeness = 1 - abs(norm_song - norm_user)
        pts = closeness * weights["tempo"]
        score += pts
        reasons.append(f"tempo closeness: {closeness:.2f} (+{pts:.2f})")

    # Danceability — secondary preference signal
    if 'target_danceability' in user_prefs:
        closeness = 1 - abs(song['danceability'] - user_prefs['target_danceability'])
        pts = closeness * weights["danceability"]
        score += pts
        reasons.append(f"danceability closeness: {closeness:.2f} (+{pts:.2f})")

    # --- Advanced features ---

    # Popularity closeness — rewards songs near the user's target fame level
    if 'target_popularity' in user_prefs:
        closeness = 1 - abs(song['popularity'] - user_prefs['target_popularity']) / 100
        pts = closeness * weights["popularity"]
        score += pts
        reasons.append(f"popularity closeness: {song['popularity']}/100 (+{pts:.2f})")

    # Release decade proximity — rewards era alignment; max gap in dataset is ~40 yrs
    if 'preferred_decade' in user_prefs:
        decade_gap = abs(song['release_decade'] - user_prefs['preferred_decade'])
        closeness = max(0.0, 1 - decade_gap / 40)
        pts = closeness * weights["decade"]
        score += pts
        if decade_gap == 0:
            reasons.append(f"decade match: {song['release_decade']}s (+{pts:.2f})")
        else:
            reasons.append(f"decade proximity: {decade_gap} yr gap (+{pts:.2f})")

    # Detailed mood tag match — fine-grained emotional alignment
    if 'favorite_detailed_mood' in user_prefs and user_prefs['favorite_detailed_mood']:
        if song['detailed_mood_tag'] == user_prefs['favorite_detailed_mood']:
            score += weights["detailed_mood"]
            reasons.append(f"detailed mood match: {song['detailed_mood_tag']} (+{weights['detailed_mood']:.2f})")

    # Instrumentalness closeness — rewards vocal/instrumental preference alignment
    if 'target_instrumentalness' in user_prefs:
        closeness = 1 - abs(song['instrumentalness'] - user_prefs['target_instrumentalness'])
        pts = closeness * weights["instrumentalness"]
        score += pts
        reasons.append(f"instrumentalness fit: {song['instrumentalness']:.2f} (+{pts:.2f})")

    # Language match — rewards preferred lyrics language
    if 'preferred_language' in user_prefs and user_prefs['preferred_language']:
        if song['language'] == user_prefs['preferred_language']:
            score += weights["language"]
            reasons.append(f"language match: {song['language']} (+{weights['language']:.2f})")

    return score, reasons

def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5, mode: str = "balanced", diversity: bool = False) -> List[Tuple[Dict, float, str]]:
    """
    Scores every song and returns the top k sorted by score descending.

    Uses sorted() rather than .sort() to avoid mutating the input list.
    Pass a mode name from SCORING_MODES to shift weight priorities.
    Each result is a (song_dict, score, explanation) tuple.

    When diversity=True, a greedy selection loop applies a soft penalty to any
    candidate whose artist or genre is already represented in the results built
    so far.  This prevents the same artist or genre from dominating the top-K.
    Penalty constants mirror the corresponding match bonuses in balanced mode:
        ARTIST_PENALTY = 2.0   (same as genre match weight)
        GENRE_PENALTY  = 1.5   (same as mood match weight)
    """
    weights = SCORING_MODES.get(mode, SCORING_MODES["balanced"])
    scored = []
    for song in songs:
        song_score, reasons = score_song(user_prefs, song, weights)
        scored.append((song, song_score, list(reasons)))

    ranked = sorted(scored, key=lambda x: x[1], reverse=True)

    if not diversity:
        return [(song, score, " | ".join(reasons)) for song, score, reasons in ranked[:k]]

    # --- Diversity penalty: greedy selection ---
    ARTIST_PENALTY = 2.0
    GENRE_PENALTY = 1.5

    seen_artists: set = set()
    seen_genres: set = set()
    results = []
    remaining = list(ranked)  # already sorted by base score

    while len(results) < k and remaining:
        # Find the candidate with the best adjusted score given what's already selected
        best_adj_score = -float("inf")
        best_idx = 0
        for i, (song, base_score, _) in enumerate(remaining):
            adj = base_score
            if song["artist"] in seen_artists:
                adj -= ARTIST_PENALTY
            if song["genre"] in seen_genres:
                adj -= GENRE_PENALTY
            if adj > best_adj_score:
                best_adj_score = adj
                best_idx = i

        song, base_score, reasons = remaining.pop(best_idx)

        # Append penalty notes to the explanation for transparency
        if song["artist"] in seen_artists:
            reasons.append(f"diversity penalty: duplicate artist ({song['artist']}) (-{ARTIST_PENALTY:.1f})")
        if song["genre"] in seen_genres:
            reasons.append(f"diversity penalty: duplicate genre ({song['genre']}) (-{GENRE_PENALTY:.1f})")

        seen_artists.add(song["artist"])
        seen_genres.add(song["genre"])
        results.append((song, best_adj_score, " | ".join(reasons)))

    return results
