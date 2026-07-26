"""
JSONL ledger for benchmark results — append-only, jq-queryable.

Each line is one benchmark run with composite score, tier scores, tests, and regressions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(__file__).parent / "ledger.jsonl"
BASELINE_PATH = Path(__file__).parent / "baseline.json"


def append_result(result: dict, path: Path | None = None) -> None:
    """Append a single run result to the ledger."""
    target = path or LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a") as f:
        f.write(json.dumps(result, default=str) + "\n")


def read_results(path: Path | None = None, last_n: int = 0) -> list[dict]:
    """Read all results from the ledger. If last_n > 0, return only the last N."""
    target = path or LEDGER_PATH
    if not target.exists():
        return []
    results = []
    for line in target.read_text().strip().split("\n"):
        line = line.strip()
        if line:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if last_n > 0:
        return results[-last_n:]
    return results


def get_last_result(path: Path | None = None, tier: int | None = None) -> dict | None:
    """Get the most recent result, optionally filtered by tier."""
    results = read_results(path)
    if tier is not None:
        results = [r for r in results if r.get("tier") == tier]
    return results[-1] if results else None


def get_last_tier_scores(path: Path | None = None) -> dict[int, float | None]:
    """Get the most recent score for each tier from the ledger."""
    results = read_results(path)
    scores: dict[int, float | None] = {0: None, 1: None, 2: None}
    for r in results:
        tier = r.get("tier")
        tier_scores = r.get("tier_scores", {})
        for t in [0, 1, 2]:
            key = f"tier{t}"
            if tier_scores.get(key) is not None:
                scores[t] = tier_scores[key]
            elif tier == t and r.get("composite_score") is not None:
                # Fallback: if this run was for this tier, use composite
                scores[t] = r["composite_score"]
    return scores


def load_baseline(path: Path | None = None) -> dict | None:
    """Load the committed baseline for regression detection."""
    target = path or BASELINE_PATH
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_baseline(result: dict, path: Path | None = None) -> None:
    """Save a result as the new baseline."""
    target = path or BASELINE_PATH
    target.write_text(json.dumps(result, indent=2, default=str) + "\n")


def get_trend(path: Path | None = None, last_n: int = 5) -> list[dict[str, Any]]:
    """Get a trend summary of the last N runs."""
    results = read_results(path, last_n=last_n)
    trend = []
    for r in results:
        trend.append({
            "run_id": r.get("run_id", "?"),
            "timestamp": r.get("timestamp", "?"),
            "tier": r.get("tier"),
            "composite_score": r.get("composite_score"),
            "duration_s": r.get("duration_s"),
            "total_cost_usd": r.get("total_cost_usd", 0.0),
            "regressions": len(r.get("regressions", [])),
        })
    return trend
