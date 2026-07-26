# V11 Protocol Changelog

> **This file is the source of truth for V11 version history.** Every version bump adds its
> full entry HERE, newest first — NOT into CLAUDE.md. CLAUDE.md §17 carries only a one-line
> "Current: v11.X" pointer, so the protocol doc stays lean in every subagent's context (every
> non-Explore subagent loads CLAUDE.md). Enforced by `scripts/check-changelog-drift` (soft-block
> in both `scripts/run-tests --regression` and `--regression-extended`): it fails on inline entries in CLAUDE.md §17 OR a Current
> version missing from this file. For rollback env vars, see [ROLLBACK_REFERENCE.md](ROLLBACK_REFERENCE.md).

---

## v11.34 — Session-Aware Write-Gate — 2026-07-20

Closes `improvements/13-write-gate-session-aware.md` (field report, session `comedic-study` + 4-agent recon swarm) and absorbs `improvements/12-spawn-contract-gaps.md` §H2. Root cause: `guard-write-gates` blocked the first honest edit of a fresh session in a task-bearing project — a session that never touched the task system reads identically to a genuine stall, so the gate punished the standard "spawn/handoff into a project that already has tasks from another session" path. The blocked actor structurally could not satisfy the gate (its remedy is session-scoped; the gate's signal is project-scoped), so it routed around it — via Bash-heredoc (this field report) or by editing the task-state JSON to pass and reverting it (the improvement-12 incident). Both escape hatches were ungated and audit-invisible.

**F1 — Fresh-vs-stall discriminator**: `guard-write-gates` now distinguishes a session that has never engaged the task system (no per-session task-state file) from a genuine stall (a session that HAD a task in_progress and let all its tasks lapse). Fresh sessions — and sessions that have *finished* all their own work — are **allowed through** with a once-per-session stderr advisory naming the open-task count (from the project aggregate) and the remedy. Only a session carrying its own unfinished work (`pending + in_progress ≥ 1`) still `exit 2` under the default. This also subsumes improvement-12 §H2: a subagent's session likewise carries no per-session task-state, so it now reads as fresh (advisory) instead of unsatisfiable (block) — the tampering incentive it created is closed at the root, not patched at the symptom.

**F3 — `V11_WRITE_GATE` knob**: `block` (default, unchanged stall behavior) | `warn` (downgrades the stall block to advisory, never exits 2) | `off` (disables task-state enforcement entirely). The `total<2` and completed-project exemptions are unconditional either way.

**F4 — Observable Bash-write bypass**: `guard-enforcement` now emits a non-blocking stderr warning when a Bash command performs a source-file write (heredoc `<<`, `>`/`>>` redirect, `tee`, `sed -i`, `dd of=`) in a task-bearing project, plus a best-effort synthetic audit row for attribution. This closes a previously-silent, undocumented bypass of the Write/Edit audit trail (verify-syntax, attribution) — the escape hatch the field-report incident actually used. Gated by `V11_BASH_WRITE_WARN` (default on); disabling only silences the warning, it was never a block.

**Doc coherence (F5)**: `docs/ENFORCEMENT.md`, `CLAUDE.md` §13, `docs/PROTOCOL_FUNDAMENTALS.md`, `docs/AGENT_TEAMS.md` (deleted a dead V11.11-era ownership-block claim), `docs/ROLLBACK_REFERENCE.md`, and the `improvements/` index corrected to describe the shipped fresh-vs-stall behavior instead of the old flat "advisory" or "blocks ownership" mislabels.

Commits: 6c32e29 (F1+F2+F3), 7afd3fa (merge), 914ccd4 (F4), 814280b (merge), 030ba87 (spec). Rollback: `V11_WRITE_GATE=warn|off`, `V11_BASH_WRITE_WARN=off`.

**v11.34.1 — same-day post-ship review remediation.** Three adversarial reviewers (hook correctness, consumer-surface coherence, orchestrator workflow integration) audited the merge. Fixed: **Q2** (finished-wave false block — the discriminator keyed on "ever touched a task" so a session that *completed* all its own tasks re-hit the stall block whenever sibling sessions had pending work; now keys on the session's own open work `pending+in_progress≥1` via `v11_session_has_open_work`), **Q4** (fresh advisory throttled to once-per-session), **Q3** (open-task count read from the aggregate, not `handoff-tasks.json`; remedy leads with "create+start a task", `/v11` made conditional), **Q5** (F4 narrowed — dropped the command-substitution heredoc match that false-warned on `git commit -m "$(cat <<EOF)"` / `gh pr create`, and exempted `v11_is_metadata_file` targets + atomic `.tmp` writes). Commits bd1c1d5, ccaab60; verify fixtures 9/9 + 14/14, regression 17/17. **Known limitation (deferred → improvement 14):** *multi-session aggregate masking/misattribution* is pre-existing and unfixed — because `guard-write-gates` and `track-autonomy` read the project aggregate, a sibling session's `in_progress` masks the gate for every other session AND mis-stamps their edits onto the sibling's `task_id`/`agent_id` (counted against an innocent agent by `agent-scorecard`). Needs a session-scoped gate+attribution signal. "v11.34 shipped" ≠ "multi-session attribution is trustworthy."

**v11.34.2 — session-scoped write-gate + attribution (improvement 14).** Resolves the T4 limitation above. `guard-write-gates` now reads THIS session's own `.in_progress` for the block decision instead of the project aggregate (`guard-write-gates:136` → `v11_session_state_path`), so a sibling session's active task no longer masks a genuine stall for everyone else. `track-autonomy` now attributes an edit to the session's OWN active task/agent (`track-autonomy:207` → session file), falling back to `null` — a sibling's `task_id`/`agent_id` is never borrowed, so `agent-scorecard` stops blaming the wrong agent. Single-session behavior is unchanged (aggregate ≡ session when there's one session); the only new blocking is a session neglecting *its own* created-but-unstarted tasks (satisfiable). Downstream (`agent-scorecard` keys on `agent_id`, `audit-query` treats `task_id` as an honest denominator) verified compatible with null attribution. Commits 48f6436 (F1), 107388a (F2), 6b81f1e (spec); verify fixtures 12/12 + 3/3, regression 17/17. No stamp sweep (patch keeps anchor 11.34).

## v11.33 — Lossless Sync Fallback + Test-Isolation Hardening — 2026-07-17

Closes the sync-tasks silent lost-update gap (found via adversarial audit session v11-active-project-drift; BugG root-cause). On >`V11_SYNC_TASKS_LOCK_TIMEOUT` (default 10s) FD-201 contention, sync-tasks proceeded unserialized and a concurrent same-session completion write could be silently dropped from the per-session scratch (reproduced: 4 racers → completed=3, one task stuck in_progress). The durable ledger was never lossy (own FD-207 lock); only the scratch — which `scripts/handoff` reads — drifted. **Fix (design (c)+(d)-lite, adversarially reviewed, 4 findings remediated)**: (d)-lite narrows the FD-201 hold to end at the last STATE write (release before the aggregate rebuild; `V11_SYNC_NARROW_HOLD=off`); (c) raced writers append a marker line (subject capped 500ch, O_APPEND-atomic) + artifacts to per-task atomic sidecars, drained exactly-once by the next locked call AND by session-end (backstop for a race on the session's last TaskUpdate) via `v11_apply_reconcile_markers`; replays the V11.21 sibling `pending_parent→pending` flip and `task_artifacts`; STR advisory counter is a documented accepted loss (`V11_SYNC_SCRATCH_RECONCILE=off`); `scripts/handoff` prefers the ledger-derived aggregate when a `.needs-reconcile` marker is present. Commits: dbda947 (fix), 535ba83 (test-isolation sweep: 26-module HOME-leak fix + conftest real-plans-dir leak detector + xdist timeout hardening), e3994cd (track-autonomy rotation keep-count byte-derived — was rotating on every hook call, 13,876 micro-archives). Tests: +17 incl. genuinely-concurrent race tests with deterministic readiness barriers (holder-acquired + all-racers-in-fallback confirmed before release; no sleep-tuning). Full suite green.

## v11.32 — Half-Wired Loop Audit — 2026-07-15

Closes improvements/11 (5-lane audit, 3-agent interference review, waves risk-ordered by activation risk). **H1**: git-event hooks layer (v11.25) activated for the FIRST time anywhere — installer names corrected in docs (W0-1), scaffold git-inits + auto-installs both hooks with compliance Gate 15 (W2-5), canary install caught 2 latent BASH_SOURCE symlink bugs (W2-4b) and review-drain caught a third (installers now resolve `--git-common-dir` so worktree installs land where git reads hooks). Existing-project backfill stays user-triggered. **H2**: routing fields get their first reader — `agent-scorecard --routing` override-rate rollup (79.3% divergence surfaced; completion-row double-count fixed in drain). **H3**: guard-effort revived (`Task|Agent` matcher — dead since the Agent rename) + tab-collapse field misalignment fixed with per-field jq reads (W3-3). **H4**: review-queue-maintenance gains flock across read-backup-rewrite (W2-1) and is wired into the review-cadence wrapper after the daemon (W2-2) — queue GC finally scheduled. **H5**: `V11_AUTO_REHYDRATE` code-enforced in `scripts/v11-resume-tasks` (was doc-only 6×). **M1**: `scripts/ledger-verify` cold-path verdict-hash verification (36/36 OK live; never in the replay fold). **M2**: auto-pair review siblings stamped `scope:"small"` — criterion #3 pair_N pollution closed (re-measured live post-boot: PASS). **M3**: two-tier regression — `--regression` = deterministic fast core (17 tests, <30s), `--regression-extended` = full suite (`-m "not benchmark"`, ~2,500 tests); first-ever full run surfaced 24 pre-existing slow-tier failures (all outside the default tier) → W4-1 triage. **M4/M5/L1/L2**: prompt-level levers labeled honestly, ledger-archive + review-queue-maintenance in SCRIPTS.md, unattributed-findings count in `scripts/status`, backfill tool header note.

## v11.31 — Pre-Scope Actuation + Two-Source Token Capture — 2026-07-15

Closes the dead v11.29 pre-scope loop end-to-end. Spec: `improvements/10-prescope-actuation.md` (21 tasks, session v11-prescope-alignment).

**Honest detection (S1-A1/A2)**: sync-tasks warns on missing/invalid `metadata.scope` on work tasks (review-sibling/blocker exempt; `V11_SCOPE_WARN=off`) and on multi-deliverable description smells — conjunction / 3+ runbook steps / >600 chars non-small (`V11_PRESCOPE_SMELL=off`). Kills the self-labeling dependency: before this, only 13% of tasks carried scope and the v11.29 advisory had never fired in production.

**Visible signal (S1-B1/B2)**: fired advisories emit a PostToolUse `hookSpecificOutput.additionalContext` envelope — the orchestrator model now SEES them in the TaskCreate tool result (`V11_PRESCOPE_CONTEXT=off`; dogfood-verified live in the shipping session). Each firing also lands as a status-neutral `ev:prescope` durable-ledger row with reason code, plus a replay fold branch preventing counter inflation (`V11_PRESCOPE_LEDGER=off`).

**Dispatch consumption (S1-C1/C2/C3)**: new read-only `scripts/prescope-check PROJECT [TASK_ID]` (exit 11 = split-before-spawn, replicates the S1-A1 exemption asymmetry), wired into orchestrate.md Phase 4 dispatch filter + task-patterns.md; `scripts/status` gains `Pre-scope: X% scoped, N advisories open` (`V11_PRESCOPE_STATUS=off`).

**Two-source token capture (S1-D1..D7)**: root cause of the inert v11.29 token ledger — track-agents probed hypothesized snake_case fields; real harness payloads are camelCase (`totalTokens`). Fixed with camelCase-first probing. Async spawns expose no usage at hook time, so the orchestrator records `artifacts.tokens` from completion-notification usage at the closing TaskUpdate (orchestrate.md §4e Rule 9); agent-scorecard merges both sources deduped by (project, task_id) with source-labeled capture rates, and `scripts/token-baseline` snapshots before/after (pre-rollout baseline: 0.22% capture, median 140k).

**Playbook alignment (S1-E1/E2)**: 4 playbook↔tooling mismatches fixed (prescope wording, agent-recommend precedence over spec.md roster, token-economy carve-out xref, TaskList carve-out); all 121 task-template example rows now carry owner/scope/complexity.

Tests: +6 advisory, +6 context/ledger, +14 scope/smell, +23 prescope-check, +11 scorecard tokens, +8 token capture; test_ledger_wiring fixtures updated for the ev:prescope era (found by a supplementary agent run — the file sits outside the run-tests manifest, gap noted). Known deferred: scope-adoption ≥90% measurement (criterion #3) next session; run-tests manifest backfill.

## v11.30 — Review-Loop Structural: Layer A Actuation + Verdict Fold-Back — 2026-07-11

W5 of `improvements/07-v1129-alignment.md` (specs: `improvements/08`, `improvements/09`) + production-readiness swarm fixes.

**Layer A actuation (W5-T15)**: self_review absence is now actuated, not just nudged — completion-hint suggests the self_review postamble; sync-tasks appends a synthetic `missing_self_review` `lite_self` row (LOW) on reviewable completion without one, symmetric with the malformed-payload guard. Rollback: `V11_SELF_REVIEW_ACTUATE=off` (independent of `V11_SELF_REVIEW_NUDGE` — gates de-nested in prod-fix). KEY FIND: the V11.22 reviewable gate had never fired (post-fold STATE read + tab-collapse in TSV join) — both latent bugs fixed; Layer A "compliance near-zero" was largely instrumentation that couldn't see.

**Cross-session verdict fold-back (W5-T16)**: drained review verdicts land in the durable ledger as `ev:"review"` events (status-neutral, counters-free replay) with full verdict JSON in `~/.agent-metrics/review-verdicts/{project}/` (sha-addressed, `verdict_ref`/`verdict_sha` on the queue done event). New CLI: `review-queue mark-done PROJECT TASK_ID [SEV] [SESSION] [--verdict-file FILE]`. Identity recovery for prior-session/wiped tasks via ledger scan; `identity_unresolved` flag beats dropping. Rollback: `V11_REVIEW_LEDGER=off`. Validated in production the same session by a live mid-session TaskList wipe: all 5 verdicts folded with zero loss.

**v11-coherence skill (W5-T17)**: L6 ledger gate keys on V11 markers (spec.md/.task-state.json) not dir mtime (kills 46 false LEDGER_MISSING); dual-lens reliability note (single-scanner clean bills are not clean bills).

**Production-readiness swarm (5 lenses) found + fixed**: case-sensitive severity derivation in `--verdict-file` (lowercase "critical" recorded as NONE — INV-3 poison); `V11_SELF_REVIEW_ACTUATE` nested inside NUDGE gate; phantom `ev:review` records inflating counters via realign; verdict-store same-second filename collisions; `check-stamp-drift` anchor polluted by merge-commit subjects (`--no-merges`); replay keying collision for identity-unresolved reviews; silent CLI exit on dangling `--verdict-file`.

Known deferred: fold-back data is write-only in the replay aggregate (nothing projects `last_review_*` into dashboards yet) — follow-up noted in `improvements/09`.

## v11.29 — Concurrency Lanes, Pre-Scoped Tasks, Token Ledger, Worktree Default — 2026-07-10

Closes the 4 gaps from the 2026-07-10 operator review + user notes. Spec: `sessions/v11-improvements/spec.md`.

**Lane lease** (concurrent-session task-execution guard, mirrors review-queue ownership):
- `v11_lane_claim/release/force_release/gc/status` in `hooks/lib/common.sh` — store `~/.agent-metrics/lanes/<project>.jsonl`, flock fd 209, append-only, steal only from not-live holders. Rollback: `V11_LANE_LEASE=off`.
- sync-tasks auto-claims on `TaskUpdate(in_progress)` with "LANE CONFLICT" stderr advisory (never blocks), releases on `completed`.
- `scripts/lanes` CLI (status/gc/release [--force]) + Phase 4 dispatch-filter clause + dashboard "Lanes:" line (orchestrator skill).

**Pre-scoped tasks**: decomposition moved from spawn time to TaskCreate (skill rule 21 rewritten; task-patterns §Pre-scoping discipline); sync-tasks advisory fires on `metadata.scope=large` or complex/novel without `metadata.deliverable_of`. Rollback: `V11_PRESCOPE_ADVISORY=off`.

**Token ledger**: `dispatch-trace-append --tokens/--tool-uses/--duration-ms/--event completion`; track-agents defensive usage passthrough to usage.jsonl (never fabricates); avg-tokens/spawn column in agent-effectiveness + agent-scorecard (omit-when-absent). Rollback: `V11_TOKEN_CAPTURE=off`. Lean-agent spike: `spec-implementer-v11-lean` (~68% token cut/spawn, contract-parity checked; rollout pending user decision).

**Worktree default**: editing spawns default to `isolation:"worktree"` (skill rule 20 + orchestrate + context-tiered-mode); guard rails first — `scripts/worktree-sweep` (dry-run/--apply sweep + `verify` exit-code contract 0=CLEAN_MERGED/10=UNCOMMITTED/11=UNMERGED/12=GENERATED_ONLY/2=UNKNOWN), CLOSE-checklist sweep step, gotcha docs (silent-edit-loss, Task-tool cwd quirks, main-tree diff checks). Rollback: `V11_WORKTREE_DEFAULT=off` (docs-level policy).

**Bug fixes** (scout-found, pre-existing): session liveness misjudged sessions writing only to subdirs (`.heartbeat` touch in sync-tasks); review-queue GC default now derived as 2× liveness window (was silently divergent 15/30); 4 worktrees leaked since 2026-07-01 cleaned; untracked-dirs porcelain bug in sweep classification; lint-test-honesty P1 in lane test.

Tests: ~90 new across 8 suites; full regression 20/20 + drift + honesty-lint green. Dual live validation: real token traces captured for this sprint's own spawns; lane machinery exercised by the concurrent sessions that built it.

## Backfilled from CLAUDE.md §17 (v11.24–v11.28) — 2026-07-01

## v11.28 — Handoff Steering Prompt

Closes the longest-standing handoff gap: the orchestrator could never put a single word into the *first message* of a spawned session — the continuation prompt was 100% derived from disk state (task-state / session-summary / plan-context) and immutable once assembled, with no `--steer`/`--message`/positional/env override anywhere. Worse, `--spawn` doesn't even reuse that bash `$PROMPT`; `spawn-claude-window.py::build_bootstrap_prompt` re-reads `handoff.md` and synthesizes its own terser <1500-char bootstrap, so there are **two independent prompt-builders**. **Fix routes through the one shared artifact both read — `handoff.md`.** Two input paths: sidecar file `sessions/<project>/.handoff-steer.md` (primary — the orchestrator Writes it losslessly, no shell-quoting of multi-line text) and `--steer "TEXT"` flag (convenience); **file wins** if both, stderr warns. The steer lands in `handoff.md` between `<!-- v11-steer-start -->`/`<!-- v11-steer-end -->` markers (OUTSIDE the Quick Resume code fence so steer content can't break fence extraction), is prepended into bash `$PROMPT` (so stdout/`--copy`/`--file` manual-paste carries it too), and is extracted + placed by the python bootstrap immediately after `/v11\n\n` — `/v11` stays the leading slash-command token so auto-rehydrate still fires; the steer is the first instruction, ahead of the mechanical state pointer. **Consume-and-clear**: the sidecar is baked into `handoff.md`, archived to `.handoff-steer.md.prev`, then removed — one-shot steering never leaks into a LATER handoff (same discipline as the V11.25.1 stale-summary archive). **Safety** (the spawned window runs `--dangerously-skip-permissions`, so steer is trust-elevated): both layers strip ANSI/control bytes incl. bracketed-paste terminators (`\x1b[201~`) and neutralize the literal steer markers; capped at 2000 chars; `--json` mode exits before steer logic (safe no-op, preserves the file). **Dual-layer reviewed** (V11.21): Layer-B adversarial pass returned PASS with 1 MED + 2 LOW — E1 a crafted steer containing the literal end-marker could forge a span boundary and inject a fake `## Quick Resume`/field lines the bootstrap parser reads → strip marker literals + anchor structural-section search past the steer-end marker; E2 a steer with a fake `- Progress:` line shadowed bootstrap stats (steer lives inside the fenced `$PROMPT`) → parse fields from `rfind("## Current State")` (the REAL heading is always the LAST occurrence since steer is prepended; first-occurrence `find` was defeated by steer containing the heading); E3 a test off-by-one. All fixed + pinned with 2 new regression tests. Rollback: `V11_HANDOFF_STEER=off` (also skips file consumption). Files: `scripts/handoff`, `.claude/hooks/spawn-claude-window.py` (live host file — `~/.claude` is unversioned), `.claude/skills/handoff/SKILL.md` (live), `tests/test_handoff_steer.py` (14 tests). 14/14 steer + 78/78 handoff-cluster green, honesty-lint clean.

## v11.27 — Ledger Integrity (six half-wired loops)

Closes six half-wired control loops in the tracking substrate — where an artifact/sensor was generated, incremented, or read but the matching consume/reset/validate/write half was never built. Spec at `sessions/v11-ledger-integrity/spec.md` (impl-grade spec `pm/v11-ledger-integrity-spec.md`); recon = two waves (13 agents) + 3 adversarial lenses. **Core principle: mechanize acknowledgment, not actuation** — surface/read halves are mechanized (safe); every mutate half stays gated, propose-only, or default-off. Live confirmation at sprint start: sofly `.retro-counter == 791` (>15× the >50 flywheel-broken threshold). **(T2) Retro flywheel flock + sanity guard** — `hooks/session-end` wraps the retro read-increment-write in an fd-201 flock (200=task-state, 202=aggregate; 201 collision-free) so concurrent CLOSEs can't lose a write; `scripts/status` prints `⚠ retro flywheel likely broken` when counter>10×`V11_RETRO_THRESHOLD`. No auto-reset. Rollback `V11_RETRO_SANITY_GUARD=off`. **(T3) A4 dead-gate legibility** — `v11_check_risk` (`common.sh:1056`) auto-approves A4 high-risk only on a `high_risk_history` match, but nothing ever appends to it (`any([])==false → return 2`): a silent always-block. `track-autonomy` + `scripts/status` now warn when level≥4 and history empty. Zero behavior change. **A characterization test pins the current empty→block `return 2`** (via `v11_check_risk`, not `v11_check_autonomy` which delegates high-risk) as the deliberate landing gate for any future writer. Rollback `V11_A4_DEADGATE_WARN=off`. **(T1) S1 DETECT reconcile surface** — `hooks/detect-project` emits one read-only `v11_detect_reconcile` JSON block (zombie/discipline + review-queue + fold-families + retro-counter) consolidating four unsurfaced signals; new `v11_fold_manifest_read`/`v11_retro_counter_read` wrappers with `[ -f ]` guards. **Strictly non-mutating** — reads the existing discipline log rather than invoking the writer (adversarial-review M1 fix). Hook count stays 17 (no new hook). Opt-in `V11_DETECT_RECONCILE` (default off). **(T5) Enqueue unknown-attribution trace** — `v11_review_queue_add` admits `agent_id=="unknown"` (a legit orchestrator/bg-agent fallback), adds a `trace` field, emits a WARN — never rejects; Rules A/B unchanged. Rollback `V11_RQ_TRACE_UNKNOWN=off`. **(T6) Propose-only fold-reconcile** — new `scripts/lib/family_fold.py::propose_merge()` + `scripts/fold-reconcile` CLI: `--dry-run` default proposes a merge only when family_size>1 ∧ identical `subject_norm` ∧ identical sprint (absent-sprint families skipped — adversarial-review L1); `--apply --confirm` appends append-only `reconcile scope=identity` ledger events (SKIPPED+WARN on append failure, not silent inflation — M2). Never runs in hooks/DETECT. Rollback `--dry-run` default + `V11_FOLD_RECONCILE=off`. **(T4) CUT to a design spike** (`sessions/v11-ledger-integrity/T4-spike.md`) — an A4 history writer is not safely feasible as scoped (MATCHED_PATTERN duplication, no pre→post hook signal, unreliable `caller_kind`); spike reframes the fix as "detect blocked-then-executed" instead of "detect human." **Dual-layer reviewed** (V11.21): Layer-B adversarial pass found 2 MED + 1 LOW, all fixed and re-verified. Tests: +830 lines across 9 files (T2 6, T3 9, T1 SC1/SC2, T5 SC7, T6 7×SC8); `--regression` 20/20 + honesty-lint clean; affected classes green serially. All five levers default to the safe state.

## v11.26 — Handoff State Machine Extraction + Test-Honesty Lint

Stops the V11.25.x handoff-bug whack-a-mole loop (10 fixes in 5 weeks) by naming and enforcing the invariants. Spec at `sessions/v11-handoff-invariants/spec.md`. The V11.25.2 retro and backfill review independently flagged "silent state-machine failures in auto-emit hooks — source attribution must be baked in" as the recurring pattern; V11.26 bakes it in. **(1) Handoff confidence state machine extracted to typed Python** (`scripts/lib/handoff_state.py`, 250 lines, stdlib only): four enums (`SessionSummarySource`, `StateSource`, `LedgerSource`, `HandoffDecision`), two exceptions (`ProtocolViolation`, `UnhandledHandoffState`), `resolve_decision()` pure function + `main()` CLI. Bash now subprocesses the module via JSON IPC at scripts/handoff:1407-1456 (replacing the V11.25.2 inline case block). `_CONF_DECISION="UNKNOWN"` is statically unreachable — Python raises `UnhandledHandoffState` instead. Invariants enforced at runtime: I1 decision always in declared enum, I2 raw inputs raise ProtocolViolation, I3 unhandled tuples raise UnhandledHandoffState, I4 AUTHORITATIVE implies empty downgrade_reasons, I5 non-canonical summary sources always contribute `session_summary_not_from_disk`. Graceful degradation on subprocess failure (loud stderr + skip artifact + handoff.md still builds). **(2) Hypothesis property tests** (`tests/test_handoff_state_invariants.py`, 26 tests, 200 examples each, `derandomize=True` for CI stability): I1–I9 + C1 (CLI subprocess output parity vs direct Python) + C2 (exit codes 0/1/2). All 5 `SessionSummarySource` enum values exhaustively parametrized. **(3) Test-honesty lint** (`scripts/lint-test-honesty`, AST + regex hybrid, <2s on the suite, wired into `scripts/run-tests --regression` as a soft-block): four patterns — P1 stderr-subtraction (V11.25.2 5d3492d), P2 disjunctive-decision-assert (5d3492d), P3 bare `_run()` followed by negative-only asserts (5d3492d), P4 bash case-without-`*)`-default (the V11.25.x root pattern). Initial run flagged 19 violations; AST refinement of P3 narrowed to 5 real issues. Two were T7-E4 hits my V11.25.2 sprint missed (`test_handoff_hygiene.py:161,478` — `_run()` followed by `assert not …`). Three were P4 in `scripts/handoff` (autonomy-name lookup, decision warning case, handoff-category banner) — all gained explicit `*)` defaults. Final state: 0 lint violations. Rollback: `V11_LINT_TEST_HONESTY=off`. **(4) 5-state dogfood matrix** (`tests/integration/test_handoff_5state_dogfood.py`, 9/9 PASS): end-to-end tests for each `SessionSummarySource` state (`missing`, `written`, `stale-replaced`, `stale-unarchived`, `synthesized`) running real `scripts/handoff` against fixtures, parsing `.handoff-confidence.json`, asserting decision + downgrade_reasons. Surfaced **V11.26.1 finding F-STALE-REPLACED-IS-STUB** (LOW): the stub regen elif branch at `scripts/handoff:660` writes the fresh stub but never sets `SESSION_SUMMARY_IS_STUB=1`, so `stale-replaced` resolves to `AUTHORITATIVE` instead of `AUTHORITATIVE-WITH-CAVEATS` — a stale-replaced stub masquerades as a human-written summary in the confidence artifact. Test asserts the current bug behavior with fail-loudly maintainer instructions so the V11.26.1 fix has a built-in landing gate. Tests: 26/26 (`test_handoff_state_invariants`) + 9/9 (`test_handoff_5state_dogfood`) + 38/38 V11.25.x regression (`test_handoff_stale_summary` + `test_handoff_hygiene`) = 73/73 PASS. Falsifiable durability bet (spec success criterion #6): the next handoff-edge-case bug must surface as a Python exception in CI or a lint failure, NOT a silent incorrect downgrade in production. If V11.27 ships another silent-fall-through patch in untyped bash, this sprint failed its goal.

## v11.25.2 — V11.18 Backfill Review Findings

Three surgical fixes carved from the V11.18 sprint adversarial-lite review backfill (9 historical tasks reviewed in parallel, 2026-06-19; report at `sessions/v11-handoff-hygiene/reviews/backfill-2026-06-19.md`). All three are the same "could-have-shipped-V11.25.1's-bug" pattern — silent state-machine failure precursors in code paths adjacent to the stale-summary work. **(1) `scripts/handoff` `_CONF_DECISION` extended for non-canonical summary sources** (T6-E1 MED HIGH-conf): the case statement only handled `STATE_SOURCE ∈ {per-session, aggregate}` and silently fell to `_CONF_DECISION="UNKNOWN"` whenever `SESSION_SUMMARY_SOURCE` landed on `stale-replaced` (archive succeeded but stub regen <30 chars) or `synthesized` (inline fallback at L960). New `_SS_NONCANONICAL` signal drives `PER-SESSION-NO-DISK-SUMMARY` (per-session branch) and `AUTHORITATIVE-WITH-CAVEATS` (aggregate branch with ledger). `.handoff-confidence.json` gains `session_summary_source` field + `session_summary_not_from_disk` downgrade_reason. Companion T6-E2 LOW: warn-only stale path (`NO_STUB_FLAG` or `V11_STUB_SUMMARY=off`) now sets `SESSION_SUMMARY_SOURCE="stale-unarchived"` instead of leaving `missing` — the file-exists branch was then promoting to `written` and masking the known-stale state. **(2) `hooks/completion-hint` METRICS_DIR guard** (T4-E2 MED HIGH-conf): the hook runs under `set -u +e` and references `$METRICS_DIR` at L63 with no guard. If `common.sh` ever fails to export it (minimal env, lazy init, source partial-failure), `set -u` would error fatally with no observable signal — indistinguishable from "no active task". Added `[ -z "${METRICS_DIR:-}" ] && exit 0` immediately after `source common.sh`. Companion T4-E1 LOW: in `V11_COMPLETION_HINT_DEBUG=1` mode, the L91 exit when `_FILE_TOKS` is empty now emits a stderr line explaining "no tokens >=4 chars from basename" so operators can distinguish silent skips. **(3) `tests/integration/test_handoff_hygiene.py` test-honesty cluster** (T7-E1 HIGH + T7-E2/E3/E4 MED): the V11.18 sprint shipped four false-green test patterns identical in shape to the cluster V11.25.1 just fixed in `test_handoff_stale_summary.py` (commit b135c71). T7-E1: L297 `second.stderr.replace(first.stderr, "")` subtraction trick — split into two direct `not in` assertions. T7-E2: L483 `test_authoritative_when_clean` accepted 3 disjunctive decision values (`{AUTHORITATIVE, PER-SESSION, LEGACY-AGGREGATE}`); fixture seeds only the aggregate, no V11_SESSION_ID, so the resolver MUST deterministically pick `AUTHORITATIVE` — assertion tightened. T7-E3: L205 `_run([str(DISC_SCRIPT), "p1"], env)` lacked `bash` prefix used everywhere else. T7-E4: 3 negative T2 tests at L224/L235/L249 called `_run(...)` without capturing rc; silent crashes passed vacuously. All gain `rc = _run(...)` + `assert rc.returncode == 0, rc.stderr`. Tests: 27/27 (`tests/integration/test_handoff_hygiene.py`) + 11/11 (`tests/test_handoff_stale_summary.py` regression) + 95/95 across handoff-hygiene + stale-summary + family-fold + handoff-corruption sweep. No rollback env-vars needed — all three fixes are pure additive correctness; no new toggle surface. Convergent signal with V11.25.2 backfill retro (`retros/2026-06-19.json`): both reviews independently flagged "silent state-machine failures in auto-emit hooks — source attribution must be baked in" as the recurring pattern.

## v11.25.1 — Drift-Sweep Follow-ups + Stale Handoff Summary

Closes the V11.25.0 F1 drift sweep follow-up list (3 LOW items, sweep score 2/10) plus a separately-discovered handoff staleness bug. **(1) DC1 coherence anchor regex `-iE`** (`v11-coherence` skill DC1 anchor): mixed-case `v11.X.Y` tokens now match alongside `V11.X.Y`. **(2) Three undocumented hooks added to §13** in this file: `require-producer-script` (Pre Bash), `completion-hint` (Post Write/Edit), `guard-stale-task` (Post TaskList) — row count 14→17; wiring re-verified against `settings.json` before write. **(3) Strategy 1.6 stderr marker** (`hooks/sync-tasks:201`): silent V11.24 rare-path resolution now emits `[v11.24-strategy-1.6]` marker carrying resolved project + task_id + session_uuid so the ledger-task-home fix is observable. 5/5 Strategy 1.6 tests pass (commits dc6db17 + d0ee144). **(4) Stale `.session-summary.md` detection + session-end ordering** (commit c8b6234): live failure 2026-06-19 — v11-sharpening's auto-generated handoff embedded a 60-day-old April session summary into a fresh Zeus spawn. Two cooperating root causes: (a) `scripts/handoff` treated any existing `.session-summary.md` as canonical with no freshness check (once written, authoritative forever); (b) `hooks/session-end` auto-emitted `handoff.md` BEFORE writing `last-session.json`, so the auto-emit read the prior session's enrichment fields. Fixes: `scripts/handoff` now archives stale summary to `.session-summary.md.prev.md` (recoverable) and regenerates a fresh stub when summary mtime exceeds `V11_STALE_SUMMARY_GRACE_SECS` (default 86400s) OR `task-state.json` is >1h newer; `hooks/session-end` extracts the auto-emit into `_v11_auto_emit_handoff` function and invokes it AFTER `last-session.json` is written. Dogfood live: v11-sharpening's 1431h-old April summary archived, fresh stub written, visible stderr WARN. Rollback: `V11_STALE_SUMMARY_CHECK=off`, `V11_STALE_SUMMARY_GRACE_SECS=N`, `V11_SESSION_END_REORDER=off`. Tests: +8 (`tests/test_handoff_stale_summary.py`). Cross-project ledger contamination in v11-sharpening's `recent_completed` surfaced as a side observation — pre-V11.24 historical drift, separate scrub.

## v11.25.0 — Discipline Mechanization + V11.21 Producer Completion

Three-strand discipline closure plus hygiene burst. **(1) Post-commit task-close hook** (`hooks/post-commit-close-tasks`) fires on git post-commit, matches `^S\d+(-prep)?-T[A-Za-z0-9]+:` in HEAD subject, appends idempotent `status_changed` events with `caller_kind="hook"`, `commit_sha`, `matched_pattern`, `hook_version` audit fields. Multi-task subjects (`S55-T2,T3:` / `S55-T2 + T3:`) close all referenced tasks. The reference project's canary chain-installed via `scripts/install-postcommit-hook` (Strand H added symlink-detection + md5-verified chain-wrapper to avoid write-through clobbering tracked source like that project's S50-T4 advisor). Catch-22 with linter resolved: HYPOTHESIZED commits with `Pairs: T<id>` exclude those task IDs from auto-close, keeping unmeasured-claim work-tasks open across iterations. **(2) Validation tag linter** (`hooks/lib/validation_lint.py` + dual-surface PreToolUse Bash matcher + commit-msg hook) enforces Lens 4's `Validation: HYPOTHESIZED|DRY-RUN|MEASURED-LIVE-PARTIAL|LIVE` tag. HYPOTHESIZED requires an open paired-task ID resolved via the durable ledger. `(verb ∧ number)` heuristic WARNs on missing tag without false-positiving chore/docs commits. Lens 4's "until linter ships" get-out-of-jail clause cleared in `agents/adversarial-lite-reviewer.md`. **(3) V11.21 auto-pair producer completion** — the marquee dual-layer review feature was *theatrical*: `hooks/sync-tasks` read `metadata.review_of`/`review_task_id` but no code path created the pair. Adoption measured at 0-1.5% across sampled projects. Now `sync-tasks` TaskCreate branch auto-synthesizes a sibling review task when (a) `V11_AUTO_PAIR_REVIEW != off`, (b) parent `complexity ∈ {medium, complex, novel}` OR `risk ∈ {medium, high}`, (c) parent has no existing `review_task_id`. Sibling enters with `pair_<n>` namespace (counter-based `_v11_pair_seq` reservation; no collision with Claude Code native int IDs), `metadata.review_of=parent_id`, `parent_status=pending_parent`. Existing activation code at line 848+ transitions `pending_parent → pending` on parent completion. Dogfood verified live (`pair_1` synthesized for complex task in an internal environment). Discovered + fixed `. as $root` jq operator-precedence trap during impl. **Hygiene burst**: `sessions/v11-sharpening/spec.md` rewritten to V11.24 reality (80→88L, V11.8 original archived), `handoff.md` 83→48L (drops manual rehydration block — V11.17 owns it), `MEMORY.md` 223→179L (27 over-length entries trimmed to ≤200-char hooks, V11.11-reform archived, partial-load resolved), 2 stale `__autonomy-grant-selftest-*` dirs cleared. F1 drift sweep score 2/10 (data plane solid; 3 LOW/MED follow-ups carved to V11.25.1: DC1 coherence anchor regex case-insensitivity, 3 undocumented hooks need §13 rows, Strategy 1.6 stderr marker). Rollback: `V11_POSTCOMMIT_AUTOCLOSE=off`, `V11_POSTCOMMIT_DRYRUN=on`, `V11_VALIDATION_LINT=off`, `V11_VALIDATION_LINT_STRICT=off` (default warn-only), `V11_VALIDATION_LINT_HEURISTIC=off`, `V11_AUTO_PAIR_REVIEW=off`. Tests: +107 hook tests (post-commit 37 + validation-lint 70 post-polish) + 10 auto-pair + 7 install-helper = +124 net.

## v11.24 — Session-Bind Drift Fix (Strategy 1.6)

Closes the misroute class surfaced live during the engine.example.com wiring-finish session on 2026-06-05: detect-project (V11.18+) binds each Claude Code session to the first project it sees and suppresses cross-project drift — a safety feature. But when a session was bound to project A (e.g. inherited from a stale `active-project` file) and the user issued `TaskCreate(metadata.project=B)`, the create events landed in B's ledger via Strategy 1 (explicit metadata) — but subsequent `TaskUpdate(completed)` calls without an explicit `metadata.project` fell through the old Strategy 1.5's `.project` fallthrough and resolved to A, silently misrouting every completion event + its artifacts + counters_delta. Fix: split Strategy 1.5 into 1.5a (`.open_tasks[id].metadata.project` only — no fallthrough) and 1.5c (the deferred `.project` fallback), and insert new **Strategy 1.6 ledger-task-home**: when 1.5a misses, scan `~/.agent-metrics/ledger/*.jsonl` for a `created` event matching `(session_uuid, task_id)` — a unique pair within a Claude Code session — and resolve PROJECT to that event's `.project`. Strategy 1.6 also captures `subject_norm` + `create_seq` from the same match so the downstream identity-resolution ladder doesn't fall through to LEDGER-IDENTITY-MISS (TaskUpdate payloads don't carry a subject, so Step 3's subject-based fallback can't fire). Rollback: `V11_LEDGER_TASK_HOME=off`. Cost: one grep + jq per ledger file (~100-200 files; early-out on grep miss). Only fires when Strategies 1 and 1.5a both miss — never on hot path.



## v11.23.0 — Handoff Cross-Project Scope Leak Fix (2026-06-01)

Fully fixes the handoff cross-project scope leak (bug report `reports/bug-handoff-cross-project-scope-leak-20260601.md`, severity HIGH, blast radius every multi-project user). Smoking gun: `handoff-tasks.json` for `atlas-terminal` contained 19 open tasks, only 4 legitimately for that project (21%). The other 15 belonged to portfolio, eigen-opus, and music-corpus projects whose contributing Claude sessions had `active-project=atlas-terminal`.

This release lands a **three-layer fix** absorbing all uncommitted handoff-hygiene strands from the past week (5/29 `handoff-accuracy` W1/W2/W3 + 6/01 AM `guard-stale-task` from the swarm-studio audit + 6/01 PM Layer 1 jq filter):

**Layer 1 — handoff aggregate filter (softened V11.23):** `scripts/handoff` jq blocks at lines ~1141 and ~1456 filter `open_tasks_by_session` by `metadata.project`. Today's first pass dropped null-metadata tasks too aggressively; V11.23 softens to accept (`metadata.project == $PROJECT` OR null), safe because Layer 3 ensures null-metadata tasks only land in $PROJECT.json when their session legitimately was for $PROJECT.

**Layer 2 — `_proj` per-task stamp at TaskCreate/Update (W1, originally 5/29):** `hooks/sync-tasks` stamps each task with a hook-resolved project on `TaskCreate` and `TaskUpdate(in_progress)` events, gated on `V11_HANDOFF_LIVE_RECONCILE=on`. Stamps ONLY when source is authoritative (metadata or task-own-record); skips when ambient-project-fallback. Plus W1 live-snapshot writer + W2 Zeus spawn fixes + W3 gate substance check + HANDOFF_CATEGORY banner (TO_BUILD / PAUSED_EXTERNAL / PAUSED_USER / RESUME).

**Layer 3 — per-task aggregate routing (NEW V11.23):** `hooks/lib/common.sh::v11_rebuild_project_aggregate` replaces the per-session V11.15.5 Bug-H quarantine with finer-grained per-task routing. Each task `t` from session `s` belongs to aggregate $P iff:
- `t.metadata.project == $P` (explicit, cross-session safe), OR
- `t.metadata.project` is null/missing AND `s.project == $P` (legacy fallback).

Applied uniformly to `open_tasks_by_session`, `recent_completed`, `blocked_tasks`, `active_task_ids`, `recommended_agents`, `task_artifacts`. Open counters (pending/in_progress/blocked) recomputed from filtered set; `completed` only contributed by sessions where `session.project == $project` (avoids cross-project over-count; under-counts slightly for cross-project sessions — accepted residual). `aggregated_from` filtered to sessions that actually contributed ≥1 task (mirrors Bug-H outcome at per-task granularity). Single session now contributes to **multiple** project aggregates correctly.

**`scripts/reconcile-aggregates`** — NEW one-shot maintenance script. Walks `$TASK_STATE_DIR/*.json`, classifies each task as clean/unstamped/mismatch. `--dry-run` reports JSON; `--apply` triggers `v11_rebuild_project_aggregate` for affected projects. Re-runnable, idempotent.

**Gate 14 — Handoff scope integrity (NEW):** in `scripts/v11-compliance-check`. Reads `sessions/$PROJECT/handoff-tasks.json` if present; verifies every emitted task's `metadata.project` is $PROJECT (or null/legacy-OK). WARNs on foreign-project mismatch.

**W4 cleanup (today, from 5/29 W3 adversarial review):** E1 `BLOCKED=0` guard on TO_BUILD HANDOFF_CATEGORY branch; E2 softened PAUSED_USER banner copy; E4 +2 regression tests.

**`hooks/guard-stale-task` (from swarm-studio audit §H9):** new PostToolUse:TaskList advisory hook. Detects zombie pattern (in_progress task with recent file-edit audit activity but no completion event). 60-min cooldown, max 3 alerts. Rollback: `V11_GUARD_STALE_TASK=off`.

**Empirical validation:**
- `scripts/reconcile-aggregates --project atlas-terminal --verbose`: 16 clean, 23 unstamped, 0 mismatch — the 23 null-project tasks now get routed AWAY on rebuild.
- 12 lying tasks (real portfolio tasks with explicit `metadata.project=atlas-terminal`) are not auto-detectable — bug report acknowledges this requires manual reconciliation.

**Five rollback levers (each independent):**
- `V11_TASK_ROUTE_BY_METADATA=off` — Layer 3 reverts to V11.15.5 per-session quarantine.
- `V11_HANDOFF_LIVE_RECONCILE=off` — Layer 2 stamp + snapshot writer disabled.
- `V11_HANDOFF_CATEGORY=off` — category banner + blocker surfacing disabled.
- `V11_GATE_SUBSTANCE=off` — gate substance check (unedited stub detection) disabled.
- `V11_GUARD_STALE_TASK=off` — zombie-task advisory hook disabled.

**Test additions:** `tests/test_v11_23_layer3_routing.py` (12 tests); `tests/test_handoff_context.py` (+2 W4 regression); `tests/test_zeus_spawn_fixes.py` (W2). **Modified:** `tests/test_sync_tasks_per_session.py::test_misstamped_session_excluded_from_aggregate` updated to V11.23 substantive contract; dropped now-irrelevant "Bug H quarantine" stderr assertion.

**Lineage:** Closes bug-H residual from V11.15.5 → V11.16 (durable ledger) → V11.17 (smooth handoff) → V11.18 (handoff hygiene) → V11.19 (review enforcement) → V11.21 (dual-layer review). This release is the LAYER below those: the underlying aggregate data plane is now per-task-routed, removing the structural source of cross-project contamination.

---

## v11.21.0 — Agent Routing & Dual-Layer Review (2026-05-23)

V11.20 made every layer's errors attributable but left two structural breaks open: (1) only 5 of 113 agents saw real use (97% of attributed errors landed on `spec-implementer-v11`; the 43 spec `## Agents` tables were theater because TaskCreate never read them), and (2) V11.19's deferred review queue failed in dogfood — 22 completions sat un-drained until backfill. V11.21 closes both by baking dual-layer review into the task lifecycle and routing every Phase 4 spawn through DAAO.

**Layer A — self-review** (executor's hand): the implementing agent emits `{severity, errors[]}` JSON in its own `TaskUpdate(completed)` payload at `metadata.artifacts.self_review`. Cheap (~500 tokens in-context), forces articulation at completion, attributes to the executor directly. **Layer B — adversarial-lite** (independent hand): the orchestrator skill pairs a sibling review task at Phase 4 TaskCreate (`metadata.review_of=parent_id`, `metadata.parent_status=pending_parent`, `metadata.agent=adversarial-lite-reviewer`). On parent completion, `sync-tasks` flips the sibling `pending_parent → pending`. The reviewer reads parent's `files_changed + metadata.artifacts + metadata.artifacts.self_review` and writes its verdict to ITS OWN `metadata.artifacts.review` — never to the parent. V11.20 attribution traverses `metadata.review_of` to find the originating agent. Layer A is made falsifiable by the **calibration miss counter** (INV-3): when self=NONE/LOW but adversarial=HIGH/CRITICAL on the same parent, `scripts/agent-scorecard` and `scripts/agent-effectiveness` log a `self_review_miss` and emit a calibration advisory at >50% miss rate (≥4 paired data points noise floor). Without that counter Layer A would degrade to ceremony; with it the layer is observable.

**Three rollback levers, each independent + one documented coupling:** `V11_AUTO_PAIR_REVIEW=off` (no paired review tasks; V11.19 queue path remains functional), `V11_SELF_REVIEW_REQUIRED=off` (self_review absence not tracked; agents may still emit), `V11_DAAO_ROUTING=off` (Phase 4 reverts to `spec-implementer-v11` for tasks WITHOUT `metadata.agent`; explicit `metadata.agent` is ALWAYS honored). **Coupling:** when `V11_AUTO_PAIR_REVIEW=on`, sync-tasks suppresses V11.19 enqueue for tasks whose parent has `metadata.review_task_id` set (O(1) lookup via the forward link the orchestrator sets at pair time — no TaskList scan). Per-task mutual exclusion, not per-project.

### Components

- **(T1) Schema migrations, additive only** — `agent-errors.schema.json` `found_by_layer` enum gains `lite_self` + `lite_adversarial` (legacy `lite` retained, aliased at read time); `task-metadata.schema.json` `artifacts` $def gains `self_review` (object: severity enum + errors array), `review_id` (≤64 char pointer), `review_task_id` (parent forward link); task-metadata gains optional `review_of`, `parent_status`, `skip_review`, `synthetic_completion`. All 37 existing V11.20 ledger entries validate against the extended schemas unchanged (STR-001). `executor_kind` added as orthogonal optional field (`self|adversarial`) — distinct from `caller_kind`.
- **(T2) `scripts/agent-recommend`** — NEW CLI. Reads `~/.agent-registry/agents.json`; `--with-scorecard` consults `agent-scorecard`. Flags: `--meta {web-app|backend-svc|cli-tool|library|integration|pipeline|realtime|agent-system|infra|data-ml}`, `--complexity {routine|medium|complex|novel}`, `--domain <str>`, `--json`. Documented JSON envelope: `{version:"1", recommendations:[{agent_id, model, category, scorecard_success_rate, scorecard_trend, reason}], fallback_used:bool, query_meta:{...}}`.
- **(T3) `scripts/wave-check PROJECT WAVE`** — INV-12 enforcement. Exits 0 when (a) all wave work tasks completed AND (b) all paired adversarial reviews completed with severity ≤ HIGH. Non-zero with structured reason: `WORK_INCOMPLETE | REVIEW_INCOMPLETE | CRITICAL_BLOCKING`.
- **(T4) `scripts/dispatch-trace-append`** + `~/.agent-metrics/dispatch-trace.jsonl` — one line per Phase 4 spawn. FD-209 flock, mkdir-p guard, 4096-byte line cap.
- **(T5-T9) Playbook rewrites** — implementation-detail invariants moved out of spec.md into playbooks: `orchestrate.md` carries DAAO routing table + pair-at-TaskCreate; `per-task-review.md` absorbs 13 invariants; `task-patterns.md` binds spec.md `## Agents` → `metadata.agent`; `interview.md` surfaces Cynefin + agent-recommend; `close.md` adds §6e per-session scorecard split by layer.
- **(T10) Self-review postamble on 8 high-usage agents** (`spec-implementer-v11`, `backend-architect`, `frontend-specialist`, `database-engineer`, `security-engineer`, `testing-engineer`, `performance-optimizer`, `ai-integration-specialist`). Remaining ~100 agents: V11.22 phased rollout.
- **(T11) `adversarial-lite-reviewer.md` v11.21.0** — required `parent_task_id` input, dual-mode contract (code-review when `files_changed` present, content-review when `files_changed=[]` + non-empty `metadata.artifacts`).
- **(T12) `hooks/sync-tasks` V11.21 branch** — `pending_parent → pending` sibling status transition on parent completion; `self_review` schema validate warn-not-fail; `metadata.synthetic_completion=true` skips ALL ledgers; O(1) V11.19 enqueue suppression.
- **(T13) Orchestrator skill Phase 4 sequence** — 3-call atomic pair-at-TaskCreate, dispatch filter excludes `parent_status==pending_parent`, startup recovery scan synthesizes missing siblings, DAAO routing via `agent-recommend`, dispatch-trace logging, wave-check gate.
- **(T14) `scripts/status`** — V11.21 grouping with plain-language summary line.
- **(T15) `scripts/handoff` review-sibling filter + `scripts/v11-resume-tasks` orphan rehydration** — pending_parent siblings dropped from `handoff-tasks.json`; orphan reviews tagged `is_review_sibling=true`.
- **(T16) `scripts/agent-scorecard` `self_review_calibration` block** — INV-3 falsifiability mechanism. Miss = self ∈ {NONE,LOW} AND adversarial ∈ {HIGH,CRITICAL}. Calibration advisory at >50% miss rate with ≥4 paired data points.
- **(T17) +56 integration tests** covering STR-001 through STR-008. Suite total: 1735 → 1791 collected.
- **(T18) Cutover** — three env var defaults already ON in code.

### Deferred to V11.22

1. Default `review_budget_per_sprint` cap (calibrates from V11.21 dogfood data)
2. Self-review postamble on remaining ~100 agents
3. Domain formations (political-pipeline, etc.)
4. Per-task multi-reviewer

### Cutover Transition Policy

Pre-cutover work tasks (completed BEFORE V11.21 shipped) are NOT retroactively paired. They flow through the V11.19 queue path which remains functional alongside V11.21.

### Dogfood Evidence

V11.21 was built using V11.21 protocol. Every reviewable sprint-02+ task carries `metadata.review_task_id` to a paired adversarial-lite-reviewer sibling.

---

## v11.20.0 — Audit & Improve Subagents (2026-05-23)

V11.19 closed the per-task adversarial-lite loop (Layer 2 attribution); V11.20 wires the remaining two review layers (wave + swarm) into the same per-agent ledger AND adds an orchestrator/subagent split to every audit event.

### Components

- **(T1) Schema extensions** — `agent-errors.jsonl` gains `found_by_layer`, `caller_kind`, `task_id_inferred`, `attribution_key`. Two NEW idempotency ledgers: `attribution-keys.jsonl` and `unattributed-findings.jsonl`.
- **(T2) Three helpers** in `hooks/lib/common.sh`: `v11_caller_kind`, `v11_compute_attribution_key`, `v11_resolve_file_to_task`.
- **(T3) `hooks/track-autonomy`** writes `caller_kind` on every audit event.
- **(T4) `hooks/sync-tasks`** stamps `found_by_layer="lite"`, `attribution_key`, optional `caller_kind`.
- **(T5) `scripts/wave-review-attribute`** — NEW. Reads wave verdict JSON, resolves file→task, attributes to executing agents.
- **(T6) `scripts/swarm-review-attribute`** — NEW. Sibling of T5 for swarm reviews.
- **(T7) `scripts/wave-review --attribute`** sub-mode.
- **(T8) `scripts/agent-scorecard`** — NEW. Single-agent deep dive across all 4 layers with caller-kind split.
- **(T9) `scripts/agent-effectiveness`** extended with `--layer` + `--caller-kind` filters.
- **(T10-T11) `scripts/backfill-wave-findings` + `scripts/backfill-swarm-findings`** — fleet-wide historical attribution.

**Cross-path determinism** (load-bearing invariant): bash `v11_compute_attribution_key` and Python `hashlib.sha256` produce BIT-IDENTICAL keys. This is the idempotency contract for cross-layer dedup.

**Caller-kind detection caveat**: V11_SUBAGENT and V11_PARENT_SESSION_ID env vars are NEW conventions. Until the Claude Code Agent-tool launcher injects them, most events fall through to "unknown".

### Dogfood Evidence

Reviewer caught 10 real bugs across T1-T5. All fixed inline. 100+ V11.20-touched tests passing.

---

## v11.19.0 — Review Enforcement (2026-05-22)

V11.15 wired the per-task adversarial-lite review loop; V11.19 makes it actually fire. Root cause of silence: completed-without-review was byte-identical to completed-with-review — sync-tasks silently no-op'd.

### Components

- **(T1) Per-project review queue** at `~/.agent-metrics/review-queue/$PROJECT.jsonl` — append-only JSONL with `pending`/`done` events.
- **(T2) `scripts/review-queue`** CLI: `pending`, `stats`, `list`, `mark-done`, `all-pending`.
- **(T3-T4) `sync-tasks` enqueue/mark-done** on `TaskUpdate(completed)` transitions.
- **(T5) `detect-project` nudge** on first Read per session per project.
- **(T6) `scripts/handoff` confidence integration** — pending reviews downgrade AUTHORITATIVE label.
- **(T7) `scripts/backfill-reviews`** — one-shot scan for historical completions missing reviews.
- **(T8) `scripts/drain-review-queue`** — orchestrator dispatch helper.
- **(T9) `scripts/agent-effectiveness` cleanup** — filters zero-task agents.
- **(T10-T11) Orchestrator skill + tests** — 38 tests, all passing.

### Dogfood Evidence

22 historical tasks backfilled, 3 adversarial-lite reviews drained against the V11.19 code itself.

---

## v11.18.0 — Handoff Hygiene (2026-05-22)

V11.17 closed the UX gap; V11.18 closes the four integrity gaps that V11.17 assumed were upstream-clean but in dogfood (claude-trader-pro) were not.

### Fixes

- **(T1) Token-overlap family fold** — Jaccard ≥ 0.25 OR overlap ≥ 0.45 clusters near-duplicate task subjects.
- **(T2) Discipline detector** — flags in_progress tasks with recent file-edit audit activity.
- **(T3) One-shot TaskList nudge** — surfaces likely-shipped tasks.
- **(T4) Write/Edit completion-hint hook** — suggests task completion when edited file matches task subject.
- **(T5) Addendum slot** — `.handoff-addendum.md` prepended above auto-generated handoff.
- **(T6) AUTHORITATIVE label downgrade** — requires ledger_source=ledger AND zero stale-in_progress AND zero folded families.
- **(T9) Family-aware rehydration** — one TaskCreate per family with `metadata.family_size`.

Tests: 42 unit + 23 integration; zero regressions.

---

## v11.17.0 — Smooth Handoff (2026-05-20)

The V11.16 durable ledger fixed every structural handoff bug; V11.17 closes the UX gap on top of it. Five additive levers:

1. `scripts/handoff` auto-writes a structured `.session-summary.md` stub when missing (quality floor 30 bytes)
2. `session-end` hook auto-emits `handoff.md` + `handoff-tasks.json` (mtime <60s guard)
3. `detect-project` surfaces "[V11] N open task(s) in handoff" on first Read per session
4. `post-compact` adds "Handoff waiting" line when applicable
5. `/v11` Phase 1 step 1a.5 auto-rehydrates TaskList from `handoff-tasks.json` when empty

Full contract: [docs/HANDOFF_SMOOTH.md](HANDOFF_SMOOTH.md).

---

*Prior versions (v11.16 and earlier) documented in session archives and git history.*
