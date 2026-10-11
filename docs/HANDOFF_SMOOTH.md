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

The `session-end` hook runs `scripts/handoff $PROJECT` in plain mode after `last-session.json` is written. It runs on `SessionEnd`, and on `Stop` only when the project's open set changed since the last emit (S0-T6). It passes neither `--file` (V11.28.1 F1) nor `--force`, so the #41 mtime guard keeps a hand-edited `handoff.md`.

Skip conditions (any one bails):
- `V11_AUTO_HANDOFF=off`
- `$PROJECT` empty (no active project)
- `handoff.md` exists and mtime < 60s (user just ran `/handoff` manually — don't stomp). The first `SessionEnd` of a sitting ignores this window when `handoff.md` is not newer than `.handoff-autoemit-at`.
- On `Stop` only: `.handoff-steer.md` is pending (a `/handoff` is between its Step 3.5 and Step 6)

A steer that `/handoff` already baked is kept in `.handoff-steer.consumed.md`, and this emit re-injects it. It stays in every regenerated `handoff.md` until a different interactive session Reads `handoff.md` (`detect-project` retires it) or regenerates it (`scripts/handoff` retires it), or it is older than `V11_STEER_PERSIST_MAX_AGE_SECS` (72 h) (S2-R3, review #20, `V11_STEER_PERSIST`).

A non-zero exit from `scripts/handoff` is logged as `emit=failed rc=N` in `~/.agent-metrics/session-end.log`, and nothing is stamped. That includes the S1-T1 empty-emission refusal (exit 2, see [S1 behaviour](#s1-behaviour-v1146)). Because the digest is not stamped, the next `Stop` tries again.

Marker `sessions/$PROJECT/.handoff-autoemit-at` (ISO-8601 timestamp) is written on every successful auto-emit and is never removed. Its presence alone does not tell you who wrote `handoff.md`. Compare mtimes, as the hook does:

```bash
[ sessions/$PROJECT/handoff.md -nt sessions/$PROJECT/.handoff-autoemit-at ] && echo "user-written" || echo "auto-emitted"
```

**Disable**: `V11_AUTO_HANDOFF=off`.

---

## Receiver side

### 3. First-Read nudge (Fix 4)

When `detect-project` (PreToolUse on Read) sees a non-empty `handoff-tasks.json` AND this `V11_SESSION_ID` has not been nudged before, it emits ONE line to stderr:

```
[V11] N open task(s) in handoff for {project}. Run /v11 to auto-rehydrate — if TaskList already lists them, ignore this.
```

Then `touch`es `~/.agent-metrics/sessions/$V11_SESSION_ID/.handoff-surfaced`. Subsequent Reads in the same session stay silent.

The session that wrote the file is not nudged. When `handoff-tasks.json` `live_session_uuid` equals `V11_SESSION_ID`, the tasks are already in that session's TaskList (S1-T3, see [S1 behaviour](#s1-behaviour-v1146)). Since S2-T0b-4 this holds only in the same claude process (`live_sitting`) and the same TaskList epoch (`live_tl_epoch`): a resumed session can hold a new TaskList, so it is nudged once. Rollback to the session-only match: `V11_HANDOFF_SELF_NUDGE_SUPPRESS=session`.

**Disable**: `V11_HANDOFF_NUDGE=off`.

### 4. Post-compact reminder (Fix 5)

After compaction, `post-compact` re-injects context (project, tasks, autonomy, etc.). If `handoff-tasks.json` still has open tasks at compaction time, it adds one line:

```
Handoff waiting: N open task(s). Run /v11 to rehydrate — if TaskList already lists them, ignore this.
```

No full `<v11-resume>` block (would auto-recreate already-loaded tasks). Just a nudge in case rehydration hasn't happened yet. Since S1-T3 the line is left out for the session that wrote the file (since S2-T0b-4: in the same sitting and TaskList epoch).

**Disable**: `V11_COMPACT_HANDOFF_LINE=off`.

### 5. Orchestrator auto-rehydrate (Fix 3)

In `/v11` Phase 1 DETECT, step **1a.5** runs before the dashboard:

1. `TaskList()` — is it empty?
2. Does `sessions/{project}/handoff-tasks.json` have `open_tasks.length > 0`?
3. If both yes → invoke `$V11_HOME/scripts/v11-resume-tasks {project}` (absolute: DETECT runs from the project directory, where `./scripts/` does not exist), read the `<v11-resume>` block, issue `TaskCreate` per entry, then `TaskUpdate(in_progress)` for any whose `status_at_handoff` was `in_progress`.
4. Add to dashboard: `✓ Rehydrated N task(s) from handoff`.

Gating: never run when TaskList has any task. The user's current work always wins.

**Disable**: `V11_AUTO_REHYDRATE=off` (orchestrator surfaces count but does not act; becomes code-enforced in `scripts/v11-resume-tasks` as of v11.32).

---

## S1 behaviour (v11.46)

> v11-leverage-program S1 "Stop the Bleeding" (#75, #57, #81). Each lever is in `docs/ROLLBACK_REFERENCE.md` § v11.46.

### Where `open_tasks` comes from (S1-T1, #75a)

Before S1, `handoff-tasks.json` took `open_tasks` from the per-session scratch or the project aggregate, and a stale `V11_SESSION_ID` could point it at an older session. Now `scripts/handoff`:

1. Replays the project ledger `~/.agent-metrics/ledger/{project}.jsonl` with `v11_replay_ledger`.
2. Picks the **live session**. From `hooks/session-end` it is the hook's own session, whatever its ledger activity. From a manual run it is the env session (`V11_SESSION_ID`, then `CLAUDE_CODE_SESSION_ID`) when its last ledger event is within `V11_HANDOFF_LIVE_WINDOW_SECS` (default 600) of the newest or a running claude process owns it. Otherwise it is the Claude session (UUID id) with the newest ledger event, and stderr says why. Tool pseudo-sessions such as `legacy-cli` never win.
3. Emits the live session's open tasks from the replay. It adds tasks from `ledger/{project}.live-snapshot.json` that the ledger never saw, and reads that snapshot only when it belongs to the live session. When a newer snapshot disagrees with the ledger, the ledger wins and stderr lists the disagreement.

A project with no ledger activity keeps the per-session / aggregate path. If the replay fails or times out, stderr prints a `WARN`, the handoff uses that path too and says so: `open_tasks_source` is `legacy-fallback:<reason>` and the `handoff.md` footer names it. The replay, the live-set pass and the drop audit share one budget, `V11_HANDOFF_SOURCE_BUDGET_SECS` (default 12 s), inside `hooks/session-end`'s 20 s kill.

Every entry carries `identity {subject_norm, create_seq}`. `create_seq` is `null` when no ledger create event backs the entry, as with snapshot-only entries and the per-session / aggregate path. The file gains three top-level fields:

| Field | Meaning |
|---|---|
| `live_session_uuid` | Whose open tasks these are (`source_session_uuid` is still the counter source) |
| `open_tasks_source` | `ledger+live-snapshot`, `legacy-fallback:<reason>` after a failed replay, or the fallback path's `source_kind` |
| `source_check` | Mode, why this live session, ledger / snapshot entry counts, what the emission dropped from the prior file (`scope`, `dropped_explained`, `dropped_unexplained[]`, `dropped_foreign[]`, `dropped_by_policy`), snapshot disagreements |
| `live_sitting` | S2-T0b-4: `CLAUDE_PID:starttime` of the writer, only when the writer is the live session. The self-nudge check needs it |
| `live_tl_epoch` | S2-T0b-4: the live session's TaskList epoch (its epoch record; `0` = seeded at rollout) |
| `task_store`, `task_store_basis`, `task_store_verified` | S2-T0b-4: the `~/.claude/tasks/<dir>` holding the live TaskList — a team config (verified) or a content match (unverified); absent when none is found. M1 counts this store |

S2-T0b-4 also stamps each entry's `tl_epoch` (its latest create's). It also adds `metadata.review_task_id`: the identity's latest `pair_` review shadow, so the rehydrated TaskCreate mints no second shadow. That shadow stays in the old session's scratch, so at completion sync-tasks keeps the task's V11.19 queue row (S2-R1). Rollback `V11_HANDOFF_REVIEW_TASK_ID=off`. Epochs: [STATE_MANAGEMENT.md § TaskList Epochs](STATE_MANAGEMENT.md#tasklist-epochs-v11-leverage-program-s2-113--111).

### Emission guards

A prior task is matched by identity (`subject_norm` + `create_seq`, resolved from the ledger for entries without one). It is *kept* when the new emission has that identity, and a dropped one is *explained* when the ledger has it completed or cancelled, or the live snapshot shows it completed (a ledger-open identity wins). One stderr line lists the explained drops. The S1 counts include `family_members` and only the live session's prior entries (review #69):

- Another session's dropped task that is still open there is listed in `dropped_foreign` with a `WARN`. It never trips a guard: that session hands it off.
- Review siblings the emission filters by design never count (`dropped_by_policy`): pending_parent siblings, and `pair_` shadows that are tagged `is_review_sibling`, whose parent closed, or that a stand-in names in `metadata.pair_shadow`.
- A live session with no ledger events yet (a Stop before the rehydrate), a fallback emission or a failed source check counts every prior entry.

| Guard | Fires when | Result | Override |
|---|---|---|---|
| Empty refusal (S1-T1) | New emission has 0 open tasks, the prior file had some, and at least one drop is unexplained | **Exit 2.** stderr lists up to 20 of the dropped tasks. `handoff.md` and `handoff-tasks.json` are left as they were, no prompt is printed and nothing is spawned. A steer this run consumed is restored from `.handoff-steer.md.prev`. | `--allow-empty` |
| Shrink breaker (S1-T1) | Prior ≥ 3, new < prior / 2, and at least one drop is unexplained | The new emission is written to `handoff-tasks.json.autoemit-proposed.json`. `handoff.md` and `handoff-tasks.json` are left as they were (review #69: no `handoff.md` for a set the tasks file refused), a consumed steer is restored, and the exit code is 0. `--spawn` exits 2. | `--allow-empty` |
| Growth breaker (pre-S1) | Prior ≥ 5 entries, new > 2 × prior | Same diversion to `.autoemit-proposed.json` | none |
| Below the floors | A drop is unexplained but no guard fires | One stderr `WARN` lists the dropped tasks | none |

Both S1 refusals print `handoff: refused — <reason>`, write `.handoff-refused` and add one note line under the title of the kept `handoff.md` (its mtime kept). `hooks/session-end` logs `emit=refused`, prints the reason and stamps the open-set digest, so a Stop does not re-run a refused emission until the task set changes. The next accepted emission removes the marker and the note.

The drop audit fails open. If it fails, stderr says so and entries that lack an identity stay unstamped. Neither S1 guard runs, and neither does the `WARN`.

`V11_HANDOFF_SOURCE_CHECK=off` restores the pre-S1 emission: no replay, no identity, no new fields, no shrink breaker and no empty refusal.

### Consumers key on identity (S1-T2, #75b)

Task ids are session-local. Every session's TaskCreate counter starts at 1, and a rehydrated task gets a fresh id. So the consumers compare identities, not ids:

- `hooks/detect-project` rehydrate verification compares the `subject_norm` multiset of `handoff-tasks.json` with the live open tasks (`scripts/lib/handoff_identity.py`). A clean rehydrate with fresh ids is no longer an `identity_mismatch`. Different tasks that reuse the old ids are one, and its `identity_delta` lists subject_norms.
- A rehydrated live task is keyed on its `metadata.rehydrated_from.identity`, so a task renamed before the handoff still matches (review #70). If the check cannot run (the helper fails, or `handoff-tasks.json` is unreadable), stderr says so and the `handoff_ack` records `identity_matched=false`. A real mismatch is always a `rehydrate_missed` event.
- `$V11_HOME/scripts/v11-resume-tasks` gives each payload whose entry has an identity a `metadata.rehydrated_from {identity, id, session}` field. A pre-S1 file (no identity) rehydrates byte-identical to before; a test checks this against a frozen copy of the pre-S1-T2 script.

`V11_HANDOFF_IDENTITY_KEYS=off` restores id-set comparison and drops `rehydrated_from`.

### No self-nudge (S1-T3, #75c)

The `Stop` auto-emit rewrites `handoff-tasks.json` while the session is still running. Its `live_session_uuid` is then the writing session, which already holds those tasks. Telling that session to rehydrate would duplicate them. So when `live_session_uuid` equals the reading session's id:

- `hooks/detect-project` skips the first-Read nudge.
- `hooks/detect-project` also skips the L2.3 rehydrate verification. No session boundary was crossed, so it logs neither `rehydrate_missed` nor `handoff_ack`.
- `hooks/post-compact` leaves out its "Handoff waiting" line. It takes the session id from its stdin `.session_id`, else `V11_SESSION_ID`.

Suppression needs a non-empty session id and a non-empty matching stamp. A pre-S1 file, a missing id or an unreadable file keeps the nudge. A different session reading the same file is nudged and verified as before. A match writes `.handoff-surfaced`, so the check runs once per stamp: a repeated Read runs no jq, and another session's `Stop` re-stamping the file mid-session does not nudge the writer (review #73). `V11_HANDOFF_SELF_NUDGE_SUPPRESS=off` restores the nudge and verification for every session.

### Summary cap and resume command (S1-T4, #57, #81)

- One helper, `_v11_summary_excerpt`, copies `.session-summary.md` into `handoff.md`. A summary within `V11_HANDOFF_SUMMARY_LINES` (default 40) passes through unchanged. A longer one keeps every `## ` heading, puts Blockers / Open Questions first and ends with `… [N more lines from <sections> — full summary: <path>]`. One stderr `NOTE:` reports the overage. `=0` means no cap, and `=20` restores the old cap (still marked).
- The rehydrate command is absolute. `handoff.md` (Rehydration and Instructions) and `handoff-tasks.json` `.rehydration_note` name `$V11_HOME/scripts/v11-resume-tasks {project}`, with `$V11_HOME` expanded when the handoff is written. `scripts/v11-bootstrap-session` prints the same form. It runs from any cwd. This half of S1-T4 has no lever.

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
| Ledger-sourced `open_tasks`, identity, shrink breaker, empty refusal (S1-T1) | `V11_HANDOFF_SOURCE_CHECK=off` | `--allow-empty` (shrink breaker and empty refusal only) |
| Identity-keyed rehydrate verification, `rehydrated_from` (S1-T2) | `V11_HANDOFF_IDENTITY_KEYS=off` | n/a |
| No nudge / post-compact line / verification for the writing session (S1-T3) | `V11_HANDOFF_SELF_NUDGE_SUPPRESS=off` | n/a |
| Summary cap with marker (S1-T4) | `V11_HANDOFF_SUMMARY_LINES=0` (no cap) | n/a |

Worst case (full opt-out, back to V11.16 behavior):
```bash
export V11_AUTO_HANDOFF=off V11_STUB_SUMMARY=off V11_HANDOFF_NUDGE=off V11_COMPACT_HANDOFF_LINE=off V11_AUTO_REHYDRATE=off
```

Back to the pre-S1 emission and consumers:
```bash
export V11_HANDOFF_SOURCE_CHECK=off V11_HANDOFF_IDENTITY_KEYS=off V11_HANDOFF_SELF_NUDGE_SUPPRESS=off V11_HANDOFF_SUMMARY_LINES=20
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
- Task IDs rotating across sessions (Claude Code framework limit — `#19` becomes `#1` on rehydration). Since S1-T2 the handoff consumers key on identity instead of ids.
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

# S1 emission, identity consumers, summary cap + resume path
python3 -m pytest tests/test_handoff_source_check.py tests/test_handoff_identity_keys.py \
    tests/test_rehydrate_verification.py tests/test_handoff_self_nudge.py \
    tests/test_handoff_summary_resume.py -v

# Fast regression core (<30s)
./scripts/run-tests --regression

# Hook latency
./scripts/hook-metrics
```

End-to-end dogfood: close a session without `/handoff`, open a new one, run `/v11`. Tasks should appear without any extra command.
