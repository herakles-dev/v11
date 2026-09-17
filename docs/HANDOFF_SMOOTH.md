# V11.17 Smooth-Handoff Contract

> Goal: close a session, open a new one, the tasks are there. No `/handoff` ritual required. No `.session-summary.md` to remember.

## TL;DR

| You do this | V11.17 does this for you |
|---|---|
| Close terminal without running `/handoff` | `session-end` hook auto-emits `handoff.md` + `handoff-tasks.json` |
| Run `/handoff` without writing `.session-summary.md` | `scripts/handoff` auto-generates a structured stub from existing signals; gate passes |
| Open a new session and start working | `detect-project` surfaces "[V11] N open task(s) in handoff" on first Read; `/v11` auto-rehydrates TaskList |

Three improvements over the V11.16 ledger baseline. Each lever has an env-var rollback.

---

## Sender side

### 1. Auto-stub `.session-summary.md` (Fix 1)

When `scripts/handoff` runs and `.session-summary.md` is missing or empty, it generates a structured stub from existing signals:

| Section | Source |
|---|---|
| `## What We Did` | `task-state.json.recent_completed[0:3]` |
| `## Key Decisions` | `.plan-context.json.decisions[-3:]` |
| `## Current Understanding` | `task-state.json.active_task` + `.plan-context.json.reasoning.bottleneck` |
| `## Blockers / Open Questions` | `task-state.json.blocked` count |

The stub header explicitly labels itself "Generated stub — edit before `--spawn`" so reviewers know it's machine-derived. Once written, the file *exists*, so the `--spawn` quality gate counts it as `SOURCE="written"`.

**Quality floor**: refuses to write a stub <30 bytes — falls back to the inline synthesis path (still labeled, still excluded from gate).

**Disable**: `--no-stub` flag (per-invocation) or `V11_STUB_SUMMARY=off` env var (global).

### 2. Session-end safety net (Fix 2)

The `session-end` hook (fires on Stop event) calls `scripts/handoff $PROJECT --file …` in plain mode after `plan-sync`, before `last-session.json` dump.

Skip conditions (any one bails):
- `V11_AUTO_HANDOFF=off`
- `$PROJECT` empty (no active project)
- `handoff.md` exists and mtime < 60s (user just ran `/handoff` manually — don't stomp)

Marker `sessions/$PROJECT/.handoff-autoemit-at` (ISO-8601 timestamp) is written on every successful auto-emit. Use it to distinguish "user wrote this" from "session-end wrote this":

```bash
[ -f sessions/$PROJECT/.handoff-autoemit-at ] && echo "auto-emitted" || echo "user-written"
```

**Disable**: `V11_AUTO_HANDOFF=off`.

---

## Receiver side

### 3. First-Read nudge (Fix 4)

When `detect-project` (PreToolUse on Read) sees a non-empty `handoff-tasks.json` AND this `V11_SESSION_ID` has not been nudged before, it emits ONE line to stderr:

```
[V11] N open task(s) in handoff for {project}. Run /v11 to auto-rehydrate.
```

Then `touch`es `~/.agent-metrics/sessions/$V11_SESSION_ID/.handoff-surfaced`. Subsequent Reads in the same session stay silent.

**Disable**: `V11_HANDOFF_NUDGE=off`.

### 4. Post-compact reminder (Fix 5)

After compaction, `post-compact` re-injects context (project, tasks, autonomy, etc.). If `handoff-tasks.json` still has open tasks at compaction time, it adds one line:

```
Handoff waiting: N open task(s). Run /v11 to rehydrate.
```

No full `<v11-resume>` block (would auto-recreate already-loaded tasks). Just a nudge in case rehydration hasn't happened yet.

**Disable**: `V11_COMPACT_HANDOFF_LINE=off`.

### 5. Orchestrator auto-rehydrate (Fix 3)

In `/v11` Phase 1 DETECT, step **1a.5** runs before the dashboard:

1. `TaskList()` — is it empty?
2. Does `sessions/{project}/handoff-tasks.json` have `open_tasks.length > 0`?
3. If both yes → invoke `scripts/v11-resume-tasks {project}`, read the `<v11-resume>` block, issue `TaskCreate` per entry, then `TaskUpdate(in_progress)` for any whose `status_at_handoff` was `in_progress`.
4. Add to dashboard: `✓ Rehydrated N task(s) from handoff`.

Gating: never run when TaskList has any task. The user's current work always wins.

**Disable**: `V11_AUTO_REHYDRATE=off` (orchestrator surfaces count but does not act; becomes code-enforced in `scripts/v11-resume-tasks` as of v11.32).

---

## Escape hatches summary

| Behavior | Env var | Flag |
|---|---|---|
| Stub `.session-summary.md` | `V11_STUB_SUMMARY=off` | `--no-stub` |
| Session-end auto-emit | `V11_AUTO_HANDOFF=off` | n/a |
| First-Read nudge | `V11_HANDOFF_NUDGE=off` | n/a |
| Post-compact reminder | `V11_COMPACT_HANDOFF_LINE=off` | n/a |
| Orchestrator auto-rehydrate | `V11_AUTO_REHYDRATE=off` (becomes code-enforced in `scripts/v11-resume-tasks` as of v11.32) | n/a |
| `--spawn` quality gate | n/a | `--spawn-anyway` |

Worst case (full opt-out, back to V11.16 behavior):
```bash
export V11_AUTO_HANDOFF=off V11_STUB_SUMMARY=off V11_HANDOFF_NUDGE=off V11_COMPACT_HANDOFF_LINE=off V11_AUTO_REHYDRATE=off
```

---

## When to still run `/handoff` manually

Auto-emit is a safety net, not a substitute. **Run `/handoff --spawn` explicitly** at:

- Sprint or milestone boundaries (richer summary for review)
- Project pivots (you control the narrative)
- Context > 70% (don't wait for session-end; spawn the new window now)
- After significant decisions you want highlighted in the next session's first message

A hand-written `.session-summary.md` always trumps the stub for review quality. The stub closes the floor; the manual summary raises the ceiling.

---

## What V11.17 does NOT change

- The V11.16 durable ledger (`~/.agent-metrics/ledger/$PROJECT.jsonl`) — same source of truth.
- The `<v11-resume>` block format emitted by `scripts/v11-resume-tasks` — unchanged.
- The `--spawn` quality gate (≥2 of 5 substantive sections required). The stub *fills* the gate honestly; we did not weaken it.
- Task IDs rotating across sessions (Claude Code framework limit — `#19` becomes `#1` on rehydration).
- Hook ability to invoke tools directly — still impossible. The orchestrator skill is the layer that does the rehydration work; hooks just surface that it's waiting.

---

## Project scope discipline (V11.23 Layer 3)

> Background: handoff bug report at `reports/bug-handoff-cross-project-scope-leak-20260601.md` documented a HIGH-severity leak: `handoff-tasks.json` for `herakles-terminal` contained 19 open tasks, only 4 of which were legitimately for that project. The other 15 belonged to portfolio / eigen-opus / music-corpus sessions whose contributing Claude orchestrator had `active-project=herakles-terminal`.

V11.23 closes the leak with three coordinated layers:

| Layer | Where | What it does |
|---|---|---|
| **Layer 1** — handoff aggregate filter | `scripts/handoff` (~line 1141, ~line 1456) | At handoff emit time, filter `open_tasks_by_session` by `metadata.project`. V11.23 softened to accept (`metadata.project == $P` OR null) so legacy unstamped tasks still flow. |
| **Layer 2** — `_proj` stamp at TaskCreate/Update | `hooks/sync-tasks` (TaskCreate branch + TaskUpdate(in_progress) branch) | Stamp each task's per-session record with the hook-resolved project (only when source is authoritative, never on ambient-fallback). Plus the W1 5/29 live-snapshot writer. |
| **Layer 3** — per-task aggregate routing | `hooks/lib/common.sh::v11_rebuild_project_aggregate` | Replace the V11.15.5 per-session Bug-H quarantine with per-task filtering. Each task `t` from session `s` belongs to aggregate $P iff (`t.metadata.project == $P`) OR (`t.metadata.project == null` AND `s.project == $P`). A single session correctly contributes to multiple aggregates. |

**Counter handling**: open counters (pending/in_progress/blocked) recomputed from filtered open_tasks. `completed` is summed only from sessions where `session.project == $project` — under-counts slightly for cross-project sessions (acceptable; user-visible bug is OPEN-task accuracy). Fallback: when a session has zero open_tasks at all (TaskList-only counter reconciliation), trust the session's scalar counters directly.

**Going forward**: new tasks routed correctly. The herakles-terminal aggregate stops growing with foreign tasks. Cross-project sessions correctly contribute their tasks to multiple project aggregates.

**Legacy contamination**: pre-V11.23 aggregates may carry tasks from sessions that were since deleted. Layer 3 rebuild can't recover orphan-source tasks (no live data to walk). Options:
- **Manual**: delete the aggregate file (`$TASK_STATE_DIR/$PROJECT.json`) and let sync-tasks rebuild it on next TaskUpdate. Loses orphan-session counters but produces a clean aggregate from current live sessions.
- **Reconciler**: `scripts/reconcile-aggregates --apply` triggers `v11_rebuild_project_aggregate` for affected projects. Same outcome as the manual path.
- **Tolerate**: legacy contamination shrinks over time as old sessions cycle out. Layer 1 + Gate 14 surface the problem so users can spot it.

**Gate 14 (handoff scope integrity)**: new compliance gate in `scripts/v11-compliance-check`. Reads `sessions/$PROJECT/handoff-tasks.json` if present; verifies every entry's `metadata.project` is $PROJECT (or null/legacy-OK). WARN on foreign mismatch with names + remediation hint. Surfaces in `/v11 compliance --scan`.

**`scripts/reconcile-aggregates`**: new one-shot maintenance script. `--dry-run` (default) walks every `$TASK_STATE_DIR/*.json` and classifies tasks as clean / unstamped / mismatch. `--apply` triggers per-project rebuild. JSON report written to `$METRICS_DIR/reconcile-report.<ts>.json`. Re-runnable, idempotent. Read-only by default.

**Rollback** (each independent): `V11_TASK_ROUTE_BY_METADATA=off` reverts Layer 3 to per-session Bug-H quarantine; `V11_HANDOFF_LIVE_RECONCILE=off` disables Layer 2 stamping; `V11_HANDOFF_CATEGORY=off` disables HANDOFF_CATEGORY banner; `V11_GATE_SUBSTANCE=off` disables substance check; `V11_GUARD_STALE_TASK=off` disables zombie-task hook (from swarm-studio audit §H9).

**What CAN'T be auto-detected**: tasks whose `metadata.project` LIES (explicit stamp but for the wrong project). The smoking-gun cc0bbe64 case had 16 tasks all stamped `project=herakles-terminal` while actually targeting portfolio/eigen-opus/music. Both Layer 1 and Layer 3 trust the explicit metadata. The bug report acknowledges this requires manual reconciliation via file-reference heuristics (subject/description mentions terminal source files vs portfolio source files). Going forward, the orchestrator should set `metadata.project` correctly at TaskCreate time — this is the contract V11 already requires.

---

## Verification

```bash
# Unit + integration scenarios
python3 -m pytest tests/integration/test_handoff_smooth.py -v

# Fast regression core (<30s)
./scripts/run-tests --regression

# Hook latency
./scripts/hook-metrics
```

End-to-end dogfood: close a session without `/handoff`, open a new one, run `/v11`. Tasks should appear without any extra command.
