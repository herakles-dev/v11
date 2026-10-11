#!/usr/bin/env python3
"""
handoff_identity.py — S1-T2 (#75b): identity keys for handoff consumers.

A task's numeric id is session-local: every session's TaskCreate counter
starts at 1, and a rehydrated task gets a fresh id in the new session. So
comparing handoff-tasks.json ids with the new session's ids flagged a clean
rehydrate as identity_mismatch, and passed two different tasks that happened
to share an id.

The canonical identity is the ledger's (subject_norm, create_seq). S1-T1
stamps it on each handoff-tasks.json entry as .identity; sync-tasks keeps it
per live task as open_tasks[id]._idk. Rehydrate verification compares the
MULTISET of subject_norms: create_seq can legitimately differ (a live
_idk.create_seq is 0 until the ledger confirms it, and pre-S1 entries carry
none). An entry without an identity falls back to normalize_subject(subject).
A live task rehydrated by v11-resume-tasks is keyed on the identity it came
from (metadata.rehydrated_from.identity), so a task renamed before the
handoff still matches (review #70).

CLI:
    handoff_identity.py delta HANDOFF_TASKS_JSON LIVE_TASK_STATE_JSON
        prints {"missing": [...], "extra": [...]} — both empty when the
        live open tasks are exactly the handoff's tasks. Exit 1 on bad input.
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from normalize_subject import normalize_subject  # noqa: E402


def _key(sn, subject):
    return sn or normalize_subject(subject or "")


def handoff_keys(doc):
    """One key per handoff-tasks.json entry (a family entry rehydrates as one task)."""
    keys = []
    for t in (doc.get("open_tasks") or []) if isinstance(doc, dict) else []:
        if isinstance(t, dict):
            ident = t.get("identity")
            keys.append(_key(ident.get("subject_norm") if isinstance(ident, dict) else None,
                             t.get("subject")))
    return keys


def _rehydrated_sn(task):
    """subject_norm of the identity a rehydrated task came from, or None.

    Review #70: a task renamed after creation keeps its creation-time
    identity, so the handoff entry's .identity.subject_norm is the OLD
    norm while the rehydrated task is created under the CURRENT subject
    (its _idk norm is new). v11-resume-tasks stamps the source identity
    into metadata.rehydrated_from.identity; compare on that when present.
    """
    md = task.get("metadata")
    rf = md.get("rehydrated_from") if isinstance(md, dict) else None
    ident = rf.get("identity") if isinstance(rf, dict) else None
    sn = ident.get("subject_norm") if isinstance(ident, dict) else None
    return sn if isinstance(sn, str) and sn else None


def live_keys(state):
    """One key per live open task (status != completed), matching detect-project's count."""
    ot = state.get("open_tasks") if isinstance(state, dict) else None
    items = ot.values() if isinstance(ot, dict) else (ot if isinstance(ot, list) else [])
    keys = []
    for t in items:
        if isinstance(t, dict) and t.get("status") != "completed":
            idk = t.get("_idk")
            keys.append(_rehydrated_sn(t)
                        or _key(idk.get("subject_norm") if isinstance(idk, dict) else None,
                                t.get("subject")))
    return keys


def delta(expected, actual):
    e, a = Counter(expected), Counter(actual)
    return {"missing": sorted((e - a).elements()), "extra": sorted((a - e).elements())}


def main(argv):
    if len(argv) != 4 or argv[1] != "delta":
        print(__doc__.strip().splitlines()[-4], file=sys.stderr)
        return 1
    try:
        with open(argv[2], encoding="utf-8") as fh:
            handoff = json.load(fh)
        with open(argv[3], encoding="utf-8") as fh:
            live = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"handoff_identity: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(delta(handoff_keys(handoff), live_keys(live))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
