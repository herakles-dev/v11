#!/usr/bin/env python3
"""
V11.25 post-commit hook ledger analysis helper.

Usage:
    python3 postcommit_analysis.py PROJECT LEDGER_FILE COMMIT_SHA PATTERNS_RAW V11_HOME

Replays the project ledger to find in_progress tasks matching the given
sprint-task patterns, checks idempotency (same commit_sha already closed),
and prints one tab-separated line per closeable task:
    PATTERN\tSUBJECT_NORM\tCREATE_SEQ\tTASK_ID

Exit 0 on success (output may be empty if no tasks to close).
Exit 1 on fatal error (ledger unreadable, etc.).
"""

import sys
import os
import json
import re

def main():
    if len(sys.argv) < 6:
        print(f"Usage: {sys.argv[0]} PROJECT LEDGER_FILE COMMIT_SHA PATTERNS_RAW V11_HOME [EXCLUDED_IDS]", file=sys.stderr)
        sys.exit(1)

    project      = sys.argv[1]
    ledger_path  = sys.argv[2]
    commit_sha   = sys.argv[3]
    patterns_raw = sys.argv[4]   # newline-separated sprint-task patterns
    v11_home     = sys.argv[5]
    # Optional: comma-separated task IDs excluded due to HYPOTHESIZED pairs
    excluded_raw = sys.argv[6] if len(sys.argv) > 6 else ""
    excluded_ids: set[str] = {t.strip() for t in excluded_raw.split(",") if t.strip()}

    if v11_home:
        sys.path.insert(0, os.path.join(v11_home, "scripts", "lib"))

    try:
        from normalize_subject import normalize_subject
    except ImportError:
        import unicodedata
        _ID_PRE = re.compile(r"^\s*(?:#?\d+[.):\-]?\s+|t-?\d+[.):\-]?\s+|task\s+#?\d+[.):\-]?\s+)", re.IGNORECASE)
        _WS = re.compile(r"\s+")
        _PU = re.compile(r"[.,:;!?_/\\|\-]+")
        _SC = ' \t\r\n.,:;!?\\-_/\\|"\'`()[]{}'
        def normalize_subject(s):
            s = unicodedata.normalize("NFC", s).casefold()
            s = _ID_PRE.sub("", s, 1)
            s = _WS.sub(" ", s).strip(_SC)
            s = _PU.sub(" ", s)
            s = _WS.sub(" ", s).strip()
            return s[:200] or "__empty__"

    patterns = [p.strip() for p in patterns_raw.split("\n") if p.strip()]
    if not patterns:
        sys.exit(0)

    # Parse ledger
    try:
        with open(ledger_path, "r", encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.read().split("\n")
    except OSError as exc:
        print(f"LEDGER-READ-ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Replay: track last-known status per (subject_norm, create_seq) identity.
    # Also detect tasks already closed by THIS commit_sha (idempotency).
    # by_idk maps idk_key -> record dict.
    by_idk = {}
    commit_already_used = set()   # task_ids closed by this commit_sha

    for raw in raw_lines:
        if not raw.strip():
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict) or ev.get("v") != 1 or ev.get("project") != project:
            continue

        sn  = ev.get("subject_norm", "")
        cs  = ev.get("create_seq")
        if not sn or cs is None:
            continue

        idk = f"{sn}\x00{cs}"
        ev_type = ev.get("ev", "")

        if idk not in by_idk:
            by_idk[idk] = {
                "status": ev_type if ev_type in ("pending", "in_progress", "completed", "blocked") else "unknown",
                "subject_norm": sn,
                "create_seq": cs,
                "task_id": ev.get("task_id", ""),
            }
        else:
            if ev_type in ("pending", "in_progress", "completed", "blocked"):
                by_idk[idk]["status"] = ev_type
            if ev.get("task_id"):
                by_idk[idk]["task_id"] = ev.get("task_id")

        # Idempotency check
        if ev_type == "completed" and ev.get("commit_sha") == commit_sha:
            tid = ev.get("task_id", "")
            if tid:
                commit_already_used.add(tid)

    # For each pattern, find matching in_progress tasks
    for pattern in patterns:
        # Normalize pattern: e.g. "S55-T2" → normalized form used as prefix
        # Task subjects are stored as "S55-T2: description" → normalized
        # We match subject_norm that starts with normalize("S55-T2")
        # with a space/separator following (word boundary).
        pattern_norm = normalize_subject(pattern)
        if not pattern_norm or pattern_norm == "__empty__":
            continue

        for idk, rec in by_idk.items():
            sn      = rec["subject_norm"]
            task_id = rec["task_id"]
            status  = rec["status"]

            if status != "in_progress":
                continue

            # Match: subject_norm starts with pattern_norm followed by space or end
            sn_lower = sn.lower()
            pn_lower = pattern_norm.lower()

            matched = False
            if sn_lower == pn_lower:
                matched = True
            elif sn_lower.startswith(pn_lower + " "):
                matched = True
            elif sn_lower.startswith(pn_lower + ":"):
                matched = True

            if not matched:
                continue

            # Idempotency: skip if already closed by this commit
            if task_id and task_id in commit_already_used:
                continue

            # Discipline coherence (B2): skip HYPOTHESIZED-paired tasks.
            # The T-token suffix of the pattern (e.g. "T2" from "S55-T2") must
            # not appear in the exclusion set passed from the commit body scanner.
            pattern_t_token = pattern.split("-")[-1] if "-" in pattern else pattern
            if pattern_t_token in excluded_ids or task_id in excluded_ids:
                continue

            # Output line: PATTERN\tSUBJECT_NORM\tCREATE_SEQ\tTASK_ID
            print(f"{pattern}\t{rec['subject_norm']}\t{rec['create_seq']}\t{task_id}")

if __name__ == "__main__":
    main()
