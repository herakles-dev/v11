# V11 Rollback Reference

> Quick lookup for all env-var rollback levers. Each can be toggled independently.

## v11.34 — Session-Aware Write-Gate — 2026-07-20

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_WRITE_GATE` | `block` | Controls the genuine-stall branch of `guard-write-gates` (a session that HAD a task in_progress and let it lapse). `block` (default) = today's `exit 2` behavior, unchanged. `warn` = downgrades the stall block to a stderr advisory (never exits 2). `off` = disables task-state enforcement entirely (both stall and fresh-session paths skip straight through). Does not affect the `total<2` or completed-project exemptions, which are unconditional. |
| `V11_BASH_WRITE_WARN` | on | `=off` disables the `guard-enforcement` advisory that fires when a Bash command performs a source-file write (heredoc `<<`, `>`/`>>` redirect, `tee`, `sed -i`, `dd of=`) in a task-bearing project. The advisory never blocks either way — this knob only silences the stderr warning and skips the synthetic audit row. |

## v11.33 — Lossless Sync Fallback — 2026-07-17

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_SYNC_SCRATCH_RECONCILE` | on | `=off` disables the entire (c) lane: no `.needs-reconcile` marker recording on the raced path, no top-of-hook drain in sync-tasks, no session-end drain. Restores pre-v11.33 scratch behavior (raced completion may leave the per-session scratch undercounted until manual repair). The `scripts/handoff` prefer-aggregate guard keys on marker presence, so with recording off it never triggers. |
| `V11_SYNC_NARROW_HOLD` | on | `=off` restores the legacy whole-process FD-201 hold (lock released at hook exit instead of after the last STATE write). Only affects contention frequency, not correctness. |
| `V11_SYNC_TASKS_LOCK_TIMEOUT` | 10 (seconds) | Numeric knob, not on/off — introduced in the v11.32-era BugG remediation, formalized here. Raises/lowers the FD-201 `flock -w` budget before the unserialized fallback fires. Tests set it to 0 to force the fallback deterministically; production default unchanged. |

## v11.32 — Half-Wired Loop Audit — 2026-07-15

No new rollback env vars were introduced this version — the audit closed half-wired *code paths*
(installers, attribution readers, gate re-wiring), not new toggles. One existing lever changes
behavior:

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_AUTO_REHYDRATE` | on | Originally introduced in V11.17 (doc-only for 6 versions — see the V11.17 section below for the original lever). As of v11.32 (H5) it is now **code-enforced** in `scripts/v11-resume-tasks`: setting `=off` disables the actual auto-rehydration-from-`handoff-tasks.json` behavior at the code level, not just the doc-level intent. |

Other v11.32 items — git-hook installer fixes (worktree/symlink `--git-common-dir` resolution),
`agent-scorecard --routing`, `guard-effort` matcher revival (`Task|Agent`), `review-queue-maintenance`
flock + `review-cadence` wiring, `scripts/ledger-verify`, auto-pair `scope:"small"` stamping, and the
`--regression` / `--regression-extended` two-tier split — are CLI-flag-level, prompt-level, or bug
fixes to existing gated code paths. The CHANGELOG entry does not name a dedicated new rollback env
var for any of them.

## v11.31 — Pre-Scope Actuation + Two-Source Token Capture — 2026-07-15

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_SCOPE_WARN` | on | `sync-tasks` stops warning on missing/invalid `metadata.scope` for work tasks (review-sibling/blocker tasks remain exempt either way). |
| `V11_PRESCOPE_SMELL` | on | `sync-tasks` stops warning on multi-deliverable description smells (conjunction / 3+ runbook steps / >600 chars on a non-small task). |
| `V11_PRESCOPE_CONTEXT` | on | Fired pre-scope advisories no longer emit the PostToolUse `hookSpecificOutput.additionalContext` envelope — the orchestrator model stops seeing the advisory inline in the `TaskCreate` tool result (this is the dogfood-verified visibility fix). |
| `V11_PRESCOPE_LEDGER` | on | Fired advisories stop landing as `ev:prescope` durable-ledger rows — both the status-neutral event and the replay-fold counter-inflation guard are disabled. |
| `V11_PRESCOPE_STATUS` | on | `scripts/status` stops printing the `Pre-scope: X% scoped, N advisories open` line. |

The two-source token-capture fix (root cause: `track-agents` probed hypothesized snake_case fields
while real harness payloads are camelCase, e.g. `totalTokens`) reuses the existing `V11_TOKEN_CAPTURE`
lever from V11.29 — no new env var was introduced for it.

## v11.30 / W2-T6 — Version-Stamp Drift Guard

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_STAMP_DRIFT` | on | `scripts/check-stamp-drift` (invoked from `scripts/run-tests` alongside the drift check) no-ops instead of comparing version stamps across the agent registry, README, VERSION.md, and CLAUDE.md against a git-derived anchor; a real version-stamp mismatch will not soft-block either regression tier (`--regression` or `--regression-extended`). |

## v11.30 / W5-T16 — Cross-Session Verdict Fold-Back

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_REVIEW_LEDGER` | on | `v11_review_queue_mark_done` skips B1 (durable verdict store at `~/.agent-metrics/review-verdicts/{project}/`), B2 (`ev:"review"` ledger event), and B4 (verdict_ref/verdict_sha on the queue done event); `mark-done` reverts to severity-only behavior identical to pre-W5-T16. Independent of `V11_REVIEW_ENFORCEMENT`. |

## V11.29 — Concurrency Lanes, Pre-Scoped Tasks, Token Ledger, Worktree Default

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LANE_LEASE` | on | `hooks/lib/common.sh` lane-lease helpers (`v11_lane_claim/release/force_release/gc/status`) and the `sync-tasks` auto-claim-on-`in_progress`/auto-release-on-`completed` behavior are disabled; no "LANE CONFLICT" advisory, no `~/.agent-metrics/lanes/<project>.jsonl` writes. |
| `V11_PRESCOPE_ADVISORY` | on | `sync-tasks` stops emitting the pre-scoping advisory when a `TaskCreate` sets `metadata.scope=large` or is complex/novel without `metadata.deliverable_of`. |
| `V11_TOKEN_CAPTURE` | on | `dispatch-trace-append` ignores `--tokens/--tool-uses/--duration-ms/--event`, and `track-agents` skips passthrough of harness-reported usage into `usage.jsonl`; scorecard/effectiveness `avg-tokens/spawn` column stays omitted. |
| `V11_WORKTREE_DEFAULT` | on | Editing spawns no longer default to `isolation:"worktree"` (skill rule 20 + orchestrate + context-tiered-mode); docs-level policy toggle only — does not touch `scripts/worktree-sweep` itself. |

## V11.28 — Handoff Steering Prompt

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_HANDOFF_STEER` | on | No steer span is prepended into `$PROMPT`/`handoff.md`, and the sidecar `.handoff-steer.md` (or `--steer` flag) is not consumed — file is left in place rather than archived to `.handoff-steer.md.prev`. |

## V11.27 — Ledger Integrity (six half-wired loops)

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_RETRO_SANITY_GUARD` | on | `scripts/status` stops printing the "retro flywheel likely broken" warning when the retro counter exceeds 10×`V11_RETRO_THRESHOLD`; the fd-201 flock around the retro read-increment-write in `hooks/session-end` still applies (not gated by this var). |
| `V11_A4_DEADGATE_WARN` | on | `track-autonomy` and `scripts/status` stop warning when autonomy level ≥4 and `high_risk_history` is empty (the always-block landing gate itself is unchanged). |
| `V11_DETECT_RECONCILE` | off | Default off — set `=on` to make `hooks/detect-project` emit the read-only `v11_detect_reconcile` JSON block (zombie/discipline + review-queue + fold-families + retro-counter signals). |
| `V11_RQ_TRACE_UNKNOWN` | on | `v11_review_queue_add` stops adding a `trace` field / WARN when admitting `agent_id=="unknown"` entries (still admits them; only the trace/WARN is disabled). |
| `V11_FOLD_RECONCILE` | off (dry-run default) | `scripts/fold-reconcile --apply --confirm` writes are gated behind this; without it, only `--dry-run` propose-only output is available even with `--apply --confirm` passed. |

## V11.26 — Handoff State Machine Extraction + Test-Honesty Lint

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LINT_TEST_HONESTY` | on | `scripts/lint-test-honesty` soft-block in both `scripts/run-tests --regression` and `--regression-extended` is skipped; P1–P4 pattern checks (stderr-subtraction, disjunctive-decision-assert, bare-`_run()`-negative-only-assert, bash case-without-default) do not run. |

## V11.25.1 — Drift-Sweep Follow-ups + Stale Handoff Summary

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_STALE_SUMMARY_CHECK` | on | `scripts/handoff` treats any existing `.session-summary.md` as canonical forever — no mtime/task-state-newer freshness check, no archive to `.session-summary.md.prev.md`, no stub regeneration. |
| `V11_STALE_SUMMARY_GRACE_SECS` | 86400 | Overrides the staleness grace window (seconds) used by the freshness check above; not an on/off toggle. |
| `V11_SESSION_END_REORDER` | on | `hooks/session-end` reverts to emitting `handoff.md` BEFORE `last-session.json` is written, reintroducing the stale-read-of-prior-session bug the reorder fixed. |

## V11.25.0 — Discipline Mechanization + V11.21 Producer Completion

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_POSTCOMMIT_AUTOCLOSE` | on | `hooks/post-commit-close-tasks` does not auto-close in_progress tasks matching `S{N}-T{M}:` in the HEAD commit subject. |
| `V11_POSTCOMMIT_DRYRUN` | off | Set `=on` to log post-commit auto-close matches without writing status_changed events. |
| `V11_VALIDATION_LINT` | on | `hooks/lib/validation_lint.py` (PreToolUse Bash matcher + commit-msg hook) stops enforcing the `Validation:` tag on commits. |
| `V11_VALIDATION_LINT_STRICT` | off | Default warn-only; set `=on` to hard-block commits missing/malformed `Validation:` tags instead of warning. |
| `V11_VALIDATION_LINT_HEURISTIC` | on | Disables the `(verb ∧ number)` heuristic that WARNs on missing tag without false-positiving chore/docs commits. |
| `V11_AUTO_PAIR_REVIEW` | on | `sync-tasks` `TaskCreate` branch stops auto-synthesizing a paired adversarial-lite-reviewer sibling task for medium/complex/novel or medium/high-risk parents. |

## V11.24 — Session-Bind Drift Fix (Strategy 1.6)

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LEDGER_TASK_HOME` | on | `sync-tasks` Strategy 1.6 (ledger `(session_uuid, task_id)` scan when Strategies 1 and 1.5a both miss) is disabled — `TaskUpdate` without `metadata.project` can silently misroute to a stale session-bound project again. |

## V11.23 — Handoff Cross-Project Scope Leak Fix

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_TASK_ROUTE_BY_METADATA` | on | `v11_rebuild_project_aggregate` reverts to V11.15.5 per-session Bug-H quarantine (whole-session include/exclude based on whether ANY task declares $PROJECT). Per-task filter disabled. |
| `V11_HANDOFF_LIVE_RECONCILE` | on | `hooks/sync-tasks` does NOT stamp `_proj` on TaskCreate / TaskUpdate(in_progress); live-snapshot writer disabled. |
| `V11_HANDOFF_CATEGORY` | on | `scripts/handoff` does not emit HANDOFF_CATEGORY banner (TO_BUILD / PAUSED_EXTERNAL / PAUSED_USER / RESUME); no blocker surfacing at top. |
| `V11_GATE_SUBSTANCE` | on | `scripts/handoff` does not check session-summary stub fingerprints (W3 5/29 — unedited stub detection). |
| `V11_GUARD_STALE_TASK` | on | `hooks/guard-stale-task` exits silently (zombie task advisory disabled). |

**Layer 1 softening (V11.23)**: `scripts/handoff` `open_tasks_by_session` filter at lines ~1141, ~1456 now accepts `metadata.project == $PROJECT` OR `metadata.project == null`. No env var — controlled by code path. Safe because Layer 3 ensures null-metadata tasks only land in $PROJECT.json when their session was legitimately for $PROJECT.

**Architectural fix (Layer 3) applies going forward**: Tasks routed by `metadata.project` (with session-project fallback for null) at every aggregate rebuild. **Pre-V11.23 legacy contamination** (tasks accumulated in wrong aggregates whose source sessions are now orphaned) requires manual cleanup — delete the aggregate file and let it rebuild from live sessions, OR run `scripts/reconcile-aggregates --apply`.

**Gate 14** (handoff scope integrity) and `scripts/reconcile-aggregates` are read-only diagnostics and have no rollback (no-ops when nothing to report).

## V11.21 — Agent Routing & Dual-Layer Review

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_AUTO_PAIR_REVIEW` | on | No paired review tasks created; V11.19 queue path resumes |
| `V11_SELF_REVIEW_REQUIRED` | on | Shape-validation of a *present* self_review payload skipped (malformed-JSON synthetic `lite_self` row no longer emitted); absence tracking is a separate lever, see `V11_SELF_REVIEW_ACTUATE` (W5-T15) |
| `V11_DAAO_ROUTING` | on | Phase 4 defaults to `spec-implementer-v11` when `metadata.agent` unset; explicit `metadata.agent` always honored (prompt-level lever — followed by the orchestrator LLM, not code-enforced) |
| `V11_HANDOFF_REVIEW_FILTER` | on | `handoff-tasks.json` reverts to V11.18 shape (pending_parent siblings kept) |
| `V11_WAVE_CHECK` | on | `scripts/wave-check` exits 0 unconditionally (script-level bypass) |

**Coupling**: when `V11_AUTO_PAIR_REVIEW=on`, sync-tasks suppresses V11.19 enqueue for tasks whose parent has `metadata.review_task_id` set.

## v11.30 / W5-T15 — Layer A Self-Review Actuation

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_SELF_REVIEW_ACTUATE` | on | Disables both the completion-hint self_review postamble (A1) and the synthetic `missing_self_review` absence row appended to `agent-errors.jsonl` on reviewable completion (A2); stderr nudge (`V11_SELF_REVIEW_NUDGE`) is unaffected |
| `V11_SELF_REVIEW_NUDGE` | on | Silences the stderr missing-self_review nudge only; the A2 absence row (`V11_SELF_REVIEW_ACTUATE`) is unaffected — the two levers are fully independent (W5 prod-fix de-nested the gates) |

## V11.20 — Audit & Improve Subagents

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_CALLER_KIND` | on | `track-autonomy` omits `caller_kind` field from audit events |
| `V11_WAVE_ATTRIBUTE` | on | `wave-review-attribute` exits 0 (no attribution) |
| `V11_SWARM_ATTRIBUTE` | on | `swarm-review-attribute` exits 0 (no attribution) |

## V11.19 — Review Enforcement

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_REVIEW_ENFORCEMENT` | on | Disables the AUTOMATIC review-queue paths: sync-tasks enqueue + sync-tasks-driven mark-done and the pending backstop. The manual `scripts/review-queue mark-done` CLI is NOT gated — deliberate operator action always works |
| `V11_REVIEW_NUDGE` | on | Silence detect-project review nudge |

## V11.18 — Handoff Hygiene

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_FOLD_FAMILIES` | on | No token-overlap family folding in handoff |
| `V11_DISCIPLINE_DETECTOR` | on | No discipline check for shipped-but-unclosed tasks |
| `V11_DISCIPLINE_NUDGE` | on | No TaskList nudge for likely-shipped tasks |
| `V11_COMPLETION_HINT` | on | No file-edit → task-completion hint |
| `V11_HANDOFF_ADDENDUM` | on | No `.handoff-addendum.md` prepend |
| `V11_REHYDRATE_FOLD` | on | Families unfolded into raw members during rehydration |
| `V11_DISCIPLINE_WINDOW_HOURS` | 6 | Window for discipline detector audit-log lookback |

## V11.17 — Smooth Handoff

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_STUB_SUMMARY` | on | No auto-written `.session-summary.md` stub |
| `V11_AUTO_HANDOFF` | on | `session-end` does not auto-emit handoff |
| `V11_HANDOFF_NUDGE` | on | No detect-project handoff nudge |
| `V11_COMPACT_HANDOFF_LINE` | on | No "Handoff waiting" line in post-compact |
| `V11_AUTO_REHYDRATE` | on | No auto-rehydration from `handoff-tasks.json` |

## V11.16 — Durable Ledger

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LEDGER_CUTOVER` | on | Aggregate is NOT replayed from ledger; legacy fold path used |

## Full Disable Recipe

To revert to V11.16 behavior (pre-review, pre-handoff-hygiene):
```bash
export V11_AUTO_PAIR_REVIEW=off V11_SELF_REVIEW_REQUIRED=off V11_DAAO_ROUTING=off
export V11_REVIEW_ENFORCEMENT=off V11_REVIEW_NUDGE=off
export V11_FOLD_FAMILIES=off V11_DISCIPLINE_DETECTOR=off V11_COMPLETION_HINT=off
export V11_HANDOFF_REVIEW_FILTER=off V11_WAVE_CHECK=off
```
