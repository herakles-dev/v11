# V11 Scripts Reference

> Complete inventory of V11 scripts. Extracted from CLAUDE.md §9.

| Script | Purpose |
|--------|---------|
| `./scripts/scaffold <name>` | Create new project |
| `./scripts/status [project]` | Show progress from Tasks |
| `./scripts/handoff [project]` | Generate continuation prompt |
| `./scripts/deploy <service>` | Production deployment |
| `./scripts/team-status` | Show active Agent Teams |
| `./scripts/create-formation-registry FORMATION PROJECT` | Create .formation-registry.json |
| `./scripts/formation-heartbeat [project]` | Formation health report |
| `./scripts/validate-config [project]` | Validate config JSON against schemas |
| `./scripts/resolve-policy AGENT_ID TOOL` | Debug tool policy resolution |
| `./scripts/plan-sync [PROJECT]` | Snapshot V11 state to ~/.claude/plans/ |
| `./scripts/plan-resume [PROJECT]` | Resume from V11 plan file |
| `./scripts/audit-query [--project P]` | Query proof-of-work audit trail |
| `./scripts/publish PROJECT` | Publish project (SSL + nginx + registry) |
| `./scripts/index-project-memory PROJECT` | Build/update memory index |
| `./scripts/effort-advisor <prompt>` | Suggest effort level |
| `./scripts/migrate-to-v11 PROJECT` | Migrate any project to V11 (auto-detects version) |
| `./scripts/v11-compliance-check PROJECT` | 10-gate V11 compliance validation |
| `./scripts/v11-compliance-check --scan` | Scan all projects for compliance |
| `./scripts/migrate-v10 <project>` | Migrate V10 project to V11 (legacy) |
| `./scripts/migrate-v8 <project>` | Migrate V8 project to V11 (legacy) |
| `./scripts/audit-codebase PROJECT PATH` | Orchestrate multi-agent codebase audit |
| `./scripts/synthesize-findings PROJECT` | Deduplicate, rank, and generate audit report |
| `./scripts/findings-to-spec PROJECT` | Convert audit findings into V11 spec for fixes |
| `./scripts/v11-benchmark [--tier 0\|1\|2]` | System-level benchmark with composite scoring |
| `./scripts/wave-review PROJECT [WAVE]` | Generate adversarial review prompt for wave |
| `./scripts/recover-session [PROJECT]` | Reconstruct context after cut-off conversation |
| `./scripts/validate-project-setup PROJECT` | 14-check project validation (V11.6+) |
| `./scripts/context-status` | Show heuristic context window usage |
| `./scripts/athenaeum-search "query"` | Search Athenaeum libraries for planning |
| `./scripts/interview-recommend --stack X` | Athenaeum-backed formation recommendations |
| `./scripts/v11-update PROJECT` | Upgrade V11 project to latest version |
| `./scripts/v11-update --scan` | Survey all projects by V11 version |
| `./scripts/tracker-status [PROJECT]` | Show tracker artifact status (V11.7) |
| `./scripts/autonomy-grant PROJECT LEVEL [--reason ...]` | Persist explicit A4/A5 grant (hook auto-escalation caps at A3) |
| `./scripts/repair-empty-state [--dry-run]` | Re-seed 0-byte task-state / autonomy-state files |
| `./scripts/v11-bootstrap-session [PROJECT]` | Initialize V11 state for mid-session hook installs |
| `./scripts/validate-module-manifest PROJECT` | Validate MODULE.md against module-manifest schema (Dark Code Layer 2) |
| `./scripts/spec-requirements-extract PROJECT [--json]` | Extract STR candidates from spec.md (Dark Code Layer 1) |
| `./scripts/flywheel-ingest [--algorithm taxonomy\|legacy] [--min-count N]` | Cluster cross-project findings into framework-improvement proposals |
| `./scripts/verify-gate0 [PROJECT]` | Sprint 0 exit gate — find-audit + test suite + coverage |
| `./scripts/formation-select PROJECT` | Project-aware formation recommender (top-3 with confidence) |
| `./scripts/suggest-formation` | Difficulty-aware formation routing helper |
| `./scripts/v11-drift-scan PROJECT [--fix]` | Lightweight drift detection; also `--scan` all projects |
| `./scripts/v11-retro [PROJECT] [--reset\|--due\|--scan]` | Manage retrospective counter driving journal flywheel |
| `./scripts/repair-task-state-drift [--dry-run]` | Heal counter drift in task-state JSON |
| `./scripts/validate-invariants PROJECT` | Static checker for MODULE.md invariants (Dark Code ADR-003) |
| `./scripts/generate-agent-roster` | Regenerate CLAUDE.md §14 agent table from V11_AGENT_REGISTRY.json |
| `./scripts/hook-metrics` | Hook performance dashboard (latency, frequency, errors per hook) |
| `./scripts/maintain-memory-index PROJECT [--rebuild]` | Maintain BM25 + embedding index for project memory search |
| `./scripts/rotate-metrics [--dry-run] [--threshold MB]` | Rotate oversized JSONL metrics files |
| `./scripts/run-tests [--fast\|--regression\|--regression-extended\|--coverage]` | Structured CI test runner; two-tier regression — `--regression` = deterministic fast core (<30s, marker `regression`), `--regression-extended` = full suite excl. benchmarks (~2500 tests), two-phase: non-slow at `-n 8`, then slow tier serial `-n0 --timeout=120` (W4-1c — slow tier is xdist-hostile) |
| `./scripts/agent-scorecard AGENT [--layer L] [--caller-kind K] [--json]` | Single-agent deep dive across all 4 review layers (V11.20) |
| `./scripts/agent-effectiveness [--layer L] [--caller-kind K]` | Fleet-wide agent effectiveness with layer/caller-kind filters (V11.20) |
| `./scripts/wave-review-attribute PROJECT WAVE` | Attribute wave-review findings to executing agents (V11.20) |
| `./scripts/swarm-review-attribute PROJECT [--report PATH]` | Attribute swarm-review findings to executing agents (V11.20) |
| `./scripts/backfill-wave-findings [--project P] [--dry-run]` | Fleet-wide historical wave finding attribution (V11.20) |
| `./scripts/backfill-swarm-findings [--project P] [--dry-run]` | Fleet-wide historical swarm finding attribution (V11.20) |
| `./scripts/improve-subagent AGENT [--apply --from-proposal P]` | Evidence-cited prompt amendments for subagents (V11.20.2) |
| `./scripts/improve-subagent --list-improvable` | List agents with logged errors, ranked (V11.20.2) |
| `./scripts/improve-subagent --rollback AGENT` | Restore most-recent agent backup (V11.20.2) |
| `./scripts/agent-recommend --meta X --complexity Y [--with-scorecard]` | DAAO agent recommendation (V11.21) |
| `./scripts/wave-check PROJECT WAVE` | Wave gate enforcement — INV-12 (V11.21) |
| `./scripts/dispatch-trace-append` | Log Phase 4 spawn to dispatch-trace.jsonl (V11.21); `--tokens N --tool-uses N --duration-ms N --event EVENT` capture real per-spawn token/tool-use/duration when the harness reports them (W3-T12/v11.29), absent flags → byte-identical pre-W3-T12 line shape, rollback `V11_TOKEN_CAPTURE=off` |
| `./scripts/review-queue pending\|stats\|list\|mark-done PROJECT [--verdict-file FILE]` | Review queue CLI (V11.19; `--verdict-file` folds full verdict JSON into the durable ledger + verdict store, v11.30) |
| `./scripts/drain-review-queue PROJECT [--limit N]` | Emit structured spawn prompts for pending reviews (V11.19) |
| `./scripts/backfill-reviews [--project P] [--since DATE]` | Enqueue historical completions missing reviews (V11.19) |
| `./scripts/handoff-discipline-check` | Flag shipped-but-unclosed tasks (V11.18) |
| `./scripts/quarantine-misstamped-sessions` | Heal mis-stamped session dirs (V11.15.5) |
| `./scripts/migrate-ledger [--all]` | Seed durable ledger idempotently (V11.16) |

## Framework Internals & Recent Additions (v11.23–v11.28)

Previously-undocumented live scripts (backfilled 2026-07-01 during the full-system review):

| Script | Purpose |
|--------|---------|
| `./scripts/check-changelog-drift` | Guard: fails on inline changelog in CLAUDE.md §17 or a Current version missing from docs/CHANGELOG.md; soft-block in both `run-tests --regression` and `--regression-extended` (V11.28.1) |
| `./scripts/lint-test-honesty` | AST+regex linter for false-green test patterns; soft-block in both `run-tests --regression` and `--regression-extended` (V11.26) |
| `./scripts/fold-reconcile [--dry-run\|--apply --confirm]` | Propose-only merge of duplicate task families (V11.27) |
| `./scripts/reconcile-aggregates` | Recompute per-project open counters from filtered task set (V11.23) |
| `./scripts/ledger-shadow-report` | Compare durable ledger vs derived aggregate for drift |
| `./scripts/task-review` | Review-queue task-review helper |
| `./scripts/v11-resume-tasks PROJECT` | Emit `<v11-resume>` entries from handoff-tasks.json for rehydration (V11.17) |
| `./scripts/v11-migrate-task-state` | Migrate task-state.json schema forward |
| `./scripts/verify-gate1` / `verify-gate2` | Gate-exit verification checks |
| `./scripts/install-postcommit-hook` | Install/chain the git post-commit task-close hook (V11.25) |
| `./scripts/install-validation-lint-hook` | Install the git commit-msg validation hook (V11.25) |
| `./scripts/formation-quality-benchmark` | Benchmark formation output quality |
| `./scripts/archive PROJECT` | Archive a completed session |
| `./scripts/cloudflare-setup` | Cloudflare tunnel setup for `publish` |
| `./scripts/lanes status\|gc\|release PROJECT [...]` | Per-project task-execution lane lease CLI — status/gc/release over `v11_lane_*` in `hooks/lib/common.sh` (V11.29) |
| `./scripts/worktree-sweep [--apply] [--base BRANCH]` | Classify/clean stale `.claude/worktrees/` — LOCKED/SAFE_REMOVE/KEEP(dirty)/KEEP(unmerged) |
| `./scripts/worktree-sweep verify [WORKTREE_PATH\|--all] [--base BRANCH] [--json]` | Read-only commit-verify guard: exit-code contract (0 clean-merged / 10 uncommitted-non-generated / 11 unmerged / 12 generated-only-dirty) — catches the "edited but never committed" silent-loss failure mode |
| `./scripts/ledger-archive` | Operator-on-demand ledger archival; rollback `V11_LEDGER_ARCHIVE=off`; first `--apply` run pending |
| `./scripts/review-queue-maintenance` | Normalize + GC the review queue; cron wiring lands in v11.32 W2 |
| `./scripts/ledger-verify [PROJECT]` | Cold-path verdict-hash verification across durable ledgers |

> Note: this file is a curated index, not exhaustive (84 executable scripts exist). Run `ls scripts/` for the full set.
