#!/usr/bin/env python3
"""Reconcile the "Pending: N" scalar in handoff.md against the true pending
count from open_tasks (QR-1-followup, 2026-09-02).

Extracted from scripts/handoff (was inline at ~L2624-2675 post-Effort-A) so
the divergence logic can be unit-tested outside the full handoff harness.
Motivation: the PENDING scalar (baked in earlier from live-snapshot or
aggregate counters) and the open_tasks array (written by
_emit_handoff_tasks_json with additional filters) are built from different
filter chains and can diverge. On divergence, patch the already-written
handoff.md text in place — the array is the contract consumers rehydrate
from (scripts/v11-resume-tasks reads handoff-tasks.json, not the prose
scalar), so the array wins.

Divergence sources (2026-09-01 audit: 46% of 109 sampled sessions):
  (a) family-fold near-duplicate collapse
  (b) review-sibling pending_parent drop
  (c) stale-session id collapse across aggregate rebuilds

Modes (env-controlled by V11_HANDOFF_PENDING_UNIFY):
  on  (default) — patch header + "Then: N pending task(s)" + "Next pending: lowest-ID of N"
  off           — patch header only (V11_HANDOFF_PENDING_UNIFY=off rollback path)

CLI:
  --handoff-tasks PATH   handoff-tasks.json (input, required)
  --staging PATH         handoff.md staging file to patch (optional; if
                         omitted, no file mutation — dry-run for callers
                         that only want the true-pending count + patch
                         pairs)
  --pending N            current header scalar (may be stale)
  --in-progress N        for header reconstruction
  --blocked N            for header reconstruction
  --review-seg STR       review-pending segment suffix (e.g. " | Review-pending: 3")
  --mode on|off          V11_HANDOFF_PENDING_UNIFY value

Output (stdout, single-line JSON):
  {"true_pending":  int|null,
   "patches_applied": [[old, new], ...],
   "patched":       bool,
   "divergence":    "family_fold"|"review_sibling"|"stale_session"|"unknown"|null,
   "reason":        str}

Exit code: always 0 on well-formed CLI (soft errors surface via reason
field so the calling scripts/handoff can never be blocked by this helper).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def compute_true_pending(handoff_tasks_path: Path) -> Optional[int]:
    """Count pending tasks in the open_tasks array. Mirrors the original jq:
    `[(.open_tasks // [])[] | select(.status == "pending")] | length`.
    Returns None if file missing/unreadable/malformed or open_tasks not a list.
    """
    try:
        with handoff_tasks_path.open() as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    open_tasks = data.get("open_tasks", [])
    if not isinstance(open_tasks, list):
        return None
    return sum(
        1 for t in open_tasks
        if isinstance(t, dict) and t.get("status") == "pending"
    )


def classify_divergence(data: dict) -> str:
    """Heuristic label for the divergence source based on handoff-tasks.json
    metadata written by _emit_handoff_tasks_json. Used for telemetry only —
    not a decision input.

    Priority (first match wins): family_fold → review_sibling → stale_session → unknown.
    """
    if isinstance(data.get("families_gt1"), int) and data["families_gt1"] > 0:
        return "family_fold"
    if isinstance(data.get("filtered_pending_parent"), int) and data["filtered_pending_parent"] > 0:
        return "review_sibling"
    if data.get("source_session") == "aggregate":
        return "stale_session"
    return "unknown"


def build_patch_pairs(pending: str, true_pending: int, in_progress: str,
                       blocked: str, review_pending_seg: str,
                       mode: str) -> list[list[str]]:
    """Build the ordered list of [old, new] pairs.

    Header pair is ALWAYS emitted (matches pre-QR-1 behavior). Next-Up
    pairs (Then / Next pending) are gated on mode="on" — the QR-1 unify
    contract. Rollback (mode="off") reverts to header-only.
    """
    old_header = (
        f"- Pending: {pending} | In progress: {in_progress} | "
        f"Blocked: {blocked}{review_pending_seg}"
    )
    new_header = (
        f"- Pending: {true_pending} | In progress: {in_progress} | "
        f"Blocked: {blocked}{review_pending_seg}"
    )
    pairs: list[list[str]] = [[old_header, new_header]]
    if mode == "on":
        pairs.append([
            f"  - Then: {pending} pending task(s) — run TaskList for full list",
            f"  - Then: {true_pending} pending task(s) — run TaskList for full list",
        ])
        pairs.append([
            f"  - Next pending: lowest-ID of {pending} pending task(s) — run TaskList",
            f"  - Next pending: lowest-ID of {true_pending} pending task(s) — run TaskList",
        ])
    return pairs


def apply_patches_to_file(path: Path, pairs: list[list[str]]) -> bool:
    """Apply search-and-replace pairs to file at `path`. Returns True if the
    file contents actually changed. Soft-fails to False on read/write errors.
    """
    try:
        content = path.read_text()
    except (FileNotFoundError, OSError):
        return False
    original = content
    for old, new in pairs:
        content = content.replace(old, new)
    if content != original:
        try:
            path.write_text(content)
        except OSError:
            return False
        return True
    return False


def reconcile(handoff_tasks: Path, staging: Optional[Path], pending: str,
               in_progress: str, blocked: str, review_seg: str, mode: str) -> dict:
    """End-to-end reconcile. Returns a structured result dict (see module
    docstring for schema). Never raises on soft errors."""
    result: dict = {
        "true_pending": None,
        "patches_applied": [],
        "patched": False,
        "divergence": None,
        "reason": "",
    }

    # Gate 1: handoff-tasks.json exists + non-empty
    if not handoff_tasks.exists():
        result["reason"] = "handoff_tasks_file_missing"
        return result
    try:
        if handoff_tasks.stat().st_size == 0:
            result["reason"] = "handoff_tasks_file_empty"
            return result
    except OSError:
        result["reason"] = "handoff_tasks_file_stat_failed"
        return result

    # Gate 2: parse-able JSON
    try:
        with handoff_tasks.open() as f:
            data = json.load(f)
    except json.JSONDecodeError:
        result["reason"] = "handoff_tasks_json_malformed"
        return result

    # Gate 3: extract true_pending
    open_tasks = data.get("open_tasks", [])
    if not isinstance(open_tasks, list):
        result["reason"] = "open_tasks_field_missing_or_invalid"
        return result
    true_pending = sum(
        1 for t in open_tasks
        if isinstance(t, dict) and t.get("status") == "pending"
    )
    result["true_pending"] = true_pending

    # Compare against caller's stale scalar
    try:
        pending_int = int(pending) if pending else 0
    except (ValueError, TypeError):
        pending_int = 0

    if true_pending == pending_int:
        result["reason"] = "no_divergence"
        return result

    # Divergence — classify + build patch pairs
    result["divergence"] = classify_divergence(data)
    pairs = build_patch_pairs(
        pending, true_pending, in_progress, blocked, review_seg, mode
    )
    result["patches_applied"] = pairs

    # Apply to staging file if provided
    if staging is not None:
        result["patched"] = apply_patches_to_file(staging, pairs)

    result["reason"] = "reconciled"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile handoff.md pending scalar against open_tasks array"
    )
    parser.add_argument("--handoff-tasks", required=True, type=Path)
    parser.add_argument("--staging", type=Path, default=None)
    parser.add_argument("--pending", default="0")
    parser.add_argument("--in-progress", default="0")
    parser.add_argument("--blocked", default="0")
    parser.add_argument("--review-seg", default="")
    parser.add_argument("--mode", default="on", choices=["on", "off"])
    args = parser.parse_args()

    result = reconcile(
        handoff_tasks=args.handoff_tasks,
        staging=args.staging,
        pending=args.pending,
        in_progress=args.in_progress,
        blocked=args.blocked,
        review_seg=args.review_seg,
        mode=args.mode,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
