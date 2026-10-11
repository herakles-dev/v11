"""The (session_uuid, tl_epoch, task_id) keying rule (S2-T0b-1, #113).

v11_replay_ledger imports this on every aggregate rebuild (every Task* call),
and scripts/lib/task_epoch.py re-exports it, so both key events the same way.
It imports nothing: the rebuild path pays for these two functions only
(review #20).
"""


def tl_epoch_of(ev):
    """The event's tl_epoch stamp as a positive int, or None when unstamped
    or malformed. Accepts an int, an integral float (a jq that prints
    doubles) and a digit string of at most 30 digits (a writer that used
    --arg), per C4."""
    v = ev.get("tl_epoch")
    if isinstance(v, bool):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    elif isinstance(v, str) and 0 < len(v) <= 30 and v.isascii() and v.isdigit():
        v = int(v)
    return v if isinstance(v, int) and v > 0 else None


def claim_key(ev):
    """(session_uuid, tl_epoch | None, task_id) — the shared keying rule.
    Stamped pairs are exact per TaskList epoch; tl_epoch None is the
    unstamped (legacy) key."""
    tid = ev.get("task_id")
    return (str(ev.get("session_uuid") or ""), tl_epoch_of(ev), "" if tid is None else str(tid))
