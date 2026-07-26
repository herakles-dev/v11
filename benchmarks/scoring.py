"""
Composite scoring for V11 benchmarks.

Score formula:
  composite = (0.50 * tier0) + (0.30 * tier1) + (0.20 * tier2)

Each tier score = (passed / total) * 100. Missing tiers use last known result.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Tier weights must sum to 1.0
TIER_WEIGHTS = {0: 0.50, 1: 0.30, 2: 0.20}


@dataclass
class TierScore:
    tier: int
    passed: int = 0
    total: int = 0
    tests: list[dict] = field(default_factory=list)

    @property
    def score(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100.0


@dataclass
class CategoryScore:
    name: str
    passed: int = 0
    total: int = 0

    @property
    def score(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100.0

    def to_dict(self) -> dict:
        return {"passed": self.passed, "total": self.total, "score": round(self.score, 1)}


def compute_composite(
    tier_scores: dict[int, TierScore | None],
    fallback_scores: dict[int, float | None] | None = None,
) -> float:
    """
    Compute weighted composite from tier scores.

    For missing tiers (None or not run), uses fallback_scores from the ledger.
    If no fallback exists, that tier contributes 0 to the composite.
    """
    fallback = fallback_scores or {}
    total = 0.0

    for tier, weight in TIER_WEIGHTS.items():
        ts = tier_scores.get(tier)
        if ts is not None and ts.total > 0:
            total += weight * ts.score
        elif fallback.get(tier) is not None:
            total += weight * fallback[tier]
        # else: contributes 0

    return round(total, 1)


def compute_category_scores(tests: list[dict]) -> dict[str, CategoryScore]:
    """Group test results by category and compute per-category scores."""
    categories: dict[str, CategoryScore] = {}
    for t in tests:
        cat = t.get("category", "unknown")
        if cat not in categories:
            categories[cat] = CategoryScore(name=cat)
        categories[cat].total += 1
        if t.get("passed", False):
            categories[cat].passed += 1
    return categories
