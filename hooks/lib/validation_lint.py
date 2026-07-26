#!/usr/bin/env python3
"""
V11 Validation Tag Linter — shared validator.
Used by BOTH surfaces (PreToolUse hook and commit-msg git hook).

Usage:
  echo "commit msg" | python3 validation_lint.py
  python3 validation_lint.py --msg-file /path/to/COMMIT_EDITMSG
  python3 validation_lint.py --msg "feat: thing"
  # Optional env for doc-only scope:
  V11_STAGED_FILES="path1\npath2" (newline-separated)

Exit codes:
  0  — PASS (or warn-only mode with warnings on stderr)
  1  — BLOCK (strict mode, or hard violation like multiple tags)
  2  — configuration error (bad ledger path, etc.)

Rollback env vars:
  V11_VALIDATION_LINT=off            — full kill switch, exit 0 immediately
  V11_VALIDATION_LINT_STRICT=off     — warn-only (default); =on upgrades HYPOTHESIZED failures to BLOCK
  V11_VALIDATION_LINT_HEURISTIC=off  — skip causal-language heuristic
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# LEDGER_DIR is read dynamically (not at module load) so tests can override it
# via V11_LEDGER_DIR env var or by patching the module-level variable directly.
_DEFAULT_LEDGER_DIR = Path.home() / ".agent-metrics" / "ledger"
LEDGER_DIR: Optional[Path] = None  # sentinel — resolved by get_ledger_dir()

_DEFAULT_SKIPS_LOG = Path.home() / ".agent-metrics" / "validation-lint-skips.jsonl"
SKIPS_LOG: Optional[Path] = None  # sentinel — resolved by get_skips_log()


def get_ledger_dir() -> Path:
    """Return the ledger directory, respecting V11_LEDGER_DIR env var and module-level override."""
    global LEDGER_DIR
    if LEDGER_DIR is not None:
        return LEDGER_DIR
    env_val = os.environ.get("V11_LEDGER_DIR")
    if env_val:
        return Path(env_val)
    return _DEFAULT_LEDGER_DIR


def get_skips_log() -> Path:
    global SKIPS_LOG
    if SKIPS_LOG is not None:
        return SKIPS_LOG
    env_val = os.environ.get("V11_VALIDATION_SKIPS_LOG")
    if env_val:
        return Path(env_val)
    return _DEFAULT_SKIPS_LOG

VALID_TAGS = {"HYPOTHESIZED", "DRY-RUN", "MEASURED-LIVE-PARTIAL", "LIVE"}

TAG_RE = re.compile(r"^Validation:\s*(HYPOTHESIZED|DRY-RUN|MEASURED-LIVE-PARTIAL|LIVE)\b", re.MULTILINE)
PAIRS_RE = re.compile(
    r"^Pairs:\s*(?:(?:[a-z0-9-]+:)?T\d+)(?:,\s*(?:[a-z0-9-]+:)?T\d+)*\s*$",
    re.MULTILINE
)
PAIRS_ITEM_RE = re.compile(r"(?:([a-z0-9-]+):)?(T\d+)")

# Causal heuristic patterns (case-insensitive)
CAUSAL_VERB_RE = re.compile(
    r"\b(fixes|fixed|closes|closed|resolves|resolved|caused|eliminates|eliminated)\b",
    re.IGNORECASE
)
# NOTE: '%' is a non-word character so \b after a digit before % does NOT anchor correctly.
# Pattern: \b matches word/non-word boundary, digit IS a word char, so \b\d+ works on left side.
# But \b AFTER digits before % (non-word) is a \b boundary too — however % fails `\b` after it.
# Solution: use a non-capturing group for the unit that handles both cases:
#   - for %, × : follow digit directly (no \b after)
#   - for x, -fold: use \b word boundary
QUANTIFIED_OUTCOME_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|×|x\b|\b-fold\b|x\s+faster\b|x\s+slower\b)",
    re.IGNORECASE
)
MECHANISM_RE = re.compile(
    r"\b(by (?:disabling|enabling|removing|bumping|patching) [^.\n]+ (?:we|to) (?:ensure|prevent|avoid|fix))\b",
    re.IGNORECASE
)

# Exemption patterns
EXEMPT_SUBJECT_RE = re.compile(r"^(Merge|Revert|Release|chore\(release\))\b", re.IGNORECASE)
NOLINT_TRAILER_RE = re.compile(r"^\[no-lint\]\s*$|^Validation-Lint:\s*skip\s*$", re.MULTILINE)
BOT_AUTHOR_RE = re.compile(r"^(dependabot|renovate|github-actions)\[bot\]", re.IGNORECASE)

# Doc/exempt file patterns
EXEMPT_PATH_PATTERNS = [
    re.compile(r"^docs/"),
    re.compile(r"\.md$"),
    re.compile(r"^agents/"),
    re.compile(r"^\.claude/agents/"),
    re.compile(r"^sessions/.*\.md$"),
]

# ---------------------------------------------------------------------------
# Rollback env helpers
# ---------------------------------------------------------------------------

def _env_off(name: str) -> bool:
    """Return True if env var is explicitly 'off' (case-insensitive)."""
    return os.environ.get(name, "").lower() == "off"

def _env_on(name: str) -> bool:
    """Return True if env var is explicitly 'on' (case-insensitive)."""
    return os.environ.get(name, "").lower() == "on"

def lint_enabled() -> bool:
    return not _env_off("V11_VALIDATION_LINT")

def strict_mode() -> bool:
    """Default is warn-only (STRICT=off). STRICT only when V11_VALIDATION_LINT_STRICT=on."""
    return _env_on("V11_VALIDATION_LINT_STRICT")

def heuristic_enabled() -> bool:
    return not _env_off("V11_VALIDATION_LINT_HEURISTIC")

# ---------------------------------------------------------------------------
# Ledger lookup
# ---------------------------------------------------------------------------

def _get_active_project() -> Optional[str]:
    """Resolve active project from git config or active-project file."""
    # Try git config v11.project first
    try:
        import subprocess
        result = subprocess.run(
            ["git", "config", "v11.project"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    # Fall back to ~/.claude/active-project
    active_proj_file = Path.home() / ".claude" / "active-project"
    if active_proj_file.exists():
        content = active_proj_file.read_text().strip()
        if content:
            return content

    return None


def _resolve_project_for_task(project_qualifier: Optional[str]) -> Optional[str]:
    """Resolve project for a task reference."""
    if project_qualifier:
        return project_qualifier
    return _get_active_project()


def check_task_open(task_id_str: str, project: Optional[str]) -> tuple[bool, str]:
    """
    Check whether a task is open (in_progress) in the V11.16 durable ledger.
    Returns (is_open, reason_string).

    task_id_str: bare number like "6" (from T6).
    project: project name to look up.

    The task_id in the ledger is stored as a string matching the bare number.
    """
    if not project:
        return False, f"cannot resolve project for task {task_id_str} (no active project)"

    ledger_path = get_ledger_dir() / f"{project}.jsonl"
    if not ledger_path.exists():
        return False, f"ledger not found for project '{project}' (task {task_id_str})"

    # Scan all events and find the LAST one for this task_id
    # The task_id in ledger is the bare number (without T prefix)
    last_event = None
    try:
        with ledger_path.open() as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    ev = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if str(ev.get("task_id", "")) == task_id_str:
                    last_event = ev
    except OSError as e:
        return False, f"error reading ledger for '{project}': {e}"

    if last_event is None:
        return False, f"task {task_id_str} not found in ledger for project '{project}'"

    # Determine open status
    ev_type = last_event.get("ev", "")
    status = last_event.get("status", "")

    # Terminal statuses
    if status in ("completed", "cancelled", "blocked"):
        return False, f"task {task_id_str} is {status} (closed)"

    if ev_type == "created" and not status:
        # Created but never updated — treat as open (pending is open enough for HYPOTHESIZED)
        return True, f"task {task_id_str} is pending (created, no status update)"

    if status == "in_progress":
        return True, f"task {task_id_str} is in_progress"

    if ev_type in ("updated",) and status in ("pending", ""):
        return True, f"task {task_id_str} is pending"

    # Unknown status — treat conservatively as not open
    return False, f"task {task_id_str} has ambiguous status (ev={ev_type!r}, status={status!r})"


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def extract_tag(message: str) -> list[str]:
    """Return list of all Validation: tags found in the message."""
    return TAG_RE.findall(message)


def extract_pairs(message: str) -> Optional[str]:
    """Return the raw Pairs: line content if present, else None."""
    m = PAIRS_RE.search(message)
    if m:
        return m.group(0)
    return None


def parse_pairs_refs(pairs_line: str) -> list[tuple[Optional[str], str]]:
    """
    Parse 'Pairs: T6, project:T9' → [(None, '6'), ('project', '9')]
    Returns list of (project_qualifier, task_id_number).
    """
    refs = []
    for m in PAIRS_ITEM_RE.finditer(pairs_line):
        qualifier = m.group(1)  # may be None
        task_num = m.group(2)[1:]  # strip 'T' prefix
        refs.append((qualifier, task_num))
    return refs


def is_doc_only(staged_files: Optional[list[str]]) -> bool:
    """Return True if all staged files match exempt doc/agent paths."""
    if not staged_files:
        return False
    return all(
        any(pat.search(f) for pat in EXEMPT_PATH_PATTERNS)
        for f in staged_files
    )


def causal_heuristic_matches(message: str) -> bool:
    """
    Return True iff the commit message triggers the causal-language heuristic.
    Trigger: (pattern1 AND pattern2) OR pattern3.
    """
    has_verb = bool(CAUSAL_VERB_RE.search(message))
    has_quantity = bool(QUANTIFIED_OUTCOME_RE.search(message))
    has_mechanism = bool(MECHANISM_RE.search(message))
    return (has_verb and has_quantity) or has_mechanism


# ---------------------------------------------------------------------------
# Log suppression
# ---------------------------------------------------------------------------

def _log_skip(reason: str, message_subject: str) -> None:
    """Append a skip event to the audit log."""
    import datetime
    skips_log = get_skips_log()
    skips_log.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reason": reason,
        "subject": message_subject[:120],
    }
    try:
        with skips_log.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # non-fatal


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------

class LintResult:
    def __init__(self, verdict: str, messages: list[str]):
        """verdict: 'PASS', 'WARN', 'BLOCK'"""
        self.verdict = verdict
        self.messages = messages

    def __repr__(self):
        return f"LintResult({self.verdict}, {self.messages})"


def lint_message(
    message: str,
    staged_files: Optional[list[str]] = None,
    author: Optional[str] = None,
    dry_run: bool = False,
) -> LintResult:
    """
    Core lint logic. Returns LintResult with verdict and explanatory messages.
    This function is PURE with respect to env vars — callers apply severity matrix.
    """
    lines = []
    subject = message.strip().split("\n")[0] if message.strip() else ""

    # Exemption 4: bot author
    if author and BOT_AUTHOR_RE.match(author.strip()):
        return LintResult("PASS", [f"exempt: bot author ({author})"])

    # Exemption 2: merge/revert/release subject
    if EXEMPT_SUBJECT_RE.match(subject):
        return LintResult("PASS", [f"exempt: subject matches merge/revert/release pattern"])

    # Exemption 3: [no-lint] trailer
    if NOLINT_TRAILER_RE.search(message):
        _log_skip("no-lint trailer", subject)
        return LintResult("PASS", ["exempt: [no-lint] trailer present (logged)"])

    # Exemption 1: doc-only scope
    if staged_files is not None and is_doc_only(staged_files):
        return LintResult("PASS", ["exempt: doc-only staged files"])

    # Tag extraction
    tags = extract_tag(message)

    # Multiple tags → always BLOCK
    if len(tags) > 1:
        return LintResult("BLOCK", [f"multiple Validation: tags found ({tags}) — ambiguous"])

    if len(tags) == 1:
        tag = tags[0]

        if tag == "HYPOTHESIZED":
            # Must have Pairs: line
            pairs_line = extract_pairs(message)
            if not pairs_line:
                return LintResult(
                    "HYPOTHESIZED_NO_PAIRS",
                    ["Validation: HYPOTHESIZED requires a 'Pairs: T<n>' line referencing an open in-progress task"]
                )

            # Validate each task reference
            refs = parse_pairs_refs(pairs_line)
            if not refs:
                return LintResult(
                    "HYPOTHESIZED_NO_PAIRS",
                    ["Pairs: line found but no valid T<n> references parsed"]
                )

            errors = []
            for qualifier, task_num in refs:
                project = _resolve_project_for_task(qualifier)
                is_open, reason = check_task_open(task_num, project)
                if not is_open:
                    errors.append(f"T{task_num}: {reason}")

            if errors:
                return LintResult(
                    "HYPOTHESIZED_CLOSED",
                    [f"HYPOTHESIZED paired task(s) not open: {'; '.join(errors)}"]
                )

            return LintResult("PASS", [f"HYPOTHESIZED with valid open paired task(s)"])

        # DRY-RUN, MEASURED-LIVE-PARTIAL, LIVE — no further checks
        return LintResult("PASS", [f"Validation: {tag} present"])

    # No tag — check heuristic
    if heuristic_enabled() and causal_heuristic_matches(message):
        return LintResult(
            "WARN_NO_TAG",
            [
                "commit contains causal language (root-cause verb + quantified outcome, or mechanism assertion) "
                "but no Validation: tag — add 'Validation: LIVE|DRY-RUN|MEASURED-LIVE-PARTIAL|HYPOTHESIZED' "
                "or suppress with [no-lint] trailer"
            ]
        )

    return LintResult("PASS", ["no causal language detected, no tag required"])


def apply_severity(result: LintResult) -> tuple[int, str]:
    """
    Apply the severity matrix given current env var configuration.
    Returns (exit_code, human_label).

    Severity matrix (from spec):
      BLOCK verdict               → exit 1 always
      HYPOTHESIZED_NO_PAIRS       → WARN in default, BLOCK in strict
      HYPOTHESIZED_CLOSED         → WARN in default, BLOCK in strict
      WARN_NO_TAG                 → WARN always (even in strict — heuristic FP risk)
      PASS                        → exit 0 always
    """
    v = result.verdict
    strict = strict_mode()

    if v == "PASS":
        return 0, "PASS"
    elif v == "BLOCK":
        return 1, "BLOCK"
    elif v in ("HYPOTHESIZED_NO_PAIRS", "HYPOTHESIZED_CLOSED"):
        if strict:
            return 1, "BLOCK (strict mode)"
        return 0, "WARN"
    elif v == "WARN_NO_TAG":
        # Always warn, never block — heuristic FP rate unknown
        return 0, "WARN"
    else:
        # Unknown verdict — treat as warn
        return 0, f"WARN (unknown verdict: {v})"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _read_message(args: list[str]) -> tuple[str, Optional[list[str]]]:
    """
    Parse CLI args and read the commit message.
    Returns (message_text, staged_files_or_None).
    """
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--msg-file", help="Path to commit message file (e.g. .git/COMMIT_EDITMSG)")
    parser.add_argument("--msg", help="Commit message as string")
    parser.add_argument("--staged-files", help="Newline-separated list of staged file paths")
    parser.add_argument("--author", help="Commit author string")
    parsed, _ = parser.parse_known_args(args)

    if parsed.msg_file:
        msg = Path(parsed.msg_file).read_text(encoding="utf-8", errors="replace")
    elif parsed.msg:
        msg = parsed.msg
    else:
        msg = sys.stdin.read()

    staged_files = None
    if parsed.staged_files:
        staged_files = [f for f in parsed.staged_files.split("\n") if f.strip()]
    elif "V11_STAGED_FILES" in os.environ:
        raw = os.environ["V11_STAGED_FILES"]
        staged_files = [f for f in raw.split("\n") if f.strip()]

    return msg, staged_files, getattr(parsed, "author", None)


def main(args: Optional[list[str]] = None) -> int:
    if args is None:
        args = sys.argv[1:]

    # Full kill switch
    if not lint_enabled():
        return 0

    try:
        msg, staged_files, author = _read_message(args)
    except Exception as e:
        print(f"[validation-lint] ERROR reading message: {e}", file=sys.stderr)
        return 2

    if not msg.strip():
        # Empty message — nothing to lint (git itself will reject it)
        return 0

    result = lint_message(msg, staged_files=staged_files, author=author)
    exit_code, label = apply_severity(result)

    prefix = "[validation-lint]"
    if label.startswith("PASS"):
        # Only print on debug
        if os.environ.get("V11_VALIDATION_LINT_DEBUG"):
            print(f"{prefix} PASS — {'; '.join(result.messages)}", file=sys.stderr)
    elif label.startswith("WARN"):
        print(f"{prefix} WARNING — {'; '.join(result.messages)}", file=sys.stderr)
    else:
        print(f"{prefix} BLOCK — {'; '.join(result.messages)}", file=sys.stderr)
        print(f"{prefix} To suppress: add '[no-lint]' trailer or add a Validation: tag.", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
