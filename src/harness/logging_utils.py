"""
Run-log writer for the harness.

Writes one JSON file per call into /logs/. Filename is
YYYYMMDD_HHMMSS_<profile-label>.json, with the slugified profile label.
Used by main.py and scripts/evaluate.py to leave an audit trail of
what the harness saw and what fallback decisions it made.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.harness.critique import HarnessReport


def _slugify(text: str) -> str:
    """Lowercase, replace non-alphanum with underscores, collapse repeats."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "unknown"


def write_run_log(
    report: HarnessReport,
    results: List[Tuple[Dict[str, Any], float, str]],
    log_dir: str = "logs",
) -> str:
    """
    Persist one harness run as JSON. Returns the absolute path written.

    The log captures the report fields plus a compact result list (id, title,
    artist, score, explanation) so that a future review can reconstruct what
    the user saw without needing to re-run scoring.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{_slugify(report.profile_label)}.json"
    full_path = log_path / filename

    payload = {
        "timestamp": datetime.now().isoformat(),
        "report": report.to_dict(),
        "results": [
            {
                "rank": i,
                "id": song["id"],
                "title": song["title"],
                "artist": song["artist"],
                "genre": song["genre"],
                "score": round(score, 4),
                "explanation": explanation,
            }
            for i, (song, score, explanation) in enumerate(results, start=1)
        ],
    }

    full_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(full_path.resolve())
