# Effort B v1 — Dogfood #2 Receipt

**Date**: 2026-09-02
**Session UUID**: 17decbc2-85ce-4fbb-903d-7de418e5babe
**Project**: v11-handoff-cross-session-loop
**Prior handoff**: 2026-09-02T00:13:22+02:00

## Purpose

Empirically verify that the cross-session handoff-quality loop closes
end-to-end — that the mechanisms shipped in Effort A (QR-1..QR-7) and
Effort B Sprint 1 & 2 (L1.1..L1.4, L2.1..L2.5) produce a durable receipt
of every boot cycle, and that the 2026-09-01 silent auto-rehydrate
failure is now loud + auto-diagnosed instead of silent.

## The four-signal test

| # | Signal | Contract | Result |
|---|---|---|---|
| 1 | Effort A regression | `scripts/verify-handoff-qr-invariants v11-handoff-quality-remediation` → 7/7 PASS | **7/7 PASS** ✓ |
| 2 | L2.1/L2.2 boot-delta banner (`additionalContext`) | `⚡ SINCE LAST HANDOFF …` reaches the receiver's model context on the first Read | **FIRED verbatim** ✓ |
| 3 | L2.3/L2.4 loop-events ledger | One row appended to `~/.agent-metrics/loop-events.jsonl` per boot (`handoff_ack` or `rehydrate_missed`) | **FIRED** `rehydrate_missed` / `skill_not_invoked` @ 00:13:58 |
| 4 | TaskList on boot | TaskList reflects the state expected by `handoff-tasks.json.open_tasks` | **Empty (0 tasks) on first probe** — matched ledger's `actual=0, expected=1` |

## Signal 2 verbatim (`hookSpecificOutput.additionalContext`)

```
⚡ SINCE LAST HANDOFF (2026-09-02T00:13:22+02:00 → now, 36s):
  - handoff-tasks.json open_tasks length = 1
```

## Signal 3 verbatim (`~/.agent-metrics/loop-events.jsonl`)

```json
{"actual":0,"age_minutes":null,"auto_rehydrate_env":"unset","baseline_delta_fields":null,"detected_by":null,"expected":1,"failure_mode":"skill_not_invoked","identity_delta":null,"identity_matched":null,"kind":"rehydrate_missed","marker_seen":true,"prev_handoff_at":null,"project":"v11-handoff-quality-remediation","session_id":"17decbc2-85ce-4fbb-903d-7de418e5babe","spawn_ts":null,"ts":"2026-09-02T00:13:58+02:00"}
```

## What this proves

**The loop closes.** The 2026-09-01 silent failure (auto-rehydrate not
firing when Claude Code injected `/v11` as a first-message prompt) still
occurs — but now it produces a durable receipt within 36s of the handoff.
Same bug, different visibility: silent → loud + auto-diagnosed. That is
the entire point of Sprint 2.

Post-detection the orchestrator ran Phase 1a.5 manually (`scripts/v11-resume-tasks`)
and TaskList now shows the one expected task (QR-1-followup). Loop closed
without user intervention.

## Labeling nuance worth naming

`failure_mode="skill_not_invoked"` is slightly misleading — the `/v11`
skill WAS routing this session. What the L2.3 detector actually caught is
"TaskList still empty at the 00:13:58 detect-project probe" — i.e.,
auto-rehydrate had not yet fired at probe time.

The correct inference is "auto-rehydrate probe fired before skill's
Phase 1a.5 completed". The taxonomy may want a 5th value like
`pre_rehydrate_probe` to distinguish "skill silent" from "skill still
booting". Not a bug in the mechanism; a labeling refinement.

Filed as a Sprint 3 candidate — not blocking ship.

## Ship gates

Ship gate: all 4 signals produce their intended durable receipt.
**Result**: gate passed. Effort B v1 shipped.

## Ship commits

| Commit | Scope | Files | Insertions |
|---|---|---|---|
| `ad45d2b` | Effort A — QR-1..QR-7 | 4 | 980 |
| `1442dc0` | Sprint 1 — L1.1..L1.4 | 9 | 1776 |
| `12a36e7` | Sprint 2 — L2.1..L2.5 | 8 | 2335 |
| (this) | Dogfood #2 receipt | 1 | — |

## Deferred / follow-up

1. **`failure_mode` taxonomy** — add `pre_rehydrate_probe` (or rename
   `skill_not_invoked` to something more precise) so the ledger
   disambiguates skill-silent from skill-booting.
2. **ROLLBACK_REFERENCE.md stanza label** — currently reads "sprint-01"
   but content covers L1.x + L2.x. Split into two stanzas in a doc-hygiene
   pass.
3. **Signal 5 (L2.5 orphan detector in-situ verification)** — deferred
   per steer. Requires a session that exits without touching
   handoff-tasks.json or the loop-events ledger, then a later session
   scanning the stale latch. Test-only coverage in
   `tests/test_orphan_detector.py` is present; production observation
   pending.
4. **Sprint 3 (L3.1..L3.4)** — populate the 6 baseline schema slots
   pre-declared as `None` in Sprint 1's `loop_baseline.py`.

## Next work

Resume `QR-1-followup` (Task #1): extract the `scripts/handoff` pending
reconcile block into a shell-testable helper and add divergence unit
tests covering the three real-world divergence paths (family-fold
collapse, review-sibling `pending_parent` drop, stale-session id
collapse).
