# 08 — Layer A Self-Review Actuation (W5-T15 spec)

> Status: SHIPPED v11.30 (2026-07-11) — implemented, adversarially reviewed, prod-fixed (lever de-nesting).
> Parent: improvements/07 §W5-T15. Author: orchestrator, 2026-07-11.
> Line anchors are as of the pre-merge tree (efefe01^); the T15 merge shifted sync-tasks ranges (~+60 lines past 1315). Grep the named identifiers (`malformed_self_review`, `V11_SELF_REVIEW_NUDGE`) for current positions.

## Problem

Layer A (executor self-review) is collect-never-emit. The V11.22 instrumentation half exists:

- `hooks/sync-tasks:1264-1301` — missing-self_review **nudge**: one stderr line on reviewable completion, gated `V11_SELF_REVIEW_NUDGE=on`. Writes nothing.
- `hooks/sync-tasks:1315-1373` — **malformed**-shape guard (`V11_SELF_REVIEW_REQUIRED=on`): a present-but-bad `self_review` appends a synthetic `lite_self` row (`error_id=malformed_self_review`) to `agent-errors.jsonl`.

The asymmetry is the bug: an agent emitting garbage is penalized visibly (synthetic row → scorecard); an agent emitting **nothing** produces only a stderr line nobody stores. Compliance is near-zero and invisible; INV-3 calibration (`agent-scorecard:296`) starves for paired data.

## Evidence

- 2026-07-01 keystone: paired_count 0→1 only after join-key fixes — Layer A emission itself was flagged then as "the deeper unaddressed issue".
- 2026-07-10 live wipe repro (improvements/07 §W5): task #43 completion hit "Task not found"; ledger absorbed it. Any actuator must survive a wiped TaskList.
- Nudge attribution degrades to `unknown` when `active_agent_id` and `recommended_agents[tid]` both miss (`sync-tasks:1286,1300`).

## Actuator decision

Considered: (a) completion-hint nudge upgrade, (b) drain-time backfill, (c) scorecard visibility.

**Chosen: (a) + symmetric absence row + lever-semantics repair. Rejected: (b).**

- (b) drain-time backfill is rejected: `drain-review-queue`/`review-queue` have zero self_review handling today (verified — no hook point), and a backfilled Layer A written by the *reviewer* path is fake Layer A — it destroys exactly the self-vs-adversarial independence INV-3 measures. Never synthesize the self side from the adversarial side.
- (c) already half-exists (`self_review_miss_rate` in agent-scorecard/agent-effectiveness) but only counts *paired* rows; absence is invisible there by construction. Fixed by A2 below feeding absence into the same ledger the scorecards already read.

## Changes

### A1 — completion-hint carries the postamble (pre-completion, cheapest site)
`hooks/completion-hint:134` already tells the model to run `TaskUpdate(completed)` when an edit matches an in_progress task. Append to the hint text: *"include `metadata.artifacts.self_review` ({severity, summary, errors[], reviewed_at, agent_id})"*. One-line change; fires **before** the completion, which is the only moment the executor still has context to self-review honestly.

### A2 — symmetric absence row (the actuator)
In `sync-tasks`, inside the existing reviewable-completion filter (1291-1298): when `self_review` is absent, append a synthetic `agent-errors.jsonl` row mirroring the malformed block (1337-1373):

- `error_id` sentinel: `missing_self_review`; `found_by_layer="lite_self"`; `executor_kind="self"`; severity **LOW** (absence is a discipline signal, not a defect claim — keep it below the malformed row's MEDIUM).
- Attribution ladder: `self_review.agent_id` (n/a here) → `active_agent_id` → `recommended_agents[tid]` → `unknown` + `attribution_degraded=true` field so unattributable rows are filterable, not silently misassigned.
- Wipe tolerance: the block runs in the PostToolUse path off `tool_input` (same as artifact persistence at 1154), so it fires even when the TaskList-side task is gone; key on the task_id from tool_input, flock-append like 1366-1373. Never fail the hook.
- Keep the stderr nudge unchanged (it's the human-visible half).

### A3 — lever semantics repair
Code and docs disagree: `ROLLBACK_REFERENCE.md:88` says `V11_SELF_REVIEW_REQUIRED` controls absence tracking; in code it only gates shape-validation, and absence is under `V11_SELF_REVIEW_NUDGE`. Resolution:

| Lever | Meaning after T15 |
|---|---|
| `V11_SELF_REVIEW_NUDGE` | stderr nudge only (unchanged) |
| `V11_SELF_REVIEW_REQUIRED` | shape-validation of present payloads (unchanged) |
| `V11_SELF_REVIEW_ACTUATE` | **new, default on** — gates A2 absence rows AND A1 hint suffix |

Update ROLLBACK_REFERENCE.md wording for REQUIRED; add ACTUATE row.

## Non-goals
- No blocking: completion is never rejected for missing self_review (task-shape-over-hook-block doctrine).
- No backfill of historical completions.
- Scorecard formulas unchanged — absence rows arrive through the existing `lite_self` layer and become visible in `--layer lite` counts automatically; calibration pairing continues to exclude non-severity-bearing rows.

## Verify
1. Complete a reviewable task without self_review → `agent-errors.jsonl` gains one `missing_self_review` row with correct project/task_id/agent; stderr nudge still prints.
2. Same with `V11_SELF_REVIEW_ACTUATE=off` → no row, nudge only.
3. Malformed path unchanged (regression: existing tests around sync-tasks:1315).
4. Wipe case: TaskUpdate(completed) for a task_id absent from TaskList → row still appended (hook reads tool_input).
5. `agent-scorecard AGENT --layer lite` surfaces the new rows.

## Rollback
`V11_SELF_REVIEW_ACTUATE=off` (A1+A2). A3 is doc-only.
