# 10 — Pre-Scope Actuation: Close the v11.29 Pre-Scope Loop + Token Measurement

> Status: ✅ EXECUTED 2026-07-14/15 (session v11-prescope-alignment, 20 tasks, branch v11.28-handoff-steer). All 5 waves shipped + D5/D6/D7 follow-ups (async-token capture via TaskUpdate artifacts — discovered mid-flight when D1 proved hook-side capture is foreground-only). Success criteria: #1 dogfood-verified live (advisories in orchestrator tool result), #2 status line live + ledger rows wired, #3 pending next-session measurement, #4 two-source capture live, baseline recorded (0.22% pre-rollout).

## Intent

The v11.29 pre-scope build exists but never acts. Make pre-scoping fire honestly (no self-labeling dependency), make its signal visible to the orchestrator at the TaskCreate chokepoint, consume it at dispatch time, and fix token capture so the "fewer tokens per agent" claim becomes measurable instead of hypothesized.

## Grounding (what recon proved, 2026-07-14)

- Advisory (`sync-tasks:475-486`) fires only when `scope=large` or `complexity∈{complex,novel}` — but only **13% of tasks (151/1161)** carry scope metadata at all. Unlabeled oversized tasks are invisible.
- Advisory output is **stderr-only**: no ledger row, no task mutation, no consumer. Live dogfood: this session's anchor task shipped `scope:"session"` (schema-invalid) and no signal surfaced to the orchestrator.
- Token ledger (v11.29) is inert: **5 of 2,299** dispatch-trace entries carry tokens (0.2%). Known half-wire at `track-agents:225`.
- 4 playbook↔tooling mismatches (agent-recommend vs spec.md `## Agents` divergence; orchestrate.md vs context-tiered-mode.md carve-out contradiction; ENFORCEMENT.md default wording; TaskList carve-out unlisted).

## Constraints

- Advisory, never block — task-shape over hook-block (house rule). Every lever gets an independent rollback env var, default **on**.
- One deliverable per task; tests are sibling tasks. All editing spawns worktree-isolated Sonnet background agents.
- No new daemons, no new state stores — reuse durable ledger, dispatch-trace, scorecard.

## Waves

### W-A — Honest detection (kill the self-labeling dependency)
- A1: `sync-tasks` warns on TaskCreate when `metadata.scope` is missing on work tasks (skip review siblings / blocker tasks), mirroring the `metadata.project` warning. Also surface schema-invalid scope values (currently silently validated). Rollback: `V11_SCOPE_WARN=off`.
- A2: multi-deliverable smell heuristic on task description at TaskCreate — conjunction pattern ("X and Y", "+ tests", numbered runbook steps), length threshold. Advisory-grade only. Rollback: `V11_PRESCOPE_SMELL=off`.
- A3: test siblings for A1 + A2 (extend `tests/test_sync_tasks_prescope.py`).

### W-B — Visible signal (actuate at the chokepoint)
- B1: prescope advisory emitted as PostToolUse `hookSpecificOutput.additionalContext` so it lands in the orchestrator's TaskCreate tool result; stderr retained for logs. Rollback: `V11_PRESCOPE_CONTEXT=off`.
- B2: persist firings as status-neutral `ev:prescope` rows in the durable ledger (same pattern as `ev:review`). Rollback: `V11_PRESCOPE_LEDGER=off`.
- B3: test siblings for B1 + B2.

### W-C — Dispatch consumption
- C1: `scripts/prescope-check <project> [task_id]` — reads task-state, exit 0 = clean, exit 11 = oversized/unscoped tasks listed with split suggestions. Read-only.
- C2: wire C1 into the orchestrator Phase 4 dispatch filter (SKILL rule 21 names the discipline; this gives it a command) — playbooks/orchestrate.md + task-patterns.md edit.
- C3: `/v11 status` dashboard line: `Pre-scope: {scoped_pct}% scoped, {open} advisories open` (status script + DETECT playbook).
- C4: test sibling for C1.

### W-D — Token loop (make "fewer tokens" measurable)
- D1: diagnose + fix token capture wiring (`track-agents:225` half-wire) so dispatch-trace rows carry real token counts. Target ≥80% capture on new spawns.
- D2: `agent-scorecard` gains tokens-per-task (median output tokens per spawn, per agent, per layer).
- D3: baseline snapshot script + record pre-rollout baseline now; re-run post-rollout for before/after.
- D4: test sibling for D1.

### W-E — Playbook alignment
- E1: fix the 4 documented mismatches (single doc-sweep task, diffable).
- E2: STEP 4b task templates in task-patterns.md emit `scope`/`complexity`/`agent` in every example TaskCreate, so the default path produces labeled tasks.

## Agents

| Task family | Agent |
|---|---|
| Hook/script edits (A1, A2, B1, B2, C1, D1, D3) | spec-implementer-v11 (worktree) |
| Test siblings (A3, B3, C4, D4) | spec-tester-v11 |
| Playbook/docs edits (C2, C3, E1, E2) | spec-implementer-v11 |
| Scorecard (D2) | spec-implementer-v11 |
| Per-task adversarial review | adversarial-lite-reviewer (auto-paired) |

## Non-goals

- No blocking enforcement at TaskCreate — advisory + dispatch-filter only.
- No auto-splitting of tasks by tooling; splitting stays an orchestrator decision.
- No changes to lane lease, review queue, or handoff machinery.

## Rollback

`V11_SCOPE_WARN` · `V11_PRESCOPE_SMELL` · `V11_PRESCOPE_CONTEXT` · `V11_PRESCOPE_LEDGER` (all default on, independent). Existing `V11_PRESCOPE_ADVISORY=off` still silences the whole lane. W-D and W-E are plain commits, revert by git.

## Success criteria

1. A TaskCreate with an unscoped or smelly-multi-deliverable description produces a visible advisory in the orchestrator's tool result (dogfood-verify live).
2. `ev:prescope` rows appear in the ledger; `/v11 status` shows the pre-scope line.
3. Scope metadata adoption on new tasks ≥90% within one session of rollout (vs 13% baseline).
4. Token capture ≥80% on new spawns; scorecard shows tokens-per-task; before/after baseline recorded.
