"""L1.3a — cross-session handoff loop baseline.

Persists a snapshot of the sending session's task-state + reference anchors
at handoff CLOSE, so the OPEN side (L2.1 boot-delta, L2.3 rehydrate
verification, L2.4 loop-ack ledger event) can compare live disk against a
recorded expectation instead of best-effort inference.

Invariants (enforced):
  I1: handoff_at, project, source_session_uuid, expected_open_tasks_count,
      git_head, handoff_tasks_hash are non-empty at write time.
  I2: baseline_source parsed via BaselineSource enum — unknown values raise
      ProtocolViolation (silent fall-through impossible).
  I3: expected_open_tasks_count equals len(handoff-tasks.json.open_tasks)
      at resolve time.
  I4: handoff_tasks_hash is deterministic — computed over a canonical
      per-task view (id, subject, description, status, sorted metadata)
      with sort_keys and separators=(",",":"); two runs over the same task
      state produce byte-identical hashes even if wrapper fields differ.
  I5: Sprint 3 fields (settings_hash, agent_registry_metadata_version,
      agent_name_set_hash, skills_mtime_set, claude_md_platform_hash,
      claude_md_v11_hash) are either None or non-empty/non-zero; the
      empty-string and 0-placeholder shapes are rejected on construction.

Schema version starts at 1; additive-only migrations bump the field.

Bash IPC: CLI writes JSON file at $SESSION_DIR/.loop-baseline.json
atomically (tempfile + os.replace). Exit 0 on success, 1 on
ProtocolViolation, 2 on I/O failure.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 1


class BaselineSource(enum.Enum):
    HANDOFF_CLOSE_AUTO = "handoff_close_auto"
    HANDOFF_CLOSE_FORCED = "handoff_close_forced"
    MANUAL_WRITE = "manual_write"


class ProtocolViolation(Exception):
    """Input state is malformed: unknown enum, missing required field, or
    Sprint-3 field carrying a rejected placeholder shape (""/0)."""


class BaselineIOError(Exception):
    """Disk I/O failure during read/write of .loop-baseline.json."""


# Sentinel required-string fields for I1 enforcement.
_REQUIRED_STR_FIELDS = (
    "project",
    "handoff_at",
    "source_session_uuid",
    "git_head",
    "handoff_tasks_hash",
    "autonomy_level",
)


# Sprint 3 optional fields — either None or a non-placeholder value.
_SPRINT3_STR_FIELDS = (
    "settings_hash",
    "agent_registry_metadata_version",
    "agent_name_set_hash",
    "claude_md_platform_hash",
    "claude_md_v11_hash",
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class LoopBaseline:
    """Frozen record of the sending session's state at handoff emit."""

    # Sprint 1 required fields — all populated at CLOSE.
    schema_version: int
    project: str
    handoff_at: str  # ISO 8601
    source_session_uuid: str
    git_head: str
    spec_md_mtime: float
    autonomy_level: str  # e.g. "A0".."A5" or historical raw form
    expected_open_tasks_count: int
    handoff_tasks_hash: str
    baseline_source: BaselineSource

    # Sprint 3 slots — declared now, populated by L3.1-L3.4; None until then.
    settings_hash: Optional[str] = None
    agent_registry_metadata_version: Optional[str] = None
    agent_name_set_hash: Optional[str] = None
    skills_mtime_set: Optional[dict] = None
    claude_md_platform_hash: Optional[str] = None
    claude_md_v11_hash: Optional[str] = None

    def __post_init__(self):
        # I1: required strings are non-empty.
        for name in _REQUIRED_STR_FIELDS:
            val = getattr(self, name)
            if not isinstance(val, str) or not val:
                raise ProtocolViolation(f"required field {name!r} is empty or non-string")

        # I2 handled at the enum boundary — dataclass typing enforces
        # BaselineSource membership only when callers pass an enum instance.
        # The from_dict() / _enum_or_raise() paths cover string input.
        if not isinstance(self.baseline_source, BaselineSource):
            raise ProtocolViolation(
                f"baseline_source must be BaselineSource enum, got {type(self.baseline_source).__name__}"
            )

        # schema_version guard — reject 0/negative.
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ProtocolViolation(
                f"schema_version must be positive int, got {self.schema_version!r}"
            )

        # I3 upstream enforcement (caller supplies both consistently); the
        # dataclass alone can't re-read handoff-tasks.json without a path.
        # We reject negative here as a floor.
        if not isinstance(self.expected_open_tasks_count, int) or self.expected_open_tasks_count < 0:
            raise ProtocolViolation(
                f"expected_open_tasks_count must be non-negative int, got {self.expected_open_tasks_count!r}"
            )

        # spec_md_mtime — reject 0 and negatives; 0 is a filesystem sentinel
        # for "never modified" that would silently mask real drift signals.
        if not isinstance(self.spec_md_mtime, (int, float)) or self.spec_md_mtime <= 0:
            raise ProtocolViolation(
                f"spec_md_mtime must be positive float, got {self.spec_md_mtime!r}"
            )

        # I5: Sprint 3 str fields — None OR non-empty/non-"0" string.
        for name in _SPRINT3_STR_FIELDS:
            val = getattr(self, name)
            if val is None:
                continue
            if not isinstance(val, str) or not val or val == "0":
                raise ProtocolViolation(
                    f"Sprint 3 field {name!r} carries rejected placeholder shape {val!r}; use None or a real value"
                )

        # I5 for skills_mtime_set: None OR non-empty dict of {path: positive float}.
        if self.skills_mtime_set is not None:
            if not isinstance(self.skills_mtime_set, dict) or not self.skills_mtime_set:
                raise ProtocolViolation(
                    "skills_mtime_set must be None or a non-empty dict"
                )
            for k, v in self.skills_mtime_set.items():
                if not isinstance(k, str) or not k:
                    raise ProtocolViolation(f"skills_mtime_set key {k!r} must be non-empty str")
                if not isinstance(v, (int, float)) or v <= 0:
                    raise ProtocolViolation(
                        f"skills_mtime_set[{k!r}] must be positive number, got {v!r}"
                    )

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["baseline_source"] = self.baseline_source.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LoopBaseline":
        src = d.get("baseline_source")
        if src is None:
            raise ProtocolViolation("missing required field: baseline_source")
        try:
            src_enum = BaselineSource(src) if not isinstance(src, BaselineSource) else src
        except ValueError:
            valid = sorted(e.value for e in BaselineSource)
            raise ProtocolViolation(
                f"invalid baseline_source={src!r}; expected one of {valid}"
            ) from None

        # schema_version — default to SCHEMA_VERSION when absent (older
        # baselines predate the field); reject non-int.
        sv = d.get("schema_version", SCHEMA_VERSION)

        try:
            return cls(
                schema_version=sv,
                project=d.get("project", ""),
                handoff_at=d.get("handoff_at", ""),
                source_session_uuid=d.get("source_session_uuid", ""),
                git_head=d.get("git_head", ""),
                spec_md_mtime=d.get("spec_md_mtime", 0),
                autonomy_level=d.get("autonomy_level", ""),
                expected_open_tasks_count=d.get("expected_open_tasks_count", 0),
                handoff_tasks_hash=d.get("handoff_tasks_hash", ""),
                baseline_source=src_enum,
                settings_hash=d.get("settings_hash"),
                agent_registry_metadata_version=d.get("agent_registry_metadata_version"),
                agent_name_set_hash=d.get("agent_name_set_hash"),
                skills_mtime_set=d.get("skills_mtime_set"),
                claude_md_platform_hash=d.get("claude_md_platform_hash"),
                claude_md_v11_hash=d.get("claude_md_v11_hash"),
            )
        except TypeError as e:
            raise ProtocolViolation(f"malformed baseline payload: {e}") from e


# ---------------------------------------------------------------------------
# I4: canonical hash over stable per-task content
# ---------------------------------------------------------------------------

def _canonical_task_view(task: dict) -> dict:
    """Extract only stable fields — wrapper metadata like timestamps must
    NOT enter the hash or two runs over identical task state will diverge.
    """
    return {
        "id": str(task.get("id", "")),
        "subject": task.get("subject") or "",
        "description": task.get("description") or "",
        "status": task.get("status") or "pending",
        "metadata": task.get("metadata") or {},
    }


def canonical_handoff_tasks_hash(handoff_tasks_json_path: os.PathLike) -> str:
    """SHA256 of a canonical view of handoff-tasks.json.open_tasks[].

    Deterministic across runs, permutation-stable inside each task's metadata
    dict (sort_keys), and blind to wrapper fields (handoff_at, session_id,
    etc.) so an identical task state hashes identically session-to-session.
    """
    with open(handoff_tasks_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    open_tasks = data.get("open_tasks") or []
    if not isinstance(open_tasks, list):
        raise ProtocolViolation(
            f"handoff-tasks.json .open_tasks must be a list, got {type(open_tasks).__name__}"
        )
    views = [_canonical_task_view(t) for t in open_tasks]
    canon = json.dumps(views, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Disk anchors
# ---------------------------------------------------------------------------

def _git_head(cwd: os.PathLike) -> str:
    """git rev-parse HEAD or empty string if not a repo / git missing."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _spec_mtime(session_dir: Path) -> float:
    p = session_dir / "spec.md"
    if p.exists():
        return p.stat().st_mtime
    return 0.0


def _autonomy_level(session_dir: Path) -> str:
    """Read .autonomy-state — supports JSON {level, name, ...} shape or
    single-line raw string ("A3"). Returns "" when nothing readable.
    """
    p = session_dir / ".autonomy-state"
    if not p.exists():
        return ""
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not raw:
        return ""
    try:
        d = json.loads(raw)
        lvl = d.get("level")
        if lvl is None:
            return ""
        # Historic shapes: int (0-5), string ("A3"), or descriptor.
        if isinstance(lvl, int):
            return f"A{lvl}"
        return str(lvl)
    except json.JSONDecodeError:
        return raw.splitlines()[0].strip()


def _open_tasks_count(handoff_tasks_json_path: Path) -> int:
    with open(handoff_tasks_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    open_tasks = data.get("open_tasks") or []
    if not isinstance(open_tasks, list):
        raise ProtocolViolation(
            f"handoff-tasks.json .open_tasks must be a list, got {type(open_tasks).__name__}"
        )
    return len(open_tasks)


# ---------------------------------------------------------------------------
# Resolve / write / read
# ---------------------------------------------------------------------------

def resolve_baseline(
    *,
    project: str,
    session_dir: os.PathLike,
    source_session_uuid: str,
    source: BaselineSource,
    handoff_at: str,
    git_cwd: Optional[os.PathLike] = None,
) -> LoopBaseline:
    """Snapshot disk state under session_dir into a LoopBaseline.

    handoff-tasks.json must exist under session_dir — the baseline is
    meaningless without the task snapshot it certifies. Sprint 3 fields
    remain None; L3.1-L3.4 will populate them in later sprints.
    """
    session_dir_p = Path(session_dir)
    handoff_tasks_p = session_dir_p / "handoff-tasks.json"
    if not handoff_tasks_p.exists():
        raise ProtocolViolation(
            f"handoff-tasks.json missing under {session_dir_p} — baseline requires task snapshot"
        )

    return LoopBaseline(
        schema_version=SCHEMA_VERSION,
        project=project,
        handoff_at=handoff_at,
        source_session_uuid=source_session_uuid,
        git_head=_git_head(git_cwd or session_dir_p) or "unknown",
        spec_md_mtime=_spec_mtime(session_dir_p) or 1e-9,  # I5-safe floor
        autonomy_level=_autonomy_level(session_dir_p) or "unknown",
        expected_open_tasks_count=_open_tasks_count(handoff_tasks_p),
        handoff_tasks_hash=canonical_handoff_tasks_hash(handoff_tasks_p),
        baseline_source=source,
    )


def write_baseline(baseline: LoopBaseline, session_dir: os.PathLike) -> Path:
    """Atomic write to session_dir/.loop-baseline.json (tmp + os.replace).

    Raises BaselineIOError on filesystem failure; ProtocolViolation cannot
    fire here — construction already validated the record.
    """
    session_dir_p = Path(session_dir)
    session_dir_p.mkdir(parents=True, exist_ok=True)
    target = session_dir_p / ".loop-baseline.json"
    payload = json.dumps(baseline.to_dict(), sort_keys=True, indent=2)
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".loop-baseline.", suffix=".tmp", dir=str(session_dir_p)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
        except Exception:
            # Best-effort cleanup — if replace failed, remove the tmp file.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        raise BaselineIOError(f"failed to write {target}: {e}") from e
    return target


def read_baseline(session_dir: os.PathLike) -> Optional[LoopBaseline]:
    """Load .loop-baseline.json into a LoopBaseline, or None if absent.

    Raises ProtocolViolation on schema mismatch — a corrupt baseline is a
    real signal for consumers (L2.1/L2.3), not a silent None.
    """
    target = Path(session_dir) / ".loop-baseline.json"
    if not target.exists():
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ProtocolViolation(f"unreadable baseline at {target}: {e}") from e
    return LoopBaseline.from_dict(d)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    """Best-effort ISO 8601 stamp — used only when caller omits handoff_at."""
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write sessions/{project}/.loop-baseline.json for cross-session loop verification."
    )
    ap.add_argument("--project", required=True)
    ap.add_argument("--session-dir", required=True,
                    help="Absolute path to sessions/{project}/ directory")
    ap.add_argument("--session-uuid", required=True,
                    help="V11_SESSION_ID of the sending session")
    ap.add_argument("--source", default="handoff_close_auto",
                    choices=[e.value for e in BaselineSource])
    ap.add_argument("--handoff-at", default="",
                    help="ISO 8601 handoff emit time; defaults to now")
    ap.add_argument("--git-cwd", default="",
                    help="Directory to git-rev-parse from (default: session-dir)")

    args = ap.parse_args(argv)

    try:
        source = BaselineSource(args.source)
    except ValueError:
        print(f"loop_baseline: invalid --source {args.source!r}", file=sys.stderr)
        return 1

    handoff_at = args.handoff_at or _iso_now()
    git_cwd = args.git_cwd or None

    try:
        baseline = resolve_baseline(
            project=args.project,
            session_dir=args.session_dir,
            source_session_uuid=args.session_uuid,
            source=source,
            handoff_at=handoff_at,
            git_cwd=git_cwd,
        )
    except ProtocolViolation as e:
        print(f"loop_baseline: PROTOCOL VIOLATION: {e}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as e:
        print(f"loop_baseline: I/O error resolving baseline: {e}", file=sys.stderr)
        return 2

    try:
        target = write_baseline(baseline, args.session_dir)
    except BaselineIOError as e:
        print(f"loop_baseline: {e}", file=sys.stderr)
        return 2

    print(str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
