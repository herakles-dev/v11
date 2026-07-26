# 09 — Cross-Session Verdict Fold-Back (W5-T16 spec)

> Status: SHIPPED v11.30 (2026-07-11) — implemented, adversarially reviewed, prod-fixed (severity case-normalization, phantom replay records, filename uniquifier). Follow-up: replay aggregate does not yet project last_review_* fields (write-only path).
> Parent: improvements/07 §W5-T16. Author: orchestrator, 2026-07-11.
> Line anchors are as of the pre-merge tree (efefe01^); the T16 merge shifted common.sh ranges. Grep the named functions (`v11_review_queue_mark_done`, `v11_ledger_identity_fallback`, `v11_replay_ledger`) for current positions.

## Problem

Drained review verdicts for prior-session task IDs evaporate to a severity string:

- `scripts/review-daemon:198` — the evaporation point: full `VERDICT_RAW` is reduced to `MAX_SEV` → `review-queue mark-done PROJECT TID $MAX_SEV`; per-error lines go to `agent-errors.jsonl`; the verdict object (verdict, confidence, summary) is persisted nowhere.
- `common.sh:3292` — the queue `done` event stores only `{review_severity, session_uuid, outcome?}`. No pointer to where the verdict went.
- The in-session path (`metadata.artifacts.review` → sync-tasks) cannot carry prior-session verdicts at all: sync-tasks only fires on TaskUpdate of a task in *this* session's TaskList. The CLI path needs its own ledger writer.
- No `review` event kind exists in any ledger (live kinds: created/completed/in_progress/reconcile/field_update/blocked/sprint_archived).

**Evidence (2026-07-10):** 21 drained verdicts survive only in a scratchpad; 71 ghost identities required manual `ev:reconcile` events precisely because verdicts/completions had no ledger path.

## Design

### B1 — durable verdict store
`v11_review_queue_mark_done` gains an optional verdict payload. Full verdict JSON is written to
`~/.agent-metrics/review-verdicts/{project}/{task_id}-{ts}.json` (append-only store, one file per verdict; mkdir -p, atomic tmp+mv).

### B2 — `ev:"review"` ledger event
After storing, append via `v11_ledger_append`:

```json
{"v":1, "ev":"review", "ts":..., "project":..., "subject_norm":..., "task_id":...,
 "create_seq":..., "session_uuid":"<drainer, via v11_session_uuid>",
 "review_severity":"NONE|LOW|MEDIUM|HIGH|CRITICAL", "reviewer_agent":"adversarial-lite-reviewer",
 "error_count":N, "verdict_sha":"sha256-of-file", "verdict_ref":"<store path>",
 "source":"review-daemon|cli-drain"}
```

- **Replay semantics (required, per ledger state machine common.sh:2264-2600):** `ev:review` is **counters_delta-free and status-neutral** — replay records it on the identity (e.g. `last_review` fields) but never touches counters or status. Mirrors how identity-scope reconcile skips counters (common.sh:2501).
- **Identity recovery** for a prior session's task: `v11_ledger_append` requires `subject_norm` + `create_seq` for `ev!="created"`. Reuse `v11_ledger_identity_fallback` (common.sh:2160) / the fold-reconcile create_seq scan (fold-reconcile:141-214). If unresolvable: append anyway with `create_seq:null, identity_unresolved:true` — a flagged event beats a dropped verdict (unattributed-never-dropped doctrine).
- Severity normalized at the existing chokepoint (common.sh:3250) before it reaches the event.

### B3 — CLI surface
```
review-queue mark-done PROJECT TASK_ID [SEV] [SESSION_UUID] [--verdict-file FILE]
```
`--verdict-file` triggers B1+B2; when given, SEV may be omitted (derived as max severity from the file, same jq as review-daemon:198). Without `--verdict-file`, behavior is byte-identical to today.

### B4 — queue done event gains the pointer
`common.sh:3292` done event adds `verdict_ref` + `verdict_sha` when present, so a queue line alone can locate its verdict forever.

### B5 — call sites
- `review-daemon:~198`: write VERDICT_RAW to a temp file, call `mark-done ... --verdict-file`.
- Orchestrator drain playbook (per-task-review.md): when draining a **prior-session** task ID, fold the verdict via `mark-done --verdict-file` instead of (impossible) TaskUpdate. Same-session verdicts keep riding `metadata.artifacts.review` (unchanged); a future increment may emit `ev:review` from sync-tasks too — out of scope here.

## Wipe tolerance
The CLI path never touches TaskList — inherently wipe-tolerant. Session identity is trustworthy CLI-side since W1-T5 (`v11_session_uuid` CLAUDE_CODE_SESSION_ID fallback, common.sh:109, commit 6aa65a7). A verdict for a task wiped mid-session folds back exactly like any prior-session task.

## Non-goals
- No migration of the 21 scratchpad verdicts (manual one-shot if wanted; the reconcile events already closed the ledger gap).
- No change to in-session sync-tasks verdict handling.
- No queue schema version bump — new fields are additive, replay ignores unknown fields.

## Verify
1. `mark-done P T --verdict-file f.json` → verdict file in store, `ev:review` line in ledger (valid envelope, create_seq resolved), done event carries verdict_ref; `jq` round-trip sha matches.
2. Without `--verdict-file` → byte-identical done event to today (regression).
3. Prior-session/wiped task_id → event lands with identity recovered (or flagged `identity_unresolved`), never dropped.
4. Ledger replay over a file containing `ev:review` → counters and statuses unchanged vs. replay without it.
5. review-daemon drain of one entry → full verdict recoverable from verdict_ref.

## Rollback
`V11_REVIEW_LEDGER=off` (new, default on) — skips B1/B2/B4 additions; mark-done reverts to severity-only. Independent of `V11_REVIEW_ENFORCEMENT`.
