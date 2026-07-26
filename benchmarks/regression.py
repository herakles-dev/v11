"""
Regression detection — 5 rules applied to benchmark results.

Severity levels: CRITICAL, HIGH, MEDIUM, LOW
Exit code 1 on HIGH or CRITICAL regressions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Regression:
    rule: int
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    message: str
    detail: str = ""


def detect_regressions(
    current: dict,
    baseline: dict | None,
    previous: dict | None = None,
) -> list[Regression]:
    """
    Apply 5 regression rules comparing current run to baseline/previous.

    Rules:
    1. Composite drop > 5% = HIGH
    2. Category score drops to 0 from >0 = CRITICAL
    3. Hook latency P50 increases > 50% = MEDIUM
    4. Previously passing test now fails = HIGH
    5. Cost per task doubles = LOW
    """
    if baseline is None and previous is None:
        return []

    regressions: list[Regression] = []
    ref = baseline or previous

    # Rule 1: Composite drop > 5%
    ref_composite = ref.get("composite_score", 0)
    cur_composite = current.get("composite_score", 0)
    if ref_composite > 0:
        drop = ref_composite - cur_composite
        drop_pct = (drop / ref_composite) * 100
        if drop_pct > 5:
            regressions.append(Regression(
                rule=1,
                severity="HIGH",
                message=f"Composite score dropped {drop_pct:.1f}% ({ref_composite} -> {cur_composite})",
                detail=f"Threshold: 5%, Actual: {drop_pct:.1f}%",
            ))

    # Rule 2: Category score drops to 0 from >0
    ref_cats = ref.get("category_scores", {})
    cur_cats = current.get("category_scores", {})
    for cat_name, ref_cat in ref_cats.items():
        ref_score = ref_cat.get("score", 0) if isinstance(ref_cat, dict) else 0
        cur_cat = cur_cats.get(cat_name, {})
        cur_score = cur_cat.get("score", 0) if isinstance(cur_cat, dict) else 0
        if ref_score > 0 and cur_score == 0:
            regressions.append(Regression(
                rule=2,
                severity="CRITICAL",
                message=f"Category '{cat_name}' dropped to 0 (was {ref_score})",
                detail=f"All tests in category now failing",
            ))

    # Rule 3: Hook latency P50 increases > 50%
    ref_latency = ref.get("latency_p50", {})
    cur_latency = current.get("latency_p50", {})
    for hook, ref_ms in ref_latency.items():
        if ref_ms and ref_ms > 0:
            cur_ms = cur_latency.get(hook)
            if cur_ms and cur_ms > 0:
                increase_pct = ((cur_ms - ref_ms) / ref_ms) * 100
                if increase_pct > 50:
                    regressions.append(Regression(
                        rule=3,
                        severity="MEDIUM",
                        message=f"Hook '{hook}' latency P50 increased {increase_pct:.0f}% ({ref_ms}ms -> {cur_ms}ms)",
                        detail=f"Threshold: 50%, Actual: {increase_pct:.0f}%",
                    ))

    # Rule 4: Previously passing test now fails
    ref_tests = {t["id"]: t for t in ref.get("tests", []) if "id" in t}
    cur_tests = {t["id"]: t for t in current.get("tests", []) if "id" in t}
    for test_id, ref_test in ref_tests.items():
        if ref_test.get("passed") and test_id in cur_tests:
            if not cur_tests[test_id].get("passed"):
                regressions.append(Regression(
                    rule=4,
                    severity="HIGH",
                    message=f"Test '{test_id}' regressed (was passing, now failing)",
                    detail=cur_tests[test_id].get("error", ""),
                ))

    # Rule 5: Cost per task doubles
    ref_tests_list = ref.get("tests", [])
    cur_tests_list = current.get("tests", [])
    ref_total_cost = sum(t.get("cost_usd", 0) for t in ref_tests_list)
    cur_total_cost = sum(t.get("cost_usd", 0) for t in cur_tests_list)
    ref_count = len(ref_tests_list) or 1
    cur_count = len(cur_tests_list) or 1
    ref_cpt = ref_total_cost / ref_count
    cur_cpt = cur_total_cost / cur_count
    if ref_cpt > 0 and cur_cpt > ref_cpt * 2:
        regressions.append(Regression(
            rule=5,
            severity="LOW",
            message=f"Cost per task doubled (${ref_cpt:.4f} -> ${cur_cpt:.4f})",
            detail=f"Total cost: ${cur_total_cost:.4f}",
        ))

    return regressions


def has_blocking_regressions(regressions: list[Regression]) -> bool:
    """Return True if any regression is HIGH or CRITICAL (should exit 1)."""
    return any(r.severity in ("HIGH", "CRITICAL") for r in regressions)
