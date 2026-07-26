"""V11.26 — Handoff decision state machine.

Extracted from scripts/handoff (V11.25.2). Replaces the silent-fall-through
bash case statement that resolved to _CONF_DECISION="UNKNOWN" with an
explicit, typed state machine that raises on unhandled state combinations.

Invariants (enforced):
  I1: resolve_decision() returns a HandoffDecision, never UNKNOWN, never None.
  I2: Unknown input enums raise ProtocolViolation (silent fall-through impossible).
  I3: Unhandled (state_source, summary_source) tuples raise UnhandledHandoffState.
  I4: AUTHORITATIVE decision implies empty downgrade_reasons (consistency check).
  I5: SessionSummarySource in {stale_replaced, stale_unarchived, synthesized}
      ALWAYS contributes 'session_summary_not_from_disk' to downgrade_reasons.

Schema: .handoff-confidence.json is additive only — no field rename, no removal.
Bash IPC: JSON on stdin, JSON on stdout. Exit 0=ok, 1=ProtocolViolation, 2=UnhandledHandoffState.

Bash parity contract (V11.25.2):
  StateSource values mirror $STATE_SOURCE assignments at scripts/handoff:388,392
  SessionSummarySource values mirror $SESSION_SUMMARY_SOURCE assignments at
    scripts/handoff:577, 632, 638, 648, 675, 960.
"""

import enum
import json
import sys


class SessionSummarySource(enum.Enum):
    MISSING = "missing"
    WRITTEN = "written"
    STALE_REPLACED = "stale-replaced"
    STALE_UNARCHIVED = "stale-unarchived"
    SYNTHESIZED = "synthesized"


class StateSource(enum.Enum):
    PER_SESSION = "per-session"
    AGGREGATE = "aggregate"


class LedgerSource(enum.Enum):
    LEDGER = "ledger"
    LEGACY = "legacy"


class HandoffDecision(enum.Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    AUTHORITATIVE_WITH_CAVEATS = "AUTHORITATIVE-WITH-CAVEATS"
    LEGACY_AGGREGATE = "LEGACY-AGGREGATE"
    PER_SESSION = "PER-SESSION"
    PER_SESSION_STUB_SUMMARY = "PER-SESSION-STUB-SUMMARY"
    PER_SESSION_NO_DISK_SUMMARY = "PER-SESSION-NO-DISK-SUMMARY"


class ProtocolViolation(Exception):
    """Input state is malformed: unknown enum value or missing required field."""


class UnhandledHandoffState(Exception):
    """No resolution rule for this (state_source, summary_source) tuple.

    Runtime replacement for the bash case-statement silent fall-through to
    _CONF_DECISION="UNKNOWN". A future state added without a resolution
    branch surfaces here as an explicit raise + non-zero exit, instead of
    a silent incorrect downgrade in production.
    """


_NONCANONICAL_SOURCES = frozenset({
    SessionSummarySource.STALE_REPLACED,
    SessionSummarySource.STALE_UNARCHIVED,
    SessionSummarySource.SYNTHESIZED,
})


def resolve_decision(
    state_source: StateSource,
    summary_source: SessionSummarySource,
    ledger_source: LedgerSource,
    is_stub: bool,
    stale_count: int,
    families_count: int,
    pending_reviews: int,
) -> dict:
    """Resolve handoff confidence decision + conditions + downgrade_reasons.

    Returns a dict matching .handoff-confidence.json (minus generated_at,
    which the caller passes through).
    """
    # Type guards (I2): callers from main() already converted, but library
    # callers may pass raw values. Reject anything not in the declared enums.
    if not isinstance(state_source, StateSource):
        raise ProtocolViolation(f"state_source must be StateSource, got {type(state_source).__name__}")
    if not isinstance(summary_source, SessionSummarySource):
        raise ProtocolViolation(f"summary_source must be SessionSummarySource, got {type(summary_source).__name__}")
    if not isinstance(ledger_source, LedgerSource):
        raise ProtocolViolation(f"ledger_source must be LedgerSource, got {type(ledger_source).__name__}")

    ss_noncanonical = summary_source in _NONCANONICAL_SOURCES
    downgrade_reasons = []
    if stale_count > 0:
        downgrade_reasons.append("stale_in_progress_detected")
    if families_count > 0:
        downgrade_reasons.append("near_duplicate_families_detected")
    if pending_reviews > 0:
        downgrade_reasons.append("pending_reviews_detected")
    if is_stub:
        downgrade_reasons.append("summary_is_unedited_stub")
    if ss_noncanonical:
        downgrade_reasons.append("session_summary_not_from_disk")

    if state_source is StateSource.PER_SESSION:
        if is_stub:
            decision = HandoffDecision.PER_SESSION_STUB_SUMMARY
        elif ss_noncanonical:
            decision = HandoffDecision.PER_SESSION_NO_DISK_SUMMARY
        else:
            decision = HandoffDecision.PER_SESSION
    elif state_source is StateSource.AGGREGATE:
        if ledger_source is LedgerSource.LEDGER:
            if downgrade_reasons:
                decision = HandoffDecision.AUTHORITATIVE_WITH_CAVEATS
            else:
                decision = HandoffDecision.AUTHORITATIVE
        elif ledger_source is LedgerSource.LEGACY:
            decision = HandoffDecision.LEGACY_AGGREGATE
        else:
            # I3: unhandled ledger_source branch. Should be unreachable given
            # the isinstance guard above, but belt-and-braces.
            raise UnhandledHandoffState(
                f"aggregate state with unhandled ledger_source={ledger_source!r}"
            )
    else:
        # I3: unhandled state_source. Defensive — isinstance guard catches
        # malformed input, this catches future-added enum values without rules.
        raise UnhandledHandoffState(
            f"unhandled state_source={state_source!r} (summary_source={summary_source!r})"
        )

    # I4 consistency check: AUTHORITATIVE must have zero downgrade_reasons.
    if decision is HandoffDecision.AUTHORITATIVE and downgrade_reasons:
        raise UnhandledHandoffState(
            f"invariant I4 violated: AUTHORITATIVE with downgrade_reasons={downgrade_reasons}"
        )

    return {
        "decision": decision.value,
        "conditions": {
            "state_source": state_source.value,
            "session_summary_source": summary_source.value,
            "stale_in_progress_count": stale_count,
            "near_duplicate_families": families_count,
            "pending_reviews": pending_reviews,
            "summary_is_unedited_stub": is_stub,
            "summary_is_noncanonical": ss_noncanonical,
        },
        "downgrade_reasons": downgrade_reasons,
    }


def _enum_or_raise(enum_cls, value, field_name):
    """Parse a string into enum_cls or raise ProtocolViolation with valid options."""
    if value is None:
        raise ProtocolViolation(f"missing required field: {field_name}")
    try:
        return enum_cls(value)
    except ValueError:
        valid = sorted(e.value for e in enum_cls)
        raise ProtocolViolation(
            f"invalid {field_name}={value!r}; expected one of {valid}"
        ) from None


def main():
    """CLI: read state JSON from stdin, write decision JSON to stdout.

    Stdin schema (V11.26):
        {
          "state_source": "per-session" | "aggregate",
          "session_summary_source": "missing|written|stale-replaced|stale-unarchived|synthesized",
          "ledger_source": "ledger" | "legacy"  (default: "legacy"),
          "is_stub": 0 | 1  (default: 0),
          "stale_in_progress_count": <int>  (default: 0),
          "near_duplicate_families": <int>   (default: 0),
          "pending_reviews": <int>           (default: 0),
          "generated_at": "<iso-8601>"       (passed through to output)
        }

    Exit codes:
        0 — success, decision written to stdout
        1 — ProtocolViolation (malformed input)
        2 — UnhandledHandoffState (case completeness gap)
    """
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"handoff_state: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        state_source = _enum_or_raise(StateSource, payload.get("state_source"), "state_source")
        summary_source = _enum_or_raise(
            SessionSummarySource, payload.get("session_summary_source"), "session_summary_source"
        )
        ledger_source = _enum_or_raise(
            LedgerSource, payload.get("ledger_source", "legacy"), "ledger_source"
        )
        is_stub = bool(int(payload.get("is_stub", 0)))
        stale_count = int(payload.get("stale_in_progress_count", 0))
        families_count = int(payload.get("near_duplicate_families", 0))
        pending_reviews = int(payload.get("pending_reviews", 0))
        generated_at = payload.get("generated_at", "")
    except ProtocolViolation as e:
        print(f"handoff_state: PROTOCOL VIOLATION: {e}", file=sys.stderr)
        sys.exit(1)
    except (TypeError, ValueError) as e:
        print(f"handoff_state: malformed input field: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = resolve_decision(
            state_source, summary_source, ledger_source,
            is_stub, stale_count, families_count, pending_reviews,
        )
    except UnhandledHandoffState as e:
        print(f"handoff_state: UNHANDLED STATE: {e}", file=sys.stderr)
        sys.exit(2)
    except ProtocolViolation as e:
        print(f"handoff_state: PROTOCOL VIOLATION: {e}", file=sys.stderr)
        sys.exit(1)

    if generated_at:
        result["generated_at"] = generated_at

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
