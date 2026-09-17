# V11 Integration & Alignment Checklist

> Full system inventory and cross-reference for the V11 spec-driven protocol.
> Generated: 2026-03-07 | Version: v11.1.0

---

## 1. Hook System (12 hooks)

Settings template: `/path/to/v11/.claude/settings.json`
Hook scripts: `/path/to/v11/hooks/`
Shared library: `/path/to/v11/hooks/lib/common.sh` (~850 lines)

### Hook Wiring (settings.json)

| # | Event | Matcher | Hook Script | Purpose |
|---|-------|---------|-------------|---------|
| 1 | PreToolUse | `Read` | `detect-project` | Set active project context from file paths |
| 2 | PreToolUse | `Write\|Edit` | `guard-write-gates` | Task state enforcement + plan mode advisory + file ownership |
| 3 | PreToolUse | `Write\|Edit` | `guard-enforcement` | Risk blocking + autonomy grants + tool policy cascade |
| 4 | PreToolUse | `Bash` | `guard-enforcement` | Risk blocking for shell commands |
| 5 | PreToolUse | `Bash` | `enforce-test-coverage` | Block deploy without test coverage |
| 6 | PreToolUse | `Task` | `guard-effort` | Advise on effort level mismatch (never blocks) |
| 7 | PostToolUse | `Write\|Edit` | `verify-syntax` | Syntax check written files + memory indexing |
| 8 | PostToolUse | `Write\|Edit` | `track-autonomy` | Update project-local autonomy state + global audit |
| 9 | PostToolUse | `Bash` | `track-autonomy` | Track shell command autonomy |
| 10 | PostToolUse | `TaskCreate\|TaskUpdate\|TaskList` | `sync-tasks` | Write task state JSON + artifact persistence + metadata validation |
| 11 | PostToolUse | `TaskList` | `guard-teammate-timeout` | Detect stalled teammates (3-tier advisory) |
| 12 | PostToolUse | `Task` | `track-agents` | Log agent metrics + escalation |
| 13 | PostToolUse | `TeamCreate\|Agent` | `fix-team-model` | Patch `"model": "inherit"` bug in team configs |
| 14 | Stop | *(none)* | `session-end` | Save session summary |

**Cross-references to verify:**
- [ ] settings.json hook count matches CLAUDE.md Section 13 table (12 unique hooks, 14 entries)
- [ ] Every hook file in `hooks/` is executable (`chmod +x`)
- [ ] Every hook file in `hooks/` is wired in settings.json (no orphans)
- [ ] `hooks/lib/common.sh` exists and is sourced by all hooks
- [ ] All hooks use `v11_*` function naming (not v10_*)
- [ ] All hook comment headers reference V11 (not V10)
- [ ] `guard-teammate-timeout` matcher is `TaskList` only (not `TaskCreate|TaskUpdate|TaskList`)
- [ ] `sync-tasks` matcher is `TaskCreate|TaskUpdate|TaskList` (not just `TaskList`)
- [ ] `fix-team-model` matcher is `TeamCreate|Agent`
- [ ] Stop hook has no matcher (session-level event)
- [ ] Env var `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set in settings.json

---

## 2. Scripts (27 scripts)

Location: `/path/to/v11/scripts/`

### Core Operations

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `scaffold` | Create new project | Listed |
| `status` | Show progress from Tasks | Listed |
| `handoff` | Generate continuation prompt | Listed |
| `deploy` | Production deployment | Listed |
| `publish` | SSL + nginx + SITE_REGISTRY | Listed |
| `generate-state-view` | Regenerate state.md | Listed |
| `cloudflare-setup` | Configure Cloudflare tunnel | Listed |

### Migration & Maintenance

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `migrate-v10` | Migrate V10 project to V11 | Listed |
| `migrate-v8` | Migrate V8 project to V11 | Listed |
| `rotate-metrics` | Rotate log files | Listed |
| `validate-config` | Validate all config JSON against schemas | Listed |

### Agent Teams & Formations

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `team-status` | Show active Agent Teams | Listed |
| `create-formation-registry` | Create .formation-registry.json | Listed |
| `formation-heartbeat` | Formation health report | Listed |
| `suggest-formation` | Suggest formation from task metadata | Not listed |
| `formation-quality-benchmark` | 20-scenario formation benchmark | Not listed |

### Effort & Policy

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `effort-advisor` | Suggest effort level | Listed |
| `resolve-policy` | Debug tool policy resolution chain | Listed |

### Memory

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `index-project-memory` | Build/update memory index | Listed |
| `maintain-memory-index` | Memory index maintenance | Listed |

### Agent Roster & Metrics

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `generate-agent-roster` | Auto-generate agent roster table | Not listed |
| `hook-metrics` | Hook performance metrics | Not listed |
| `run-tests` | Run V11 test suite | Not listed |

### SWE-bench (Research)

| Script | Purpose | CLAUDE.md Section 9 |
|--------|---------|---------------------|
| `swe_infer.py` | Gemini one-shot SWE-bench | Not listed |
| `swe_claude_baseline.py` | Claude Sonnet baseline | Not listed |
| `swe_claude_code_agent.py` | Claude Code CLI agent | Not listed |
| `swe_v11.py` | V11 multi-agent pipeline | Not listed |

**Cross-references to verify:**
- [ ] All 18 scripts in CLAUDE.md Section 9 table exist and are executable
- [ ] `handoff` script uses V11 session paths (`/path/to/operator-home/sessions/`)
- [ ] `scaffold` generates settings.json with all 12 hooks
- [ ] `scaffold` references V11 paths (not V10/V8)
- [ ] `create-formation-registry` reads from `V11_AGENT_REGISTRY.json` (not V10)
- [ ] `validate-config` validates against schemas in `v11/schemas/` (not v10)
- [ ] `generate-agent-roster` reads from `v11/agents/` (not v10)
- [ ] `status` reads `.task-state.json` from sessions dir
- [ ] `formation-heartbeat` reads `.active_task_id` (not `.active_tasks`)
- [ ] `scripts/lib/` Python modules importable with absolute path

---

## 3. Agents (9 spec agents + Team Lead)

Agent definitions: `/path/to/v11/agents/`
Registry: `/path/to/v11/agents/V11_AGENT_REGISTRY.json`
Symlinks: `~/.claude/agents/spec-*-v11.md`

| # | Agent File | Model | Effort | Mode | Symlink |
|---|-----------|-------|--------|------|---------|
| 1 | `spec-architect-v11.md` | Opus 4.6 | max | teammate | Required |
| 2 | `spec-implementer-v11.md` | Sonnet 4.6 | -- | teammate | Required |
| 3 | `spec-integrator-v11.md` | Sonnet 4.6 | -- | teammate | Required |
| 4 | `spec-optimizer-v11.md` | Opus 4.6 | high | subagent | Required |
| 5 | `spec-planner-v11.md` | Opus 4.6 | high | direct | Required |
| 6 | `spec-recovery-v11.md` | Sonnet 4.6 | high | direct | Required |
| 7 | `spec-reviewer-v11.md` | Opus 4.6 | high | teammate | Required |
| 8 | `spec-security-v11.md` | Opus 4.6 | high | teammate | Required |
| 9 | `spec-tester-v11.md` | Sonnet 4.6 | -- | teammate | Required |
| -- | Team Lead | Opus 4.6 | high | Main session | N/A |

**Cross-references to verify:**
- [ ] All 9 symlinks exist at `~/.claude/agents/spec-*-v11.md`
- [ ] Symlinks point to `/path/to/v11/agents/` (not v10 or v8)
- [ ] `V11_AGENT_REGISTRY.json` lists 9 agents (`metadata.agent_count: 9`)
- [ ] Registry `metadata.protocol` is `"V11"`
- [ ] All agent .md files have V11 in title, headers, version, footer
- [ ] Model names are current: Opus 4.6, Sonnet 4.6 (not 4.5)
- [ ] `spec-tester-v11.md` has `disallowedTools: [Write, Edit]`
- [ ] `spec-reviewer-v11.md` has `disallowedTools: [Write, Edit, Bash]`
- [ ] Agent roster in CLAUDE.md Section 14 matches registry
- [ ] No V8/V10 agent files in `~/.claude/agents/` (should be in `.v8-tombstone/`)
- [ ] No `spec-conductor` agent anywhere (absorbed into Team Lead)

---

## 4. Formations (9 formations)

Documentation: `/path/to/v11/docs/FORMATIONS.md`
Registry: `V11_AGENT_REGISTRY.json` → `formations` array

| Formation | Teammates | When |
|-----------|-----------|------|
| `new-project` | architect, 2x implementer | New project setup |
| `feature-impl` | backend-impl, frontend-impl, integrator, tester | Feature building |
| `bug-investigation` | 3-5 hypothesis investigators | Unknown root cause |
| `security-review` | threat-modeler, scanner, fixer | Security audit |
| `perf-optimization` | optimizer, tester | Performance work |
| `code-review` | security-reviewer, perf-reviewer, coverage-reviewer | PR/code review |
| `single-file` | implementer | 1-3 tasks, single file |
| `lightweight-feature` | implementer, tester | 4-8 tasks, single layer |
| `swebench-solver` | investigator, implementer, validator | SWE-bench resolution |

**Cross-references to verify:**
- [ ] `FORMATIONS.md` lists all 9 formations with correct teammate counts
- [ ] `V11_AGENT_REGISTRY.json` `formations` array has 9 entries (`formations_count: 9`)
- [ ] Formation teammate arrays in registry use agent name strings (not objects)
- [ ] `CLAUDE.md` Section 3.3 table lists all non-research formations (8)
- [ ] `create-formation-registry` can instantiate each formation
- [ ] `suggest-formation` routes complexity/scope to correct formation
- [ ] DAAO difficulty-aware routing table in CLAUDE.md Section 3.3.1 is complete
- [ ] `formation-registry.schema.json` allows `tool_policies` in teammate definition

---

## 5. Schemas (8 JSON schemas)

Location: `/path/to/v11/schemas/`

| Schema | Validates | Trigger |
|--------|-----------|---------|
| `task-metadata.schema.json` | Task metadata (risk, complexity, scope, artifacts) | `sync-tasks` on TaskCreate |
| `task-state.schema.json` | Task state JSON (.task-state.json) | `validate-config` |
| `formation-registry.schema.json` | `.formation-registry.json` | `guard-write-gates` |
| `formation-config.schema.json` | Formation definitions in agent registry | `validate-config` |
| `agent-registry.schema.json` | `V11_AGENT_REGISTRY.json` | `validate-config` |
| `autonomy-state.schema.json` | `.autonomy-state` | `guard-write-gates` |
| `tool-policy.schema.json` | Tool group taxonomy and profile presets | `validate-config` |
| `memory-index.schema.json` | Memory index structure | `index-project-memory` |

**Cross-references to verify:**
- [ ] All 8 schemas listed in CLAUDE.md Section 13 table
- [ ] `task-metadata.schema.json` requires `project`, `sprint`, `risk`
- [ ] `agent-registry.schema.json` requires `metadata`, `agents`, `formations`
- [ ] `formation-config.schema.json` uses `description` (not `when`)
- [ ] `formation-registry.schema.json` includes `tool_policies` in teammate def
- [ ] `V11_SCHEMA_DIR` in common.sh resolves to `v11/schemas/` (3x dirname)
- [ ] `validate-config` references correct schema for each file type
- [ ] Schemas mode is advisory (warn, don't block)
- [ ] `task-state.schema.json` uses `active_task_ids` (array, not scalar)

---

## 6. Skills (V11-adjacent)

Location: `~/.claude/skills/`

### Active V11 Skills

| Skill | Status | Routes To |
|-------|--------|-----------|
| `team-orchestrator` | Primary entry point | V11 orchestration |
| `v11-status` | Active | `v11/scripts/status` |
| `v11-deploy` | Active | `v11/scripts/deploy` |
| `v11-scaffold` | Active | `v11/scripts/scaffold` |
| `handoff` | Active (unified v11.4.0) | `v11/scripts/handoff` + Zeus spawn |
| `status` | Router | Routes to `/v11-status` |
| `preflight` | Active | `v11/scripts/preflight` |
| `archive` | Active | V11 session paths |
| `scaffold` | Active | V11 starter-kits |
| `spec` | Router | Routes to `/v11` |
| `execute` | Router | Routes to `/v11` |
| `new-session` | Router | Routes to `/v11` |
| `publish.md` | Active | `v11/scripts/publish` |

### Archived/Deprecated Skills

| Skill | Status | Replacement |
|-------|--------|-------------|
| `v11-handoff` | Archived | `/handoff` (unified) |
| `v10-deploy` | Archived | `/v11-deploy` |
| `v10-handoff` | Archived | `/handoff` |
| `v10-scaffold` | Archived | `/v11-scaffold` |
| `v10-status` | Archived | `/v11-status` |
| `lead-orchestrator` | Archived | `/v11` (team-orchestrator) |
| `v8-test-skill` | Legacy | Low priority |

**Cross-references to verify:**
- [ ] `team-orchestrator/SKILL.md` references V11 protocol (not V9/V10)
- [ ] `team-orchestrator/references/` and `examples/` use V11 naming
- [ ] `team-orchestrator/journal/` exists with 3 files (v11-journal.md, error-reports.md, decisions.md)
- [ ] `handoff/SKILL.md` version is v11.4.0 with Zeus integration
- [ ] `v11-handoff/SKILL.md` has `[ARCHIVED]` marker
- [ ] All 4 V10 skills have `[ARCHIVED]` in description
- [ ] `status/SKILL.md` uses TaskList (not state.md checkboxes)
- [ ] `preflight/SKILL.md` checks for 12 V11 hooks (not V5/V8)
- [ ] `archive/SKILL.md` references `.task-state.json` (not state.md)
- [ ] `scaffold/SKILL.md` starter-kit paths use `v11/` (not `spec_template_v5/`)
- [ ] `execute/SKILL.md` routes to `/v11` (not `/spec execute`)
- [ ] `new-session/SKILL.md` routes to `/v11` (not `/spec new`)
- [ ] `v11-status/SKILL.md` Related section references `/handoff` (not `/v11-handoff`)
- [ ] No skill references `spec_template_v5`, `state.md` checkboxes, or `spec.yml`

---

## 7. Documentation

### V11-Internal Docs

| File | Location | Purpose |
|------|----------|---------|
| `CLAUDE.md` | `/path/to/v11/CLAUDE.md` | V11 Protocol (main reference) |
| `VERSION.md` | `/path/to/v11/VERSION.md` | Changelog (current: v11.1.0) |
| `ROADMAP.md` | `/path/to/v11/ROADMAP.md` | V11 improvement plan |
| `FORMATIONS.md` | `v11/docs/FORMATIONS.md` | Formation patterns |
| `PROTOCOL_FUNDAMENTALS.md` | `v11/docs/PROTOCOL_FUNDAMENTALS.md` | Teammate onboarding protocol |
| `MIGRATION_V9.2_TO_V10.md` | `v11/docs/` | Migration guide |
| `MIGRATION_V9.0_TO_V9.2.md` | `v11/docs/` | Migration guide |

### Platform Docs (V11-aware)

| File | Location | Purpose |
|------|----------|---------|
| `CLAUDE.md` | `/path/to/operator-home/CLAUDE.md` | Root orchestrator (references V11) |
| `SPEC_DRIVEN.md` | `~/.claude/docs/SPEC_DRIVEN.md` | Spec-driven guide |
| `ORCHESTRATION.md` | `~/.claude/docs/ORCHESTRATION.md` | Agent coordination |
| `AGENT_ROUTER.md` | `~/.claude/docs/AGENT_ROUTER.md` | Quick agent routing |
| `AGENT_CATALOG.md` | `~/.claude/docs/AGENT_CATALOG.md` | Full agent reference |

### Templates

| File | Location | Purpose |
|------|----------|---------|
| `spec.md.template` | `v11/templates/` | New project spec template |
| `state.md.template` | `v11/templates/` | State view template |
| `gates.md.template` | `v11/templates/` | Gate definitions template |
| `docker-compose.yml.template` | `v11/templates/` | Docker compose template |
| `cloudflare.yml.template` | `v11/templates/` | Cloudflare tunnel template |
| `project-settings.json` | `v11/templates/` | Project hook settings |
| `SCALING_GUIDE.md` | `v11/templates/` | 21+ task scaling guide |

**Cross-references to verify:**
- [ ] Root `CLAUDE.md` "Spec-Driven Mode (V11)" section references V11 (not V10)
- [ ] Root `CLAUDE.md` links to `/path/to/v11/CLAUDE.md` (not v10 or v8)
- [ ] `PROTOCOL_FUNDAMENTALS.md` uses V11 hook names (guard-write-gates, not guard-task-state)
- [ ] `PROTOCOL_FUNDAMENTALS.md` mentions SendMessage as primary teammate comms
- [ ] `FORMATIONS.md` lists 9 formations (including swebench-solver)
- [ ] `FORMATIONS.md` uses v11_* naming throughout
- [ ] `project-settings.json` template matches `v11/.claude/settings.json`
- [ ] `SCALING_GUIDE.md` threshold is 21+ tasks (not 51+)
- [ ] No doc references `spec_template_v5`, `/path/to/operator-home/v8/`, or `/path/to/operator-home/v10/`
- [ ] VERSION.md has v11.1.0 entry

---

## 8. Memory & Search

### Memory Search Library

| File | Location | Purpose |
|------|----------|---------|
| `search.py` | `v11/scripts/lib/` | Hybrid vector + BM25 search |
| `bm25.py` | `v11/scripts/lib/` | FTS5 BM25 implementation |
| `chunker.py` | `v11/scripts/lib/` | 400-token chunker (heading/paragraph boundaries) |
| `embedder.py` | `v11/scripts/lib/` | TF-IDF / sentence-transformers embedder |
| `cache.py` | `v11/scripts/lib/` | Embedding cache with dims guard |
| `__init__.py` | `v11/scripts/lib/` | Package init |

### MCP Server

| File | Location | Purpose |
|------|----------|---------|
| `server.py` | `v11/mcp-tools/memory-search/` | MCP tools: project_memory_search, project_memory_context |

### Storage

| Path | Purpose |
|------|---------|
| `sessions/{project}/.memory-index/memory.sqlite` | Per-project memory DB |
| `~/.claude/projects/{path}/memory/MEMORY.md` | Auto-memory (200-line limit) |

**Cross-references to verify:**
- [ ] `search.py` `_merge_scores` hydrates vector-only results from DB
- [ ] `cache.py` has `expected_dims` guard (auto-evicts mismatched entries)
- [ ] `embedder.py` takes `model_name` param (not `backend`)
- [ ] `cache.py` takes `cache_path` param
- [ ] Chunk class uses `.text` (not `.chunk_text`)
- [ ] SearchResult class uses `.chunk` (not `.chunk_text`)
- [ ] TF-IDF dims are 512 (not 256)
- [ ] `server.py` has V11_HOME startup diagnostic
- [ ] FTS5 queries use `chunks_fts` virtual table (not `chunks` base table)
- [ ] `index-project-memory` script is executable
- [ ] `maintain-memory-index` supports `--stats|--prune|--optimize|--rebuild`

---

## 9. Session Structure

### Per-Project Session Directory

```
/path/to/operator-home/sessions/{project}/
├── spec.md                  # Intent + constraints (<100 lines, NO task list)
├── state.md                 # Auto-generated view (read-only, <100 lines)
├── gates.md                 # Gate definitions (optional, <50 lines)
├── .task-state.json         # Synced by sync-tasks hook
├── .autonomy-state          # Project-local autonomy (A0-A5)
├── .formation-registry.json # Active formation (when team running)
├── .memory-index/           # Semantic memory search DB
│   └── memory.sqlite
├── .formation-history/      # Archived formation registries
├── artifacts/               # External artifact storage (>2KB)
│   └── {task_id}/
└── .claude/
    └── settings.json        # V11 hooks (copied from template)
```

### Global State Files

| Path | Purpose |
|------|---------|
| `~/.agent-metrics/active-project` | Currently active project name |
| `~/.agent-metrics/autonomy-audit.jsonl` | Global autonomy audit trail |
| `~/config/port-registry.json` | Port allocations |

**Cross-references to verify:**
- [ ] spec.md format matches V11 template (has `Protocol: V11` footer)
- [ ] spec.md does NOT contain task lists (tasks are in TaskList)
- [ ] state.md is auto-generated by `generate-state-view` (read-only)
- [ ] `.task-state.json` uses `active_task_ids` (array)
- [ ] `.autonomy-state` schema matches `autonomy-state.schema.json`
- [ ] `.formation-registry.json` schema matches `formation-registry.schema.json`
- [ ] Per-project `.claude/settings.json` matches `v11/.claude/settings.json`
- [ ] `SESSIONS_ROOT` env var defaults to `/path/to/operator-home/sessions`

---

## 10. Autonomy System

### 5 Levels

| Level | Name | Auto-Approve Scope |
|-------|------|-------------------|
| A0 | Manual | None |
| A1 | Guided | Same-category repeats |
| A2 | Supervised | Approved file globs |
| A3 | Trusted | All medium-risk if validation passes |
| A4 | Autonomous | All non-high-risk |

### Escalation Rules

- A0 → A1: 5 successes
- A1 → A2: 10 successes + 0 rollbacks
- A2 → A3: 25 successes
- A3 → A4: Explicit user grant only
- Error → drop 1 level
- 2+ errors in 10min → A0
- User says "slow down" → A0

**Cross-references to verify:**
- [ ] `track-autonomy` hook uses `flock` around state write (race condition fix)
- [ ] `.autonomy-state` is project-local (not global)
- [ ] Default for missing state is A0
- [ ] Escalation thresholds match CLAUDE.md Section 5
- [ ] `guard-enforcement` reads autonomy level before policy check
- [ ] Global audit at `~/.agent-metrics/autonomy-audit.jsonl`

---

## 11. Tool Policy Cascade

### 5 Profiles

| Profile | Tools | Agents |
|---------|-------|--------|
| `full` | All tools | planner, architect, optimizer, recovery |
| `coding` | read + write + exec + task | implementer, integrator, security |
| `testing` | read + exec (test) + task | tester |
| `readonly` | read + task | reviewer |
| `minimal` | task only | coordinator |

### Resolution Chain (deny-wins)

```
Formation defaults → Role overrides → Agent registry → Hook enforcement → Autonomy
```

**Cross-references to verify:**
- [ ] `guard-enforcement` checks tool policies when `V11_AGENT_ID` is set
- [ ] `guard-enforcement` reads `.formation-registry.json` for policy
- [ ] Resolution is 3-layer: formation defaults → per_role → teammates.*.tool_policies
- [ ] `V11_POLICY_REASON` uses `|| true` to prevent set -e kills
- [ ] `resolve-policy` script shows full resolution chain
- [ ] `tool-policy.schema.json` validates profile definitions

---

## 12. Test Suite

Location: `/path/to/v11/tests/`
Runner: `scripts/run-tests [--fast|--regression|--coverage]`

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_hooks_selftest.py` | 13 | Hook self-tests |
| `test_regressions.py` | 11 | Regression suite |
| `test_common_sh.py` | 19 | common.sh functions |
| `test_hooks_integration.py` | 11 | Hook integration |
| `test_memory_search.py` | 23 | Memory search library |
| `test_schemas.py` | 21 | Schema validation |
| `test_schema_validation.py` | 56 | All 8 schemas accept/reject |
| `test_formation_workflow.py` | 8 | Formation pipeline |
| `test_swebench.py` | 25 | SWE-bench scripts |
| `test_coverage_boost.py` | 24 | scripts/lib coverage |
| `test_script_integration.py` | 45 | validate-config, suggest-formation, migrate-v10 |
| `test_hook_behaviors.py` | 41 | detect-project, track-autonomy, enforce-test-coverage |
| `test_e2e_formation.py` | 10 | Full formation pipeline |
| `test_adversarial.py` | -- | Adversarial inputs |
| `test_phase2_integration.py` | -- | Phase 2 integration |
| `test_swe_v11_pipeline.py` | -- | SWE V11 pipeline |

**Target: 385+ tests, 0 failures, 81%+ coverage on scripts/lib**

**Cross-references to verify:**
- [ ] `python3 -m pytest tests/` runs clean from `/path/to/v11/`
- [ ] `scripts/run-tests` is executable
- [ ] Test fixtures use paragraph-separated text for chunker tests
- [ ] Tests use absolute paths for ownership dirs in `v11_check_file_ownership`
- [ ] Tests set `cwd=str(project_dir)` for guard-write-gates (CWD-relative check)
- [ ] FTS5 tests account for unicode61 tokenizer (no stemming)

---

## 13. Platform Integration Points

### Root CLAUDE.md (`/path/to/operator-home/CLAUDE.md`)

- [ ] "Spec-Driven Mode (V11)" section exists
- [ ] Links to `/path/to/v11/CLAUDE.md`
- [ ] Links to `/path/to/operator-home/v8/CLAUDE.md` (for legacy V8 reference)
- [ ] Project Scale Detection table matches V11 thresholds (21+ = sprint+gates)
- [ ] Key features list mentions: Agent Teams, Tasks, 13 hooks, 6-level autonomy
- [ ] No references to V5 (`spec_template_v5`) or V10 as current

### Agent Registry (`~/.agent-registry/agents.json`)

- [ ] No V8 agent entries (removed during Mar 2026 audit)
- [ ] Agent count reflects removal (~95 agents)
- [ ] V11 spec agents NOT duplicated here (they live in `v11/agents/`)

### Zeus Terminal Integration

- [ ] `~/.claude/hooks/spawn-claude-window.py` reads from V11 session path
- [ ] No V8 fallback path in `find_handoff_file()`
- [ ] Handoff script `--spawn` flag triggers Zeus window creation

### MCP Servers

- [ ] Hercules Platform MCP server configured in `~/.config/.mcp.json`
- [ ] Memory search MCP server at `v11/mcp-tools/memory-search/server.py`
- [ ] Gmail, HuggingFace, Socket MCP servers independent of V11

### Observability

- [ ] `~/.agent-metrics/` directory exists for metrics
- [ ] `active-project` file updated by `detect-project` hook
- [ ] `autonomy-audit.jsonl` written by `track-autonomy` hook
- [ ] Hook performance: guard-enforcement ~225ms, guard-effort ~200ms

---

## 14. Naming Consistency

### Must be V11 everywhere (not V10/V8/V5)

| Location | Check |
|----------|-------|
| Hook comment headers | `# V11 ...` |
| Hook function names | `v11_*` (compat aliases for v10_ in common.sh) |
| Hook env variables | `V11_*` (`V11_AGENT_ID`, `V11_SCHEMA_DIR`, `V11_HOME`) |
| Agent file titles | `spec-*-v11` |
| Agent file versions | `version: 11.0.0` |
| Agent file footers | `V11 Protocol` |
| Registry protocol | `"protocol": "V11"` |
| Registry field | `v11_native` (not `v10_native`) |
| Skill descriptions | Reference V11, not V10 |
| CLAUDE.md sections | V11 throughout |
| FORMATIONS.md | V11 naming |
| PROTOCOL_FUNDAMENTALS.md | V11 hook names |

**Cross-references to verify:**
- [ ] `grep -r "v10_" hooks/` returns only backward-compat aliases in common.sh
- [ ] `grep -r "V10" hooks/` returns only comments about migration/history
- [ ] `grep -ri "spec_template_v5" ~/.claude/skills/` returns 0 results
- [ ] `grep -ri "state\.md" ~/.claude/skills/` returns only "read-only" context
- [ ] `grep -ri "spec\.yml" ~/.claude/skills/` returns 0 results

---

## 15. Critical Invariants

These must always hold true:

1. **TaskList is the single source of truth** — never state.md, never spec.md task lists
2. **TeamCreate before TaskCreate** — team task lists are isolated from main list
3. **12 hooks in settings.json** — 14 entries (some hooks appear on multiple matchers)
4. **9 spec agents** — all symlinked to `~/.claude/agents/`
5. **8 JSON schemas** — all in `v11/schemas/`, validated by `validate-config`
6. **spec.md < 100 lines** — intent + constraints only, no task lists
7. **state.md is read-only** — auto-generated, never manually edited
8. **Autonomy is project-local** — stored in `.autonomy-state` per project
9. **Deny-wins policy cascade** — if any layer denies, tool is denied
10. **Advisory hooks never block** — guard-effort, guard-teammate-timeout

---

## 16. Quick Validation Commands

```bash
# Run full config validation
/path/to/v11/scripts/validate-config

# Run test suite
cd /path/to/v11 && python3 -m pytest tests/ -q

# Check hook executability
ls -la /path/to/v11/hooks/ | grep -v lib | grep -v "^d"

# Verify agent symlinks
ls -la ~/.claude/agents/spec-*-v11.md

# Check for V10 naming leaks
grep -r "v10_" /path/to/v11/hooks/ --include="*.sh" -l
grep -r "V10" /path/to/v11/hooks/ -l

# Check for V5/V8 references in skills
grep -ri "spec_template_v5\|/v8/\|spec\.yml" ~/.claude/skills/ -l

# Formation quality benchmark
/path/to/v11/scripts/formation-quality-benchmark

# Schema count
ls /path/to/v11/schemas/*.json | wc -l  # Should be 8

# Hook count in settings
python3 -c "import json; d=json.load(open('/path/to/v11/.claude/settings.json')); print(sum(len(v) for v in d['hooks'].values()), 'entries')"
# Should be 14 entries (PreToolUse:6 + PostToolUse:7 + Stop:1)
```

---

*Generated from live system inventory. Update when components change.*
