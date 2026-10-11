#!/usr/bin/env python3
"""
V11 live roster of agents and skills (D0-1 of v11-leverage-program, ticket #88).

One read-only view of everything the orchestrator can dispatch to, for the
dispatch-advise router (D0-2) to rank against:

  agents  = ~/.agent-registry/agents.json keys that ALSO have
            ~/.claude/agents/<key>.md (maxdepth 1, symlinks followed),
            plus the harness built-ins (kind="builtin", hard-coded) unless an
            .md of the same name shadows one.
  skills  = ~/.claude/skills/<dir>/SKILL.md (name = dir), plus the skills of
            every installed plugin (installed_plugins.json -> installPath/
            skills/<dir>/SKILL.md, name = "<plugin>:<dir>"). Plugins set to
            false in settings.json enabledPlugins are left out, and so are
            marketplace catalog plugins that are not installed.

Each entry: name, kind (agent|builtin|skill), description, triggers (YAML
`triggers:` list plus the quoted phrases after `Triggers:` in the
description), model, tools / disallowed_tools (the tool surface; ["*"] means
inherit everything), path, digest (sha256 of the file bytes).

roster_hash = sha256 over the sorted (name, digest) pairs. Parsed file records
are cached at ~/.agent-metrics/roster-cache.json (or $V11_ROSTER_CACHE) keyed by
(path, mtime_ns, size); a changed file re-parses only that file. The cache is
written atomically (tmp + os.replace) and a failed write is non-fatal.

Advisory and fail-open: an unreadable or malformed file is skipped and listed
in `errors`; load_roster() never raises. If the registry itself is unreadable
the md files alone are used (and the registry error is listed).

Usage:
    python3 roster.py --counts            # counts + roster_hash + errors
    python3 roster.py --json              # full roster
    python3 roster.py --json --no-cache --home /tmp/fakehome

Library:
    from roster import load_roster
    r = load_roster()   # {agents, skills, roster_hash, counts, errors, cache}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# Bump when the parsed-record shape or parser semantics change: a cache written
# by another version is discarded whole.
PARSER_VERSION = 1

# Harness built-in agents with no .md of their own. Descriptions are
# hand-written summaries of the harness's own agent descriptions.
_READ_ONLY_DENY = ["Agent", "Edit", "Write", "NotebookEdit"]
BUILTINS: dict[str, dict[str, Any]] = {
    "Explore": {
        "description": "Read-only search agent for broad fan-out searches across many "
        "files, directories, or naming conventions when only the conclusion is "
        "needed; it locates code rather than reviewing or auditing it.",
        "tools": ["*"],
        "disallowed_tools": _READ_ONLY_DENY,
    },
    "Plan": {
        "description": "Software architect agent for designing implementation plans: "
        "step-by-step strategy, critical files, and architectural trade-offs.",
        "tools": ["*"],
        "disallowed_tools": _READ_ONLY_DENY,
    },
    "general-purpose": {
        "description": "General-purpose agent for researching complex questions, "
        "searching for code, and executing multi-step tasks.",
        "tools": ["*"],
        "disallowed_tools": [],
    },
    "claude": {
        "description": "Catch-all agent for any task that doesn't fit a more "
        "specific agent.",
        "tools": ["*"],
        "disallowed_tools": [],
    },
    "claude-code-guide": {
        "description": "Answers questions about Claude Code (CLI features, hooks, "
        "slash commands, MCP servers, settings, IDE integrations), the Claude "
        "Agent SDK, and the Claude API.",
        "tools": ["Bash", "Read", "WebFetch", "WebSearch"],
        "disallowed_tools": [],
    },
}

_RECORD_KEYS = ("digest", "fm_name", "description", "triggers", "model", "tools", "disallowed_tools")


class FrontmatterError(ValueError):
    """The file opens a YAML frontmatter block this parser cannot read."""


class _SkipFile(Exception):
    """The file is skipped; the message is the reason recorded in errors."""


# ---------------------------------------------------------------------------
# Minimal YAML frontmatter parser (stdlib only)
# ---------------------------------------------------------------------------
# Top-level `key: value` pairs only. Values: plain scalars (folded across
# indented continuation lines, `#` comments stripped), single/double-quoted
# scalars (may span lines), `|` / `>` block scalars, `[a, b]` flow sequences
# and `- item` block sequences. Nested mappings parse to None. Lenient where
# YAML is strict about plain scalars (`description: Foo: bar` is kept as-is),
# strict about structure: an unclosed fence, an unterminated quote or a
# top-level line that is not `key: ...` raises FrontmatterError.

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t]+(.*))?$")
_BLOCK_RE = re.compile(r"^([|>])[+-]?[1-9]?[+-]?[ \t]*(?:#.*)?$")
_FENCE_RE = re.compile(r"^---[ \t]*$")
_END_RE = re.compile(r"^(?:---|\.\.\.)[ \t]*$")
_DQ_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "0": "\0", "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "e": "\x1b", " ": " ", "/": "/", '"': '"',
    "\\": "\\", "N": "\x85", "_": "\xa0", "L": " ", "P": " ",
}


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter, body). frontmatter is None when the text does not
    open with a `---` fence; an opening fence with no closing one raises."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines(keepends=True)
    if not lines or not _FENCE_RE.match(lines[0].rstrip("\r\n")):
        return None, text
    for i in range(1, len(lines)):
        if _END_RE.match(lines[i].rstrip("\r\n")):
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    raise FrontmatterError("frontmatter opened with '---' but never closed")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def _strip_comment(s: str) -> str:
    """Drop a trailing ` # comment` from a plain scalar."""
    m = re.search(r"(?:^|[ \t])#", s)
    return (s[: m.start()] if m else s).strip()


def _plain(s: str) -> str | None:
    s = _strip_comment(s)
    return None if s in ("", "~", "null", "Null", "NULL") else s


def _close_quote(s: str, quote: str) -> int:
    """Index of the closing quote in s (s[0] is the opening quote), or -1."""
    i = 1
    while i < len(s):
        c = s[i]
        if quote == '"' and c == "\\":
            i += 2
            continue
        if c == quote:
            if quote == "'" and i + 1 < len(s) and s[i + 1] == "'":
                i += 2  # '' is an escaped single quote
                continue
            return i
        i += 1
    return -1


def _unescape_dq(s: str) -> str:
    def repl(m: re.Match) -> str:
        e = m.group(1)
        if e[0] in "xuU":
            return chr(int(e[1:], 16))
        return _DQ_ESCAPES.get(e, e)  # unknown escape: keep the char (lenient)

    return re.sub(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.)", repl, s)


def _quoted(lines: list[str], i: int, first: str, lineno: int) -> tuple[str, int]:
    """Parse a quoted scalar starting at `first` (the text after `key:` on line
    i), folding continuation lines with a space. Returns (value, next_i)."""
    quote = first[0]
    text = first
    j = i
    while True:
        end = _close_quote(text, quote)
        if end >= 0:
            break
        j += 1
        if j >= len(lines):
            raise FrontmatterError(f"line {lineno}: unterminated {quote}-quoted value")
        text = text.rstrip() + " " + lines[j].strip()
    rest = text[end + 1:].strip()
    if rest and not rest.startswith("#"):
        raise FrontmatterError(f"line {lineno}: unexpected text after quoted value")
    inner = text[1:end]
    value = _unescape_dq(inner) if quote == '"' else inner.replace("''", "'")
    return value, j + 1


def _flow_items(inner: str) -> list[str | None]:
    """Split the inside of a `[...]` flow sequence on top-level commas."""
    items: list[str] = []
    buf = ""
    quote = ""
    depth = 0
    for c in inner:
        if quote:
            buf += c
            if c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
            buf += c
        elif c in "[{":
            depth += 1
            buf += c
        elif c in "]}":
            depth -= 1
            buf += c
        elif c == "," and depth == 0:
            items.append(buf)
            buf = ""
        else:
            buf += c
    if buf.strip():
        items.append(buf)
    return [_scalar(x.strip()) for x in items if x.strip()]


def _scalar(s: str) -> str | None:
    """A one-line scalar: quoted, or plain."""
    if len(s) >= 2 and s[0] in "'\"" and _close_quote(s, s[0]) == len(s) - 1:
        inner = s[1:-1]
        return _unescape_dq(inner) if s[0] == '"' else inner.replace("''", "'")
    return _plain(s)


def _flow_seq(lines: list[str], i: int, first: str, lineno: int) -> tuple[list, int]:
    text = first
    j = i
    while True:
        depth = 0
        quote = ""
        end = -1
        for k, c in enumerate(text):
            if quote:
                if c == quote:
                    quote = ""
            elif c in "'\"":
                quote = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end >= 0:
            break
        j += 1
        if j >= len(lines):
            raise FrontmatterError(f"line {lineno}: unterminated [ ] list")
        text = text.rstrip() + " " + lines[j].strip()
    rest = text[end + 1:].strip()
    if rest and not rest.startswith("#"):
        raise FrontmatterError(f"line {lineno}: unexpected text after [ ] list")
    return _flow_items(text[1:end]), j + 1


def _block_scalar(lines: list[str], i: int, style: str) -> tuple[str, int]:
    """Collect the indented lines after a `|` or `>` header on line i-1."""
    j = i
    body: list[str] = []
    while j < len(lines) and (not lines[j].strip() or _indent(lines[j]) > 0):
        body.append(lines[j])
        j += 1
    while body and not body[-1].strip():
        body.pop()
    base = min((_indent(ln) for ln in body if ln.strip()), default=0)
    stripped = [ln[base:] if ln.strip() else "" for ln in body]
    if style == "|":
        return "\n".join(stripped), j
    paragraphs: list[str] = []
    cur: list[str] = []
    for ln in stripped:
        if ln:
            cur.append(ln.strip())
        else:
            paragraphs.append(" ".join(cur))
            cur = []
    paragraphs.append(" ".join(cur))
    return "\n".join(paragraphs).strip(), j


def _block_value(lines: list[str], i: int) -> tuple[Any, int]:
    """Value of a `key:` with nothing after it: a `- item` sequence (indented
    or at column 0), a nested mapping (-> None), a scalar on the following
    indented line(s), or null."""
    j = i
    while j < len(lines):
        ln = lines[j]
        if _is_blank_or_comment(ln) or _indent(ln) > 0 or ln.startswith("-"):
            j += 1
            continue
        break
    firsts = [k for k in range(i, j) if not _is_blank_or_comment(lines[k])]
    if not firsts:
        return None, j
    meaningful = [lines[k] for k in firsts]
    first = meaningful[0]
    s = first.strip()
    if not (s.startswith("- ") or s == "-"):
        if _KEY_RE.match(s):
            return None, j  # nested mapping — not needed by the roster
        if s[0] in "'\"":
            return _quoted(lines, firsts[0], s, firsts[0] + 2)
        return _plain(" ".join(ln.strip() for ln in meaningful)), j
    base = _indent(first)
    raw_items: list[str] = []
    for ln in meaningful:
        s = ln.strip()
        if _indent(ln) == base and (s.startswith("- ") or s == "-"):
            raw_items.append(s[1:].strip())
        elif raw_items:
            raw_items[-1] = (raw_items[-1] + " " + s).strip()
    return [_scalar(x) for x in raw_items], j


def parse_frontmatter(fm: str) -> dict[str, Any]:
    """Parse the text between the `---` fences into a flat dict."""
    lines = fm.splitlines()
    out: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = i + 2  # +1 for 1-based, +1 for the opening fence
        if _is_blank_or_comment(line):
            i += 1
            continue
        if _indent(line) > 0:
            raise FrontmatterError(f"line {lineno}: unexpected indentation")
        m = _KEY_RE.match(line.rstrip())
        if not m:
            raise FrontmatterError(f"line {lineno}: expected 'key: value'")
        key, rest = m.group(1), (m.group(2) or "").strip()
        if not rest or rest.startswith("#"):
            out[key], i = _block_value(lines, i + 1)
        elif _BLOCK_RE.match(rest):
            out[key], i = _block_scalar(lines, i + 1, rest[0])
        elif rest[0] in "'\"":
            out[key], i = _quoted(lines, i, rest, lineno)
        elif rest[0] == "[":
            out[key], i = _flow_seq(lines, i, rest, lineno)
        else:
            parts = [rest]
            i += 1
            while i < len(lines):
                nxt = i
                while nxt < len(lines) and not lines[nxt].strip():
                    nxt += 1  # blank lines inside a multi-line plain scalar
                if nxt >= len(lines) or _indent(lines[nxt]) == 0:
                    break
                parts.append(lines[nxt].strip())
                i = nxt + 1
            out[key] = _plain(" ".join(parts))
    return out


# ---------------------------------------------------------------------------
# Field normalisation
# ---------------------------------------------------------------------------

_TRIGGERS_MARKER = re.compile(r"\btriggers\s*:", re.IGNORECASE)
_SEP = re.compile(r"(?:[\s,;]|\b(?:or|and)\b)*")


def description_triggers(desc: str) -> list[str]:
    """Quoted phrases after `Triggers:` in a description, e.g.
    "... Triggers: '/add-nginx', 'add nginx', 'who's due'." A closing quote
    must be followed by a separator, so apostrophes inside a phrase survive."""
    m = _TRIGGERS_MARKER.search(desc or "")
    if not m:
        return []
    out: list[str] = []
    pos = m.end()
    while True:
        pos = _SEP.match(desc, pos).end()
        if pos >= len(desc) or desc[pos] not in "'\"":
            return out
        q = desc[pos]
        close = re.compile(re.escape(q) + r"(?=$|[\s,.;:)\]])")
        c = close.search(desc, pos + 1)
        if not c:
            return out
        phrase = desc[pos + 1:c.start()].strip()
        if phrase:
            out.append(phrase)
        pos = c.end()


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    return [s.strip() for s in str(v).split(",") if s.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        k = it.lower()
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _tool_surface(v: Any) -> list[str]:
    """Allowed tools; ["*"] when undeclared or declared as 'All tools'."""
    tools = _as_list(v)
    if not tools or {t.lower() for t in tools} <= {"*", "all", "tools", "all tools"}:
        return ["*"]
    return tools


def _first_heading(body: str) -> str:
    for ln in body.splitlines():
        s = ln.strip().lstrip("#").strip()
        if s:
            return s
    return ""


def _parse_file(path: Path, require_frontmatter: bool) -> dict[str, Any]:
    """Read and parse one agent/skill file into a cacheable record."""
    try:
        data = path.read_bytes()
    except OSError as e:
        raise _SkipFile(f"unreadable: {e.strerror or e}") from None
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _SkipFile("not UTF-8") from None
    try:
        fm_text, body = split_frontmatter(text)
        fm = parse_frontmatter(fm_text) if fm_text is not None else {}
    except FrontmatterError as e:
        raise _SkipFile(f"malformed frontmatter: {e}") from None
    if fm_text is None and require_frontmatter:
        raise _SkipFile("no YAML frontmatter")
    desc = fm.get("description")
    desc = str(desc).strip() if desc is not None and not isinstance(desc, list) else ""
    if not desc and fm_text is None:
        desc = _first_heading(body)
    model = fm.get("model")
    tools_v = fm.get("tools", fm.get("allowed-tools", fm.get("allowed_tools")))
    deny_v = fm.get("disallowedTools", fm.get("disallowed-tools", fm.get("disallowed_tools")))
    name = fm.get("name")
    return {
        "digest": digest,
        "fm_name": str(name).strip() if isinstance(name, str) and name.strip() else None,
        "description": desc,
        "triggers": _dedupe(_as_list(fm.get("triggers")) + description_triggers(desc)),
        "model": str(model).strip() if isinstance(model, str) and model.strip() else None,
        "tools": _tool_surface(tools_v),
        "disallowed_tools": _as_list(deny_v),
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _read_cache(cache_path: Path) -> dict[str, Any] | None:
    """Cached entries, or None when the cache is absent, corrupt or stale."""
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("parser_version") != PARSER_VERSION:
        return None
    entries = data.get("entries")
    return entries if isinstance(entries, dict) else None


def _write_cache(cache_path: Path, entries: dict[str, Any]) -> None:
    """Atomic write (tmp in the same dir + os.replace). Raises OSError."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"parser_version": PARSER_VERSION, "entries": entries}, sort_keys=True, indent=1
    )
    fd, tmp = tempfile.mkstemp(prefix=".roster-cache.", suffix=".tmp", dir=str(cache_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")
        os.replace(tmp, cache_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _valid_record(rec: Any) -> bool:
    """A cached record with the shape _parse_file produces (else re-parse)."""
    if not isinstance(rec, dict) or any(k not in rec for k in _RECORD_KEYS):
        return False
    return (
        isinstance(rec["digest"], str)
        and isinstance(rec["description"], str)
        and all(rec[k] is None or isinstance(rec[k], str) for k in ("fm_name", "model"))
        and all(
            isinstance(rec[k], list) and all(isinstance(x, str) for x in rec[k])
            for k in ("triggers", "tools", "disallowed_tools")
        )
    )


class _Loader:
    def __init__(self, cache_entries: dict[str, Any], use_cache: bool):
        self.use_cache = use_cache
        self.old = cache_entries
        self.new: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0
        self.errors: list[dict[str, str]] = []

    def error(self, path: Path | str | None, reason: str) -> None:
        self.errors.append({"path": str(path) if path is not None else "", "reason": reason})

    def record(self, path: Path, require_frontmatter: bool) -> dict[str, Any] | None:
        """Parsed record for path, from cache when (mtime_ns, size, realpath)
        match; None (and an error) when the file is skipped."""
        key = str(path)
        try:
            st = path.stat()
            real = os.path.realpath(path)
        except OSError as e:
            self.error(path, f"unreadable: {e.strerror or e}")
            return None
        stamp = {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "realpath": real}
        cached = self.old.get(key)
        if (
            self.use_cache
            and isinstance(cached, dict)
            and all(cached.get(k) == v for k, v in stamp.items())
            and _valid_record(cached.get("record"))
        ):
            self.hits += 1
            self.new[key] = cached
            return cached["record"]
        try:
            rec = _parse_file(path, require_frontmatter)
        except _SkipFile as e:
            self.error(path, str(e))
            return None
        self.misses += 1
        self.new[key] = {**stamp, "record": rec}
        return rec


# ---------------------------------------------------------------------------
# Roster assembly
# ---------------------------------------------------------------------------

def _entry(name: str, kind: str, rec: dict[str, Any], path: Path | None) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "description": rec["description"],
        "triggers": list(rec["triggers"]),
        "model": rec["model"],
        "tools": list(rec["tools"]),
        "disallowed_tools": list(rec["disallowed_tools"]),
        "path": str(path) if path is not None else None,
        "digest": rec["digest"],
    }


def _builtin_entry(name: str) -> dict[str, Any]:
    spec = BUILTINS[name]
    rec = {
        "description": spec["description"],
        "triggers": [],
        "model": None,
        "tools": spec["tools"],
        "disallowed_tools": spec["disallowed_tools"],
    }
    rec["digest"] = hashlib.sha256(
        json.dumps({"name": name, **rec}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return _entry(name, "builtin", rec, None)


def _registry_names(registry: Path, ld: _Loader) -> set[str] | None:
    """Registry agent names, or None when the registry is unusable."""
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
        agents = data["agents"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        ld.error(registry, f"registry unusable ({type(e).__name__}); using agent .md files alone")
        return None
    if isinstance(agents, dict):
        return {str(k) for k in agents}
    if isinstance(agents, list):
        return {str(a["name"]) for a in agents if isinstance(a, dict) and a.get("name")}
    ld.error(registry, "registry 'agents' is neither an object nor a list; using agent .md files alone")
    return None


def _md_files(agents_dir: Path, ld: _Loader) -> dict[str, Path]:
    out: dict[str, Path] = {}
    try:
        names = sorted(os.listdir(agents_dir))
    except OSError as e:
        if not isinstance(e, FileNotFoundError):
            ld.error(agents_dir, f"unreadable: {e.strerror or e}")
        return out
    for n in names:
        p = agents_dir / n
        if n.startswith(".") or not n.endswith(".md") or p.is_dir():
            continue
        out[n[: -len(".md")]] = p
    return out


def _skill_dirs(skills_dir: Path, ld: _Loader) -> list[tuple[str, Path]]:
    """(dir name, SKILL.md path) for each skill directory (symlinks followed)."""
    try:
        names = sorted(os.listdir(skills_dir))
    except OSError as e:
        if not isinstance(e, FileNotFoundError):
            ld.error(skills_dir, f"unreadable: {e.strerror or e}")
        return []
    out = []
    for n in names:
        skill_md = skills_dir / n / "SKILL.md"
        if not n.startswith(".") and (skills_dir / n).is_dir() and skill_md.exists():
            out.append((n, skill_md))
    return out


def _plugin_skill_dirs(claude_dir: Path, ld: _Loader) -> list[tuple[str, Path]]:
    """("<plugin>:<dir>", SKILL.md path) for installed, not-disabled plugins."""
    installed = claude_dir / "plugins" / "installed_plugins.json"
    if not installed.exists():
        return []
    try:
        plugins = json.loads(installed.read_text(encoding="utf-8"))["plugins"]
        if not isinstance(plugins, dict):
            raise TypeError("plugins is not an object")
    except (OSError, ValueError, KeyError, TypeError) as e:
        ld.error(installed, f"unusable ({type(e).__name__})")
        return []
    enabled: dict[str, Any] = {}
    try:
        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        if isinstance(settings, dict) and isinstance(settings.get("enabledPlugins"), dict):
            enabled = settings["enabledPlugins"]
    except (OSError, ValueError):
        pass  # no settings: every installed plugin counts as enabled
    out: list[tuple[str, Path]] = []
    for key in sorted(plugins):
        if enabled.get(key) is False:
            continue
        installs = plugins[key] if isinstance(plugins[key], list) else [plugins[key]]
        plugin = key.split("@", 1)[0]
        for inst in installs:
            ipath = inst.get("installPath") if isinstance(inst, dict) else None
            if not isinstance(ipath, str) or not ipath or not Path(ipath).is_dir():
                ld.error(installed, f"{key}: installPath missing or not a directory")
                continue
            for d, skill_md in _skill_dirs(Path(ipath) / "skills", ld):
                out.append((f"{plugin}:{d}", skill_md))
    return out


def roster_hash(entries: list[dict[str, Any]]) -> str:
    pairs = sorted([e["name"], e["digest"]] for e in entries)
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode("utf-8")).hexdigest()


def default_cache_path(home: Path) -> Path:
    env = os.environ.get("V11_ROSTER_CACHE")
    return Path(env) if env else home / ".agent-metrics" / "roster-cache.json"


def _load(home: Path, use_cache: bool, cache_path: Path) -> dict[str, Any]:
    claude_dir = home / ".claude"
    cached = _read_cache(cache_path) if use_cache else None
    ld = _Loader(cached if cached is not None else {}, use_cache)

    registry = _registry_names(home / ".agent-registry" / "agents.json", ld)
    md = _md_files(claude_dir / "agents", ld)
    if registry is None:
        wanted, registry_only, md_only = sorted(md), 0, 0
    else:
        wanted = sorted(set(md) & registry)
        registry_only = len(registry - set(md))
        md_only = len(set(md) - registry)

    agents: list[dict[str, Any]] = []
    for stem in wanted:
        rec = ld.record(md[stem], require_frontmatter=True)
        if rec is not None:
            agents.append(_entry(rec["fm_name"] or stem, "agent", rec, md[stem]))
    # An .md agent of a built-in's name replaces the built-in (as in the harness).
    taken = {a["name"] for a in agents}
    shadowed = [n for n in BUILTINS if n in taken]
    builtins = [_builtin_entry(n) for n in BUILTINS if n not in taken]

    def skill_entries(pairs: list[tuple[str, Path]]) -> list[dict[str, Any]]:
        out = []
        for name, skill_md in pairs:
            rec = ld.record(skill_md, require_frontmatter=False)
            if rec is not None:
                out.append(_entry(name, "skill", rec, skill_md))
        return out

    user_skills = skill_entries(_skill_dirs(claude_dir / "skills", ld))
    plugin_skills = skill_entries(_plugin_skill_dirs(claude_dir, ld))

    all_agents = sorted(agents + builtins, key=lambda e: e["name"])
    skills = sorted(user_skills + plugin_skills, key=lambda e: e["name"])

    written, write_error = False, None
    if use_cache and (cached is None or ld.misses or set(ld.new) != set(cached)):
        try:
            _write_cache(cache_path, ld.new)
            written = True
        except OSError as e:
            write_error = f"{type(e).__name__}: {e}"

    return {
        "agents": all_agents,
        "skills": skills,
        "roster_hash": roster_hash(all_agents + skills),
        "counts": {
            "agents": len(agents),
            "builtins": len(builtins),
            "builtins_shadowed": len(shadowed),
            "skills": len(user_skills),
            "plugin_skills": len(plugin_skills),
            "registry_only": registry_only,
            "md_only": md_only,
            "errors": len(ld.errors),
        },
        "errors": ld.errors,
        "cache": {
            "path": str(cache_path) if use_cache else None,
            "hits": ld.hits,
            "misses": ld.misses,
            "written": written,
            "write_error": write_error,
        },
    }


def load_roster(
    home: str | os.PathLike | None = None,
    use_cache: bool = True,
    cache_path: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """Live agent + skill roster. Never raises (fail-open).

    home defaults to $HOME; cache_path defaults to $V11_ROSTER_CACHE, else
    <home>/.agent-metrics/roster-cache.json. Returns
    {agents, skills, roster_hash, counts, errors, cache}.
    """
    home_p = Path(home) if home is not None else Path(os.environ.get("HOME") or os.path.expanduser("~"))
    cache_p = Path(cache_path) if cache_path is not None else default_cache_path(home_p)
    try:
        return _load(home_p, use_cache, cache_p)
    except Exception as e:  # fail-open: advisory data must never break the caller
        return {
            "agents": [],
            "skills": [],
            "roster_hash": roster_hash([]),
            "counts": {
                "agents": 0, "builtins": 0, "builtins_shadowed": 0, "skills": 0,
                "plugin_skills": 0, "registry_only": 0, "md_only": 0, "errors": 1,
            },
            "errors": [{"path": "", "reason": f"internal error: {type(e).__name__}: {e}"}],
            "cache": {"path": None, "hits": 0, "misses": 0, "written": False, "write_error": None},
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live V11 agent + skill roster (read-only).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--json", action="store_true", help="print the full roster")
    mode.add_argument("--counts", action="store_true", help="print counts, roster_hash, errors")
    ap.add_argument("--home", help="home directory to read (default: $HOME)")
    ap.add_argument("--no-cache", action="store_true", help="neither read nor write the cache")
    args = ap.parse_args(argv)
    r = load_roster(home=args.home, use_cache=not args.no_cache)
    if args.counts:
        r = {k: r[k] for k in ("roster_hash", "counts", "errors", "cache")}
    json.dump(r, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
