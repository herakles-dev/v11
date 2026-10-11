#!/usr/bin/env python3
"""
wiring_diff — reconcile a project's .claude/settings.json hook wiring against
the canonical template (v11/.claude/settings.json).

Ticket #86 (S0-T4/S0-T5, v11-leverage-program). Consumed by:
  - scripts/v11-update   (fleet reconciliation, single project + --all)
  - scripts/scaffold     (new-project settings.json = template hooks + scaffold's own env)
  - scripts/check-wiring-parity (read-only fleet parity report)

Design contract (see improvements/86-fleet-hook-wiring-drift-and-frozen-v11-update.md):
  - Managed  = every hook command string that appears anywhere in the template.
               A managed command's wiring in a project is made EXACTLY equal to
               the template's: missing (event, matcher) pairs are added,
               mismatched matchers are re-matched, and wiring at events/matchers
               the template does not use for that command is removed.
  - Unmanaged = any command not in the template (custom project hooks, and v11
               opt-in hooks like enforce-subagent / pg-*). Preserved
               byte-for-byte, reported as "custom_preserved".
  - A managed entry is rebuilt from the project's own prior entry: only
    "type"/"command" are overlaid from the template, so every other per-hook
    key the project set ("async", "statusMessage", ...) survives, reported as
    "fields_preserved". A command new to the project gets the template's full
    entry.
  - A per-hook "timeout" already set in the project is preserved; it is
    reported as "timeout_preserved" only when it differs from the template's
    timeout for that entry (an equal one is not a customisation). Otherwise
    the template's timeout (if any) is used.
  - SUPERSEDED_BY maps an unmanaged command to the managed hook that replaced
    it (guard-teammate-timeout -> guard-agent-stall). The old command is
    removed ("superseded", a wiring change) only when its successor is in the
    template and therefore placed; otherwise it is preserved as custom.
  - RETIRED_COMMANDS lists commands whose wiring should be removed fleet-wide
    (empty today). S0-T6 retires nothing: session-end stays wired to Stop
    (the per-turn cheap path and safety net) and is additionally wired to
    SessionEnd, both through the template.
  - All non-"hooks" top-level keys are left untouched. Key order is preserved
    for keys that already existed on the object being mutated.

`load_template` and `diff` are pure: no filesystem access happens inside
`diff`, and `load_template`'s only I/O is reading the one file it's given.
Discovery/backup/atomic-write helpers below are explicitly I/O and are kept
separate so the core diff logic stays trivially unit-testable.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

# Commands whose wiring is removed fleet-wide regardless of where a project
# currently wires them. Empty today — S0-T6 (Stop/SessionEnd split) keeps
# session-end on Stop and adds a SessionEnd wiring, so it retires nothing.
RETIRED_COMMANDS: frozenset[str] = frozenset()

# old command -> the command that replaced it. guard-agent-stall's header says
# it "Replaces guard-teammate-timeout (V11.11)": both fire on
# PostToolUse/TaskList with the same thresholds and the same
# stall-alerts-<project>.json tracker, so wiring both double-alerts.
SUPERSEDED_BY: dict[str, str] = {
    "/path/to/v11/hooks/guard-teammate-timeout": "/path/to/v11/hooks/guard-agent-stall",
}

# Per-hook keys diff() owns; any other key on a managed entry is the
# project's and is carried over ("fields_preserved").
_CORE_HOOK_KEYS = ("type", "command", "timeout")

# Directory name patterns pruned unconditionally during fleet discovery.
_PRUNE_EXACT_DIRNAMES = {"node_modules", ".git"}
# Backup/snapshot dirs: a separator-delimited backup token anywhere in the
# name (".v11-backups", "v11.backup.20260413-205153", "x.bak", "snapshot-1").
# "archive" is also a project-name word (internet-archive, example-project-archive),
# so it only prunes as the whole name or when followed by a dated suffix.
_PRUNE_BACKUP_RE = re.compile(
    r"(^|[._-])(backups?|bak|snapshots?)([._-]|$)"
    r"|^\.?(v11[-_])?archives?$"
    r"|(^|[._-])archives?[._-]\d",
    re.IGNORECASE,
)

# A settings file "references V11" when it contains this path — the one
# predicate discover_settings_files() and check-wiring-parity's unwired
# session-dir scan share.
V11_HOOKS_REF = "/path/to/v11/hooks/"


def is_backup_dirname(name: str) -> bool:
    """True for a backup/snapshot/archive dir name (see _PRUNE_BACKUP_RE)."""
    return bool(_PRUNE_BACKUP_RE.search(name))


class SettingsShapeError(ValueError):
    """A settings.json that parses as JSON but isn't a shape diff() can
    reconcile safely (hooks not an object, a group not an object, ...)."""


# ─────────────────────────────────────────────────────────────────────────
# Core (pure)
# ─────────────────────────────────────────────────────────────────────────

def load_template(path: str | Path) -> dict:
    """Read and parse a settings.json template. The only I/O in the core."""
    with open(path, "r") as f:
        return json.load(f)


def validate_shape(settings: Any, label: str = "settings") -> None:
    """Raise SettingsShapeError unless settings has the hooks shape Claude
    Code expects: {"hooks": {event: [{"matcher"?: str, "hooks": [{...}]}]}}."""
    if not isinstance(settings, dict):
        raise SettingsShapeError(f"{label}: top level is not a JSON object")
    if "hooks" not in settings:
        return
    hooks = settings["hooks"]
    if not isinstance(hooks, dict):
        raise SettingsShapeError(f"{label}: 'hooks' is not an object")
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise SettingsShapeError(f"{label}: hooks.{event} is not a list")
        for i, group in enumerate(groups):
            where = f"{label}: hooks.{event}[{i}]"
            if not isinstance(group, dict):
                raise SettingsShapeError(f"{where} is not an object")
            if group.get("matcher") is not None and not isinstance(group["matcher"], str):
                raise SettingsShapeError(f"{where}.matcher is not a string")
            entries = group.get("hooks")
            if entries is None:
                continue
            if not isinstance(entries, list):
                raise SettingsShapeError(f"{where}.hooks is not a list")
            for j, hook in enumerate(entries):
                if not isinstance(hook, dict):
                    raise SettingsShapeError(f"{where}.hooks[{j}] is not an object")
                if "command" in hook and not isinstance(hook["command"], str):
                    raise SettingsShapeError(f"{where}.hooks[{j}].command is not a string")


def _iter_hook_entries(hooks_dict: dict | None) -> Iterator[tuple[str, str | None, dict]]:
    """Yield (event, matcher_or_None, hook_entry) for every command entry."""
    for event, groups in (hooks_dict or {}).items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher")
            for hook in group.get("hooks", []) or []:
                if isinstance(hook, dict):
                    yield event, matcher, hook


def _template_positions(template_hooks: dict) -> dict[str, dict[str, dict[str, dict]]]:
    """command -> event -> matcher -> {"timeout": N|None, "type": str}

    A command CAN be wired more than once within a single event under
    different matchers in the real template (e.g. guard-enforcement is wired
    at PreToolUse under both "Write|Edit" and "Bash") — this is a set of
    matchers per (command, event), not a single slot.
    """
    out: dict[str, dict[str, dict[str, dict]]] = {}
    for event, matcher, hook in _iter_hook_entries(template_hooks):
        cmd = hook.get("command")
        if not cmd:
            continue
        out.setdefault(cmd, {}).setdefault(event, {})[matcher] = {
            "timeout": hook.get("timeout"),
            "type": hook.get("type", "command"),
        }
    return out


def _build_entry(base: dict, hook_type: str, cmd: str, timeout: Any) -> dict:
    """base with only type/command overlaid and the resolved timeout applied;
    every other key of base (and its position) is kept."""
    entry = copy.deepcopy(base)
    if "type" in entry:
        entry["type"] = hook_type
    else:
        entry = {"type": hook_type, **entry}
    entry["command"] = cmd
    if timeout is not None:
        entry["timeout"] = timeout
    else:
        entry.pop("timeout", None)
    return entry


def diff(
    project_settings: dict,
    template_hooks: dict,
    retired_commands: Iterable[str] | None = None,
    superseded_by: dict[str, str] | None = None,
) -> tuple[dict, list[dict]]:
    """Reconcile project_settings["hooks"] against template_hooks.

    Returns (new_settings, changes). new_settings is a deep copy of
    project_settings with only the "hooks" key rewritten; every other
    top-level key (and its position) is untouched. changes is a list of
    dicts, each {"type": "added"|"rematched"|"removed"|"superseded"|
    "timeout_preserved"|"fields_preserved"|"custom_preserved", ...}.

    Raises SettingsShapeError if either input isn't a valid hooks shape.
    """
    validate_shape(project_settings, "project")
    validate_shape({"hooks": template_hooks}, "template")
    retired = frozenset(RETIRED_COMMANDS if retired_commands is None else retired_commands)
    template_positions = _template_positions(template_hooks)
    managed_commands = set(template_positions)
    # A superseded command is only removed when its successor is managed —
    # i.e. step 3 is guaranteed to place the replacement.
    supersede = {
        old: new
        for old, new in (SUPERSEDED_BY if superseded_by is None else superseded_by).items()
        if new in managed_commands and old not in managed_commands
    }

    new_settings = copy.deepcopy(project_settings)
    project_hooks = new_settings.get("hooks", {}) or {}

    changes: list[dict] = []
    # command -> event -> matcher -> the project's full prior hook entry.
    project_positions: dict[str, dict[str, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))

    # Step 1: walk the project's existing wiring. Strip managed/retired
    # entries (recording their prior position), keep unmanaged ones in place.
    new_hooks: dict[str, list[dict]] = {}
    for event, groups in project_hooks.items():
        if not isinstance(groups, list):
            new_hooks[event] = groups  # unreachable: validate_shape() rejects this
            continue
        new_groups: list[dict] = []
        for group in groups:
            if not isinstance(group, dict):
                new_groups.append(group)
                continue
            matcher = group.get("matcher")
            kept_hooks = []
            for hook in group.get("hooks", []) or []:
                cmd = hook.get("command") if isinstance(hook, dict) else None
                if cmd in managed_commands:
                    project_positions[cmd][event][matcher] = hook
                    continue  # strip; re-placed in step 3
                if cmd in retired:
                    changes.append({
                        "type": "removed", "command": cmd, "event": event,
                        "matcher": matcher, "reason": "retired_command",
                    })
                    continue  # strip permanently
                if cmd in supersede:
                    changes.append({
                        "type": "superseded", "command": cmd, "event": event,
                        "matcher": matcher, "by": supersede[cmd],
                    })
                    continue  # strip; its successor is placed in step 3
                kept_hooks.append(hook)
                changes.append({
                    "type": "custom_preserved", "command": cmd,
                    "event": event, "matcher": matcher,
                })
            if kept_hooks:
                new_group = dict(group)
                new_group["hooks"] = kept_hooks
                new_groups.append(new_group)
            # else: group had only managed/retired entries — drop it; step 3
            # recreates it under the template's wiring if still needed.
        if new_groups:
            new_hooks[event] = new_groups
        # else: event carried nothing forward; step 3 recreates it if needed.

    # Step 2: per (command, event), diff the SET of matchers required by the
    # template against the set the project currently has. A matcher present
    # in both is unchanged; a 1:1 pairing of (stale matcher the template
    # doesn't want here) <-> (needed matcher missing here) is reported as
    # "rematched" (covers the common "Task" -> "Task|Agent" drift case);
    # anything left over is a plain "added" or "removed".
    # rematch_of[cmd][event][new_matcher] = old_matcher
    rematch_of: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    for cmd in managed_commands:
        t_events = template_positions.get(cmd, {})
        p_events = project_positions.get(cmd, {})
        for event in set(t_events) | set(p_events):
            t_matchers = list(t_events.get(event, {}).keys())
            p_matchers = list(p_events.get(event, {}).keys())
            missing = [m for m in t_matchers if m not in p_matchers]
            stale = [m for m in p_matchers if m not in t_matchers]
            n = min(len(missing), len(stale))
            for old_m, new_m in zip(stale[:n], missing[:n]):
                rematch_of[cmd][event][new_m] = old_m
            reason = "not_in_template" if event not in t_events else "extra_matcher"
            for old_m in stale[n:]:
                changes.append({
                    "type": "removed", "command": cmd, "event": event,
                    "matcher": old_m, "reason": reason,
                })

    # Step 3: place every managed command at every (event, matcher) the
    # template requires, in template order (deterministic reconstruction).
    for event, matcher, hook in _iter_hook_entries(template_hooks):
        cmd = hook.get("command")
        if not cmd:
            continue
        p_at_event = project_positions.get(cmd, {}).get(event, {})

        if matcher in p_at_event:
            prior = p_at_event[matcher]
            action = None  # already correctly wired here
        else:
            old_matcher = rematch_of.get(cmd, {}).get(event, {}).get(matcher)
            if old_matcher is not None:
                prior = p_at_event[old_matcher]
                action = ("rematched", old_matcher)
            else:
                prior = None
                action = ("added",)

        prior_timeout = prior.get("timeout") if prior is not None else None
        if prior_timeout is not None:
            timeout = prior_timeout
            # Report only a genuinely custom timeout; one equal to the
            # template's (e.g. SessionEnd's 60 s after the S0-T7 sync) is
            # not a preservation and would drown the real ones in noise.
            if prior_timeout != hook.get("timeout"):
                changes.append({
                    "type": "timeout_preserved", "command": cmd,
                    "event": event, "matcher": matcher, "timeout": timeout,
                })
        else:
            timeout = hook.get("timeout")

        if action is not None:
            if action[0] == "added":
                changes.append({"type": "added", "command": cmd, "event": event, "matcher": matcher})
            else:
                changes.append({
                    "type": "rematched", "command": cmd, "event": event,
                    "from_matcher": action[1], "to_matcher": matcher,
                })

        # Built from the project's own entry when it had one (so its extra
        # keys survive), else from the template's full entry.
        new_entry = _build_entry(prior if prior is not None else hook, hook.get("type", "command"), cmd, timeout)
        if prior is not None:
            extra = [k for k in new_entry if k not in _CORE_HOOK_KEYS]
            if extra:
                changes.append({
                    "type": "fields_preserved", "command": cmd,
                    "event": event, "matcher": matcher, "fields": extra,
                })

        event_groups = new_hooks.setdefault(event, [])
        target_group = next((g for g in event_groups if isinstance(g, dict) and g.get("matcher") == matcher), None)
        if target_group is None:
            # Key order matches the template/fleet convention ("matcher" before
            # "hooks") so a semantic no-op re-serializes byte-identically.
            target_group = {"matcher": matcher, "hooks": []} if matcher is not None else {"hooks": []}
            event_groups.append(target_group)
        target_group["hooks"].append(new_entry)

    new_settings["hooks"] = new_hooks
    return new_settings, changes


# Change types that are real wiring drift; the rest are informational.
WIRING_CHANGE_TYPES = ("added", "rematched", "removed", "superseded")


def is_at_parity(changes: list[dict]) -> bool:
    """True if no wiring-level change is needed (custom/timeout/field
    preservation alone doesn't count — those are informational, not drift)."""
    return not any(c["type"] in WIRING_CHANGE_TYPES for c in changes)


def managed_coverage(project_settings: dict, template_hooks: dict) -> tuple[int, int]:
    """(present, expected): how many of the template's (event, matcher,
    command) wirings the project already has exactly. Unmanaged commands —
    custom hooks, opt-in v11 hooks — never count toward present."""
    _new, changes = diff(project_settings, template_hooks)
    expected = sum(1 for _event, _matcher, hook in _iter_hook_entries(template_hooks) if hook.get("command"))
    missing = sum(1 for c in changes if c["type"] in ("added", "rematched"))
    return expected - missing, expected


def custom_commands(changes: list[dict]) -> list[str]:
    """Distinct commands reported as custom_preserved, in first-seen order."""
    seen: list[str] = []
    for c in changes:
        if c["type"] == "custom_preserved" and c["command"] not in seen:
            seen.append(c["command"])
    return seen


_JSON_WS = re.compile(r"[ \t\n\r]*")


def _detect_format(original_text: str | None) -> tuple[str, bool]:
    """(indent, trailing_newline) of original_text: the leading whitespace of
    its first indented line (default 2 spaces) and whether it ends in a
    newline (default yes, for a brand-new file)."""
    if original_text is None:
        return "  ", True
    m = re.search(r"\n([ \t]+)\S", original_text)
    return (m.group(1) if m else "  "), original_text.endswith("\n")


def _top_level_value_span(text: str, key: str) -> tuple[int, int] | None:
    """(start, end) offsets of the top-level `key`'s value in a JSON object
    text, or None if it's absent, duplicated, or the text isn't an object."""
    decoder = json.JSONDecoder()
    try:
        i = _JSON_WS.match(text, 0).end()
        if text[i:i + 1] != "{":
            return None
        i = _JSON_WS.match(text, i + 1).end()
        if text[i:i + 1] == "}":
            return None
        span = None
        while True:
            if text[i:i + 1] != '"':
                return None
            k, i = json.decoder.scanstring(text, i + 1)
            i = _JSON_WS.match(text, i).end()
            if text[i:i + 1] != ":":
                return None
            i = _JSON_WS.match(text, i + 1).end()
            _value, end = decoder.raw_decode(text, i)
            if k == key:
                if span is not None:
                    return None
                span = (i, end)
            i = _JSON_WS.match(text, end).end()
            if text[i:i + 1] == ",":
                i = _JSON_WS.match(text, i + 1).end()
                continue
            return span if text[i:i + 1] == "}" else None
    except (ValueError, AttributeError):
        return None


def dump_settings(settings: dict, original_text: str | None = None) -> str:
    """Serialize settings. With no original_text: 2-space indent, trailing
    newline. With original_text: reuse its indent and trailing-newline
    choice, and re-serialize only the top-level "hooks" value in place so
    every non-hook byte of the original survives unchanged."""
    indent, trailing_newline = _detect_format(original_text)
    if original_text is not None and "hooks" in settings:
        span = _top_level_value_span(original_text, "hooks")
        if span is not None:
            hooks_text = json.dumps(settings["hooks"], indent=indent).replace("\n", "\n" + indent)
            spliced = original_text[:span[0]] + hooks_text + original_text[span[1]:]
            try:
                if json.loads(spliced) == settings:
                    return spliced
            except ValueError:
                pass
    return json.dumps(settings, indent=indent) + ("\n" if trailing_newline else "")


# ─────────────────────────────────────────────────────────────────────────
# I/O helpers (discovery, backup, atomic write) — used by v11-update /
# check-wiring-parity. Kept apart from the pure core above.
# ─────────────────────────────────────────────────────────────────────────

def discover_settings_files(
    root: str | Path,
    template_path: str | Path | None = None,
    extra_prune_roots: Iterable[str | Path] | None = None,
) -> tuple[list[Path], dict[str, list[Path]]]:
    """Find every .claude/settings.json under root that references
    /path/to/v11/hooks/.

    Prunes: node_modules, .git, any */.claude/worktrees/* subtree, backup/
    snapshot dirs (by name — ".v11-backups", "v11.backup.<stamp>", "*.bak",
    "archive", ... — see _PRUNE_BACKUP_RE),
    any extra_prune_roots (e.g. the live V11_UPDATE_BACKUP_ROOT), and the
    template file itself.

    Returns (discovered, pruned) where pruned maps a reason string to the
    list of paths skipped for that reason (dirs for structural prunes, files
    for content/template prunes) — used for reconciling the discovered count
    against a human audit.
    """
    root = Path(root)
    template_resolved = Path(template_path).resolve() if template_path else None
    extra_roots = [Path(p).resolve() for p in (extra_prune_roots or [])]

    discovered: list[Path] = []
    pruned: dict[str, list[Path]] = defaultdict(list)

    for dirpath, dirnames, filenames in os.walk(root):
        dirpath_p = Path(dirpath)

        kept_dirnames = []
        for d in dirnames:
            full = dirpath_p / d
            reason = None
            if d in _PRUNE_EXACT_DIRNAMES:
                reason = d
            elif d == "worktrees" and dirpath_p.name == ".claude":
                reason = "worktrees"
            elif _PRUNE_BACKUP_RE.search(d):
                reason = "backup_dir"
            else:
                full_resolved = full.resolve()
                for extra in extra_roots:
                    if full_resolved == extra or extra in full_resolved.parents:
                        reason = "extra_prune_root"
                        break
            if reason:
                pruned[reason].append(full)
            else:
                kept_dirnames.append(d)
        dirnames[:] = kept_dirnames

        if dirpath_p.name == ".claude" and "settings.json" in filenames:
            f = dirpath_p / "settings.json"
            if template_resolved and f.resolve() == template_resolved:
                pruned["template"].append(f)
                continue
            try:
                text = f.read_text()
            except OSError:
                pruned["unreadable"].append(f)
                continue
            if V11_HOOKS_REF in text:
                discovered.append(f)
            else:
                pruned["no_v11_hooks_ref"].append(f)

    return discovered, dict(pruned)


def atomic_write(path: str | Path, content: str | bytes, mode: int | None = None) -> None:
    """Write content to path atomically: tmp file in the same directory, then
    os.replace (same-filesystem rename is atomic on POSIX). A symlinked path
    is followed — the resolved target is replaced and the link survives —
    and the target's permission bits are kept (mkstemp creates 0600) unless
    an explicit mode is given. bytes content is written verbatim (restore)."""
    target = Path(os.path.realpath(path))
    if mode is None:
        try:
            mode = stat.S_IMODE(target.stat().st_mode)
        except FileNotFoundError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
    fd, tmp_name = tempfile.mkstemp(prefix=".wiring_diff.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb" if isinstance(content, bytes) else "w") as f:
            f.write(content)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def backup_path_for(path: str | Path, backup_root: str | Path, timestamp: str) -> Path:
    """Mirror an absolute path under backup_root/timestamp/<mirrored path>."""
    path = Path(path).resolve()
    backup_root = Path(backup_root)
    return backup_root / timestamp / path.relative_to(path.anchor)


def backup_file(path: str | Path, backup_root: str | Path, timestamp: str) -> Path:
    """Copy path to its mirrored backup location (created on demand). Returns
    the backup path. This function performs I/O and must never be called in
    --dry-run mode."""
    dest = backup_path_for(path, backup_root, timestamp)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


# ─────────────────────────────────────────────────────────────────────────
# CLI — small primitives for non-Python callers (scripts/scaffold is bash).
# ─────────────────────────────────────────────────────────────────────────

def _cli() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="wiring_diff", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hooks = sub.add_parser("hooks-json", help="print template['hooks'] as JSON")
    p_hooks.add_argument("--template", required=True)

    p_cov = sub.add_parser("managed-coverage", help="print 'PRESENT EXPECTED' template-managed wirings for a project")
    p_cov.add_argument("--template", required=True)
    p_cov.add_argument("--settings", required=True)

    p_new = sub.add_parser("new-project-settings", help="build a fresh project settings.json from the template")
    p_new.add_argument("--template", required=True)
    p_new.add_argument("--schema", default=None)
    p_new.add_argument("--env-json", default=None, help="JSON object to use as the 'env' key")

    args = parser.parse_args()

    if args.cmd == "hooks-json":
        template = load_template(args.template)
        print(json.dumps(template.get("hooks", {}), indent=2))
        return 0

    if args.cmd == "managed-coverage":
        try:
            template = load_template(args.template)
            present, expected = managed_coverage(load_template(args.settings), template.get("hooks", {}))
        except (OSError, ValueError) as e:
            print(f"wiring_diff: {args.settings}: {e}", file=sys.stderr)
            return 2
        print(f"{present} {expected}")
        return 0

    if args.cmd == "new-project-settings":
        template = load_template(args.template)
        new_settings, _changes = diff({}, template.get("hooks", {}))
        out = {"$schema": args.schema or template.get("$schema", "https://json.schemastore.org/claude-code-settings.json")}
        out["hooks"] = new_settings["hooks"]
        if args.env_json:
            out["env"] = json.loads(args.env_json)
        elif "env" in template:
            out["env"] = template["env"]
        print(dump_settings(out), end="")
        return 0

    return 1


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
