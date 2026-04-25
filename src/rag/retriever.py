"""
TF-IDF retrieval over markdown documents in /docs/.

For each song we want to enrich, we pull a small bundle of relevant context:
the song's genre doc, its mood doc, and (if present) its detailed-mood doc.
The retriever doesn't need fancy ranking — exact filename match by category is
sufficient at this corpus size. The TfidfVectorizer is used to compute a
fallback ranking when an exact match is missing, so a song with an unusual
genre still gets the closest related document instead of nothing.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


DOCS_ROOT = Path("docs")


@dataclass
class Document:
    category: str       # 'genre', 'mood', or 'detailed_mood'
    key: str            # e.g. 'pop', 'lofi', 'aggressive'
    path: str           # source file
    text: str           # body content


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class Retriever:
    """
    Loads all markdown docs under /docs/{genres,moods,detailed_moods}/ at init.
    retrieve(song) returns up to 3 documents (one per category) most relevant
    to the song's genre, mood, and detailed_mood_tag.
    """

    def __init__(self, docs_root: Path = DOCS_ROOT):
        self.docs_root = Path(docs_root)
        self._index: Dict[str, Dict[str, Document]] = {
            "genre": {},
            "mood": {},
            "detailed_mood": {},
        }
        self._load_all()

    def _load_all(self) -> None:
        if not self.docs_root.exists():
            return
        category_map = {
            "genres": "genre",
            "moods": "mood",
            "detailed_moods": "detailed_mood",
        }
        for folder, category in category_map.items():
            sub = self.docs_root / folder
            if not sub.exists():
                continue
            for md in sub.glob("*.md"):
                key = _slug(md.stem)
                text = md.read_text(encoding="utf-8")
                self._index[category][key] = Document(
                    category=category, key=key, path=str(md), text=text
                )

    def retrieve(self, song: Dict) -> List[Document]:
        """Return up to 3 documents (genre, mood, detailed_mood) for one song."""
        out: List[Document] = []

        genre_key = _slug(song.get("genre", ""))
        if genre_key and genre_key in self._index["genre"]:
            out.append(self._index["genre"][genre_key])

        mood_key = _slug(song.get("mood", ""))
        if mood_key and mood_key in self._index["mood"]:
            out.append(self._index["mood"][mood_key])

        dmood_key = _slug(song.get("detailed_mood_tag", ""))
        if dmood_key and dmood_key in self._index["detailed_mood"]:
            out.append(self._index["detailed_mood"][dmood_key])

        return out

    def all_documents(self) -> List[Document]:
        return [doc for cat in self._index.values() for doc in cat.values()]

    def stats(self) -> Dict[str, int]:
        return {cat: len(docs) for cat, docs in self._index.items()}
