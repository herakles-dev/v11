"""L2.3a — cross-session handoff loop event ledger.

Companion to `scripts/lib/loop_baseline.py` (L1.3a — the baseline written by
the SENDING session at CLOSE). This module appends loop-observation events
written by the RECEIVING session at OPEN, so a query against
`~/.agent-metrics/loop-events.jsonl` can reconstruct what happened
cross-session — including the diagnostic signature of the silent V11.17
auto-rehydrate failure documented in `sessions/v11-handoff-cross-session-
loop/spec.md § Empirical Evidence`.

Invariants (enforced):
  I1: ts, project, session_id, kind, expected, actual, marker_seen,
      auto_rehydrate_env, failure_mode are non-empty / correctly typed.
  I2: kind and failure_mode parsed via enums; unknown values raise
      ProtocolViolation (silent fall-through impossible).
  I3: append is atomic under flock — concurrent writers produce a single
      whole-line entry per event, never interleaved bytes.
  I4: event serializes with sort_keys=True + compact separators for
      grep-ability across artifacts (mirrors L1.3a canonical view).

Schema evolution: `LoopEventKind` is deliberately additive — L2.4 will add
REHYDRATE_ACK (or similar) once the loop is bidirectional; today only
REHYDRATE_MISSED ships.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import fcntl
import json
import os
import sys
from pathlib import Path
from typing import Optional


class LoopEventKind(enum.Enum):
    REHYDRATE_MISSED = "rehydrate_missed"
    # L2.4 (v11-handoff-cross-session-loop): success case — verification
    # passed. Closes the round-trip so operators can grep loop-events.jsonl
    # for {event: handoff_ack} rows as receipts of a healthy loop cycle.
    HANDOFF_ACK = "handoff_ack"
    # L2.5 (v11-handoff-cross-session-loop): safety net — a spawn latch
    # (.last-spawn-at) exists with no matching ack or rehydrate_missed event
    # within V11_LOOP_ORPHAN_MINUTES. Emitted by hooks/session-end.
    HANDOFF_ORPHAN = "handoff_orphan"


class FailureMode(enum.Enum):
    """Why the receiving session's TaskList did not match the baseline.

    - SKILL_NOT_INVOKED: `.handoff-surfaced` marker exists AND live
      TaskList=0 while baseline.expected>0 → detect-project nudged but the
      team-orchestrator skill was never actually invoked. Diagnostic
      signature from the 2026-09-01 dogfood.
    - GATE_OFF: V11_AUTO_REHYDRATE=off — user has deliberately disabled
      rehydrate; divergence is expected, not a bug.
    - SCRIPT_ERROR: `scripts/v11-resume-tasks` exit non-zero or malformed
      output — rehydrate tried but failed.
    - MANUAL_OVERRIDE: TaskList non-empty on first Read — user pre-created
      tasks; contract says user wins.
    - IDENTITY_MISMATCH: counts match but (session_uuid, task_id) identity
      set does not (v11.24 pattern). Bug-H-class ghost-task resurrection.
    """
    SKILL_NOT_INVOKED = "skill_not_invoked"
    GATE_OFF = "gate_off"
    SCRIPT_ERROR = "script_error"
    MANUAL_OVERRIDE = "manual_override"
    IDENTITY_MISMATCH = "identity_mismatch"


class AutoRehydrateEnv(enum.Enum):
    """Observed state of $V11_AUTO_REHYDRATE at event time."""
    ON = "on"
    OFF = "off"
    UNSET = "unset"


class ProtocolViolation(Exception):
    """Input malformed: unknown enum, missing required field, wrong type."""


DEFAULT_LEDGER_PATH = "~/.agent-metrics/loop-events.jsonl"


_REQUIRED_STR_FIELDS = ("ts", "project", "session_id")


@dataclasses.dataclass(frozen=True, kw_only=True)
class LoopEvent:
    """Frozen record of one cross-session loop observation."""

    ts: str
    project: str
    session_id: str
    kind: LoopEventKind
    # REHYDRATE_MISSED + HANDOFF_ACK share expected/actual.
    expected: Optional[int] = None
    actual: Optional[int] = None
    # REHYDRATE_MISSED-only.
    marker_seen: Optional[bool] = None
    auto_rehydrate_env: Optional[AutoRehydrateEnv] = None
    failure_mode: Optional[FailureMode] = None
    identity_delta: Optional[dict] = None  # {"missing": [...], "extra": [...]}
    # HANDOFF_ACK-only (L2.4).
    prev_handoff_at: Optional[str] = None
    identity_matched: Optional[bool] = None
    baseline_delta_fields: Optional[list] = None
    # HANDOFF_ORPHAN-only (L2.5).
    spawn_ts: Optional[str] = None
    detected_by: Optional[str] = None
    age_minutes: Optional[int] = None

    def __post_init__(self):
        for name in _REQUIRED_STR_FIELDS:
            val = getattr(self, name)
            if not isinstance(val, str) or not val:
                raise ProtocolViolation(f"required field {name!r} empty or non-string")

        if not isinstance(self.kind, LoopEventKind):
            raise ProtocolViolation(
                f"kind must be LoopEventKind enum, got {type(self.kind).__name__}"
            )

        # Kind-dispatched validation.
        if self.kind is LoopEventKind.REHYDRATE_MISSED:
            self._validate_rehydrate_missed()
        elif self.kind is LoopEventKind.HANDOFF_ACK:
            self._validate_handoff_ack()
        elif self.kind is LoopEventKind.HANDOFF_ORPHAN:
            self._validate_handoff_orphan()

        if self.identity_delta is not None:
            if not isinstance(self.identity_delta, dict):
                raise ProtocolViolation(
                    "identity_delta must be None or dict {missing:[...], extra:[...]}"
                )
            for k in ("missing", "extra"):
                if k in self.identity_delta:
                    v = self.identity_delta[k]
                    if not isinstance(v, list):
                        raise ProtocolViolation(
                            f"identity_delta[{k!r}] must be list of task ids, got {type(v).__name__}"
                        )

    def _validate_rehydrate_missed(self):
        if not isinstance(self.failure_mode, FailureMode):
            raise ProtocolViolation(
                f"REHYDRATE_MISSED: failure_mode must be FailureMode enum, got {type(self.failure_mode).__name__}"
            )
        if not isinstance(self.auto_rehydrate_env, AutoRehydrateEnv):
            raise ProtocolViolation(
                f"REHYDRATE_MISSED: auto_rehydrate_env must be AutoRehydrateEnv enum, got {type(self.auto_rehydrate_env).__name__}"
            )
        for name in ("expected", "actual"):
            val = getattr(self, name)
            if not isinstance(val, int) or val < 0:
                raise ProtocolViolation(
                    f"REHYDRATE_MISSED: {name} must be non-negative int, got {val!r}"
                )
        if not isinstance(self.marker_seen, bool):
            raise ProtocolViolation(
                f"REHYDRATE_MISSED: marker_seen must be bool, got {type(self.marker_seen).__name__}"
            )

    def _validate_handoff_ack(self):
        for name in ("expected", "actual"):
            val = getattr(self, name)
            if not isinstance(val, int) or val < 0:
                raise ProtocolViolation(
                    f"HANDOFF_ACK: {name} must be non-negative int, got {val!r}"
                )
        if not isinstance(self.prev_handoff_at, str) or not self.prev_handoff_at:
            raise ProtocolViolation(
                f"HANDOFF_ACK: prev_handoff_at must be non-empty str, got {self.prev_handoff_at!r}"
            )
        if not isinstance(self.identity_matched, bool):
            raise ProtocolViolation(
                f"HANDOFF_ACK: identity_matched must be bool, got {type(self.identity_matched).__name__}"
            )
        if not isinstance(self.baseline_delta_fields, list):
            raise ProtocolViolation(
                f"HANDOFF_ACK: baseline_delta_fields must be list (may be empty), got {type(self.baseline_delta_fields).__name__}"
            )

    def _validate_handoff_orphan(self):
        if not isinstance(self.spawn_ts, str) or not self.spawn_ts:
            raise ProtocolViolation(
                f"HANDOFF_ORPHAN: spawn_ts must be non-empty str, got {self.spawn_ts!r}"
            )
        if not isinstance(self.detected_by, str) or not self.detected_by:
            raise ProtocolViolation(
                f"HANDOFF_ORPHAN: detected_by must be non-empty str, got {self.detected_by!r}"
            )
        if not isinstance(self.age_minutes, int) or self.age_minutes < 0:
            raise ProtocolViolation(
                f"HANDOFF_ORPHAN: age_minutes must be non-negative int, got {self.age_minutes!r}"
            )

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["kind"] = self.kind.value
        if self.failure_mode is not None:
            d["failure_mode"] = self.failure_mode.value
        if self.auto_rehydrate_env is not None:
            d["auto_rehydrate_env"] = self.auto_rehydrate_env.value
        return d

    def to_jsonl_line(self) -> str:
        """Compact single-line JSON with sorted keys for grep-ability."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> "LoopEvent":
        def _enum(cls_, val, field):
            if val is None:
                raise ProtocolViolation(f"missing required field: {field}")
            try:
                return cls_(val) if not isinstance(val, cls_) else val
            except ValueError:
                valid = sorted(e.value for e in cls_)
                raise ProtocolViolation(
                    f"invalid {field}={val!r}; expected one of {valid}"
                ) from None

        def _enum_optional(cls_, val, field):
            if val is None:
                return None
            return _enum(cls_, val, field)

        kind = _enum(LoopEventKind, d.get("kind"), "kind")
        failure = _enum_optional(FailureMode, d.get("failure_mode"), "failure_mode")
        env = _enum_optional(AutoRehydrateEnv, d.get("auto_rehydrate_env"), "auto_rehydrate_env")

        _ms = d.get("marker_seen")
        _im = d.get("identity_matched")
        try:
            return cls(
                ts=d.get("ts", ""),
                project=d.get("project", ""),
                session_id=d.get("session_id", ""),
                kind=kind,
                expected=d.get("expected"),
                actual=d.get("actual"),
                marker_seen=(None if _ms is None else bool(_ms)),
                auto_rehydrate_env=env,
                failure_mode=failure,
                identity_delta=d.get("identity_delta"),
                prev_handoff_at=d.get("prev_handoff_at"),
                identity_matched=(None if _im is None else bool(_im)),
                baseline_delta_fields=d.get("baseline_delta_fields"),
                spawn_ts=d.get("spawn_ts"),
                detected_by=d.get("detected_by"),
                age_minutes=d.get("age_minutes"),
            )
        except TypeError as e:
            raise ProtocolViolation(f"malformed event payload: {e}") from e


def _resolve_ledger_path(ledger_path: Optional[os.PathLike] = None) -> Path:
    if ledger_path:
        return Path(os.path.expanduser(str(ledger_path)))
    return Path(os.path.expanduser(DEFAULT_LEDGER_PATH))


def append_loop_event(event: LoopEvent,
                      ledger_path: Optional[os.PathLike] = None) -> Path:
    """Atomic append to loop-events.jsonl under flock (LOCK_EX).

    Concurrent writers serialize; the ledger never sees a partial or
    interleaved line. Returns the resolved ledger path.

    Directory is created on first write. Best-effort: I/O errors bubble up
    as OSError; callers (e.g. detect-project) MUST wrap in `|| true` so a
    ledger write failure never breaks the receiving session.
    """
    target = _resolve_ledger_path(ledger_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = event.to_jsonl_line() + "\n"
    with open(target, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return target


def read_loop_events(ledger_path: Optional[os.PathLike] = None) -> list:
    """Yield-style read as a list — for tests and future consumer scripts.

    Malformed lines raise ProtocolViolation; the ledger is authoritative,
    silent skip would hide corruption.
    """
    target = _resolve_ledger_path(ledger_path)
    if not target.exists():
        return []
    events = []
    with open(target, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                raise ProtocolViolation(
                    f"loop-events.jsonl line {i} is malformed JSON: {e}"
                ) from e
            events.append(LoopEvent.from_dict(d))
    return events


def _iso_now() -> str:
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Append one loop-observation event to ~/.agent-metrics/loop-events.jsonl."
    )
    ap.add_argument("--project", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--kind", default="rehydrate_missed",
                    choices=[e.value for e in LoopEventKind])
    # REHYDRATE_MISSED + HANDOFF_ACK share these.
    ap.add_argument("--expected", type=int, default=None)
    ap.add_argument("--actual", type=int, default=None)
    # REHYDRATE_MISSED-only.
    ap.add_argument("--marker-seen", type=int, default=None,
                    choices=[0, 1], help="0|1 (defaults to 0 for rehydrate_missed)")
    ap.add_argument("--auto-rehydrate-env", default=None,
                    choices=[e.value for e in AutoRehydrateEnv],
                    help="defaults to 'unset' for rehydrate_missed")
    ap.add_argument("--failure-mode", default=None,
                    choices=[e.value for e in FailureMode])
    ap.add_argument("--identity-delta", default="",
                    help='JSON: {"missing":[...],"extra":[...]}')
    # HANDOFF_ACK-only (L2.4).
    ap.add_argument("--prev-handoff-at", default=None,
                    help="ISO 8601 from baseline.handoff_at")
    ap.add_argument("--identity-matched", type=int, default=None,
                    choices=[0, 1], help="0|1 — true when count+IDs match")
    ap.add_argument("--baseline-delta-fields", default=None,
                    help="comma-separated field names OR JSON list")
    # HANDOFF_ORPHAN-only (L2.5).
    ap.add_argument("--spawn-ts", default=None,
                    help="ISO 8601 spawn latch mtime")
    ap.add_argument("--detected-by", default=None,
                    help="session_id of the observer that noticed the orphan")
    ap.add_argument("--age-minutes", type=int, default=None,
                    help="minutes since spawn without matching ack/missed")
    # Shared knobs.
    ap.add_argument("--ts", default="",
                    help="ISO 8601 timestamp; defaults to now")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER_PATH,
                    help="Override ledger path (test escape hatch)")

    args = ap.parse_args(argv)

    identity = None
    if args.identity_delta:
        try:
            identity = json.loads(args.identity_delta)
        except json.JSONDecodeError as e:
            print(f"loop_events: --identity-delta must be valid JSON: {e}", file=sys.stderr)
            return 1

    # baseline-delta-fields accepts comma-sep OR JSON list — normalise to list.
    baseline_delta = None
    if args.baseline_delta_fields is not None:
        raw = args.baseline_delta_fields.strip()
        if not raw:
            baseline_delta = []
        elif raw.startswith("["):
            try:
                baseline_delta = json.loads(raw)
                if not isinstance(baseline_delta, list):
                    raise ValueError("must be JSON list")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"loop_events: --baseline-delta-fields JSON must be a list: {e}", file=sys.stderr)
                return 1
        else:
            baseline_delta = [f for f in raw.split(",") if f]

    kind = LoopEventKind(args.kind)
    ts = args.ts or _iso_now()

    # Backward-compat: REHYDRATE_MISSED defaults kept as marker_seen=0,
    # auto_rehydrate_env=unset when caller omits them. Applied here (not at
    # argparse defaults) so HANDOFF_ACK/HANDOFF_ORPHAN events don't get
    # noisy zero-valued marker_seen/auto_rehydrate_env fields they don't need.
    if kind is LoopEventKind.REHYDRATE_MISSED:
        if args.marker_seen is None:
            args.marker_seen = 0
        if args.auto_rehydrate_env is None:
            args.auto_rehydrate_env = "unset"

    kw = dict(
        ts=ts, project=args.project, session_id=args.session_id, kind=kind,
        identity_delta=identity,
    )
    if args.expected is not None:
        kw["expected"] = args.expected
    if args.actual is not None:
        kw["actual"] = args.actual
    if args.marker_seen is not None:
        kw["marker_seen"] = bool(args.marker_seen)
    if args.auto_rehydrate_env is not None:
        kw["auto_rehydrate_env"] = AutoRehydrateEnv(args.auto_rehydrate_env)
    if args.failure_mode is not None:
        kw["failure_mode"] = FailureMode(args.failure_mode)
    if args.prev_handoff_at is not None:
        kw["prev_handoff_at"] = args.prev_handoff_at
    if args.identity_matched is not None:
        kw["identity_matched"] = bool(args.identity_matched)
    if baseline_delta is not None:
        kw["baseline_delta_fields"] = baseline_delta
    if args.spawn_ts is not None:
        kw["spawn_ts"] = args.spawn_ts
    if args.detected_by is not None:
        kw["detected_by"] = args.detected_by
    if args.age_minutes is not None:
        kw["age_minutes"] = args.age_minutes

    try:
        event = LoopEvent(**kw)
    except ProtocolViolation as e:
        print(f"loop_events: PROTOCOL VIOLATION: {e}", file=sys.stderr)
        return 1

    try:
        target = append_loop_event(event, args.ledger)
    except OSError as e:
        print(f"loop_events: I/O error: {e}", file=sys.stderr)
        return 2

    print(str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
