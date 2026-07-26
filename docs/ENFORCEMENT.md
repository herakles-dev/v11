# Enforcement — Detailed Reference

> Extracted from V11 CLAUDE.md Section 13. Hook table below reflects V11.11 reforms.

---

## Hook Table (historical V11.11 snapshot)

> ⚠ This table is a **V11.11-era snapshot** kept for the per-hook "V11.11 Change" rationale
> column. It is NOT the current hook inventory. **The canonical, current hook list lives in
> [CLAUDE.md §13](../CLAUDE.md)** (18 tool-event + 2 git-event as of v11.33). Do not treat the
> count below as authoritative — restating hook counts across docs is a known drift source.

At V11.11: 13 hooks — `guard-agent-stall` replaced `guard-teammate-timeout`.

| Hook | Trigger | Purpose | V11.11 Change |
|------|---------|---------|---------------|
| `detect-project` | Pre: Read | Set active project context | Unchanged |
| `guard-write-gates` | Pre: Write/Edit | Task-state: blocks on genuine stall, advises on fresh session (V11.34 `V11_WRITE_GATE`); plan-mode file-count is advisory-only | File ownership check removed (was formation-based) |
| `guard-enforcement` | Pre: Write/Edit/Bash | Risk + autonomy | Tool policy cascade removed — native agent `tool_profile` handles it |
| `guard-effort` | Pre: Task | Effort level advisory (never blocks) | Unchanged |
| `enforce-test-coverage` | Pre: Bash | Block deploy without tests | Unchanged |
| `verify-syntax` | Post: Write/Edit | Check syntax of written files | Unchanged |
| `track-autonomy` | Post: Write/Edit/Bash | Update autonomy state + audit log | Minor comment cleanup only |
| `sync-tasks` | Post: TaskCreate/Update/List | Task state JSON + artifacts + validation; extracts `metadata.agent` → `recommended_agents` map; V11.15: on completed tasks carrying `metadata.artifacts.review`, appends per-error lines to `~/.agent-metrics/agent-errors.jsonl`, a rolling-window snapshot to `agent-effectiveness.jsonl`, folds a `review_summary` rollup into task-state, and persists `artifacts.meta_feedback` to `sessions/{project}/meta-feedback/{task_id}.json`. Backward compatible — absent `artifacts.review` ⇒ identical pre-V11.15 behavior. W5-T15 (v11.30): reviewable completions missing `metadata.artifacts.self_review` also get a synthetic `missing_self_review` row in `agent-errors.jsonl` (rollback `V11_SELF_REVIEW_ACTUATE=off`). ADVISORY ONLY — never blocks. Also emits a stderr pre-scope advisory — default ON, gated by `V11_PRESCOPE_ADVISORY`, never blocks — on `TaskCreate` when `metadata.scope=large` or complexity is `complex`/`novel` without `deliverable_of` set; see `task-patterns.md` §Pre-scoping discipline. | Extracts `metadata.agent` per-task; no formation writes |
| `guard-agent-stall` | Post: TaskList | Detect stalled agents via task-state timestamps | NEW — replaces `guard-teammate-timeout`; uses timestamps, not formation heartbeat |
| `track-agents` | Post: Task | Agent metrics + escalation | `formation` field removed from metrics (v11.11) |
| `fix-team-model` | Pre+Post: TeamCreate/Agent | DORMANT — exits immediately with deprecation notice | Deprecated; native model handling makes this unnecessary |
| `post-compact` | PostCompact | Re-inject V11 state after context compaction | Shows `recommended_agents` instead of formation info |
| `session-end` | Stop | Save session summary | Unchanged |

---

## Hook Activation

Hooks fire automatically in projects created with `./scripts/scaffold` (each project gets its own `.claude/settings.json`).

**For manually-adopted projects** (existing codebases not created with scaffold):
```bash
mkdir -p ~/sessions/YOUR_PROJECT/.claude
cp ~/v11/.claude/settings.json ~/sessions/YOUR_PROJECT/.claude/settings.json
```
Hooks should **not** be added to `~/.claude/settings.json` globally — they would fire on every project across the platform, causing false enforcement.

---

## Schema Validation

JSON Schemas in `schemas/` validate configuration at creation time:

| Schema | Validates | Trigger |
|--------|-----------|---------|
| `task-metadata.schema.json` | Task metadata (risk, complexity, scope, artifacts) | `sync-tasks` on TaskCreate |
| `task-state.schema.json` | Task state JSON (totals, active_task_ids, artifacts) | `validate-config` script |
| `formation-registry.schema.json` | `.formation-registry.json` (teammates, ownership) | `validate-config` script (no longer triggered by `guard-write-gates` — V11.11) |
| `formation-config.schema.json` | Formation definitions in agent registry | `validate-config` script |
| `agent-registry.schema.json` | V11_AGENT_REGISTRY.json (agents, formations) | `validate-config` script |
| `autonomy-state.schema.json` | `.autonomy-state` (level, grants) | `guard-write-gates` on Write |
| `tool-policy.schema.json` | Tool group taxonomy and profile presets | `validate-config` script |
| `memory-index.schema.json` | Memory index structure (.memory-index/memory.sqlite) | `index-project-memory` script |
| `module-manifest.schema.json` | MODULE.md module manifests (Dark Code Layer 2: responsibility, dependencies, invariants, performance envelope) | `validate-module-manifest` script; `v11-compliance-check` Gate 11 **FAILS on any unvalidated or invalid manifest** (V11.8+, previously WARN) |

**Mode**: Advisory (warn, don't block). Catches contradictions like `routine + high-risk` at creation time.

**Validate all configs**: `./scripts/validate-config [PROJECT]`

---

## Lane Lease (V11.29)

Prevents two concurrent orchestrator sessions from executing the same task at once. Lib functions live in `hooks/lib/common.sh` ("Lane lease (V11.29)" section): `v11_lane_claim`, `v11_lane_release`, `v11_lane_force_release`, `v11_lane_gc`, `v11_lane_status`. Store: append-only per-project JSONL at `~/.agent-metrics/lanes/<project>.jsonl` — replay semantics, latest event per `task_id` wins. Holder liveness is checked via `v11_session_is_live`.

**Auto-wiring**: `sync-tasks` claims the lane on `TaskUpdate(in_progress)` and emits a `LANE CONFLICT` stderr advisory if a different LIVE session already holds it (advisory only — does not block the update); releases the lane on `TaskUpdate(completed)`.

**CLI**: `scripts/lanes status PROJECT [--json]` | `scripts/lanes gc PROJECT [--max-age MIN]` | `scripts/lanes release PROJECT TASK_ID [--force]`.

**Rollback**: `V11_LANE_LEASE=off` — the lane lease mechanism becomes a no-op everywhere (hook wiring and CLI both), used only when investigating hook bugs.

---

## Tool Policy (V11.11)

Tool restrictions are now defined natively in each agent's `.md` definition via `tool_profile`. The formation-based cascade (`guard-enforcement` reading `.formation-registry.json`) has been removed.

**5 Profiles** (still valid, now declared in agent definitions):

| Profile | Tools | Agents |
|---------|-------|--------|
| `full` | All tools | planner, architect, optimizer, recovery |
| `coding` | read + write + exec + task | implementer, integrator, security |
| `testing` | read + exec (test) + task | tester |
| `readonly` | read + task | reviewer |
| `minimal` | task only | coordinator |

**Enforcement**: Each agent's `tool_profile` field in its `.md` definition is enforced natively by Claude Code. `guard-enforcement` no longer reads `.formation-registry.json` for this purpose — it handles risk + autonomy checks only.

**Debug**: `./scripts/resolve-policy AGENT_ID TOOL_NAME` still shows the resolution chain (updated for native profile resolution).

---

## Semantic Memory Search

Hybrid vector + BM25 search over project files. Teammates can query "what was the auth decision?" instead of guessing file paths.

**Architecture**:
```
Sources: spec.md, tasks, notes/*.md, artifacts
  -> Chunker (400 tokens, 80 overlap)
  -> SQLite FTS5 (BM25) + optional vector embeddings
  -> Hybrid search (70% vector + 30% BM25)
  -> Results with source citations
```

**Storage**: `sessions/{project}/.memory-index/memory.sqlite`

**MCP Tools**:
- `project_memory_search`: Query with ranked results
- `project_memory_context`: Get topic-focused context for agent injection

**Indexing**: Auto-triggered on task completion (via `sync-tasks`) and file writes to sessions/ (via `verify-syntax`). Manual: `./scripts/index-project-memory PROJECT`

**Maintenance**: `./scripts/maintain-memory-index PROJECT [--stats|--prune|--optimize|--rebuild]`

**Embedding backends** (auto-detected):
1. sentence-transformers (best quality, requires install)
2. TF-IDF with numpy (always available fallback)
3. BM25-only (no vector search, FTS5 keyword matching)

**Performance**: Index builds in <5s for typical projects. Search returns in <200ms.
