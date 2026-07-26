# V11 Improvement 06 — Self-Improving Subagent Loop: closing the keystone

**Author:** orchestrator (2026-07-01 session, continuing the 2026-07-01 rating-loop audit)
**Severity:** HIGH — the loop collects data at scale (1016 review-queue entries, 72 error records, 1146 dispatch-trace records) but never acts on it. Visibility shipped (06dd1d4); actuation never has.
**Scope:** `hooks/sync-tasks`, `hooks/track-agents`, `scripts/agent-scorecard`, `scripts/dispatch-trace-append`, `.claude/skills/improve-subagent/`, `.claude/skills/team-orchestrator/playbooks/per-task-review.md`

---

## Ground truth (Haiku swarm, read-only, 2026-07-01)

Six parallel surfaces investigated against real code + real `~/.agent-metrics/*.jsonl` data. No assumptions — every claim below is file:line or measured.

| Surface | Finding |
|---|---|
| Rating write/read path | Fully wired: task complete → `sync-tasks` enqueue → verdict → `agent-errors.jsonl` + `task_artifacts.self_review` → `agent-scorecard`/`agent-effectiveness`. Mechanically sound. |
| INV-3 calibration | **0 paired data ever** because `hooks/sync-tasks` (~line 1315) writes `agent-errors.jsonl` with the **reviewer sibling's** `task_id`, not the **parent work task's** `task_id` (available as `review.task_id`/`review_of` on the verdict object, never read). Self-review keys on parent ID; adversarial verdict keys on reviewer ID. Confirmed: 8/72 `agent-errors.jsonl` records show any self+adversarial overlap. |
| Improvement actuator | `improve-subagent` works (ran once manually 2026-05-23, produced real applied patches) but has **zero programmatic trigger**. The ">50% miss rate ⇒ schedule improve-subagent" line (team-orchestrator SKILL.md line 184, per-task-review.md line 416) is advisory prose in a Situation Playbook table — no hook or script reads `agent-scorecard`'s `.self_review_miss` and acts. |
| Attribution (`caller_kind`) | 99.48% unknown, confirmed on live `dispatch-trace.jsonl` (1140/1146). Root cause is NOT a logic bug: `v11_caller_kind()` correctly branches on `V11_SUBAGENT`/`V11_PARENT_SESSION_ID`, but nothing sets those env vars — flagged in the V11.20 changelog as "awaiting Claude Code Agent-tool launcher integration," never completed. Out of V11's direct control at the env-var layer. |
| Drainage cadence | 570/1016 (56%) review-queue entries still pending live. No hook calls `drain-review-queue` — 100% orchestrator discretion, atrophied 251→193→1/month. **Already designed**: `v11/improvements/03-review-queue-drainage.md` (drafted 2026-06-22, unshipped) specifies session-scoped claiming + a hard DETECT-phase backstop blocker + honest dashboard messaging. |

**The pattern across all four gaps: every fix that exists today is advisory text the orchestrator LLM has to remember, not code that enforces itself.** That's the collect-heavy/consume-light diagnosis from the 2026-07-01 audit, traced to its literal source in each case.

---

## Design: four fixes, sequenced by dependency

### Fix 1 — INV-3 join-key correction (unblocks everything downstream)

This is the actual keystone: nothing else in the loop can be evaluated as "did the loop work" until self-review and adversarial verdicts land on the same key.

**Change** (`hooks/sync-tasks`, the block around line 1315 that writes `agent-errors.jsonl`):
```
# before: task_id = <reviewer sibling's own task_id>
# after:  task_id = review.get("task_id") or review_of_parent_id or <reviewer's own task_id as last-resort fallback>
```
The verdict object already carries the parent ID (schema documents a `task_id` field on the review verdict) — this is a one-field redirect, not new plumbing.

**Backfill**: precedent exists — the 06dd1d4 commit already ran a 126-record backfill for a related normalization bug. Same pattern here: a one-shot script re-derives parent task_id for historical `agent-errors.jsonl` rows via `review_of` lookup in task-state, so INV-3 gets real historical signal on day one instead of waiting 30 days for fresh data.

**Verify**: after the fix, `agent-scorecard --layer lite` should show `self_review_miss` computed from >0 paired records for any agent with recent dual-layer review activity. That's the falsifiable acceptance test — INV-3 has never had one before because it never had data.

### Fix 2 — Improve-subagent actuator, mechanized as a TASK not silent actuation

Per the v11.27 doctrine ("mechanize acknowledgment not actuation"), this must NOT become an auto-run hook that silently patches an agent definition. It becomes a **task-creation trigger**:

- New check in `agent-scorecard` (or a thin wrapper called from DETECT, alongside the existing "Reviews pending" signal): if `self_review_miss > 50%` over a 30-day rolling window for any agent, AND no open task already references `improve-subagent-candidate:{agent}` (dedup/cooldown), emit a `TaskCreate` with `metadata.agent="improve-subagent"`, `metadata.trigger="calibration-miss"`, `metadata.candidate_agent={agent}`, `risk="medium"`.
- This surfaces exactly like the review-queue signal already does in the DETECT dashboard: `Calibration miss: {agent} at 62% (30d) — improve-subagent task created (T{id})`.
- The orchestrator (or user) still approves/dispatches the task normally through Phase 4 — no silent file edits. `improve-subagent` itself is unchanged; only its trigger moves from "orchestrator remembers to read a scorecard" to "a task exists in TaskList."
- Depends on Fix 1: without paired data, `self_review_miss` is meaningless, so this can't be validated until the join is fixed.

### Fix 3 — Attribution: fix what V11 controls, stop waiting on the launcher

The env-var injection gap is real but not the only lever. Two deterministic fixes that don't require the Agent-tool launcher to change:

- `hooks/track-agents` fires as a PostToolUse hook **on the Task tool itself** — at that moment it deterministically KNOWS a subagent was just spawned, without needing to infer it from env vars. It should set `caller_kind=subagent` directly from the hook's own trigger context, not delegate to `v11_caller_kind()`'s env-var guess.
- For the orchestrator-self-execution case (CLAUDE.md's "log orchestrator-override" rule, currently advisory-only and unenforced — confirmed no code path calls it), add a `sync-tasks` check: if a completed task carries `metadata.agent=X` but no matching `dispatch-trace.jsonl` entry exists for that task_id in the session, auto-emit a default `caller_kind=orchestrator, override_reason="unattributed-self-exec"` entry at completion time. This closes the gap even when the LLM forgets to call `dispatch-trace-append` manually — mechanizing the acknowledgment CLAUDE.md §23 already asks for.
- Leaves the true "unknown" bucket for cases where neither signal is available — honest, not padded.

### Fix 4 — Drainage: ship improvement 03 as designed

No new design needed — `v11/improvements/03-review-queue-drainage.md` already specifies this correctly: per-review `claimed_by` + `session_uuid` ownership, a DETECT-phase hard backstop (default >20 pending AND oldest >24h ⇒ blocker, `V11_REVIEW_BACKSTOP_COUNT`/`V11_REVIEW_BACKSTOP_AGE` overrides, `V11_REVIEW_BACKSTOP=off` rollback), and honest dashboard messaging (drainable-here vs owned-by-concurrent-session). Given live data shows 570 pending against exactly the failure mode that proposal predicted, this should move from backlog to sprint.

---

## Sequencing

1. **Fix 1 first** (INV-3 join key + backfill) — small, mechanical, unblocks measurement for fix 2.
2. **Fix 4 in parallel** (drainage) — independent, already designed, reduces the 570-item backlog that's masking signal in the other three.
3. **Fix 3** (attribution) — independent, improves data quality for all scorecards.
4. **Fix 2 last** (actuator-as-task) — depends on Fix 1's data being real before the >50% threshold means anything.

## Rollback levers (each independent, matching existing V11 convention)

- Fix 1: none needed — pure bug fix, no behavior toggle. Backfill script is a one-shot, not a standing behavior.
- Fix 2: `V11_IMPROVE_SUBAGENT_TRIGGER=off`
- Fix 3: `V11_CALLER_KIND_INFERENCE=off` (falls back to current env-var-only behavior)
- Fix 4: `V11_REVIEW_BACKSTOP=off` (already specified in improvement 03)

## Why this is the keystone, not another data-quality pass

06dd1d4 already fixed severity normalization and surfaced queue depth — pure visibility. Every fix above turns a currently-advisory sentence into something that either can't silently fail (Fix 1, a data bug) or creates a durable artifact (a task, a dashboard line, a blocker) instead of relying on an LLM's memory across sessions. That's the actual definition of closing collect-heavy/consume-light: the four places where the loop was *designed* to close but never got wired now have code, not prose, in the loop.

## Validation — shipped and dogfooded live (2026-07-01)

All 4 fixes implemented (4 parallel `spec-implementer-v11` background agents, isolated worktrees), merged into `v11.28-handoff-steer` (commit range starting `34f8312`..`8395101`), regression-clean (20/20 throughout).

**Production backfill run**: `scripts/backfill-agent-errors-task-id --apply` against real `~/.agent-metrics/agent-errors.jsonl` — 7 rows corrected, 25 left unresolved (no parent found, safely untouched), backup written. Confirmed via `agent-scorecard`: `paired_count_total` went from 0 (system-wide, all of history) to a real nonzero value once dual-layer review data existed for the same task — the literal proof the join-key fix works.

**Deeper finding surfaced by validation, not fixed by design alone**: even after the join-key fix, real production data initially still showed 0 paired records for the specific rows the backfill corrected — because `task_artifacts[task_id].self_review` simply didn't exist for those historical tasks. Cross-checked *every* project on the box: zero cases, system-wide, where a task had both a self-review and an adversarial-lite verdict recorded simultaneously. The join-key bug was real and is fixed, but self-review compliance (Layer A actually being emitted) is a second, deeper gap — worth its own follow-up investigation (why do executing agents skip the self-review nudge?).

**Closed the loop live**: rather than stop at that negative result, drained this very project's own review queue (dogfooding Fix 2's `--force` drain path) and spawned 3 real `adversarial-lite-reviewer` agents against the 4 fixes' own code. Result: `paired_count_total: 1` — the first real, live, non-synthetic paired calibration data point in the system's history (self-review LOW, adversarial PASS, correctly computing `miss_rate: 0` since both sides agreed).

**The review agents also did their job**: found 1 HIGH + 3 MEDIUM real bugs in the just-shipped code, all fixed same-session (commit `8395101`):
- HIGH: `hooks/track-agents`'s caller_kind no-signal case was inverted — mapped to `"subagent"` when reasoning from CLAUDE.md's "subagents cannot spawn sub-subagents" rule shows it should be `"orchestrator"` (this hook fires when the Task tool is invoked; per that rule, the caller is overwhelmingly the top-level orchestrator).
- MEDIUM ×2: missing `PROJECT_SOURCE` guard and a check-then-write race in the sync-tasks auto-emit block.
- MEDIUM: `v11_review_queue_gc` released stale claims by age alone, without checking the claiming session was actually dead — reopening the exact double-dispatch race the drainage feature exists to prevent.

**Separate operational finding, not part of this fix set**: the live `TaskList` registry emptied twice mid-session with no corresponding session-end file activity (confirmed via timestamps) — task-state persisted correctly to the on-disk `.task-state.json` mirror throughout, but the harness's live view had to be reconstructed from that mirror twice. This looks like Claude Code harness-level flakiness under sustained parallel background-agent load, not a V11 hooks bug (no hook fired to explain it). Flagging for a future investigation; out of scope here since it's not reproducible from V11's own code.
