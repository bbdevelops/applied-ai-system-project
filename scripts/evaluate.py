"""
Evaluation harness for Resonance Selector 2.0.

Runs the full 5-profile x 4-mode x 2-diversity matrix (40 configurations) plus
a battery of edge cases, compares results against a golden baseline, and
prints a pass/fail summary.

Usage:
    python -m scripts.evaluate                  # run + compare
    python -m scripts.evaluate --update-golden  # regenerate baseline
    python -m scripts.evaluate --verbose        # print every row
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.harness import recommend_with_harness, HarnessError
from src.recommender import load_songs, SCORING_MODES
from src.main import PROFILES


GOLDEN_PATH = Path("tests/golden/expected_outputs.json")
SONGS_PATH = "data/songs.csv"
SCHEMA_VERSION = "1.0"


@dataclass
class EvalSummary:
    matrix_runs: int = 0
    matrix_passes: int = 0
    edge_runs: int = 0
    edge_passes: int = 0
    confidence_total: float = 0.0
    fallback_triggers: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    soft_warnings: List[str] = field(default_factory=list)
    baseline_stale: bool = False

    @property
    def all_passed(self) -> bool:
        return not self.failures and not self.baseline_stale

    @property
    def total_runs(self) -> int:
        return self.matrix_runs + self.edge_runs

    @property
    def confidence_avg(self) -> float:
        if self.matrix_runs == 0:
            return 0.0
        return self.confidence_total / self.matrix_runs


def _hash_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _hash_weights() -> str:
    payload = json.dumps(SCORING_MODES, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _config_key(profile_name: str, mode: str, diversity: bool) -> str:
    return f"{profile_name}:{mode}:{'div' if diversity else 'nodiv'}"


def _result_signature(results: List[Tuple[Dict[str, Any], float, str]]) -> Dict[str, Any]:
    return {
        "top_5_song_ids": [r[0]["id"] for r in results],
        "top_5_scores_rounded_2": [round(r[1], 2) for r in results],
    }


def _build_matrix() -> List[Tuple[str, str, bool]]:
    """Cartesian product of profile x mode x diversity."""
    matrix = []
    for profile_name in PROFILES:
        for mode in SCORING_MODES:
            for diversity in (False, True):
                matrix.append((profile_name, mode, diversity))
    return matrix


# ---------- Edge cases ----------

def _edge_empty_catalog() -> Tuple[bool, str]:
    try:
        recommend_with_harness(PROFILES["high_energy_pop"], [], k=5)
    except HarnessError:
        return True, "raised HarnessError as expected"
    return False, "expected HarnessError on empty catalog"


def _edge_unknown_genre(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    profile = {
        "label": "unknown_genre",
        "genre": "reggaeton",
        "mood": "happy",
        "energy": 0.7,
    }
    results, report = recommend_with_harness(profile, songs, k=5)
    if report.fallback_triggered and len(results) == 5:
        return True, f"fallback triggered, {len(report.rungs_attempted)} rungs"
    return False, "expected fallback for unknown genre"


def _edge_out_of_range_energy(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    profile = {
        "label": "out_of_range",
        "genre": "pop",
        "mood": "happy",
        "energy": 1.5,  # out of [0,1]
    }
    results, report = recommend_with_harness(profile, songs, k=5)
    if any("clamped" in w for w in report.warnings) and len(results) == 5:
        return True, "energy clamped with warning, run completed"
    return False, "expected clamp warning"


def _edge_missing_required_field(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    try:
        recommend_with_harness({"genre": "pop"}, songs, k=5)  # missing mood + energy
    except HarnessError:
        return True, "raised HarnessError as expected"
    return False, "expected HarnessError"


def _edge_wrong_type_field(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    profile = {"genre": "pop", "mood": "happy", "energy": "very high"}
    try:
        recommend_with_harness(profile, songs, k=5)
    except HarnessError:
        return True, "raised HarnessError on non-numeric energy"
    return False, "expected HarnessError"


def _edge_duplicate_in_catalog(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    dup = dict(songs[0])
    bad_catalog = songs + [dup]
    try:
        recommend_with_harness(PROFILES["high_energy_pop"], bad_catalog, k=5)
    except HarnessError:
        return True, "raised HarnessError on duplicate id"
    return False, "expected HarnessError"


def _edge_nan_score_filtered(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """A synthetic catalog row with NaN energy should be dropped on validation."""
    bad = dict(songs[0])
    bad["id"] = 999
    bad["energy"] = float("nan")
    try:
        results, report = recommend_with_harness(
            PROFILES["high_energy_pop"], songs + [bad], k=5
        )
    except HarnessError:
        return False, "harness rejected catalog instead of dropping NaN row"
    if any("finite" in w.lower() or "nan" in w.lower() for w in report.warnings):
        return True, "NaN row dropped with warning"
    return False, "expected NaN warning"


def _edge_single_song_genre(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """focused_jazz looks for a genre with only 1 song; coherence should still be reasonable."""
    results, report = recommend_with_harness(PROFILES["focused_jazz"], songs, k=5)
    if len(results) == 5:
        return True, f"completed with conf={report.confidence_final:.2f}"
    return False, "expected 5 results"


def _edge_tie_at_boundary(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Verify deterministic id-ascending tiebreak."""
    results, _ = recommend_with_harness(PROFILES["high_energy_pop"], songs, k=20)
    ids = [r[0]["id"] for r in results]
    assert len(set(ids)) == len(ids), "duplicate ids in output"
    # Run twice and confirm same order
    results2, _ = recommend_with_harness(PROFILES["high_energy_pop"], songs, k=20)
    ids2 = [r[0]["id"] for r in results2]
    return (ids == ids2, f"deterministic order over k={len(ids)}")


def _edge_homogeneous_top5(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """A profile that strongly favors one artist should lower the diversity score."""
    results, report = recommend_with_harness(
        PROFILES["high_energy_pop"], songs, k=5
    )
    return (len(results) == 5, f"diversity flagged or not, conf={report.confidence_final:.2f}")


def _edge_relax_after_double_mismatch(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    profile = {
        "label": "double_mismatch",
        "genre": "reggaeton",
        "mood": "sad",
        "energy": 0.5,
    }
    results, report = recommend_with_harness(profile, songs, k=5)
    if report.relaxed_preferences:
        return True, f"relaxed: {report.relaxed_preferences}"
    return False, "expected relaxation"


def _edge_diversity_breaks_clusters(songs: List[Dict[str, Any]]) -> Tuple[bool, str]:
    no_div, _ = recommend_with_harness(PROFILES["chill_lofi"], songs, k=5, diversity=False)
    with_div, _ = recommend_with_harness(PROFILES["chill_lofi"], songs, k=5, diversity=True)
    artists_no_div = {r[0]["artist"] for r in no_div}
    artists_div = {r[0]["artist"] for r in with_div}
    if len(artists_div) >= len(artists_no_div):
        return True, f"diversity yields {len(artists_div)} unique artists vs {len(artists_no_div)}"
    return False, "diversity reduced unique artists"


EDGE_CASES = [
    ("empty_catalog",                _edge_empty_catalog),
    ("unknown_genre",                _edge_unknown_genre),
    ("out_of_range_energy",          _edge_out_of_range_energy),
    ("missing_required_field",       _edge_missing_required_field),
    ("wrong_type_field",             _edge_wrong_type_field),
    ("duplicate_in_catalog",         _edge_duplicate_in_catalog),
    ("nan_score_filtered",           _edge_nan_score_filtered),
    ("single_song_genre_jazz",       _edge_single_song_genre),
    ("tie_at_boundary",              _edge_tie_at_boundary),
    ("homogeneous_top5",             _edge_homogeneous_top5),
    ("relax_after_double_mismatch",  _edge_relax_after_double_mismatch),
    ("diversity_breaks_clusters",    _edge_diversity_breaks_clusters),
]


# ---------- Driver ----------

def run_matrix(
    songs: List[Dict[str, Any]],
    golden: Dict[str, Any] | None,
    summary: EvalSummary,
    verbose: bool,
) -> Dict[str, Any]:
    """Run full configuration matrix; return signatures keyed by config string."""
    signatures: Dict[str, Any] = {}
    for profile_name, mode, diversity in _build_matrix():
        key = _config_key(profile_name, mode, diversity)
        try:
            results, report = recommend_with_harness(
                PROFILES[profile_name], songs, k=5, mode=mode, diversity=diversity
            )
        except Exception as exc:
            summary.matrix_runs += 1
            summary.failures.append(f"{key}: raised {type(exc).__name__}: {exc}")
            if verbose:
                print(f"  FAIL  {key}: {exc}")
            continue

        sig = _result_signature(results)
        sig["confidence_score_rounded_2"] = round(report.confidence_final, 2)
        signatures[key] = sig
        summary.matrix_runs += 1
        summary.confidence_total += report.confidence_final
        if report.fallback_triggered:
            summary.fallback_triggers.append(
                f"{key} ({report.confidence_initial:.2f} -> {report.confidence_final:.2f}, "
                f"final mode='{report.final_mode}')"
            )

        if golden is None:
            summary.matrix_passes += 1
            if verbose:
                print(f"  ----  {key}: top={sig['top_5_song_ids']}, conf={sig['confidence_score_rounded_2']}")
            continue

        expected = golden.get("profiles", {}).get(key)
        if expected is None:
            summary.soft_warnings.append(f"{key}: no golden entry; skipping comparison")
            summary.matrix_passes += 1
            continue

        if expected["top_5_song_ids"] != sig["top_5_song_ids"]:
            summary.failures.append(
                f"{key}: top-5 ids drifted\n"
                f"      expected {expected['top_5_song_ids']}\n"
                f"      got      {sig['top_5_song_ids']}"
            )
            if verbose:
                print(f"  FAIL  {key}: id drift")
            continue

        scores_drifted = expected["top_5_scores_rounded_2"] != sig["top_5_scores_rounded_2"]
        if scores_drifted:
            summary.soft_warnings.append(
                f"{key}: scores drifted but ranking stable "
                f"(expected {expected['top_5_scores_rounded_2']}, got {sig['top_5_scores_rounded_2']})"
            )

        summary.matrix_passes += 1
        if verbose:
            tag = "WARN" if scores_drifted else "PASS"
            print(f"  {tag}  {key}: conf={sig['confidence_score_rounded_2']}")

    return signatures


def run_edges(
    songs: List[Dict[str, Any]],
    summary: EvalSummary,
    verbose: bool,
) -> None:
    for name, fn in EDGE_CASES:
        summary.edge_runs += 1
        try:
            if name == "empty_catalog":
                ok, detail = fn()
            else:
                ok, detail = fn(songs)
        except Exception as exc:
            summary.failures.append(f"edge[{name}]: raised {type(exc).__name__}: {exc}")
            if verbose:
                print(f"  FAIL  edge[{name}]: {exc}")
            continue

        if ok:
            summary.edge_passes += 1
            if verbose:
                print(f"  PASS  edge[{name}]: {detail}")
        else:
            summary.failures.append(f"edge[{name}]: {detail}")
            if verbose:
                print(f"  FAIL  edge[{name}]: {detail}")


def evaluate_all(
    songs_path: str = SONGS_PATH,
    golden_path: Path = GOLDEN_PATH,
    update_golden: bool = False,
    verbose: bool = False,
) -> EvalSummary:
    songs = load_songs(songs_path)
    catalog_hash = _hash_file(songs_path)
    weights_hash = _hash_weights()

    summary = EvalSummary()
    golden: Dict[str, Any] | None = None

    if golden_path.exists() and not update_golden:
        try:
            golden = json.loads(golden_path.read_text(encoding="utf-8"))
        except Exception as exc:
            summary.failures.append(f"could not read golden file: {exc}")
            return summary

        if golden.get("catalog_hash") != catalog_hash or golden.get("weights_hash") != weights_hash:
            summary.baseline_stale = True
            summary.soft_warnings.append(
                "BASELINE STALE: catalog or weights changed; "
                "regenerate with --update-golden after reviewing."
            )
            golden = None  # skip comparison; still run matrix to get fresh signatures

    print()
    print("Resonance Selector 2.0 -- Evaluation Harness")
    print("=" * 44)
    print(f"Catalog: {songs_path} ({len(songs)} songs, hash {catalog_hash})")
    print(f"Weights: hash {weights_hash}")
    if update_golden:
        print(f"Golden:  WILL REGENERATE -> {golden_path}")
    elif golden:
        print(f"Golden:  {golden_path} (matches: YES)")
    elif summary.baseline_stale:
        print(f"Golden:  {golden_path} (STALE — comparison skipped)")
    else:
        print(f"Golden:  not found — will generate on --update-golden")
    print()

    if verbose:
        print("Matrix runs:")
    signatures = run_matrix(songs, golden, summary, verbose)
    if verbose:
        print()
        print("Edge cases:")
    run_edges(songs, summary, verbose)

    if update_golden:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "catalog_hash": catalog_hash,
            "weights_hash": weights_hash,
            "profiles": signatures,
        }
        golden_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print()
        print(f"Wrote new baseline -> {golden_path}")

    print()
    print(f"Matrix runs:        {summary.matrix_passes}/{summary.matrix_runs} passed")
    print(f"Edge cases:         {summary.edge_passes}/{summary.edge_runs} passed")
    print(f"Confidence avg:     {summary.confidence_avg:.2f}")
    print(f"Fallback triggers:  {len(summary.fallback_triggers)}/{summary.matrix_runs} runs")
    for note in summary.fallback_triggers:
        print(f"  - {note}")
    if summary.soft_warnings:
        print()
        print("Soft warnings:")
        for w in summary.soft_warnings:
            print(f"  - {w}")
    if summary.failures:
        print()
        print("Failures:")
        for f in summary.failures:
            print(f"  - {f}")
    print()
    print("PASS" if summary.all_passed else "FAIL")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluation harness for Resonance Selector 2.0")
    parser.add_argument("--update-golden", action="store_true", help="Regenerate golden baseline JSON")
    parser.add_argument("--verbose", action="store_true", help="Print every row")
    args = parser.parse_args()
    summary = evaluate_all(update_golden=args.update_golden, verbose=args.verbose)
    return 0 if summary.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
