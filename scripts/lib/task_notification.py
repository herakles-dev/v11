"""Parse Claude Code <task-notification> blocks (S1-T9, #72; shared with #69: parse once).

The harness appends one of these to the PARENT session transcript each time a
background subagent stops (S1-P2 spike, Claude Code 2.1.283):

    <task-notification>
    <task-id>a8b250be6290c02b4</task-id>
    <tool-use-id>toolu_...</tool-use-id>
    <status>completed</status>
    ...
    <usage><subagent_tokens>24879</subagent_tokens><tool_uses>0</tool_uses><duration_ms>1621</duration_ms></usage>
    </task-notification>

subagent_tokens is input + output + cache_creation + cache_read of the agent's
LAST assistant turn, i.e. its final context size (26/26 notifications matched
their transcript's last turn, 2026-09-26). It suits a context-budget check
(#69); it is not the tokens billed over the run, so it can't give a $ figure.
The format is undocumented, so every field is optional and a malformed block
is skipped, never raised. The same task-id can notify more than once (resumed
agents).
"""
from __future__ import annotations

import re

_BLOCK = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
_FIELDS = ("task-id", "tool-use-id", "status", "subagent_tokens", "tool_uses", "duration_ms")
_FIELD_RE = {name: re.compile(rf"<{name}>\s*(.*?)\s*</{name}>", re.S) for name in _FIELDS}


def _field(body: str, name: str) -> str | None:
    m = _FIELD_RE[name].search(body)
    return m.group(1) if m and m.group(1) else None


def _int(raw: str | None) -> int | None:
    return int(raw) if raw is not None and raw.isdigit() else None


def parse_task_notifications(text: str) -> list[dict]:
    """Return one dict per block that carries a task-id.

    Keys: task_id, tool_use_id, status (str | None) and subagent_tokens,
    tool_uses, duration_ms (int | None; None when absent or non-numeric).
    """
    out = []
    if not isinstance(text, str) or "<task-notification>" not in text:
        return out
    for m in _BLOCK.finditer(text):
        body = m.group(1)
        task_id = _field(body, "task-id")
        if not task_id:
            continue
        out.append({
            "task_id": task_id,
            "tool_use_id": _field(body, "tool-use-id"),
            "status": _field(body, "status"),
            "subagent_tokens": _int(_field(body, "subagent_tokens")),
            "tool_uses": _int(_field(body, "tool_uses")),
            "duration_ms": _int(_field(body, "duration_ms")),
        })
    return out
