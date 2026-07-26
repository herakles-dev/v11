# V11 Protocol — Open-Source Distribution Manifest

**What this is**: A complete partition of every asset in `~/v11` (source version **v11.34.0**,
2026-07-20 per `VERSION.md`) into CORE / OPTIONAL / EXCLUDE, produced for the Claude Partner
Network application's public V11 release. This supersedes `~/opensource-staging/v11-starter-pack/`,
which was a hand-picked, partial teaching extract (6/24 hooks, 2/19 schemas, 0/98 scripts, no
installer, organized into 7 "modules": task-system, hooks, formations, autonomy, sessions, agents,
scaling). This manifest classifies **everything** on disk instead of a curated subset, so gaps are
visible rather than silently absent.

**Date**: 2026-07-26.

**Bucket definitions** (from the brief):
- **CORE** — required for the V11 loop to function on someone else's machine: task system, write
  gates, task sync, handoff, autonomy tracking, review loop.
- **OPTIONAL** — genuinely useful and transferable, but not required to run (benchmarking,
  scorecards, memory indexing, formations, etc.).
- **EXCLUDE** — welded to this server (hardcoded paths/domains/ports/services), dead/experimental,
  or bulky generated artifacts.

Not counted in any table below (out of the requested scope, noted here for completeness):
`swebench-repos/` (1.4G — pre-excluded per the brief), `swebench-predictions/` (1.4M, generated),
`swebench-full-run.log`, and every `__pycache__/` directory (compiled bytecode, ~360K combined,
build artifacts that should be `.gitignore`d, not shipped).

---

## 1. Hooks (`~/v11/hooks/` — 24 entries)

`git-hooks/` and `lib/` are each counted as one row (containing the installed git-event hook
copies and the shared bash/Python library, respectively) — that is how the raw `ls hooks/` listing
reaches 24; see Open Questions §4 for the exact accounting.

| Asset | Bucket | Justification | Weld to fix (file:line or —) |
|---|---|---|---|
| `commit-msg-validation` | OPTIONAL | Git-surface `Validation:`-tag linter (shares validator with guard-validation-lint). Genuinely useful empirical-rigor discipline, but task-sync/write-gates/handoff/autonomy/review-loop all work without it. | `hooks/commit-msg-validation:4,6` (install-path comments — parameterized to a generic `/path/to/v11/hooks` example) |
| `completion-hint` | OPTIONAL | Advisory-only nudge to mark a task completed after a matching edit. Never blocks; pure UX sugar. | — |
| `detect-project` | CORE | Sets the active-project context every other hook/script keys off of; without it per-project task state can't resolve. | — (inherits `V11_WORKSPACE_ROOT` default via `hooks/lib/common.sh:5`) |
| `enforce-subagent` | EXCLUDE | CLAUDE.md's own §13 "Dormant hook scripts" list says this is **not wirable as shipped** — it warns once per open task on every spawn because the Agent payload carries no `task_id` to correlate against. Documented as broken, not just unused. | — |
| `enforce-test-coverage` | OPTIONAL | Blocks deploy-shaped commands under a coverage threshold. A specific quality gate, not one of the six required loop primitives. | `hooks/enforce-test-coverage:14` (`SESSIONS_ROOT` default) |
| `fix-team-model` | EXCLUDE | Its own header: *"DEPRECATED (V11.11): TeamCreate-based formations replaced by per-task agent assignment... exits immediately."* Dead code, kept only as a no-op safety net for a mechanism V11 no longer uses. | `hooks/fix-team-model:84` (moot — dead code path) |
| `git-hooks/` (dir: `commit-msg` symlink + `post-commit` shim) | OPTIONAL | The actual installed copies git executes (created by the two `install-*-hook` scripts). Convenience wiring for optional commit-time discipline; not required for the Claude-Code-side loop. | `hooks/git-hooks/post-commit:4,6` (install-path comments — parameterized to a generic `/path/to/v11` example) |
| `guard-agent-stall` | OPTIONAL | Advisory-only stalled-background-agent detector. Monitoring/QoL, loop functions without it. | — |
| `guard-effort` | OPTIONAL | Advisory-only effort-level suggestion for Task dispatch. Never blocks. | — |
| `guard-enforcement` | CORE | The write-gate risk + autonomy-grant enforcement engine — this **is** "write gates" and "autonomy tracking" from the required list. | — (inherits via `hooks/lib/common.sh:5`) |
| `guard-stale-task` | OPTIONAL | Advisory zombie-task (in-progress-but-abandoned) detector, companion to `handoff-discipline-check`. Useful drift signal, not required for function. | `hooks/guard-stale-task:54` (`SESSIONS_ROOT` default) |
| `guard-teammate-timeout` | EXCLUDE | CLAUDE.md's own "Dormant hook scripts" list: *"superseded by `guard-agent-stall`; kept for reference."* Confirmed dead. | — |
| `guard-validation-lint` | OPTIONAL | Bash-side `git commit` validation-tag linter. Discipline feature, not one of the six required primitives. | — |
| `guard-write-gates` | CORE | Literally "write gates" — blocks Write/Edit without an in-progress task; the exact mechanism the brief names. | — |
| `lib/` (dir: `common.sh`, `get-chicago-time.sh`, `validation_lint.py`) | **CORE (needs parameterizing)** | `common.sh` is `source`d by nearly every hook (project detection, task-state I/O, lane leasing). Remove it and every CORE hook breaks. | `hooks/lib/common.sh:5` (`V11_WORKSPACE_ROOT="${V11_WORKSPACE_ROOT:-$HOME/.v11}"`); `hooks/lib/get-chicago-time.sh:6` (`METRICS_DIR` default + hardcoded America/Chicago business timezone) |
| `post-commit-close-tasks` | OPTIONAL | Auto-closes tasks from commit-subject patterns. Convenient git-integration for task sync, but `TaskUpdate` calls already close tasks with zero git-hook dependency. | — |
| `post-compact` | OPTIONAL | Re-injects V11 state after context compaction. Valuable continuity aid, but the on-disk task-state loop is unaffected by whether this hook runs. | — |
| `refresh-freshness-tags` | OPTIONAL | CLAUDE.md's own "Dormant" list: opt-in only since it mutates files. Cosmetic doc-freshness feature. | — |
| `require-producer-script` | OPTIONAL | Blocks commits shipping unverifiable validation artifacts. Narrow empirical-rigor discipline, not one of the six primitives. | — |
| `session-end` | CORE | Implements "handoff" — Stop hook that saves the session summary and triggers auto-handoff. | — |
| `sync-tasks` | CORE | Literally "task sync" — the 184KB backbone writing task-state, review queue, durable ledger, and attribution on every TaskCreate/Update/List. | — |
| `track-agents` | OPTIONAL | Agent metrics + escalation logging; feeds scorecards/benchmarking (explicitly an OPTIONAL category). | — |
| `track-autonomy` | CORE | Literally "autonomy tracking" — updates trust metrics + audit log on every Write/Edit/Bash. | — |
| `verify-syntax` | OPTIONAL | Post-write syntax check, advisory-only, never blocks. | — |

**Hooks tally**: CORE 7 · OPTIONAL 14 · EXCLUDE 3 (= 24)

---

## 2. Schemas (`~/v11/schemas/` — 19 files)

| Asset | Bucket | Justification | Weld to fix |
|---|---|---|---|
| `agent-effectiveness.schema.json` | OPTIONAL | Backs the `agent-effectiveness` dashboard — scorecards/benchmarking, explicitly OPTIONAL. | — |
| `agent-errors.schema.json` | CORE | Shape of the per-agent verdict/error record the review loop attributes findings to (README: *"errors attributed to the executing agent in agent-errors.jsonl"*) — this **is** review-loop output. | — |
| `agent-registry.schema.json` | OPTIONAL | Validates `agents/V11_AGENT_REGISTRY.json` (the OSS agent roster + doc-gen source), not the task/gate/handoff/autonomy/review mechanics. | schema `$id` — already parameterized to a bare filename (no domain) |
| `attribution-keys.schema.json` | OPTIONAL | V11.20 four-layer attribution refinement layered on top of the review loop, not the loop itself. | — |
| `autonomy-audit.schema.json` | CORE | The audit-trail schema for "autonomy tracking." | — |
| `autonomy-state.schema.json` | CORE | Shape of `.autonomy-state` — persisted A0–A5 grants; core of "autonomy tracking." | — |
| `dispatch-trace.schema.json` | OPTIONAL | Phase-4 spawn-record tracing for the attribution/analytics layer. | — |
| `formation-config.schema.json` | OPTIONAL | Formations — explicitly named OPTIONAL example. | — |
| `formation-registry.schema.json` | OPTIONAL | Formations — same. | — |
| `guard-blocks.schema.json` | CORE | Own description: *"a write blocked by guard-write-gates"* — direct write-gate artifact. | — |
| `memory-index.schema.json` | OPTIONAL | Memory indexing — explicitly named OPTIONAL example. | — |
| `module-manifest.schema.json` | OPTIONAL | MODULE.md/MODULE.json contract validation — documentation-hygiene feature, not required to run the loop. | — |
| `plan-context.schema.json` | **CORE (already parameterized)** | Backs `plan-sync`, which `sync-tasks` and `session-end` (both CORE) auto-invoke per CLAUDE.md §12 — a load-bearing dependency of two CORE hooks. | `schemas/plan-context.schema.json:3` (`$id` — already a bare filename, doesn't affect validation) |
| `review-config.schema.json` | **CORE (already parameterized)** | Own description: *"Controls the post-task adversarial-lite review loop"* — the review loop's config contract. | `schemas/review-config.schema.json:3` (`$id` — already a bare filename) |
| `session-manifest.schema.json` | CORE | Session bootstrap manifest — backs handoff/session continuity. | — |
| `task-metadata.schema.json` | CORE | The task system's own schema (largest at 25KB) — defines TaskCreate/Update metadata shape. | — |
| `task-state.schema.json` | CORE | Shape of `task-state.json`, written by `sync-tasks` — direct "task sync" artifact. | — |
| `tool-policy.schema.json` | **OPTIONAL (verify before shipping)** | Backs a 4-layer tool-policy resolution chain that `guard-enforcement`'s own header says was **removed** in V11.11 ("native agent `tool_profile` handles it"), yet `resolve-policy` and `formation-quality-benchmark` still call `v11_resolve_tool_policy()` in `common.sh`. Live-but-unused-in-the-hot-path, or genuinely dead — see Open Questions §1. | `schemas/tool-policy.schema.json:3` (`$id` — already a bare filename) |
| `unattributed-findings.schema.json` | OPTIONAL | Attribution-system edge case (findings that can't be pinned to an agent) — refinement layer, not the loop itself. | — |

**Schemas tally**: CORE 9 · OPTIONAL 10 · EXCLUDE 0 (= 19)

---

## 3. Scripts (`~/v11/scripts/` — 96 executable scripts + `lib/` support library)

The brief said "98." The actual on-disk count is 96 real scripts + a `lib/` subdirectory (12
Python support modules) + a `__pycache__/` build-artifact directory. I've counted `lib/` as one
additional row (97 total) and excluded `__pycache__` entirely as a non-asset; see Open Questions §3
for why "98" doesn't cleanly reconcile.

| # | Asset | Bucket | Justification | Weld to fix |
|---|---|---|---|---|
| 1 | `agent-effectiveness` | OPTIONAL | Per-agent effectiveness dashboard reading review-loop ledgers — scorecard/benchmarking (explicitly OPTIONAL). | `:30` `V11_WORKSPACE_ROOT` default |
| 2 | `agent-recommend` | EXCLUDE | Reads `~/.agent-registry/agents.json` — an origin-deployment-specific agent registry that lives outside `~/v11` entirely and isn't part of this release. Meaningless without that external file. | external dependency, not a literal path string |
| 3 | `agent-scorecard` | OPTIONAL | Per-agent deep-dive across all 4 audit layers — scorecard/benchmarking. | `:33` `V11_WORKSPACE_ROOT` default |
| 4 | `archive` | OPTIONAL | Moves a completed session to archive — session housekeeping, not required for the loop to run. | `:13` |
| 5 | `athenaeum-search` | EXCLUDE | Hardcodes an internal RAG-service URL (`http://localhost:<port>`) and a `Remote-User: user@example.com`-style auth header — a bridge to an origin-deployment-only Athenaeum RAG service. | `:7,28,66` |
| 6 | `audit-codebase` | OPTIONAL | Orchestrates a multi-agent codebase audit — audit tooling, not a loop primitive. | `:8` |
| 7 | `audit-query` | CORE | CLI for the autonomy audit trail — the queryable half of "autonomy tracking." | `:17` `V11_WORKSPACE_ROOT` default |
| 8 | `autonomy-grant` | CORE | Persists explicit A4/A5 autonomy grants to `.autonomy-state` — directly "autonomy tracking." | `:20` |
| 9 | `backfill-agent-errors-task-id` | EXCLUDE | Own header: *"HISTORICAL: one-shot INV-3 join-key backfill, already executed 2026-07-01. Do NOT re-run."* Dead for any new install. | — |
| 10 | `backfill-reviews` | OPTIONAL | One-shot enqueue of completed tasks with no recorded review verdict — reusable reconciliation utility for upgraders. | — |
| 11 | `backfill-swarm-findings` | OPTIONAL | Same category — swarm-attribution backfill. | — |
| 12 | `backfill-wave-findings` | OPTIONAL | Same category — wave-attribution backfill. | — |
| 13 | `check-changelog-drift` | OPTIONAL | Guards CLAUDE.md's own changelog-pointer discipline (wired into `run-tests --regression`); reusable pattern, tuned to this repo's own doc structure. | — |
| 14 | `check-improve-subagent-triggers` | OPTIONAL | Trigger detection for the self-improvement flywheel (`improve-subagent`). | — |
| 15 | `check-stamp-drift` | OPTIONAL | Checks version-stamp consistency across V11's **own** `agents/V11_AGENT_REGISTRY.json`, README.md, VERSION.md, CLAUDE.md — useful to whoever maintains this fork, not a consumer's own project files. | — |
| 16 | `cloudflare-setup` | EXCLUDE | Every domain it touches is a `*.example.com`-style origin-deployment domain — sets up a Cloudflare tunnel for that deployment's own infra. | `:13,43-309` (throughout) |
| 17 | `context-status` | OPTIONAL | Heuristic context-window usage estimator — diagnostic. | — |
| 18 | `create-formation-registry` | OPTIONAL | Formations (explicitly OPTIONAL category). | `:71,82` |
| 19 | `deploy` | EXCLUDE | Hardcodes a `<port-registry>.json` + a `~/.secrets/<origin-deployment>.env`-style lookup — this *is* the origin deployment's production-deploy script. | `:13,25,27,59,69,106,115` |
| 20 | `dispatch-trace-append` | OPTIONAL | Atomic JSONL writer for Phase-4 spawn/attribution records — analytics layer. | — |
| 21 | `drain-review-queue` | CORE | Orchestrator dispatch helper for the review queue — directly "review loop." | — |
| 22 | `effort-advisor` | OPTIONAL | Suggests an effort level for a task — advisory companion to the (OPTIONAL) `guard-effort` hook. | — |
| 23 | `findings-to-spec` | OPTIONAL | Converts audit findings into a V11 spec — audit-flywheel tooling. | `:8` |
| 24 | `flywheel-ingest` | OPTIONAL | Findings-back-into-framework ingestion — same audit flywheel. | `:20` |
| 25 | `fold-reconcile` | OPTIONAL | Propose-only reconcile for "folded" task families under V11.29 concurrency lanes — maintenance for an advanced/optional feature. | `:27` |
| 26 | `formation-heartbeat` | OPTIONAL | Health polling for active formations (OPTIONAL category). | `:160` |
| 27 | `formation-quality-benchmark` | OPTIONAL | Explicit benchmark (FQB); also calls the possibly-vestigial tool-policy resolver (see Open Questions §1). | — |
| 28 | `formation-select` | OPTIONAL | Formation recommender (OPTIONAL category). | `:18` |
| 29 | `generate-agent-roster` | OPTIONAL | Generates CLAUDE.md §14 from `agents/V11_AGENT_REGISTRY.json` — docs-gen convenience for the (OPTIONAL) roster file. | `:5,6` |
| 30 | `handoff` | CORE | Generates session-continuation context — this **is** "handoff." | `:39` (`:919` is an illustrative comment only, not functional) |
| 31 | `handoff-discipline-check` | OPTIONAL | Detects handoff-discipline violations (T2/T3) — an audit layer on top of handoff, not the mechanism itself. | `:32,37` |
| 32 | `hook-metrics` | OPTIONAL | Hook performance dashboard — benchmarking. | — |
| 33 | `improve-subagent` | OPTIONAL | Self-improvement / meta-agent-tuning flywheel tool. | `:42` |
| 34 | `index-project-memory` | OPTIONAL | Memory indexing (explicitly OPTIONAL category). | `:29,30` |
| 35 | `install-postcommit-hook` | OPTIONAL | Installs the git post-commit auto-close convenience; task sync already works via direct `TaskUpdate` without any git hook. | `:237,238` (hardcoded absolute fallback path, not env-overridable) |
| 36 | `install-review-cadence` | OPTIONAL | Installs a nightly cron for `review-daemon`; the review loop runs fine manually (`review-queue`/`task-review`) without this cadence. | — |
| 37 | `install-validation-lint-hook` | OPTIONAL | Installs the commit-msg validation-tag hook. | `:275,276` (same hardcoded-fallback pattern) |
| 38 | `interview-recommend` | OPTIONAL | Evidence-backed architecture/methodology recommender. **Verified in source**: degrades gracefully to pure-bash Cynefin/decomposition advice when Athenaeum is unreachable — not hard-welded. | `:49` (Athenaeum reachability check, optional enhancement only) |
| 39 | `lanes` | OPTIONAL | CLI for the V11.29 concurrency-lane lease — advanced scaling feature, not required for a single-session loop. | — |
| 40 | `ledger-archive` | OPTIONAL | Segments completed-sprint history out of the live ledger — scale-maintenance. | `:46` |
| 41 | `ledger-shadow-report` | OPTIONAL | Gate-1 instrument for the (already-completed) V11.16 shadow-reconciliation rollout — historical migration aid, still generically usable. | — |
| 42 | `ledger-verify` | CORE | Cold-path verdict-hash verification across the durable ledgers backing both task sync and the review loop. | — |
| 43 | `lint-test-honesty` | OPTIONAL | V11.26 test-honesty lint pass — quality/rigor discipline, not a loop primitive. | `:38,218` |
| 44 | `maintain-memory-index` | OPTIONAL | Memory indexing (explicitly OPTIONAL category). | `:22,23` |
| 45 | `migrate-ledger` | OPTIONAL | Idempotent ledger-migration seed (ADR-LEDGER §5) — safe-to-run-anytime upgrade utility. | — |
| 46 | `migrate-to-v11` | EXCLUDE | Migrates from V5/V7/V8/V9/V10 — none of those predecessor protocol versions exist in this OSS release; nothing to migrate from. | `:18` |
| 47 | `migrate-v10` | EXCLUDE | Migrates a V10 project to V11; V10 isn't part of the OSS release. | — |
| 48 | `migrate-v8` | EXCLUDE | Migrates V8→V10 (not even to V11) and literally `sed`-rewrites `/path/to/v8/hooks/` → `/path/to/v10/hooks/` — doubly irrelevant, doubly welded. | `:14,63` |
| 49 | `plan-resume` | OPTIONAL | Scans `~/.claude/plans/` for V11 plan files — a Plan-Mode convenience, not auto-invoked by anything CORE. | `:13` |
| 50 | `plan-sync` | CORE | CLAUDE.md states `sync-tasks` and `session-end` (both CORE) call this automatically — a load-bearing dependency. | `:15` |
| 51 | `prescope-check` | OPTIONAL | Read-only advisory flagging tasks that look like they need splitting before dispatch (V11.31) — advisory refinement. | — |
| 52 | `publish` | EXCLUDE | Makes a project reachable at `https://{project}.example.com` via nginx + a `<port-registry>` — entirely origin-deployment-infra-specific. | `:13,16,143,187,212,261,307,327,358,415,522,561` |
| 53 | `quarantine-misstamped-sessions` | OPTIONAL | V11.15.5 repair utility for misstamped sessions — reusable, not a one-time historical fix like #9. | — |
| 54 | `reconcile-aggregates` | OPTIONAL | Reconciles task/ledger aggregate drift — maintenance utility. | `:30,31` (usage examples at `:59-60` name an internal project — cosmetic only) |
| 55 | `recover-session` | OPTIONAL | Reconstructs session context after a cut-off conversation — a safety net on top of handoff, not the mechanism itself. | `:12` |
| 56 | `repair-empty-state` | OPTIONAL | Repairs corrupted/empty task state — recovery tool, only needed once something is already broken. | `:20` |
| 57 | `repair-task-state-drift` | OPTIONAL | Same category. | `:30` |
| 58 | `resolve-policy` | OPTIONAL (verify before shipping) | Debug tool for the 4-layer tool-policy chain that `guard-enforcement` says was removed in V11.11 — may be debugging a mechanism nothing enforces anymore. See Open Questions §1. | — |
| 59 | `review-daemon` | CORE | Headless review-queue consumer — the review loop's unattended execution path. | — |
| 60 | `review-queue` | CORE | CLI for the per-project adversarial-lite review queue — directly "review loop." | — |
| 61 | `review-queue-maintenance` | OPTIONAL | Normalizes + GCs the review queue — hygiene; loop functions without periodic GC, at least initially. | — |
| 62 | `rotate-metrics` | OPTIONAL | Rotates oversized JSONL metrics files — housekeeping. | — |
| 63 | `run-tests` | OPTIONAL | Runs the V11 test suite (`tests/`, itself OPTIONAL) — dev-time verification, not runtime-required. | — |
| 64 | `scaffold` | EXCLUDE | Creates a new project but bundles origin-deployment-specific docker-compose templates, `<port-registry>` auto-registration, `~/.secrets/<origin-deployment>.env`-style sourcing, and `example.com` auto-publish in one 800+-line script — not separable from this instance's infra without a rewrite. | `:13,21,22,67-99,224,296,767-839` |
| 65 | `spec-requirements-extract` | OPTIONAL | Proposes `spec_test_requirements` from spec.md — spec-quality tool. | `:15` |
| 66 | `status` | OPTIONAL | CLI view of task-system progress; the Claude-Code-native `TaskList` tool already surfaces this inside the session. | `:8` |
| 67 | `suggest-formation` | OPTIONAL | Formations (OPTIONAL category). | — |
| 68 | `swarm-review-attribute` | OPTIONAL | V11.20 four-layer attribution for swarm dispatch — refinement on top of the review loop. | `:148,165,166` |
| 69 | `swe_claude_baseline.py` | OPTIONAL | SWE-bench one-shot Claude baseline — benchmarking (explicit OPTIONAL category). | `:45,46,429` |
| 70 | `swe_claude_code_agent.py` | OPTIONAL | SWE-bench Claude Code CLI agent harness — benchmarking. | `:53-55,259,657` |
| 71 | `swe_infer.py` | OPTIONAL | SWE-bench inference engine — benchmarking. | `:43,44` |
| 72 | `swe_v11.py` | OPTIONAL | SWE-bench V11 multi-agent formation orchestrator — benchmarking. | `:66,67,1176` |
| 73 | `synthesize-findings` | OPTIONAL | Dedupes/ranks/generates an audit report from findings — audit-flywheel tooling. | `:8` |
| 74 | `task-review` | CORE | Builds the adversarial-lite-reviewer prompt for one task — this is literally how a task gets reviewed. | — |
| 75 | `team-status` | OPTIONAL | Shows active Agent Teams / formation health (OPTIONAL category). | `:5` |
| 76 | `token-baseline` | OPTIONAL | Snapshots per-agent output-token capture stats — benchmarking/analytics. | `:28` |
| 77 | `tracker-status` | OPTIONAL | Shows which tracking artifacts exist/are missing for a project — diagnostic. | — |
| 78 | `v11-benchmark` | OPTIONAL | Explicit system-level quality benchmark (Tier 0/1/2). | — |
| 79 | `v11-bootstrap-session` | CORE | Bootstraps a new V11 session/project directory structure — the entry point that gets the task system running at all. | `:18` |
| 80 | `v11-compliance-check` | OPTIONAL | Validates a project's full V11 setup — diagnostic, not required to run the loop. | `:24` |
| 81 | `v11-drift-scan` | OPTIONAL | Lightweight drift detection — diagnostic. Note: one of its checks explicitly targeted a `<port-registry>.json`, so part of this generic-looking tool was itself origin-deployment-specific — being genericized as part of this release's scrub. | `:24,26` |
| 82 | `v11-migrate-task-state` | OPTIONAL | One-time task-state schema migration for version upgraders — irrelevant to a fresh install. | `:34` |
| 83 | `v11-resume-tasks` | OPTIONAL | Convenience resume helper. | `:32` |
| 84 | `v11-retro` | OPTIONAL | Manages the per-project retrospective counter driving the "journal flywheel" — secondary feature. | `:25` |
| 85 | `v11-update` | **OPTIONAL (fixed)** | Upgrades a project's installed hooks to the latest V11 version — important for long-term maintenance but not needed for a fresh install. | `:15,88,99,108` — **was** functional, not cosmetic: three `jq` filters hardcoded the hook **source** path as literal text inside single-quoted jq programs (shell variables never expand there), so swapping in `$V11_HOME` alone wouldn't have worked. Fixed via `jq --arg cmd "$V11_HOME/hooks/..."` passing the shell-resolved value in as a proper jq variable — portable now, behavior-identical on the original machine. |
| 86 | `validate-config` | OPTIONAL | Validates project config files against the JSON Schemas — diagnostic. | — |
| 87 | `validate-invariants` | OPTIONAL | Static checker for MODULE.md invariants — part of the (OPTIONAL) module-manifest system. | `:30` |
| 88 | `validate-module-manifest` | OPTIONAL | Schema validation for MODULE.md/MODULE.json. | `:31,32,202` |
| 89 | `validate-project-setup` | OPTIONAL | Validates a project is correctly set up for V11 — diagnostic. Includes an Athenaeum-reachability check that only warns, never blocks. | `:8,9,437-440` |
| 90 | `verify-gate0` | EXCLUDE | "Sprint 0 exit gate for v11-sharpening" — checks deliverables of one specific, already-completed internal V11 dev sprint; not a reusable gate template. | `:21` |
| 91 | `verify-gate1` | EXCLUDE | Same — Sprint 1 of the same internal sprint. | `:22` |
| 92 | `verify-gate2` | EXCLUDE | Same — gates the "V11.8 release" milestone specifically. Also confirmed **orphaned**: not referenced by CLAUDE.md, README.md, or any `docs/*.md`. | `:19` |
| 93 | `wave-check` | OPTIONAL | INV-12 gate enforcement for wave-formation dispatch — advanced multi-agent-formation feature. | — |
| 94 | `wave-review` | OPTIONAL | Gathers wave output, generates adversarial review prompts for wave-based (formation) dispatch. | — |
| 95 | `wave-review-attribute` | OPTIONAL | Wave-side four-layer attribution (same category as #68). | `:142,160,161` |
| 96 | `worktree-sweep` | OPTIONAL | Classifies/cleans stale git worktrees — housekeeping for the (optional) worktree-isolation feature. | — |
| 97 | `lib/` (dir: `search.py`, `bm25.py`, `cache.py`, `normalize_subject.py`, `family_fold.py`, `handoff_state.py`, `embedder.py`, `chunker.py`, `postcommit_extract_patterns.py`, `postcommit_analysis.py`, `__init__.py`, `context_tracker.py`) | CORE (mixed) | `handoff_state.py`, `family_fold.py`, `postcommit_extract_patterns.py`/`postcommit_analysis.py`, `normalize_subject.py`, `context_tracker.py` are imported by CORE-adjacent paths (handoff state machine, post-commit task closure). `search.py`/`bm25.py`/`cache.py`/`embedder.py`/`chunker.py` are memory-indexing-only (OPTIONAL) support code shipped in the same folder — kept as one row since the split isn't filesystem-clean. | — |

**Scripts tally**: CORE 11 · OPTIONAL 73 · EXCLUDE 13 (= 97 rows; 96 real scripts + 1 `lib/` row)

---

## 4. Top-level directories (`~/v11/{agents,playbooks,templates,formations,patterns,mcp-tools,docs,examples,deep-plan,benchmarks,tests,improvements,pm,research}`)

Several directories mix CORE/OPTIONAL/EXCLUDE content internally; split into sub-rows where the
split is materially important rather than forcing one bucket per directory.

| Asset | Bucket | Justification | Weld to fix |
|---|---|---|---|
| `agents/` — review-loop set (`adversarial-lite-reviewer.md`, `adversarial-lite-fixer.md`, `adversarial-reviewer.md`, `coherence-reviewer.md`) | **CORE (already parameterized)** | These are the agents that actually execute the "review loop"; without them there's no reviewer to dispatch. | `agents/adversarial-reviewer.md:31` — was a hardcoded absolute doc link, already fixed (relative link, no residual hit) |
| `agents/` — spec-pipeline suite (`spec-planner-v11.md`, `spec-architect-v11.md`, `spec-implementer-v11.md`, `spec-integrator-v11.md`, `spec-optimizer-v11.md`, `spec-recovery-v11.md`, `spec-reviewer-v11.md`, `spec-security-v11.md`, `spec-tester-v11.md`, `V11_AGENT_REGISTRY.json`) | OPTIONAL (fixed) | A complete "V11 spec-driven dev team" agent suite — genuinely useful template, not required; the review loop only needs the four agents above. | All 10 files individually scrubbed as part of this release — see Open Questions §7 for what was found and fixed |
| `agents/.v10-archive/` | EXCLUDE | Legacy V10 agent definitions + `V10_AGENT_REGISTRY.json`, kept only for historical reference; V10 isn't part of this OSS release. | — |
| `playbooks/` (`per-task-review.md`) | CORE | Documents the per-task review process — the operational playbook for the review loop. | — (clean) |
| `templates/` — session/spec bootstrap (`spec.md.template`, `session-manifest.json.template`, `plan-context.json.template`, `gates.md.template`, `roadmap.md.template`, `state.md.template`, `architecture.md.template`, `project-settings.json`, `review-config.json`, `MODULE.md.template`, `spec-hypothesis.md.template`, `SCALING_GUIDE.md`) | CORE | Session/spec templates consumed by `v11-bootstrap-session`/`scaffold` to stand up a new project's task system. | — (clean) |
| `templates/` — infra (`docker-compose.yml.template`, `cloudflare.yml.template`) | EXCLUDE | Docker-compose against this instance's local infra + a Cloudflare-tunnel-to-`example.com` template. | — |
| `formations/` (`code-review.json`) | OPTIONAL | Formations — explicitly named OPTIONAL example. | — (updated, final content-safety pass: the original example formation was removed and replaced with a benign multi-wave code-review formation) |
| `patterns/` (`task-claiming.md`, `typescript-standards.md`, `python-standards.md`, `docker-compose-template.md`, `performance-optimization.md`) | OPTIONAL | Generic coding-pattern docs, genuinely transferable. | `patterns/docker-compose-template.md` flagged by weld sweep — review its content before shipping; other 4 files clean |
| `mcp-tools/` (`memory-search/server.py`) | OPTIONAL | Memory-search MCP server — memory indexing, explicitly OPTIONAL category. | `mcp-tools/memory-search/server.py:17,31,32` (env-var defaults, same pattern as elsewhere) |
| `docs/` — core reference (`SCRIPTS.md`, `STATE_MANAGEMENT.md`, `AGENT_TEAMS.md`, `MCP_INTEGRATION.md`, `PROBLEM_SOLVING.md`, `CHANGELOG.md`, `HANDOFF_SMOOTH.md`, `PROTOCOL_FUNDAMENTALS.md`, `FORMATIONS.md`, `ENFORCEMENT.md`, `ROLLBACK_REFERENCE.md`, `V11_22_AGENT_POSTAMBLE_ROLLOUT.md`) | CORE (fixed) | Reference docs for how the loop actually works (`ENFORCEMENT.md` documents the hooks, `HANDOFF_SMOOTH.md` documents handoff, `CHANGELOG.md` is the authoritative version history per `VERSION.md`'s own pointer). | `CHANGELOG.md`, `ENFORCEMENT.md`, `FORMATIONS.md`, `HANDOFF_SMOOTH.md`, `MCP_INTEGRATION.md` referenced a fixed operator path/domain/brand in example text — scrubbed as part of this release; the other 7 files in this row were already clean |
| `docs/` — origin-deployment-specific (`ATHENAEUM_LIBRARIES.md`, `MIGRATION_V9.0_TO_V9.2.md`, `MIGRATION_V9.2_TO_V10.md`) | EXCLUDE | Athenaeum is an origin-deployment-only service; the V9→V10 migration docs describe protocol versions not present in this release. | — |
| `examples/` (`full-session-planning.md`, `integration-testing.md`, `implementation-workflow.md`) | OPTIONAL | Illustrative walkthroughs; useful for onboarding, not required for the loop to function. | `examples/integration-testing.md` flagged by weld sweep — minor reference, review before shipping |
| `deep-plan/` — methodology (`TEMPLATES.md`, `GATE_FRAMEWORK.md`, `SKILLS.md`, `UPGRADE_SPEC.md`, `README.md`, `SUBAGENTS.md`, `METHODOLOGY.md`) | OPTIONAL (fixed) | Advanced multi-week-sprint planning methodology — transferable, not required for a baseline install. | All 7 files scrubbed as part of this release, including the `Remote-User: user@example.com` auth-header example fix in `METHODOLOGY.md` |
| `deep-plan/ATHENAEUM_PROTOCOL.md` | EXCLUDE | Documents integration with an origin-deployment-only Athenaeum service. | — |
| `deep-plan/case-studies/` | **RESOLVED (removed)** | Contained a case study of an internal reference project; removed during the content-safety pass rather than ship unreviewed internal detail — see Open Questions §2. | — |
| `benchmarks/` (`report.py`, `ledger.py`, `baseline.json`, `runner.py`, `scoring.py`, `ledger.jsonl`, `__init__.py`, `regression.py`, `tasks/*.yml`) | OPTIONAL | Explicit benchmarking harness (Tier 0/1/2 quality scoring) — named OPTIONAL example. | `baseline.json`/`ledger.jsonl` are accumulated run data from this instance, not templates — a public release likely wants a fresh/empty baseline rather than shipping this instance's own scores (content-appropriateness note, not a path weld) |
| `tests/` (source `test_*.py`, `test_*.sh`, `integration/`, `hooks/`) | **EXCLUDE (post-audit decision)** | Originally classified OPTIONAL — proves the hooks/scripts work, a strong credibility signal, not required to install or run the loop. **Decision made after this manifest was written**: dropped from the final public distribution entirely. Dozens of files hardcoded a fixed operator home directory in fixtures/comparisons — fixing that cleanly needs a fixture-root env var threaded through every test, which is more surgery than a pre-release scrub justifies, and `tests/` was also the single largest source of internal-path debris in the whole tree. See README.md's "Known limitations" for the replacement language (points to the project's own EVIDENCE.md instead). | — (not shipped) |
| `tests/.reports/` (`results.json`, `results-slow.json`) | EXCLUDE | Generated test-run output, not source — bulky accumulated artifact that should be `.gitignore`d, not shipped. (Moot now that `tests/` itself isn't shipped.) | — |
| `improvements/` (`01`–`14` + `README.md`) | OPTIONAL | V11's own internal engineering retrospectives/postmortems — interesting credibility artifact, not required to run. | 4 files referenced a fixed operator home directory (per weld sweep) — scrubbed to portable/generic paths as part of this release |
| `pm/` (`v11-ledger-integrity-spec.md`) | OPTIONAL | Design spec for ledger integrity — informational, not executable, not required for the loop to run. | — |
| `research/` (`v10-vision.md`, `multi-agent-patterns.md`) | OPTIONAL | Background research notes — not required. | — |

**Top-level-dirs tally**: CORE 4 rows · OPTIONAL 10 rows · EXCLUDE 6 rows · Unclassified 1 row (= 21 rows)
(Updated post-audit: `tests/` moved from OPTIONAL to EXCLUDE — see its row above — after the decision
to drop it from the public distribution entirely. Row count is unchanged; only the bucket shifted.)
(Updated again, final content-safety pass: an internal case-study file under `deep-plan/case-studies/` — the
Unclassified row — was removed rather than shipped, resolving Open Questions §2. Top-level dirs shifts to CORE 4 · OPTIONAL 10 ·
EXCLUDE 7 · Unclassified 0 (still 21 rows); Grand total in the Summary table below shifts to EXCLUDE 23 ·
Unclassified 0 (still 161). Byte/file counts in "Install footprint" below were not recomputed for this
single-file removal — negligible relative to the `tests/` correction already noted there.)

---

## Summary

| Group | CORE | OPTIONAL | EXCLUDE | Unclassified | Total |
|---|---|---|---|---|---|
| Hooks | 7 | 14 | 3 | 0 | 24 |
| Schemas | 9 | 10 | 0 | 0 | 19 |
| Scripts | 11 | 73 | 13 | 0 | 97 |
| Top-level dirs | 4 | 10 | 6 | 1 | 21 |
| **Grand total** | **31** | **107** | **22** | **1** | **161** |

**Welds needing parameterizing inside CORE rows** (i.e. things that had to be fixed, not just noted,
before a stranger's install works cleanly): **11 distinct line-item welds** were identified across 10
CORE rows — `hooks/lib/common.sh:5`, `hooks/lib/get-chicago-time.sh:6`,
`schemas/plan-context.schema.json:3`, `schemas/review-config.schema.json:3`, `scripts/audit-query:17`,
`scripts/autonomy-grant:20`, `scripts/handoff:39`, `scripts/plan-sync:15`,
`scripts/v11-bootstrap-session:18`, `agents/adversarial-reviewer.md:31`, plus a handful of doc-text
absolute-path references inside the CORE `docs/` set. **Status: all fixed as of this release** — every
file above was re-checked against the full weld pattern and returns zero hits. The env var previously
named after the origin deployment has also been renamed to `V11_WORKSPACE_ROOT` tree-wide (kept distinct from the
pre-existing, differently-scoped `V11_HOME` — see README.md's environment-variables table) and its
soft-default fallback value changed from a hardcoded operator home directory to the portable
`$HOME/.v11`.

For context: the initial repo-wide grep for weld markers (a hardcoded operator home directory, the
origin brand/domain, port ranges, a port-registry filename, an environment secrets filename) across
just `hooks/` + `scripts/` returned **172 hits**; the large majority landed in OPTIONAL or EXCLUDE
material (benchmarks, migration scripts, deploy/publish/scaffold, formations) and didn't block a
CORE-only install. A full second pass across every shipped file (this release) brought the tree-wide
residual count down substantially — see README.md's "Known limitations" for the current number.

---

## Install footprint

Computed from the CORE and CORE+OPTIONAL file sets above (excludes `__pycache__` everywhere, which
was never counted as an asset).

| Footprint | Files | Disk size |
|---|---|---|
| **CORE only** | 57 | 949,418 bytes (≈ 0.91 MB) |
| **CORE + OPTIONAL** | 382 | 5,194,764 bytes (≈ 4.95 MB) |
| *(OPTIONAL alone, for reference)* | *325* | *≈ 4.05 MB* |
| *(EXCLUDE, within the requested scope, for reference)* | *62* | *≈ 1.75 MB* |

**Post-audit correction**: the rows above were computed *before* the decision (made during the
publish-safety pass that produced this release) to drop `tests/` from the distribution entirely —
see its row in §4 above. `tests/` measured 151 files / 2,414,575 bytes (≈2.30 MB) on disk at removal
time. Subtracting that from the OPTIONAL and CORE+OPTIONAL rows above gives an approximate corrected
**CORE + OPTIONAL: ≈231 files, ≈2.65 MB** and **OPTIONAL alone: ≈174 files, ≈1.75 MB**. Treat these as
approximate, not re-verified with the same `du -scb` method as the original table — a few of this
table's directory-structure assumptions (e.g. a `tests/.reports/` subdirectory) didn't match what was
actually on disk when checked, which is a pre-existing manifest-accuracy gap independent of this pass.

Method: `du -scb --exclude='__pycache__'` over `hooks/ + schemas/ + scripts/` + the 14 named
top-level dirs gives 444 files / 7,030,165 bytes total in-scope. Subtracting the 62-file/
1,835,401-byte EXCLUDE set (13 scripts + 3 hooks + `agents/.v10-archive/` [10 files] +
`templates/{docker-compose,cloudflare}.yml.template` + 3 `docs/` files +
`deep-plan/ATHENAEUM_PROTOCOL.md` + `tests/.reports/` [30 files]) yields the CORE+OPTIONAL row above.
The CORE row (57 files) was summed directly from the 57-file CORE list (all hooks, schemas, scripts,
and top-level-dir files marked CORE above); every path in that list was verified to exist on disk.

Not included in either row: `swebench-repos/` (1.4G, pre-excluded per the brief) and
`swebench-predictions/`/`swebench-full-run.log` (generated benchmark output, ~1.5M) — both sit
outside the 14 named top-level directories.

---

## Open questions

1. **`tool-policy.schema.json` / `resolve-policy` / `v11_resolve_tool_policy()`** — `guard-enforcement`'s
   own header states *"V11.11: Tool policy cascade removed — native agent tool_profile handles it,"*
   yet the resolution function still lives in `hooks/lib/common.sh` and is actively called by
   `scripts/resolve-policy` and `scripts/formation-quality-benchmark`. I could not determine from
   static reading alone whether this is (a) dead code kept for a possible future re-enablement, or
   (b) still consumed by some live path I didn't trace (e.g. agent `tool_profile` resolution under a
   different name). Flagging rather than guessing at which; classified OPTIONAL pending verification.

2. **An internal case-study file under `deep-plan/case-studies/`** (RESOLVED) — a case study of an
   internal reference project. The open question was whether its content referenced internal/sensitive
   details inappropriate for public release. Resolved during the final content-safety pass: the file
   was removed rather than risk shipping unreviewed internal detail.

3. **Scripts count reconciliation** — the brief specified "98" scripts. The actual on-disk count is
   96 real executable scripts + `scripts/lib/` (12 Python support modules) + `scripts/__pycache__`
   (build artifact). Counting `lib/` as one row (as done above) lands at 97; counting each of its 12
   modules individually would overshoot to 108; counting `__pycache__` as a countable directory would
   add 1 more. I could not determine which accounting the original "98" was based on, so I've been
   explicit about my method (96 + 1 `lib/` row = 97) rather than forcing a match to 98.

4. **Hooks count reconciliation** — similarly, "24" only reconciles by counting `git-hooks/` and
   `lib/` as one row each (22 top-level executable hook files + 2 subdirectories = 24), which is what
   the raw `ls hooks/` listing shows and what I did above. Noting the method since the *file* count
   inside those two subdirectories (2 + 3, excluding caches) is different from "1 row each."

5. **`review-daemon` is undocumented** — classified CORE (it's the review loop's headless/unattended
   consumer) but it is not referenced by name anywhere in `CLAUDE.md`, `README.md`, or any `docs/*.md`
   file I checked. Either genuinely undocumented (a real gap worth fixing before public release) or
   documented under a name/alias I didn't grep for. Not confident enough to call this a documentation
   bug outright, so flagging instead.

6. **Six other scripts are similarly orphaned from docs**: `check-improve-subagent-triggers`,
   `install-review-cadence`, `swe_claude_code_agent.py`, `swe_infer.py`, `verify-gate2`, and
   `backfill-agent-errors-task-id` exist on disk but are never named in `CLAUDE.md`, `README.md`, or
   `docs/*.md`. Doc lag against a fast-moving repo is plausible and not necessarily wrong, but I
   couldn't confirm intended public-facing status for each individually within the effort budget.

7. **`agents/` spec-pipeline suite content depth** — I classified the 9 `spec-*-v11.md` files +
   `V11_AGENT_REGISTRY.json` as OPTIONAL based on a directory-level weld grep (several files hit
   the fixed-operator-path/brand patterns) but did not read each file in full to enumerate every line
   needing a scrub at the time this manifest was written. **Status: subsequently re-audited and fixed**
   as part of this release — all 10 files were individually read and scrubbed. Treat the "needs
   parameterizing" note on that row as a flag to re-audit those 10
   files individually, not as a complete fix list.
