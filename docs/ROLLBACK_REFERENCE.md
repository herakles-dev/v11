# V11 Rollback Reference

> Quick lookup for all env-var rollback levers. Each can be toggled independently.

## v11.44 — Orchestrator Quality

Spec: `sessions/v11-orchestrator-quality/spec.md`. Fold-table: `hooks/lib/actor-canonical.json`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_ORCH_QUALITY` | on | Read-side actor canonicalization. `=off` makes `v11_canonical_actor` the identity, so `agent-scorecard`/`agent-effectiveness` revert to literal-string matching (the orchestrator family splits back into 5 rows). Pure read-side — no data change. |
| `V11_BRIEF_REVIEW` | on | Gates brief grading. `=off` makes `scripts/grade-briefs` a no-op (exit 0), stops `sync-tasks` stamping `cause_kind="execution_defect"` on new lite findings, and skips the `orchestrator-briefing-quality` consumer in `check-improve-subagent-triggers`. Additive fields only — legacy readers unaffected either way. |
| `V11_RUNTIME_ERROR_CAPTURE` | on | Gates the G2 fix in `track-autonomy`. `=off` restores the legacy `.error`-only outcome check (identical pre-v11.44 behavior — the runtime-error layer goes dormant again). `is_error` detection cannot false-positive on a success. |
| `V11_ORCH_BRIEF_DEFECT_THRESHOLD` | 0.30 | Briefing-defect rate at/above which the `orchestrator-briefing-quality` consumer trigger fires. |
| `V11_ORCH_BRIEF_MIN` | 3 | Minimum briefs graded before the consumer trigger can fire (noise floor). |

Deferred (need a `dispatch-trace` v2 `session_uuid` bump): orchestrator/subagent runtime split, per-brief override attribution. Not levers — documented follow-ons.

## v11.43 — Timing Calibration

Anchor doc: `docs/BUILD_TIMING.md`. Re-derivation: `scripts/build-timing`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_TIMING_ANCHOR` | on | Prompt-level lever (like `V11_LIVE_OPS_LANE`). Gates the wall-clock estimate line added to the interview STEP 4c plan-summary (`playbooks/interview.md`). `=off` suppresses the estimate — the gate reverts to task-count-only ("Plan summary: {N} tasks across {formation}. Apply?"). The `scripts/build-timing` script, `docs/BUILD_TIMING.md`, the `task-patterns.md`/`SKILL.md` anchors, and the retro `timing_actual` field are all additive and inert without acting on the estimate, so `=off` is a clean revert of the behavior with no data change. |

## v11.42 (candidate) — Task-State Integrity — Wave 1 + Wave 2

Spec: `sessions/v11-task-state-integrity/spec.md`. Recon+review artifacts: `sessions/v11-task-state-integrity/recon-notes/README.md`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_CANCELLED_COUNTER` | on | W1-T1 (RC4). `hooks/lib/common.sh` replay populates aggregate `.cancelled` counter from per-record status sum. `=off` sets `.cancelled=0` unconditionally (pre-v11.42 behavior — the field is still present in the schema, just always zero). Additive; zero downstream consumers per recon-6, so `=off` is a no-op for observed callers. |
| `V11_LEDGER_AUDIT_NOLEDGER` | on | W1-T2 (RC5a). `v11_rebuild_project_aggregate` empty-scan-preserve branch (`common.sh:L280`) appends `{decision:"empty-scan-preserve", has_ledger:bool}` JSONL entry to `~/.agent-metrics/ledger-cutover.jsonl` alongside the existing stderr warn. Makes no-ledger dormant projects programmatically discoverable. `=off` skips the append (stderr signal remains). Never blocks the rebuild. |
| `V11_IDENTITY_HELPER` | on | W1-T3 (RC1). `v11_resolve_identity(project, task_id, session_uuid, subject)` bash helper walks `~/.agent-metrics/ledger/${project}.jsonl` for most-recent `created` event and returns `{create_seq, subject_norm, found}` JSON. Canonical-identity resolution reused by `/align-aggregate` v1.3+ and Wave 2 T3's age-out logic. `=off` makes the helper unconditionally return `{"found": false}` — callers fall back to their own inline logic. |
| `V11_PAIR_ID_DURABLE` | on | W2-T1 (RC3). `hooks/sync-tasks` mints `pair_<sid8>_<seq>_<rand6hex>` where `seq` is sourced from durable ledger max (not per-session STATE_FILE counter). Belt+braces against STATE_FILE reset + `legacy-cli` fallback. `=off` reverts to `pair_<sid8>_<seq>` where seq is the STATE_FILE-local counter (pre-v11.42; retains collision risk). Old pair_ ids stay resolvable as opaque strings under either setting. |
| `V11_REVIEW_SIBLING_AGEOUT` | on | W2-T3 (RC2). `/align-aggregate` skill v1.3 age-out logic — invoked via `hooks/session-end` when `V11_ALIGN_ON_SESSION_END=apply` — cancels V11.21 review siblings whose `metadata.parent_status="pending"` AND `parent_unblocked_at` older than `V11_REVIEW_SIBLING_AGEOUT_DAYS`. Emits `ev:cancelled` with `reason="review_sibling_ageout"`. `=off` disables age-out; siblings sit pending forever (pre-v11.42). |
| `V11_REVIEW_SIBLING_AGEOUT_DAYS` | 14 | W2-T3. Age cutoff in days. `legacy-cli`-created siblings use 2× this value (default 30 days) as best-effort protection since `v11_session_is_live("legacy-cli")` is structurally false — see spec non-goal for rationale. Tighten (lower) or loosen (higher) freely. |
| `V11_AGEOUT_GUARD_CARVEOUT` | on | W2-T2 (RC5b). `common.sh:L816` GUARD ROLLBACK carve-out: when replay-vs-legacy delta is fully accounted for by ledger `cancelled` events with `reason="review_sibling_ageout"`, do NOT trip the regression-guard. Compares `(replay + reason_ageout_count) vs legacy` instead of raw `replay vs legacy`. **FOOTGUN**: setting `V11_REVIEW_SIBLING_AGEOUT=on + V11_AGEOUT_GUARD_CARVEOUT=off` reproduces exactly the silent-revert the bundling was designed to prevent. **Load-time protection**: `common.sh` WARNs loudly + auto-forces `CARVEOUT=on` when it detects `AGEOUT=on + CARVEOUT=off`. The reverse combo (AGEOUT=off + CARVEOUT=on) is inert (carve-out has zero ageout events to credit) and safe. |
| `V11_ALIGN_ON_SESSION_END` | dryrun | W2-T3. `hooks/session-end` invocation of `/align-aggregate` skill for automatic phantom-cleanup. `=dryrun` (default) runs the skill in list-phantoms mode — reports what it WOULD cancel but writes nothing. `=apply` opts in to auto-apply cancellations. `=off` skips the invocation entirely. |
| `V11_TASK_STATE_INTEGRITY_V1` | on | Umbrella lever. `=off` reverts ALL v11.42 behavior to pre-v11.42 by short-circuiting each individual lever's on-path. Emergency rollback. Prefer per-lever `=off` for targeted issue diagnosis. |

## v11.41 (candidate) — Cross-Session Handoff Loop — sprint-01

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_DOC_DRIFT` | on | L1.1 (v11-handoff-cross-session-loop). `scripts/handoff` reads cached `sessions/{project}/.drift-scan-result.json` (from prior `/v11-drift`) and folds a `⚠ DOC-DRIFT` warning into `handoff.md` `_WARNING_BLOCK` when grade ∈ {C, D, F}. `=off` suppresses the warning entirely (cache file untouched). Missing / empty / malformed cache is silently skipped either way. Test: `tests/test_handoff_doc_drift.py`. |
| `V11_LOOP_BASELINE` | on | L1.3b (v11-handoff-cross-session-loop). `scripts/handoff` invokes `scripts/lib/loop_baseline.py` AFTER the QR-1 pending reconcile and QR-2 category re-derivation, BEFORE the staging→final promotion. Writes `sessions/{project}/.loop-baseline.json` atomically (schema v1: `handoff_at`, `git_head`, `spec_md_mtime`, `autonomy_level`, `expected_open_tasks_count`, `handoff_tasks_hash`, `baseline_source` + Sprint 3 slots). Load-bearing for L2.1 boot-delta, L2.3 rehydrate verification, L2.4 loop-ack. `=off` skips the write entirely; the write is non-blocking (timeout 5s + `\|\| echo WARN`), so it can NEVER orphan a handoff. Tests: `tests/test_loop_baseline.py` (unit, 54 tests), `tests/test_loop_baseline_integration.py` (integration, L1.3c). |
| `V11_LOOP_BOOT_DELTA` | on | L2.1 (v11-handoff-cross-session-loop). `hooks/detect-project` reads `.loop-baseline.json`, diffs against current disk (`git_head`, `spec_md_mtime`, `expected_open_tasks_count`), and emits a `⚡ SINCE LAST HANDOFF` banner via `hookSpecificOutput.additionalContext` on stdout — the model actually sees this (stderr from hooks is invisible per the 2026-09-01 dogfood). `=off` skips both diff compute and emit; L2.3 rehydrate verification and L2.2 freshness gate stay live. Also caches the diff field list in `_RV_DELTA_FIELDS` for L2.4 `handoff_ack.baseline_delta_fields` to reuse without re-derivation. Test: `tests/test_boot_delta.py`. |
| `V11_HANDOFF_FRESHNESS_GATE` | on | L2.2 (v11-handoff-cross-session-loop). Same `detect-project` handler: if `handoff.md` mtime exceeds `V11_HANDOFF_MAX_AGE_DAYS` (default 7), prepends `⚠ STALE HANDOFF: … verify state before resuming.` to the L2.1 `additionalContext` block. `=off` disables the check entirely, keeping `V11_HANDOFF_MAX_AGE_DAYS` free as a tightening knob (a 0-day cap would fire on any handoff older than 24h — legitimate tightening, not disable semantics). Test: `tests/test_boot_delta.py::TestFreshnessGate`. |
| `V11_ORPHAN_DETECTOR` | on | L2.5 (v11-handoff-cross-session-loop). `hooks/session-end` scans `$SESSIONS_ROOT/*/.last-spawn-at` files older than `V11_LOOP_ORPHAN_MINUTES` (default 60). For each latch, checks `~/.agent-metrics/loop-events.jsonl` for a matching `handoff_ack` OR `rehydrate_missed` event (same project, ts >= latch mtime). Missing → emits `HANDOFF_ORPHAN` event via `scripts/lib/loop_events.py`, then touches `{latch}.orphan-notified` sibling marker for fire-once (persistent across sessions — the observer that later re-notices should not re-emit). `=off` disables the entire scan. Never blocks session-end (hook always exits 0). Also gated by `V11_LOOP_ORPHAN_MINUTES > 0`. Test: `tests/test_orphan_detector.py`. |
| `V11_LOOP_ORPHAN_MINUTES` | 60 | L2.5 orphan-age threshold (integer minutes). Setting to `0` acts as an alternative disable path for the whole detector. Above 0, tighten (lower) or loosen (higher) as needed. |
| `V11_LOOP_ACK_EVENT` | on | L2.4 (v11-handoff-cross-session-loop). Emits a `handoff_ack` event to `~/.agent-metrics/loop-events.jsonl` when rehydrate verification passes (counts + IDs match, no divergence). Carries `prev_handoff_at` (from baseline), `identity_matched=true`, and `baseline_delta_fields` reused from L2.1's diff — grep receipts of healthy cycles. Independent of `V11_REHYDRATE_VERIFY` so operators can silence receipts without silencing the `rehydrate_missed` failure emission path. Test: `tests/test_rehydrate_verification.py::TestHappyPath`. |
| `V11_REHYDRATE_VERIFY` | on | L2.3b (v11-handoff-cross-session-loop). `hooks/detect-project` compares `sessions/{project}/.loop-baseline.json.expected_open_tasks_count` (recorded at emit by L1.3b) against the live per-session `task-state.json` count. On divergence, discriminates a `failure_mode` (`skill_not_invoked` \| `gate_off` \| `script_error` \| `manual_override` \| `identity_mismatch`) and appends a `rehydrate_missed` event to `~/.agent-metrics/loop-events.jsonl` via `scripts/lib/loop_events.py` (L2.3a). Fire-once via `~/.agent-metrics/sessions/$V11_SESSION_ID/.rehydrate-verify-done` marker (same pattern as `.handoff-surfaced` and `.review-surfaced-*`). Piggybacks the existing `detect-project` hook — no new hook wiring per Sprint 2 constraint. `=off` skips verification entirely (marker not written). Identity-mismatch discrimination requires `sessions/{project}/handoff-tasks.json` to be present for ID-set comparison. Test: `tests/test_rehydrate_verification.py` (L2.3c). |
| `V11_HANDOFF_FORCE_RECONCILE` | on | L1.2 (v11-handoff-cross-session-loop). `scripts/handoff` runs `v11_rebuild_project_aggregate` on the per-session path too, not only the aggregate-fallback path. Extends the existing rebuild at `handoff:517-524` (which only fires when `STATE_SOURCE=aggregate`) with a mirror block at `handoff:527-546` gated on `STATE_SOURCE=per-session` + this lever, `timeout 5`. Fixes the stale-durable-aggregate problem (2026-09-01 dogfood: v11 project aggregate was 11 days stale on this box). `=off` restores per-session-skip behavior. Independent of the aggregate-path rebuild, which fires unconditionally regardless of this lever. Tests: `tests/test_handoff_force_reconcile.py` (4 tests: on/off × per-session/aggregate). Also fixed a pre-existing bug in the same edit: both rebuild subshells now pass `V11_HOME="$V11_HOME"` instead of the hardcoded `"$HERCULES_ROOT/v11"` (which silently no-op'd whenever `HERCULES_ROOT` didn't have v11 co-located — invisible in production, but the class of bug the drift-check block at `handoff:1615/1618` already got right). |

## v11.37 — Alignment Remediation — 2026-08-28

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_REGISTRY_RECONCILE` | on | v11.37 W1-T1 ticket #38-F2: `scripts/reconcile-agent-registry` runs its full add/prune/atomic-write path. `=off` puts the reconciler into pure no-op mode (exits 0 without touching `~/.agent-registry/agents.json`) — used during incident containment or when a stale environment shouldn't get reconciled. Independent of `--dry-run`/`--apply`/`--revert` flags: any of those exit cleanly at 0 with the lever off. |
| `V11_LEDGER_STRICT_ATTRIBUTION` | off | v11.37 W1-T2 ticket #38-F1: write-time normalization gate in `v11_ledger_append` (`hooks/lib/common.sh:2436`). Tri-state — `off` (default, pre-v11.37 behavior — no observability); `advisory` or `on` — for agent-authored events (`created`/`review`/`artifact_warn`) missing `owner`+`metadata.agent`+`recommended_agent`, emit a STDERR WARN and mirror the event to `~/.agent-metrics/unattributed-events.jsonl` for later analysis. **Primary ledger write ALWAYS proceeds** — this is observability, not data-loss. Read-only companion audit: `scripts/audit-ledger-attribution`. |
| `V11_INDEX_BODY_CHECK` | on | v11.37 W2-T1 ticket #42: `scripts/check-index-body-status-consistency` runs. `=off` no-ops the check (exit 0). Wired into `scripts/handoff:1425` drift-check loop + `run-tests --regression`. See `docs/DRIFT_CHECKS.md`. |
| `V11_ROLLBACK_LEVER_CHECK` | on | v11.37 W2-T2 ticket #44: `scripts/check-rollback-lever-drift` runs. `=off` no-ops (exit 0). Same wiring surfaces as `V11_INDEX_BODY_CHECK`. |
| `V11_REGISTRY_CHECK` | on | v11.37 W2-T3 ticket #38-F2 companion check: `scripts/check-registry-drift` runs the 3-way disk↔registry↔ledger reconciliation. `=off` no-ops (exit 0). Same wiring surfaces. A FAIL from this check IS a `--spawn` block (data-honesty class: adversarial-lite-reviewer-shaped regressions must not silently hide). |
| `V11_DRIFT_VERBOSE` | off | v11.37 W2-T4 UX lever for `scripts/handoff` drift-check block. `off` (default) — 1-line summary only (`drift checks: N ran, P PASS, W WARN, F FAIL`); `on` — full per-check WARN/FAIL block on stderr. FAIL blocks always print regardless of verbose. |
| `V11_SKIP_DRIFT_CHECKS` | (unset) | v11.37 W2-T4 unified operator bypass. Setting to `1` (or passing `--skip-drift-checks` to `scripts/handoff`) skips the ENTIRE drift-check family in one lever. Individual per-check env-vars still work at the script level. Recovery path for stuck operators. |

## v11.36 — Proactive Discipline (W2) — 2026-08-28

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_HANDOFF_MTIME_GUARD` | on | Ticket #41 F1 (post-CLOSE follow-up shipped 2026-08-28): `scripts/handoff` refuses to regenerate `handoff.md` when the file is NEWER than the trigger basis (`.session-summary.md`, falling back to `STATE_FILE`). The unattended `session-end` auto-emit path is what this protects — the `/handoff` skill and any manual invocation pass `--force` implicitly. Content-hash fallback: if the summary is still the V11.17 auto-stub (fingerprint match), the guard does not fire and regen proceeds (nothing to protect). `=off` reverts to the pre-F1 always-regenerate behavior. See `improvements/41-auto-handoff-clobbers-hand-written.md` and `tests/test_handoff_mtime_guard.py`. |
| `V11_TASK_PROJECT_AUTODEFAULT` | on | Controls `sync-tasks` Strategy 1.7 (#36-F1): when `metadata.project` is absent and no task/session/ledger-identity strategy resolves it, checks whether the session's CWD is inside `$SESSIONS_ROOT/{project}/` and auto-defaults to that project. `=off` disables Strategy 1.7 entirely (falls through to Strategy 2 / NO PROJECT HOME as before) AND restores the original WARN/ADVISORY text at the two downstream sites (the `TaskCreate` implicit-attribution warning and the `TaskUpdate(completed)` Bug E advisory) instead of the V11.36 INFO-level downgrade. The all-strategies-failed "NO PROJECT HOME" warning is unaffected either way — it stays WARN. |
| `V11_SPAWN_NOTIFY_ON_IDLE` | off | Doc-only, prompt-level lever in `orchestrate.md` §"Idle notification hygiene" (#36-F2 fold-in, W3-T1/T2/T3). Governs ONLY the orchestrator's own default, when messaging a peer session via `SendMessage`, of whether to subscribe for that peer's idle notice — not code-enforced, no hook reads it. `=on` reverts to the pre-sprint default of always subscribing. It has no effect on `Agent()`-tool background spawns: those fire an unconditional harness idle-completion event with no per-call field to gate — do not treat this lever as suppressing that (see the §"Idle notification hygiene" audit finding: 0 `notify_when_idle` occurrences existed in any spawn template prior to this change). |
| `V11_CLASS_INCLUDED_CHECK` | on | `scripts/check-class-included` (W2-T2, wired into `scripts/handoff` and `scripts/run-tests --regression`) no-ops instead of flagging a class/function referenced in source without a matching `#Include`/import line. `=off` disables the check entirely (exit 0 always) — a confirmed missing-include drift (exit 1) will neither block `handoff --spawn` nor soft-block the regression tier. See `docs/DRIFT_CHECKS.md`. |
| `V11_GIT_TASKLIST_CHECK` | on | `scripts/check-git-tasklist-alignment` (W2-T3, wired into `scripts/handoff` and `scripts/run-tests --regression`) no-ops instead of flagging git-modified/untracked files not tied to any completed task's `metadata.artifacts`. `=off` disables the check entirely (exit 0 always). Advisory-only either way — this check never FAILs (exit 2 WARN at most), so it never blocked `--spawn` or the regression tier to begin with. See `docs/DRIFT_CHECKS.md`. |
| `V11_HOTKEY_SYNC_CHECK` | on | `scripts/check-hotkey-sync` (W2-T4, wired into `scripts/handoff` and `scripts/run-tests --regression`) no-ops instead of flagging a hotkey present on one configured surface but missing from another. `=off` disables the check entirely (exit 0 always). Advisory-only either way — this check never FAILs (exit 2 WARN at most). See `docs/DRIFT_CHECKS.md`. |

## v11.35 — Artifact-on-Complete Advisory — 2026-07-29

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_ARTIFACT_ON_COMPLETE` | `warn` | Controls the improvement-16 audit-class completion check in `hooks/sync-tasks`. `warn` (default) = model-visible `additionalContext` advisory + a durable ledger row (`ev:"artifact_warn"`/`ev:"artifact_exempt"`) when an audit-class task (Explore/adversarial-reviewer/adversarial-lite-reviewer/coherence-reviewer, or an Audit/Verify/Inventory/Map/Find/Investigate subject, or `metadata.task_class:"audit"`) completes with no evidence in `files_changed`/`summary`/`review.summary`/`self_review`. `off` = the check does not run at all (no advisory, no ledger row). There is no `block` mode — `sync-tasks` is PostToolUse and always exits 0 (see file header); a 5-lens swarm review found the originally-proposed block mode structurally impossible. |
| `V11_ARTIFACT_STATUS` | on | `=off` disables the `scripts/status` consumer line ("Artifact evidence: N advisory(ies) recorded, M exempt") that reads the ledger rows above. Shipped in the same change as the producer. |

## v11.34 — Session-Aware Write-Gate — 2026-07-20

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_WRITE_GATE` | `block` | Controls the genuine-stall branch of `guard-write-gates` (a session that HAD a task in_progress and let it lapse). `block` (default) = today's `exit 2` behavior, unchanged. `warn` = downgrades the stall block to a stderr advisory (never exits 2). `off` = disables task-state enforcement entirely (both stall and fresh-session paths skip straight through). Does not affect the `total<2` or completed-project exemptions, which are unconditional. |
| `V11_BASH_WRITE_WARN` | on | `=off` disables the `guard-enforcement` advisory that fires when a Bash command performs a source-file write (heredoc `<<`, `>`/`>>` redirect, `tee`, `sed -i`, `dd of=`) in a task-bearing project. The advisory never blocks either way — this knob only silences the stderr warning and skips the synthetic audit row. |
| `V11_SESSION_LIVENESS_MINUTES` | 15 | v11.37 W1-T5 documented (was silent). Tuning knob (integer minutes) — NOT an on/off toggle. Controls the aliveness window used by `v11_session_is_live()` in `hooks/lib/common.sh:3649` for write-gate + active-project ownership decisions + review-queue GC coupling. Higher values keep dead sessions treated as live longer (less stealing); lower values are stricter. Related sites: `hooks/lib/common.sh:4445-4535` (review-queue liveness/GC), `common.sh:3705` (V11_REVIEW_CROSS_PROJECT_CHECK also reads this indirectly). |

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
| `V11_STAMP_DRIFT` | on | `scripts/check-stamp-drift` (invoked from `scripts/run-tests` alongside the drift check, and — as of v11.36 W2-T5 — also from `scripts/handoff` at the pre-handoff drift-check site) no-ops instead of comparing version stamps across the agent registry, README, VERSION.md, and CLAUDE.md against a git-derived anchor; a real version-stamp mismatch will not soft-block either regression tier (`--regression` or `--regression-extended`), and will not surface in `handoff` output either. **v11.36 W2-T1 extension**: this same lever ALSO gates the independent per-project version-file consistency phase (`sessions/{project}/.stamp-drift-extra.json`) — `=off` disables both the git-anchor comparison and the per-project phase together; there is no separate lever for the extension. |

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
| `V11_STEER_PREV_GRACE_SECS` | 300 | v11.37 W1-T5 documented (was silent). Tuning knob (integer seconds) — NOT an on/off toggle. Controls the freshness window for V11.28.2 steer re-bake from `.handoff-steer.md.prev`. If a prior handoff in this episode consumed the sidecar to `.prev`, the next handoff within `V11_STEER_PREV_GRACE_SECS` seconds re-bakes from the fresh `.prev` to keep the steer intact. Higher values = longer episode window; lower values = stricter one-shot semantics. Read at `scripts/handoff:1781`. |
| `V11_SPAWN_LATCH_SECS` | 120 | v11.37 W1-T5 documented (was silent). Duplicate-spawn idempotency latch window (integer seconds — 0 disables). If two `--spawn` invocations of the same project fire within this window, the second is refused as a duplicate (unless `--spawn-anyway`). Prevents accidental double-Zeus-window launches. Read at `scripts/handoff:2455-2460`. |

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
| `V11_TASKCREATE_DEDUPE` | `advisory` | v11.37 W1-T5 documented (was silent). **Tri-state**, NOT binary: `off` = dedupe disabled entirely, TaskCreate always creates; `advisory` (default) = detect duplicates, log a WARN, still create; `on` = detect and refuse (`exit 2`). Read at `hooks/sync-tasks:782`. Advisory keeps historical behavior while surfacing false-duplicate patterns; strict `on` protects sensitive projects from accidental re-creation. |

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
| `V11_REVIEW_CROSS_PROJECT_CHECK` | on | v11.37 W1-T5 documented (was silent). Gates the cross-project review scope guard in `hooks/lib/common.sh:3705,3920` — when on, well-formed review entries with cross-project paths are rejected (silent per site comment); `=off` restores permissive behavior across project boundaries. Behavior-significant for cross-project review workflows. |

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
| `V11_ACTIVE_PROJECT_OWNER` | on | v11.35.6 #15-F2: No liveness check on Tier-2 global active-project; any session can read another's binding |
| `V11_ATTRIBUTE_BY_PATH` | on | v11.35.6 #15-F3: Reverts to active-project fallback for NON_PROJECTS paths in track-autonomy (restores the self-work leak) |
| `V11_HANDOFF_STRICT` | on | v11.35.6 #30: No provenance warning when counters come from a different session |
| `V11_PROJECT_NAME_GUARD` | on | v11.35.6 #15-F4: No character validation on metadata.project in sync-tasks |

## V11.16 — Durable Ledger

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LEDGER_CUTOVER` | on | Aggregate is NOT replayed from ledger; legacy fold path used |
| ~~`V11_CANCELLED_FILTERS_REPLAY`~~ | ~~on~~ | **HISTORICAL — documented for release-notes clarity; NEVER made it into code.** grep confirms 0 reads across `scripts/`+`hooks/` (v11.37 W1-T4 doc-downgrade fix for ticket #43). Improvement #17's cancelled-events-open-view fold is UNGATED — no rollback lever exists. If a user needs to disable #17's behavior at runtime, see ticket #48 (v11.38 candidate) which proposes wiring the lever properly with a paired cutoff timestamp so a toggle doesn't retroactively unfold historical cancelled events across the entire ledger. |
| `V11_RISK_TEXT_MASK` | on | v11.35.4 improvement #25: `=off` restores raw-text risk classification — prose inside commit-message heredocs/quotes trips HIGH patterns again. Masking is consulted only to re-test a raw HIGH hit and bails to raw on any structural doubt. |
| `V11_CUTOVER_ACCEPT_CORRECTION` | **off** | v11.35.2 improvement #24 — ENABLE knob, not a rollback: set it to the EXACT project name (`=HAM`, never `=on` — refused) to let ONE rebuild of THAT project pass BOTH cutover count floors when a correction legitimately shrinks counts (logged `reason:"correction-authorized"`). Project-scoped per adversarial finding #3 so a leaked flag cannot authorize other projects. Per-invocation only. |

## Full Disable Recipe

To revert to V11.16 behavior (pre-review, pre-handoff-hygiene):
```bash
export V11_AUTO_PAIR_REVIEW=off V11_SELF_REVIEW_REQUIRED=off V11_DAAO_ROUTING=off
export V11_REVIEW_ENFORCEMENT=off V11_REVIEW_NUDGE=off
export V11_FOLD_FAMILIES=off V11_DISCIPLINE_DETECTOR=off V11_COMPLETION_HINT=off
export V11_HANDOFF_REVIEW_FILTER=off V11_WAVE_CHECK=off
```
