#!/usr/bin/env python3
"""
V11 handoff-layer task family fold (T1 of v11-handoff-hygiene).

Clusters near-duplicate task subjects across sessions so the handoff emits ONE
entry per conceptual task instead of N raw entries when two sessions phrased
the same work differently.

Algorithm: greedy single-linkage on salient-token sets, using Jaccard OR
overlap-coefficient (same family of metrics V11.15.4's flywheel-ingest uses).
Thresholds (jac=0.25, ovl=0.45) tuned on the claude-trader-pro dogfood —
all 5 known cross-session duplicate pairs cluster.

Known limitation: pure token-overlap cannot distinguish "same conceptual task,
different phrasing" from "same verb on different object" without semantic
understanding. Pairs like "Add migration for users table" and "Add migration
for products table" will OVER-MERGE. Mitigation: every family carries the
full family_members[] list with raw subjects; the receiving session is
explicitly directed to verify before treating a family as a single task.

This is a READ-TIME fold — input ledger/aggregate entries stay untouched; the
output is a transient handoff artifact. Manifest captures every cluster
decision for audit.

Usage:
    cat tasks.json | python3 family_fold.py [--threshold-jaccard 0.30]
                                            [--threshold-overlap 0.50]
                                            [--exact-only]
    python3 family_fold.py --input tasks.json --output folded.json

Input schema (JSON array):
    [{"id": str, "subject": str, "description": str?, "status": str?,
      "metadata": dict?, "source_session_uuid": str?, ...}, ...]

Output schema (JSON object):
    {
      "families": [{
        "family_id": str,
        "canonical_subject": str,
        "subject_norm": str,
        "status": str,
        "description": str?,
        "metadata": dict,
        "family_members": [
          {"id": str, "subject": str, "subject_norm": str,
           "status": str, "source_session_uuid": str?, "description": str?}
        ],
        "size": int,
        "has_mixed_statuses": bool,
        "has_completed_member": bool
      }],
      "manifest": {
        "fold_version": "v1",
        "input_count": int,
        "output_count": int,
        "threshold_jaccard": float,
        "threshold_overlap": float,
        "exact_only": bool,
        "cluster_decisions": [...]
      }
    }

Rollback / env-var control (handoff layer):
    V11_FOLD_FAMILIES=off       → caller should not invoke this script
    V11_FOLD_JACCARD=<float>    → override --threshold-jaccard default
    V11_FOLD_OVERLAP=<float>    → override --threshold-overlap default
    V11_FOLD_EXACT_ONLY=1       → equivalent to --exact-only

Determinism: input is processed in input order, ties broken lexicographically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Any

# Reuse the canonical subject normalizer (ADR-LEDGER §2.1)
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
try:
    from normalize_subject import normalize_subject  # type: ignore
except ImportError:
    # Fallback when invoked outside the v11/scripts/lib tree
    def normalize_subject(s: str) -> str:  # type: ignore[no-redef]
        if not isinstance(s, str):
            return "__empty__"
        s = s.casefold().strip()
        s = re.sub(r"\s+", " ", s)
        return s or "__empty__"


# ---------------------------------------------------------------------------
# Salient tokens — copied from flywheel-ingest._sal_tokens with a slightly
# expanded stopword list tuned for task subjects (verbs like "fix", "add",
# "implement" are themselves common in task titles so we keep them; we drop
# only the genuinely-noisy connectives).
# ---------------------------------------------------------------------------
_STOP = set(
    (
        "the a an of to is it on in this and or for not be as by we i its "
        "itself per still so use uses needs which should sets real "
        "that with into any value off only run runs single each fresh are was "
        "has have had but if then else when from at out non its can may must "
        "more most less than over under via no yes new old all both "
        # V11.18.2: "task" is universally non-discriminative in V11 (every
        # task subject is a "task"). Fixture-style subjects like "task 1",
        # "task 2" would collapse on this single shared token; real
        # subjects don't use the word "task" as a discriminator. Same for
        # "todo" / "todos" — common in test data, never carries identity.
        "task tasks todo todos"
    ).split()
)


def salient_tokens(s: str) -> set[str]:
    """Lowercased token set, stopwords + <=2-char noise dropped."""
    if not isinstance(s, str):
        return set()
    return {
        t
        for t in re.findall(r"[a-z0-9][a-z0-9_+.\-]*", s.casefold())
        if len(t) > 2 and t not in _STOP
    }


# ---------------------------------------------------------------------------
# Status priority for canonical selection.
# in_progress beats pending beats completed beats stale.
# Rationale: a task someone is currently working on is the most-recent claim
# about it. A "completed" sibling in a family is INFORMATION (worth surfacing
# via has_completed_member), but the family's representative should be the
# active in_progress entry so the receiving session knows what's live.
# ---------------------------------------------------------------------------
_STATUS_PRIORITY = {
    "in_progress": 0,
    "pending": 1,
    "completed": 2,
    "stale": 3,
}


def _status_rank(s: str) -> int:
    return _STATUS_PRIORITY.get(s or "", 99)


def _family_id(canonical_subject_norm: str) -> str:
    """Stable 12-char ID derived from canonical subject_norm."""
    h = hashlib.sha256(canonical_subject_norm.encode("utf-8")).hexdigest()
    return f"fam-{h[:12]}"


def _pick_canonical(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the most informative member as the family canonical.

    Priority (lower wins):
        1. status rank (in_progress > pending > completed > stale)
        2. largest salient-token set (most specific subject)
        3. longest description (most detail)
        4. lex-smallest id (deterministic tiebreak)
    """
    def key(m: dict[str, Any]) -> tuple:
        return (
            _status_rank(m.get("status", "")),
            -len(salient_tokens(m.get("subject", ""))),
            -len(m.get("description") or ""),
            str(m.get("id") or ""),
        )

    return sorted(members, key=key)[0]


def _similar(
    a_tok: set[str],
    b_tok: set[str],
    jac_thr: float,
    ovl_thr: float,
) -> tuple[bool, float, float]:
    """Return (clusters?, jaccard, overlap) for two salient-token sets."""
    if not a_tok or not b_tok:
        return (False, 0.0, 0.0)
    inter = len(a_tok & b_tok)
    if inter == 0:
        return (False, 0.0, 0.0)
    union = len(a_tok | b_tok)
    jac = inter / union if union else 0.0
    ovl = inter / min(len(a_tok), len(b_tok))
    return (jac >= jac_thr or ovl >= ovl_thr, jac, ovl)


def fold_families(
    tasks: list[dict[str, Any]],
    jac_thr: float = 0.25,
    ovl_thr: float = 0.45,
    exact_only: bool = False,
) -> dict[str, Any]:
    """Cluster tasks into families.

    See module docstring for the input/output schemas.
    """
    # Normalize and pre-tokenize every task once
    enriched: list[dict[str, Any]] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        subj = t.get("subject") or ""
        norm = normalize_subject(subj)
        tok = salient_tokens(subj)
        enriched.append({**t, "subject_norm": norm, "_tok": tok})

    clusters: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    for entry in enriched:
        placed = False
        norm = entry["subject_norm"]
        tok = entry["_tok"]

        for cl in clusters:
            # Exact match path: subject_norm equality is a strong signal even
            # when --exact-only is off (skip Jaccard cost when it already holds).
            if norm and norm == cl["canonical_subject_norm"]:
                cl["members"].append(entry)
                decisions.append({
                    "family_id": cl["family_id"],
                    "added_id": entry.get("id"),
                    "reason": "subject_norm_exact",
                    "jaccard": 1.0,
                    "overlap": 1.0,
                })
                placed = True
                break

            if exact_only:
                continue

            # Fuzzy match against ANY existing cluster member's tokens
            best_jac = 0.0
            best_ovl = 0.0
            matched = False
            for m in cl["members"]:
                ok, jac, ovl = _similar(tok, m["_tok"], jac_thr, ovl_thr)
                if jac > best_jac:
                    best_jac = jac
                if ovl > best_ovl:
                    best_ovl = ovl
                if ok:
                    matched = True
                    break

            if matched:
                cl["members"].append(entry)
                decisions.append({
                    "family_id": cl["family_id"],
                    "added_id": entry.get("id"),
                    "reason": "token_overlap",
                    "jaccard": round(best_jac, 3),
                    "overlap": round(best_ovl, 3),
                })
                placed = True
                break

        if not placed:
            fid = _family_id(norm or "__empty__")
            clusters.append({
                "family_id": fid,
                "canonical_subject_norm": norm,
                "members": [entry],
            })
            decisions.append({
                "family_id": fid,
                "added_id": entry.get("id"),
                "reason": "new_cluster",
                "jaccard": 0.0,
                "overlap": 0.0,
            })

    # Build output families
    families: list[dict[str, Any]] = []
    for cl in clusters:
        members = cl["members"]
        canon = _pick_canonical(members)
        statuses = {m.get("status", "") for m in members}
        family_members_out = [
            {
                "id": m.get("id"),
                "subject": m.get("subject"),
                "subject_norm": m.get("subject_norm"),
                "status": m.get("status"),
                "source_session_uuid": m.get("source_session_uuid"),
                "description": m.get("description"),
            }
            for m in members
        ]

        # Build the family record. Canonical's metadata is preserved and
        # extended with family_size / member ids for downstream consumers.
        canon_meta = dict(canon.get("metadata") or {})
        canon_meta["family_size"] = len(members)
        if len(members) > 1:
            canon_meta["family_member_ids"] = [
                str(m.get("id")) for m in members if m.get("id") is not None
            ]

        family_record = {
            "family_id": cl["family_id"],
            # Both `subject` (drop-in compat for legacy consumers like
            # v11-resume-tasks) and `canonical_subject` (explicit family
            # semantics for new consumers) point at the same value.
            "subject": canon.get("subject"),
            "canonical_subject": canon.get("subject"),
            "subject_norm": canon.get("subject_norm"),
            "status": canon.get("status"),
            "description": canon.get("description"),
            "metadata": canon_meta,
            "family_members": family_members_out,
            "size": len(members),
            "has_mixed_statuses": len(statuses) > 1,
            "has_completed_member": "completed" in statuses,
            # Preserve source_session_uuid for the canonical (useful for v11-resume-tasks)
            "source_session_uuid": canon.get("source_session_uuid"),
            # Preserve the canonical's original id so v11-resume-tasks can keep
            # an audit-trail of which raw task became the family canonical.
            "id": canon.get("id"),
        }
        # Propagate the staleness flags set by the upstream handoff staleness
        # stage (scripts/handoff jq emits {status:"stale", stale:true,
        # stale_reason:...} on an all-terminated group). The explicit field list
        # above carries `status` through but would otherwise DROP the boolean
        # `stale` + its `stale_reason` — the receiver-facing "VERIFY before
        # re-creating, do not blind-resume" guidance. Emit only when the
        # canonical actually carries them so non-stale families stay
        # byte-identical for existing consumers.
        if canon.get("stale") is not None:
            family_record["stale"] = canon.get("stale")
        if canon.get("stale_reason") is not None:
            family_record["stale_reason"] = canon.get("stale_reason")
        families.append(family_record)

    manifest = {
        "fold_version": "v1",
        "input_count": len(tasks),
        "output_count": len(families),
        "threshold_jaccard": jac_thr,
        "threshold_overlap": ovl_thr,
        "exact_only": exact_only,
        "cluster_decisions": decisions,
    }

    return {"families": families, "manifest": manifest}


def propose_merge(
    families: list[dict[str, Any]],
    original_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Propose ledger merges for families that are safe to consolidate.

    A merge is proposed ONLY when ALL of:
      1. family_size > 1
      2. All members share the same metadata.sprint value
      3. All member subjects are normalize_subject-equal (identical subject_norm)

    Guards the known over-merge case (see test_family_fold.py::TestKnownLimitations):
    families created by fuzzy token-overlap — where subjects differ after
    normalization — are silently skipped. No cross-sprint proposals ever fire.

    Args:
        families: the ``families`` list from a ``fold_families()`` return value.
        original_tasks: the same task list that was passed to ``fold_families()``.
            Used to read ``metadata.sprint`` for each member (fold_families does
            not thread sprint into family_members_out).

    Returns:
        A list of proposal dicts. Each proposal is data only — this function
        NEVER writes anything. Fields per proposal:
            family_id       str   — stable family identifier
            canonical       dict  — {id, subject, subject_norm, status}
            non_canonical   list  — [{id, subject, subject_norm, status}, ...]
            sprint          str   — shared sprint (or "__missing__" when absent)
            family_size     int   — total member count
            reason          str   — always "same_sprint_same_norm"
    """
    # Build id -> metadata lookup from original tasks (sprint lives in metadata).
    meta_by_id: dict[str, dict[str, Any]] = {}
    for t in original_tasks:
        if isinstance(t, dict) and t.get("id") is not None:
            meta_by_id[str(t["id"])] = t.get("metadata") or {}

    proposals: list[dict[str, Any]] = []
    for family in families:
        members = family.get("family_members", [])
        if len(members) <= 1:
            continue

        # Guard 1: all subject_norms must be identical.
        # Fuzzy-matched families can contain members with different subject_norms;
        # proposing a merge on those would reproduce the known over-merge bug.
        norms = {m.get("subject_norm", "") for m in members}
        if len(norms) != 1:
            continue

        # Guard 2: all members must share the same metadata.sprint.
        # Cross-sprint merges are always blocked — different sprints imply
        # the same conceptual task was re-created in a new planning cycle.
        sprints: set[str] = set()
        for m in members:
            mid = str(m.get("id") or "")
            raw_sprint = meta_by_id.get(mid, {}).get("sprint")
            sprints.add(str(raw_sprint) if raw_sprint is not None else "__missing__")
        if len(sprints) != 1:
            continue

        sprint = next(iter(sprints))

        # Guard 3 (V11.27 review L1): an absent sprint is too ambiguous to
        # auto-merge. If no member carries metadata.sprint, sprints == {"__missing__"}
        # would pass Guard 2 — but tasks from different planning cycles can both
        # lack a sprint and must NOT be folded on subject_norm alone. Skip; leave
        # for manual review rather than risk a cross-cycle over-merge.
        if sprint == "__missing__":
            continue

        # Identify canonical: the family's representative task (family["id"]).
        canonical_id = str(family.get("id") or "")
        canonical = next(
            (m for m in members if str(m.get("id") or "") == canonical_id),
            members[0],
        )
        non_canonical = [m for m in members if str(m.get("id") or "") != canonical_id]
        if not non_canonical:
            continue  # degenerate: all members map to the same id

        proposals.append({
            "family_id": family["family_id"],
            "canonical": {
                "id": canonical.get("id"),
                "subject": canonical.get("subject"),
                "subject_norm": canonical.get("subject_norm"),
                "status": canonical.get("status"),
            },
            "non_canonical": [
                {
                    "id": m.get("id"),
                    "subject": m.get("subject"),
                    "subject_norm": m.get("subject_norm"),
                    "status": m.get("status"),
                }
                for m in non_canonical
            ],
            "sprint": sprint,
            "family_size": len(members),
            "reason": "same_sprint_same_norm",
        })

    return proposals


def _resolve_env_thresholds(
    jac_thr: float,
    ovl_thr: float,
    exact_only: bool,
) -> tuple[float, float, bool]:
    """Apply V11_FOLD_* env-var overrides over CLI defaults."""
    env_jac = os.environ.get("V11_FOLD_JACCARD")
    env_ovl = os.environ.get("V11_FOLD_OVERLAP")
    env_exact = os.environ.get("V11_FOLD_EXACT_ONLY")
    if env_jac:
        try:
            jac_thr = float(env_jac)
        except ValueError:
            pass
    if env_ovl:
        try:
            ovl_thr = float(env_ovl)
        except ValueError:
            pass
    if env_exact and env_exact.strip().lower() in ("1", "true", "yes", "on"):
        exact_only = True
    return jac_thr, ovl_thr, exact_only


def main() -> int:
    ap = argparse.ArgumentParser(description="V11 task family fold (handoff layer)")
    ap.add_argument("--threshold-jaccard", type=float, default=0.25)
    ap.add_argument("--threshold-overlap", type=float, default=0.45)
    ap.add_argument(
        "--exact-only",
        action="store_true",
        help="Only fold byte-identical subject_norm matches (no fuzzy)",
    )
    ap.add_argument(
        "--input",
        help="Read input JSON array from this path (default: stdin)",
    )
    ap.add_argument(
        "--output",
        help="Write output JSON to this path (default: stdout)",
    )
    args = ap.parse_args()

    jac, ovl, exact = _resolve_env_thresholds(
        args.threshold_jaccard, args.threshold_overlap, args.exact_only
    )

    # Read input
    if args.input:
        with open(args.input, "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = sys.stdin.read()
    raw = (raw or "").strip()
    if not raw:
        raw = "[]"

    try:
        tasks = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"family_fold: invalid input JSON: {e}", file=sys.stderr)
        return 2

    if not isinstance(tasks, list):
        print(
            "family_fold: input must be a JSON array of task objects",
            file=sys.stderr,
        )
        return 2

    out = fold_families(tasks, jac_thr=jac, ovl_thr=ovl, exact_only=exact)

    serialized = json.dumps(out, indent=2, sort_keys=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(serialized)
    else:
        sys.stdout.write(serialized)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
