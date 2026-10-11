"""S1-P3 (#97, #99) — which ev:"review" ledger rows a reader may count.

A review row is corrected when a LATER ev:"review" row names it with outcome
"waived" (S1-P1: the review was waived) or "void" (S1-P3: the row was bound to
the wrong parent). A correction names its row by:
  - corrects_seqno + corrects_ts — the exact form every writer uses (the pair,
    because the ledger holds duplicate seqnos, #99 item 1);
  - corrects_seqno alone, or corrects_ts alone (with the correction's own
    task_id) — matched only when exactly one earlier review row fits.
A corrected correction corrects nothing, so voiding a waiver brings back the
row it had waived, and voiding a void brings back its target. A "void" row is
never a review itself. "Later" means later in the ledger file; pass the WHOLE
ledger in file order, before any --since window.

Waiver rows themselves are left to each reader: agent-scorecard drops them
from its counts, wave-check reports them as "waived" coverage.

A void row is an ordinary ev:"review" row with review_severity "NONE" (seqno
421 voids 311), so a reader that counts review rows without this module
counts it as a clean review of the task it names. Every reader must use it.

One implementation for every reader: agent-scorecard (superseded_review_keys,
is_counted_review) and v11_replay_ledger in hooks/lib/common.sh — the fold's
review branch and the identity view wave-check reads (correction_outcomes).
"""

CORRECTING_OUTCOMES = ("waived", "void")


def row_key(row):
    return (row.get("seqno"), row.get("ts"))


def _outcome(row):
    return str(row.get("outcome") or "").lower()


def correction_outcomes(rows):
    """{row_key: "waived" | "void"} for every ev:"review" row that a later,
    uncorrected ev:"review" row corrects. `rows` is the whole ledger in file order."""
    reviews = [(i, r) for i, r in enumerate(rows) if r.get("ev") == "review"]
    by_pair, by_seqno, by_ts = {}, {}, {}
    for i, r in reviews:
        seqno, ts = r.get("seqno"), r.get("ts")
        if seqno is not None:
            by_pair.setdefault((str(seqno), ts), []).append(i)
            by_seqno.setdefault(str(seqno), []).append(i)
        by_ts.setdefault((ts, str(r.get("task_id") or "")), []).append(i)
    corrected = {}  # row index -> outcome of the row that corrects it
    for i, r in reversed(reviews):
        if i in corrected:
            continue  # a corrected correction corrects nothing
        oc = _outcome(r)
        if oc not in CORRECTING_OUTCOMES:
            continue
        seqno, ts = r.get("corrects_seqno"), r.get("corrects_ts")
        if seqno is not None and ts:
            named = by_pair.get((str(seqno), ts), [])
        elif seqno is not None:
            named = by_seqno.get(str(seqno), [])
        elif ts:
            named = by_ts.get((ts, str(r.get("task_id") or "")), [])
        else:
            continue
        named = [j for j in named if j < i]
        if len(named) == 1:
            corrected.setdefault(named[0], oc)  # the latest correction wins
    return {row_key(rows[j]): oc for j, oc in corrected.items()}


def superseded_review_keys(rows):
    """(seqno, ts) of every ev:"review" row that a later row waives or voids."""
    return set(correction_outcomes(rows))


def is_counted_review(row, superseded):
    """True for an ev:"review" row that still stands. Waivers are included;
    each reader decides what a waiver means."""
    return (row.get("ev") == "review"
            and _outcome(row) != "void"
            and row_key(row) not in superseded)
