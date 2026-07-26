"""
Benchmark reporting — terminal, JSON, and markdown output.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from .regression import Regression

# ANSI
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

NO_COLOR = False


def c(text: str, colour: str) -> str:
    if NO_COLOR:
        return str(text)
    return f"{colour}{text}{RESET}"


def print_terminal_report(result: dict, verbose: bool = False) -> None:
    """Print a formatted benchmark report to the terminal."""
    print()
    print(c("=" * 60, BOLD))
    print(c("  V11 Benchmark Report", BOLD + CYAN))
    print(c("=" * 60, BOLD))
    print()

    # Run info
    print(f"  Run ID:    {result.get('run_id', '?')}")
    print(f"  Git SHA:   {result.get('git_sha', '?')[:8]}")
    print(f"  Tier:      {result.get('tier', '?')}")
    print(f"  Duration:  {result.get('duration_s', 0):.1f}s")
    print(f"  Cost:      ${result.get('total_cost_usd', 0):.4f}")
    print()

    # Composite score
    score = result.get("composite_score", 0)
    color = GREEN if score >= 90 else YELLOW if score >= 70 else RED
    print(f"  Composite: {c(f'{score:.1f}', BOLD + color)} / 100")
    print()

    # Tier scores
    tier_scores = result.get("tier_scores", {})
    print(c("  Tier Scores:", BOLD))
    for t in [0, 1, 2]:
        key = f"tier{t}"
        val = tier_scores.get(key)
        if val is not None:
            tc = GREEN if val >= 90 else YELLOW if val >= 70 else RED
            print(f"    Tier {t}: {c(f'{val:.1f}', tc)}")
        else:
            print(f"    Tier {t}: {c('(not run)', DIM)}")
    print()

    # Category scores
    cats = result.get("category_scores", {})
    if cats:
        print(c("  Categories:", BOLD))
        for name, data in sorted(cats.items()):
            if isinstance(data, dict):
                passed = data.get("passed", 0)
                total = data.get("total", 0)
                cat_score = data.get("score", 0)
                cc = GREEN if cat_score >= 90 else YELLOW if cat_score >= 70 else RED
                print(f"    {name:24s} {c(f'{passed}/{total}', cc)} ({cat_score:.0f}%)")
        print()

    # Individual tests (verbose)
    if verbose:
        tests = result.get("tests", [])
        if tests:
            print(c("  Tests:", BOLD))
            for t in tests:
                status = c("PASS", GREEN) if t.get("passed") else c("FAIL", RED)
                dur = t.get("duration_ms", 0)
                print(f"    [{status}] {t.get('id', '?'):30s} {dur:6.0f}ms")
                if not t.get("passed") and t.get("error"):
                    print(f"           {c(t['error'][:80], DIM)}")
            print()

    # Hook latencies
    latencies = result.get("latency_p50", {})
    if latencies:
        print(c("  Hook Latency P50:", BOLD))
        for hook, ms in sorted(latencies.items()):
            lc = GREEN if ms < 300 else YELLOW if ms < 500 else RED
            print(f"    {hook:24s} {c(f'{ms}ms', lc)}")
        print()

    # Regressions
    regs = result.get("regressions", [])
    if regs:
        print(c("  REGRESSIONS DETECTED:", BOLD + RED))
        for r in regs:
            sev_color = RED if r["severity"] in ("HIGH", "CRITICAL") else YELLOW
            print(f"    [{c(r['severity'], sev_color)}] Rule {r['rule']}: {r['message']}")
        print()
    else:
        print(c("  No regressions detected.", GREEN))
        print()

    print(c("=" * 60, BOLD))
    print()


def format_json(result: dict) -> str:
    """Format result as indented JSON."""
    return json.dumps(result, indent=2, default=str)


def format_markdown(result: dict) -> str:
    """Format result as a markdown summary."""
    lines = []
    lines.append("# V11 Benchmark Report")
    lines.append("")
    lines.append(f"- **Run ID**: {result.get('run_id', '?')}")
    lines.append(f"- **Git SHA**: {result.get('git_sha', '?')[:8]}")
    lines.append(f"- **Tier**: {result.get('tier', '?')}")
    lines.append(f"- **Duration**: {result.get('duration_s', 0):.1f}s")
    lines.append(f"- **Cost**: ${result.get('total_cost_usd', 0):.4f}")
    lines.append(f"- **Composite Score**: **{result.get('composite_score', 0):.1f}** / 100")
    lines.append("")

    # Tier scores table
    lines.append("## Tier Scores")
    lines.append("")
    lines.append("| Tier | Score |")
    lines.append("|------|-------|")
    tier_scores = result.get("tier_scores", {})
    for t in [0, 1, 2]:
        key = f"tier{t}"
        val = tier_scores.get(key)
        lines.append(f"| {t} | {f'{val:.1f}' if val is not None else 'N/A'} |")
    lines.append("")

    # Categories
    cats = result.get("category_scores", {})
    if cats:
        lines.append("## Categories")
        lines.append("")
        lines.append("| Category | Passed | Total | Score |")
        lines.append("|----------|--------|-------|-------|")
        for name, data in sorted(cats.items()):
            if isinstance(data, dict):
                lines.append(
                    f"| {name} | {data.get('passed', 0)} | {data.get('total', 0)} | {data.get('score', 0):.0f}% |"
                )
        lines.append("")

    # Regressions
    regs = result.get("regressions", [])
    if regs:
        lines.append("## Regressions")
        lines.append("")
        for r in regs:
            lines.append(f"- **[{r['severity']}]** Rule {r['rule']}: {r['message']}")
        lines.append("")

    return "\n".join(lines)


def print_trend(trend: list[dict]) -> None:
    """Print a trend comparison of recent runs."""
    if not trend:
        print("  No previous runs found.")
        return

    print()
    print(c("  V11 Benchmark Trend", BOLD + CYAN))
    print(c("  " + "-" * 50, DIM))
    print(f"  {'Run ID':36s} {'Tier':>4s} {'Score':>6s} {'Time':>6s} {'Reg':>4s}")
    print(c("  " + "-" * 50, DIM))

    for r in trend:
        score = r.get("composite_score", 0) or 0
        sc = GREEN if score >= 90 else YELLOW if score >= 70 else RED
        regs = r.get("regressions", 0)
        rc = RED if regs > 0 else GREEN
        print(
            f"  {r.get('run_id', '?'):36s} "
            f"{r.get('tier', '?'):>4} "
            f"{c(f'{score:5.1f}', sc)} "
            f"{r.get('duration_s', 0):5.1f}s "
            f"{c(str(regs), rc):>4s}"
        )
    print()
