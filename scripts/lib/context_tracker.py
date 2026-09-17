"""V11 Context Tracker: Heuristic estimator for Claude Code context window usage.

Claude Code does not expose token counts directly. This module estimates usage
based on observable signals (hook calls, file reads, Bash commands, etc.).

Estimates are intentionally conservative (biased to over-estimate) so warnings
fire early rather than late.

Token heuristics:
  hook         ~500 tokens  (tool call + response overhead)
  file_read    ~bytes / 4   (rough chars-to-tokens for source code)
  file_write   ~1000 tokens (diff + confirmation)
  bash         ~800 tokens  (command + output)
  task         ~300 tokens  (TaskCreate / TaskUpdate)
  conversation ~1200 tokens (one round-trip: 200 user + 1000 assistant)

Context window: 1,000,000 tokens.

Session scoping (fixed 2026-08-02): state used to live at one global,
un-scoped file shared by every V11 session on the host, with the only
reset path being hooks/post-compact (manual compaction). Nothing reset it
on a fresh session, so usage accumulated across sessions indefinitely —
confirmed live at 105%+ of the window after 16 days / 3510 events from
unrelated sessions, tripping false CRITICAL alerts on brand-new sessions.
Fix mirrors the existing sessions/$V11_SESSION_ID/task-state.json
convention (hooks/lib/common.sh): when a session_id is supplied, state is
scoped to sessions/{session_id}/context-estimate.json. context_file
(explicit override, used by tests and callers that manage their own path)
still wins over both. Omitting session_id keeps the legacy global path for
backward compatibility (manual `context-status` inspection has no session
context to scope by). A staleness fallback (_STALE_AFTER_SECONDS) resets
state that hasn't been touched recently, as a backstop against any bucket
(e.g. the "legacy-cli" fallback) being shared longer than intended.
"""

import calendar
import fcntl
import json
import os
import re
import time
from typing import Dict, Optional, Any

# Token weights by event type
_TOKEN_WEIGHTS = {
    "hook": 500,
    "file_read": 0,   # computed from bytes
    "file_write": 1000,
    "bash": 800,
    "task": 300,
    "conversation": 1200,
}

_BYTES_PER_TOKEN = 4        # rough estimate for source code / prose
_CONTEXT_WINDOW = 1_000_000  # Claude's 1M context window

_THRESHOLDS = [
    (0.85, "critical"),
    (0.70, "alert"),
    (0.50, "warning"),
    (0.00, "ok"),
]

_METRICS_DIR = os.path.expanduser("~/.agent-metrics")
# Same well-formedness check hooks/lib/common.sh applies to V11_SESSION_ID
# before trusting it as a path component.
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_STALE_AFTER_SECONDS = 6 * 3600  # belt-and-suspenders: force-reset a bucket idle this long


def _percent_to_threshold(percent: float) -> str:
    for cutoff, label in _THRESHOLDS:
        if percent >= cutoff:
            return label
    return "ok"


def _default_context_file(session_id: Optional[str]) -> str:
    """Resolve the state file path for a given session_id.

    Mirrors hooks/lib/common.sh's sessions/$V11_SESSION_ID/ convention so a
    fresh session naturally starts at zero instead of inheriting whatever
    total every other session on the host has already accumulated.
    """
    if session_id:
        safe = session_id if _SESSION_ID_RE.match(session_id) else "legacy-cli"
        return os.path.join(_METRICS_DIR, "sessions", safe, "context-estimate.json")
    # No session_id given at all (e.g. manual `context-status` inspection) —
    # fall back to the pre-fix global path for backward compatibility.
    return os.path.join(_METRICS_DIR, "context-estimate.json")


def _fresh_state(session_id: Optional[str]) -> Dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "estimated_tokens": 0,
        "event_counts": {},
        "session_start": now,
        "last_updated": now,
        "session_id": session_id or "",
    }


def _is_stale(data: Dict[str, Any]) -> bool:
    """True if the loaded bucket hasn't been touched in _STALE_AFTER_SECONDS."""
    last_updated = data.get("last_updated")
    if not last_updated:
        return False
    try:
        last_epoch = calendar.timegm(time.strptime(last_updated, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return False
    return (time.time() - last_epoch) > _STALE_AFTER_SECONDS


class ContextTracker:
    """Heuristic estimator for context window token usage.

    Stores running totals in a JSON file so state persists across
    hook invocations and tool calls within a session.

    Usage::

        tracker = ContextTracker()
        tracker.record_event("file_read", {"bytes": 4096})
        tracker.record_event("bash")
        est = tracker.get_estimate()
        print(est["percent_used"], est["threshold"])
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        context_file: Optional[str] = None,
    ):
        self.session_id = session_id
        self.context_file = context_file or _default_context_file(session_id)
        self.estimates = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_event(
        self, event_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Record a tool-call event and add its token estimate.

        Args:
            event_type: One of "hook", "file_read", "file_write",
                        "bash", "task", "conversation".
            metadata:   Optional dict.  For "file_read", pass
                        ``{"bytes": N}`` to compute tokens from file size.

        Returns:
            Tokens added for this event.
        """
        metadata = metadata or {}

        if event_type == "file_read":
            byte_count = int(metadata.get("bytes", 0))
            tokens = max(1, byte_count // _BYTES_PER_TOKEN)
        else:
            tokens = _TOKEN_WEIGHTS.get(event_type, 300)

        # File lock protects read-modify-write cycle from concurrent hooks
        lock_path = self.context_file + ".lock"
        try:
            os.makedirs(os.path.dirname(lock_path), exist_ok=True)
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            self._load()  # Re-read under lock to get latest state

            self.estimates["estimated_tokens"] = (
                self.estimates.get("estimated_tokens", 0) + tokens
            )
            counts = self.estimates.setdefault("event_counts", {})
            counts[event_type] = counts.get(event_type, 0) + 1
            self.estimates["last_updated"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            self._save()
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass

        return tokens

    def get_estimate(self) -> Dict[str, Any]:
        """Return the current context usage estimate.

        Returns a dict with::

            {
                "estimated_tokens": int,
                "percent_used":     float,   # 0.0 – 100.0
                "events":           int,
                "threshold":        str,     # "ok" | "warning" | "alert" | "critical"
                "context_window":   int,
                "event_counts":     dict,
                "session_start":    str,
                "last_updated":     str,
            }
        """
        estimated = self.estimates.get("estimated_tokens", 0)
        percent = (estimated / _CONTEXT_WINDOW) * 100.0

        counts = self.estimates.get("event_counts", {})
        total_events = sum(counts.values())

        return {
            "estimated_tokens": estimated,
            "percent_used": percent,
            "events": total_events,
            "threshold": _percent_to_threshold(percent / 100.0),
            "context_window": _CONTEXT_WINDOW,
            "event_counts": dict(counts),
            "session_start": self.estimates.get("session_start", ""),
            "last_updated": self.estimates.get("last_updated", ""),
        }

    def reset(self) -> None:
        """Reset tracker for a new session, preserving session_id."""
        self.estimates = _fresh_state(self.session_id)
        self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        """Load state from the JSON file, initialising if missing, corrupt, or stale."""
        try:
            with open(self.context_file, "r") as fh:
                data = json.load(fh)
            # Minimal schema check — must be a dict with the core key
            if not isinstance(data, dict):
                raise ValueError("state file is not a JSON object")
            if _is_stale(data):
                # Bucket hasn't been touched in _STALE_AFTER_SECONDS — treat as a
                # new session rather than keep piling onto a forgotten total.
                return _fresh_state(self.session_id)
            return data
        except (OSError, IOError):
            # File doesn't exist yet — start fresh
            pass
        except (json.JSONDecodeError, ValueError):
            # Corrupt file — start fresh (do not crash)
            pass

        return _fresh_state(self.session_id)

    def _save(self) -> None:
        """Persist state to the JSON file atomically (write-then-rename)."""
        target = self.context_file
        tmp = target + ".tmp"
        try:
            # Ensure parent directory exists
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(tmp, "w") as fh:
                json.dump(self.estimates, fh, indent=2)
                fh.write("\n")

            os.replace(tmp, target)
        except (OSError, IOError):
            # Best-effort persistence; never crash on save failure
            try:
                os.unlink(tmp)
            except OSError:
                pass
