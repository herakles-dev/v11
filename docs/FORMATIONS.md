# V11 Formations — Task-Template Recipes

> Formations are recipes: they define which agents handle which roles, how tasks break down,
> and what wave structure to follow. They do NOT require TeamCreate to use.
>
> V11.11+: Apply a formation by setting `metadata.agent` on tasks and spawning background agents.
> TeamCreate is deprecated — see [AGENT_TEAMS.md](AGENT_TEAMS.md) for the execution approach reference.

**Formation Selection**: Use the flowchart at the bottom for quick decision-making.

**Execution Patterns**: See [AGENT_TEAMS.md](AGENT_TEAMS.md) for how to spawn agents (background, subagent, or legacy TeamCreate).

---

## Formation Template

Each formation defines:
- **When**: Trigger condition
- **Roles**: Agent assignments per task type, with file ownership
- **Task Flow**: Dependency diagram showing parallelization and waves
- **Specific Rules**: Formation-unique patterns

A formation is applied by:
1. Creating tasks in the main task list with `metadata.agent` matching the role
2. Spawning agents as background agents (or subagents for sequential phases)
3. Following the wave structure — do not start Wave N+1 until Wave N tasks are completed

---

## When to Apply a Formation

| Scope | Formation Recipe |
|-------|-----------------|
| 1-3 tasks, single file | single-file |
| 4-8 tasks, single layer | lightweight-feature |
| 6+ coordinated tasks, multi-layer | feature-impl or appropriate specialty formation |
| 16+ tasks, multi-phase | Chain formations across sprints |

### Model Cost by Execution Mode

Background agents use their definition model (Sonnet). TeamCreate (deprecated) forces all teammates to Opus.

| Formation | Background Agent Cost | Legacy TeamCreate Cost |
|-----------|----------------------|----------------------|
| single-file | Sonnet (1 agent) | Opus — prefer background |
| lightweight-feature | Sonnet (2 agents) | Opus — prefer background |
| feature-impl | Sonnet (4 agents) | Opus |
| bug-investigation | Sonnet (3-5 agents) | Opus |
| security-review | Sonnet (3 agents) | Opus |
| code-review | Sonnet (3 agents) | Opus |
| new-project | Sonnet (3 agents) | Opus |
| perf-optimization | Sonnet subagents | Sonnet subagents — no team needed |
| swebench-solver | Sonnet (3 agents) | Opus |
| business-launch | Sonnet (background) | N/A — already background |
| all-hands-planning | Sonnet (background) | N/A — already background |
| codebase-audit | Sonnet (background) | N/A — already background |
| deep-research | Sonnet (background) | N/A — already background |
| pm-audit | Sonnet (background) | N/A — already background |

**Rule of thumb**: If direct work would take <2 hours, skip the formation and work directly. Formation recipes add value when parallelizing 3+ distinct roles or enforcing wave dependencies.

---

## Formation 1: new-project

**When**: Greenfield project setup, scaffolding + initial implementation.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Architect | spec-architect-v11 | Architecture docs, docker-compose structure, config templates |
| Scaffolder | spec-implementer-v11 | Project skeleton, build config, CI setup |
| DB Designer | spec-implementer-v11 | Database schema, migrations, seed data |

**Task Flow**:
```
Architect → (Scaffolder + DB Designer) in parallel
```

**Specific Rules**:
- Architect output unblocks implementers
- Team lead reviews architecture before unblocking scaffold/DB tasks

**Wave Review (V11.6)**: After scaffold + DB wave completes, spawn adversarial-reviewer to validate architecture implementation before proceeding. See feature-impl formation for full protocol.

---

## Formation 2: feature-impl

**When**: Adding features to an existing project. Most common formation.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Backend | spec-implementer-v11 | src/routes/, src/services/, src/models/ |
| Frontend | spec-implementer-v11 | src/components/, src/pages/, src/hooks/ |
| Integrator | spec-integrator-v11 | docker-compose.yml, nginx.conf, API contracts |
| Tester | spec-tester-v11 | tests/, __tests__/, *.test.* |

**Task Flow**:
```
(Backend + Frontend) in parallel → Integrator → Tester
```

**Specific Rules**:
- Backend/Frontend create tasks for Integrator describing new API endpoints
- Integrator claims tasks only after both sides complete
- Tester runs after integration verified

**Adversarial Verification (V11)**:
- Tester uses two-phase verification: JUDGE (assess) → REPORT (STATUS: done/retry)
- Tester default position is FAIL — evidence must prove success
- All findings include `file:line` citations and confidence levels
- STATUS is binary: `done` or `retry` (never partial)

**Wave Review (V11.6)** — After each implementation wave completes:
1. Collect `files_changed` from completed task artifacts
2. Spawn `adversarial-reviewer` background agent (Sonnet, READ-ONLY) with file list + spec excerpt
3. Reviewer applies 5 lenses: code quality, completeness, integration, security vectors, architectural rationale (Dark Code Layer 4 — the "why" lens)
4. Returns structured JSON with verdict (PASS / ISSUES_FOUND / BLOCKED)
5. If BLOCKED: fix CRITICAL findings before next wave
6. If `security_plan_needed`: schedule security-engineer agent wave
7. Script: `./scripts/wave-review {project} {wave-number}`

---

## Formation 3: bug-investigation

**When**: Root cause is unknown. Parallelize hypothesis testing.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Hypothesis 1 | spec-implementer-v11 | Investigation area 1 |
| Hypothesis 2 | spec-implementer-v11 | Investigation area 2 |
| Hypothesis 3 | spec-implementer-v11 | Investigation area 3 |

**Task Flow**:
```
(Investigator 1 + Investigator 2 + Investigator 3) in parallel
→ First to find root cause creates fix task
→ Team lead shuts down others
```

**Investigation Strategies** (assign one per investigator for diversity):

| Strategy | Approach | Best For |
|----------|----------|----------|
| **Backward Chaining** | Start from error, trace call stack to root | Stack traces, clear error messages |
| **Temporal Analysis** | Correlate logs/metrics with when bug first appeared | Intermittent bugs, regressions |
| **Isolation Testing** | Disable components one-by-one to find culprit | Multi-service interactions |
| **Pattern Matching** | Search codebase for similar past bugs or anti-patterns | Recurring issues, known bad patterns |
| **Environmental** | Check config, deps, infra differences from working state | "Works on my machine", deploy failures |

**Specific Rules**:
- Scale to 3-5 investigators based on complexity
- Assign distinct strategies to avoid duplicate investigation work
- First to find root cause TaskCreate(fix task, blockedBy=[investigation tasks])
- Team lead terminates remaining investigators when root cause found

---

## Formation 4: security-review

**When**: Security audit, threat modeling, vulnerability assessment.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Threat Modeler | spec-security-v11 | Threat model document, security findings |
| Scanner | spec-security-v11 | Scan results, dependency audit |
| Fixer | spec-implementer-v11 | Source code fixes for findings |

**Task Flow**:
```
(Threat Modeler + Scanner) in parallel → Fixer
```

**Specific Rules**:
- Scanner/Modeler create BLOCKER tasks for HIGH/CRITICAL findings
- Fixer tasks blocked by findings
- No parallel fixing while scanning continues (prevents race conditions)

---

## Formation 5: perf-optimization

**When**: Performance work -- profiling, optimization, regression testing.

**Mode**: Sequential subagents (NOT teammates). Deep single-expert work.

**Agents**:
| Step | Agent | Mode |
|------|-------|------|
| 1. Profile & Optimize | spec-optimizer-v11 | Subagent |
| 2. Regression Test | spec-tester-v11 | Subagent |

**Task Flow**:
```
Optimizer (subagent) → Tester (subagent)
```

**Specific Rules**:
- Use subagents, not teammates (deep focus required)
- Sequential only (no parallelization)
- Team lead waits for optimizer report before launching tester

---

## Formation 6: code-review

**When**: PR review, code quality assessment, pre-merge checks.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Security Reviewer | spec-reviewer-v11 | Security lens findings |
| Perf Reviewer | spec-reviewer-v11 | Performance lens findings |
| Coverage Reviewer | spec-reviewer-v11 | Test coverage lens findings |

**Task Flow**:
```
(Security + Perf + Coverage Reviewers) in parallel → Team lead synthesis
```

**Specific Rules**:
- All reviewers READ-ONLY (no code modifications)
- Each reviewer writes findings to separate task
- Team lead synthesizes into unified report
- Fix tasks created separately for implementers

**Adversarial Verification (V11)**:
- Reviewers use three-phase process: SPEC SUMMARY → CODE SUMMARY → GAP ANALYSIS
- Each reviewer applies ONE lens only (security, performance, or coverage)
- VERDICT is binary: `approved` or `rejected`
- All findings include `file:line` citations and confidence levels
- Challenge threshold: 0 issues on >100 lines of change means not looking hard enough

---

## Formation 7: single-file

**When**: Small, focused file edits. Minimal-overhead implementation for 1-3 task changes in a single file.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Implementer | spec-implementer-v11 | Single target file + related utilities |

**Task Flow**:
```
Implementer claims task → [Read → Edit → Verify] → Task marked complete
```

**Specific Rules**:
- Task count: 1-3 tasks, all in same file
- Scope: No cross-file dependencies
- Effort: <2 hours total
- Verification: Syntax check, unit tests (if defined), no breakage in dependents
- Examples: "Fix navbar styling", "Add email validation regex", "Update config variables"

---

## Formation 8: lightweight-feature

**When**: Small, single-layer features (frontend-only OR backend-only). 4-8 tasks with integrated testing.

**Teammates**:
| Role | Agent | File Ownership |
|------|-------|---------------|
| Implementer | spec-implementer-v11 | Source code changes (src/...) |
| Tester | spec-tester-v11 | Test files (tests/, __tests__/, *.test.*) |

**Task Flow**:
```
(Implementer + Tester) in parallel

Implementer: Task 1 (feature core) → Task 2 (edge case) → Task 3 (polish)
Tester (after each impl task): Write unit tests → Update integration tests → Verify coverage >80%

Sync point: Both complete, verify no breakage
```

**Specific Rules**:
- Task count: 4-8 tasks
- Scope: Frontend-only OR backend-only (NOT both)
- Effort: <4 hours total
- File ownership: Implementer owns src/, Tester owns tests/
- Parallelization: Impl + Test work in parallel, tester tasks blocked by corresponding impl tasks
- Verification: Syntax check + test coverage >80% + no broken imports
- Examples: "Add dark mode toggle", "Implement CSV export", "Add rate limiting middleware"
- Escalate to feature-impl if: backend + frontend both needed, >8 tasks, or multi-phase work

**Adversarial Verification (V11)**:
- Tester uses two-phase verification (JUDGE → REPORT) with binary STATUS
- Tester default is FAIL — code must prove correctness via test execution

**Wave Review (V11.6)**: After sync point, spawn adversarial-reviewer for final quality gate before marking formation complete. See feature-impl formation for full protocol.

---

## Formation 9: swebench-solver

**When**: SWE-bench Lite instance resolution. Research benchmark using V11's 3-wave
formation pattern to solve GitHub issues from the SWE-bench Lite dataset.

**Mode**: Sequential waves with feedback loop (NOT parallel teammates).

**Teammates**:
| Role | Agent Prompt | Responsibility |
|------|-------------|---------------|
| Investigator | spec-architect-v11 | Root cause analysis + target file identification |
| Implementer | spec-implementer-v11 | FIND/REPLACE patch generation |
| Validator | spec-tester-v11 | Actual test execution + feedback to implementer |

**Wave Architecture**:
```
Wave 0: Investigator
  Input:  issue text + repo file tree + FAIL_TO_PASS hints
  Output: { hypothesis, target_files, complexity }
    │
    ▼
Wave 1: Implementer (up to 3 iterations)
  Input:  investigator artifact + target file contents
  Output: FIND/REPLACE patch
    │
    ▼
Wave 2: Validator
  Input:  patch + FAIL_TO_PASS test IDs
  Action: apply patch → run tests
  Output: { resolved, f2p_tested, f2p_passed, error_log }
    │
    ├─► Tests PASS → done (final patch saved)
    └─► Tests FAIL → error_log → back to implementer (max 3 loops total)
```

**Key Differentiator vs One-Shot**:
The validator→implementer feedback loop is what separates V11 formation from single-agent
baselines. Test failure details are fed back with the original context for surgical revision.

**Specific Rules**:
- Investigator is READ-ONLY (readonly profile)
- Implementer has coding profile (Write + Edit allowed)
- Validator is testing profile (no Write/Edit — runs tests only)
- Max 3 total implementer attempts per instance
- Trajectory log saved to `trajs/{instance_id}.jsonl` for analysis
- Final patch is kept even if tests don't pass (harness may still resolve)

**Cost Model**:
- ~3 Claude API calls per instance at attempt 1 (investigator + implementer + validator)
- ~5 calls if 2 iterations needed, ~7 if 3 iterations
- Average ~3.5 calls per instance (many resolve on first try)

**Benchmark Script**: `scripts/swe_v11.py`
**Baseline Script**: `scripts/swe_claude_baseline.py` (one-shot, no formation)
**Output**: `swebench-predictions/v11-formation/`

**Running**:
```bash
# Pilot (50 instances, django repo)
source ~/.secrets/app.env
python3 scripts/swe_v11.py --num 50 --repo-filter django --max-attempts 3

# Full run
python3 scripts/swe_v11.py --num 300 --max-attempts 3

# Official evaluation
python -m swebench.harness.run_evaluation \
    --predictions_path swebench-predictions/v11-formation/all_preds.jsonl \
    --swe_bench_tasks princeton-nlp/SWE-bench_Lite \
    --run_id v11-formation-claude-sonnet \
    --max_workers 4
```

**Formation table row**:
| swebench-solver | 3-4x | SWE-bench research: investigator+implementer+validator beat one-shot |

---

## Discovery Board (Cross-Teammate Info Sharing)

When teammates discover information relevant to other teammates, they share it via **discovery tasks**:

```python
TaskCreate(
    subject="DISCOVERY: API rate limit is 100 req/min, not 1000",
    description="Found during integration testing. Backend implementer should add rate limiting middleware.",
    metadata={
        "type": "discovery",
        "found_by": "tester",
        "relevant_to": ["backend-impl", "integrator"],
        "project": "my-project",
        "sprint": "sprint-01",
        "risk": "low"
    }
)
```

**Convention**: Tasks with `metadata.type = "discovery"` are informational — they don't need to be claimed or completed. Teammates check for discoveries before starting new work.

**When to create discoveries**:
- API contracts differ from spec assumptions
- Performance characteristics found during testing
- Security considerations found during implementation
- Configuration requirements discovered during integration

---

## Formation Chaining Protocol

When a project spans multiple sprints, chain formations with explicit handoff:

**Between-Formation Handoff Steps**:
1. **Capture decisions**: Update `spec.md` Notes section with architecture decisions, API contracts, and configuration choices made during the formation
2. **Close out tasks**: Ensure all tasks from the current formation are `completed` or explicitly deferred to the next sprint
3. **Archive registry** (legacy TeamCreate only): Move `.formation-registry.json` to `.formation-history/` for audit trail. Not needed for per-task agent assignment.
4. **Update spec.md**: Add any new constraints or learnings to the Constraints section
5. **Select next formation recipe**: Choose the appropriate formation for the next sprint's work

**Task Continuity**: Tasks that span formations should be split — complete the portion done in the current formation, create a new task for the remaining work in the next sprint. Never carry `in_progress` tasks across formation boundaries.

**Example Chain**:
```
Sprint 1: new-project (scaffold + architecture)
  → Handoff: Update spec.md with arch decisions, archive registry
Sprint 2: feature-impl (core features)
  → Handoff: Update spec.md with API contracts, archive registry
Sprint 3: security-review + perf-optimization (hardening)
```

---

## Custom Formations

Custom formations are defined by specifying agent roles, file ownership, and wave structure — without requiring TeamCreate.

**Guidelines**:
- Max 5 parallel agents (beyond this, coordination overhead exceeds benefit)
- Clear file ownership per role (no overlap)
- At least one tester role per 3 implementer roles
- Security role for any auth/data handling work
- Define wave dependencies explicitly in task `blockedBy` metadata

---

## Formation Selection Flowchart

### Manual Selection (V11)

```
Is this a new project?
  YES → new-project formation
  NO ↓

Is the root cause unknown?
  YES → bug-investigation formation
  NO ↓

Is this a security audit?
  YES → security-review formation
  NO ↓

Is this performance work?
  YES → perf-optimization formation
  NO ↓

Is this a code review?
  YES → code-review formation
  NO ↓

Is this 1-3 tasks, single file?
  YES → single-file formation
  NO ↓

Is this 4-8 tasks, single layer?
  YES → lightweight-feature formation
  NO ↓

Default → feature-impl formation
```

### Difficulty-Aware Auto-Suggestion (V11)

When task metadata includes `complexity` and `scope`, the `guard-effort` hook auto-suggests the optimal formation:

| Complexity | Scope | Suggested Formation |
|------------|-------|---------------------|
| routine | small | single-file |
| routine | medium | lightweight-feature |
| medium | small | single-file or lightweight-feature |
| medium | medium | lightweight-feature |
| medium | large | feature-impl |
| complex | small | lightweight-feature or feature-impl |
| complex | medium-large | feature-impl |
| novel | any | new-project (with architect) |

**Override**: Always allowed. The suggestion is advisory.

**How it works**: The hook reads `metadata.complexity` and `metadata.scope` from TaskCreate/Task tool calls and prints a formation suggestion. Team lead can accept or override.

**Research backing**: DAAO (Difficulty-Aware Agentic Orchestration, Sept 2025): +11.21% accuracy with 36% less compute by routing easy tasks to simpler workflows.

**Helper**: Run `./scripts/suggest-formation COMPLEXITY SCOPE` to get a suggestion without the hook.

---

## Tool Policy Defaults by Formation (V11)

Each formation recipe defines a default tool profile for agents in each role. Deny-wins semantics: if any layer denies a tool, it's denied regardless of other layers allowing it.

For per-task agent assignment, tool policy is enforced by `guard-enforcement` using the agent's `tool_profile` field in its definition (`~/.claude/agents/*.md`). The `.formation-registry.json` (legacy TeamCreate) is optional — if present, its per-role overrides still apply.

### Profile Summary

| Profile | Includes | Excludes |
|---------|----------|----------|
| **full** | All tools (read, write, exec, task, team, search) | None |
| **coding** | FS (read+write) + exec + task | team, search |
| **testing** | read + exec (test commands) + task | write, edit |
| **readonly** | read + task | write, edit, exec |
| **minimal** | task only | Everything else |

### Formation Default Policies

| Formation | Default Profile | Key Role Overrides | Global Deny |
|-----------|----------------|-------------------|-------------|
| **new-project** | coding | architect: full | group:deploy |
| **feature-impl** | coding | backend/frontend: full, tester: testing (deny Write/Edit) | group:deploy |
| **bug-investigation** | coding | (none) | group:deploy |
| **security-review** | coding | threat-modeler: readonly, scanner: testing | group:deploy |
| **perf-optimization** | full | (none) | group:deploy |
| **code-review** | readonly | (none) | (none) |
| **single-file** | coding | (none) | group:deploy |
| **lightweight-feature** | coding | tester: testing (deny Write/Edit) | group:deploy |
| **swebench-solver** | coding | investigator: readonly, validator: testing (deny Write/Edit) | group:deploy |
| **business-launch** | coding | PM: full, legal-finance: readonly | group:deploy |
| **all-hands-planning** | readonly | (all reviewers readonly) | (none) |
| **codebase-audit** | readonly | (all auditors readonly) | (none) |
| **deep-research** | readonly | (all researchers readonly) | (none) |
| **pm-audit** | readonly | (all auditors readonly) | (none) |

### Resolution Chain

```
Formation defaults (tool_policies.defaults)
  -> Role overrides (tool_policies.per_role[role])
  -> Agent registry (agents[id].tool_profile)
  -> Hook enforcement (guard-enforcement)
  -> Autonomy level (guard-enforcement -> v11_check_autonomy)
```

At every layer, `deny` overrides `allow` (deny-wins).

### Overriding Policies

For per-task agent assignment: override tool profile by editing the agent definition at `~/.claude/agents/{agent}.md` (change `tool_profile`).

For legacy TeamCreate: edit `.formation-registry.json` to add tools to a role's `allow` list, change a role's `profile`, or remove `deny` entries.

**Debug tool**: `./scripts/resolve-policy AGENT_ID TOOL_NAME` shows the full resolution chain.

---

## Formation Heartbeat Protocol (V11)

Proactive health polling during active agent work. Complements reactive timeout detection (15/30/45 min tiers).

### Heartbeat Checklist

Run every N minutes (default: 10; for legacy TeamCreate, configurable via `heartbeat_interval_minutes` in `.formation-registry.json`):

```
1. TaskList -> count by status
   - pending: N | in_progress: N | completed: N/total
   - Calculate completion percentage

2. For each in_progress task:
   - Identify owner (teammate name)
   - Check last file modification in owner's directories
   - If no activity > heartbeat interval -> flag as IDLE

3. System resources:
   - Disk space (warn < 5GB)
   - Memory usage (warn > 80%)

4. Report format:
   "Formation pulse [formation-name]:
    Progress: 5/12 tasks (42%)
    Active: backend-impl (task #5), tester (task #8)
    Idle: frontend-impl (no writes in 12 min)
    Resources: OK
    ETA: ~20 min"

5. Escalation:
   - IDLE teammate -> send message asking for status
   - 2x idle in a row -> prepare restart context
   - Resources critical -> pause spawning new waves
```

### Heartbeat Interval by Formation

| Formation | Default Interval | Rationale |
|-----------|-----------------|-----------|
| new-project | 10 min | Architect phase is slow, normal |
| feature-impl | 10 min | Standard monitoring |
| bug-investigation | 5 min | Fast iteration, quick convergence |
| security-review | 15 min | Deep analysis takes time |
| perf-optimization | 15 min | Sequential subagents, less monitoring needed |
| code-review | 10 min | Standard monitoring |
| single-file | N/A | Single teammate, no heartbeat needed |
| lightweight-feature | 10 min | Standard monitoring |
| codebase-audit | 10 min | Standard monitoring |
| deep-research | 15 min | Research takes time, less monitoring |
| pm-audit | 10 min | Standard monitoring |

### Running Heartbeat

```bash
./scripts/formation-heartbeat [PROJECT]
```

Zero API calls. Reads task state JSON + `.formation-registry.json` only.

---

## Advanced: Terminal Isolation (Optional)

For formations with 3+ teammates doing heavy I/O work (builds, tests, docker operations), team lead can optionally dispatch teammates to isolated terminal sessions using tmux:

```bash
# Create isolated session for a teammate
tmux new-session -d -s "teammate-backend" "claude --team my-project --name backend-impl"
tmux new-session -d -s "teammate-frontend" "claude --team my-project --name frontend-impl"

# Monitor all teammates
tmux list-sessions
```

**When to use**: Only when teammates run long-running bash commands (builds, test suites, docker operations) that could interfere with each other's I/O. Standard Agent Teams via the Task tool handle most scenarios without terminal isolation.

**When NOT to use**: File editing, task management, code review — these don't benefit from terminal isolation and the added complexity is not justified.

---

## Formation 10: business-launch

**When**: New business or product launch requiring multi-function planning across operations, legal, finance, marketing, and business development. Use when a project needs business strategy alongside engineering — not just code.

**Mode**: Parallel background agents (not teams). Business research tasks are independent.

**Teammates**:
| Role | Default Agent | Specialist Upgrade | Output |
|------|--------------|-------------------|--------|
| Project Manager | spec-planner-v11 | technical-pm | Team charter, sprint plan, task breakdown, synthesis |
| Operations | spec-implementer-v11 | sre-specialist | Fulfillment plan, SOPs, partner pipeline, inventory |
| Growth | spec-implementer-v11 | App-Design | GTM strategy, ad campaigns, SEO plan, launch playbook |
| Legal & Finance | spec-reviewer-v11 | data-privacy-engineer, Excel-AI | Legal checklist, financial model, entity plan, compliance |
| Business Dev | spec-integrator-v11 | ai-integration-specialist | Partner list, outreach templates, B2B strategy, competitive intel |

**Task Flow**:
```
Wave 0: Project Manager (planning)
  Output: team_charter, scope, budget, timeline
    │
    ▼
Wave 1: (Operations + Growth + Legal/Finance + BD) in parallel
  Each produces specialist report with spec.md additions
    │
    ▼
Wave 2: Orchestrator synthesizes into:
  - Updated spec.md (business dependencies section)
  - ROADMAP.md (unified engineering + business timeline)
  - Phase gates with pass/fail criteria
  - Task list (engineering + business tasks)
```

**Key Insight from KeyMakers.ai (first deployment)**:
- Business research tasks (#25 Competitive, #26 Financial) are perfect for **background agents** — independent, no coordination needed, use Sonnet (cheap)
- Human-action tasks (#23 Atlantic Lock calls, #24 Legal entity filing) CANNOT be automated — create them as tasks with clear instructions but mark owner as "human"
- The Explore agent is READ-ONLY — orchestrator must save its output to files
- Excel-AI excels at financial modeling with scenario analysis
- 4 parallel specialist reviews + 1 synthesis pass produces spec.md that's 3-4x more thorough than solo authoring

**Specific Rules**:
- Wave 0 (PM) produces the plan BEFORE specialists start
- Wave 1 agents work independently — no shared state needed (use background agents, not teams)
- Wave 2 synthesis is done by orchestrator, not an agent (saves context by reading artifacts directly)
- Business tasks that need human action get `metadata.owner = "human"` and clear step-by-step instructions
- Financial model tasks should use Excel-AI agent for scenario analysis
- Competitive research should use Explore agent (thorough web search)
- All outputs saved to `docs/` subdirectories (research/, investor/, ops/)

**Cost Model**:
| Approach | Model | Cost | Duration |
|----------|-------|------|----------|
| 4 background agents | Sonnet (definition model) | ~$2-4 | 5-15 min each |
| Orchestrator synthesis | Opus (main session) | ~$1-2 | 5 min |
| Total | Mixed | ~$3-6 | 15-20 min wall time |

**Comparison**: Solo-authoring all 4 reports would cost ~$8-12 in Opus context and take 60+ min sequentially. Parallel background agents are 3-4x faster and 50% cheaper.

---

## Formation 11: all-hands-planning

**When**: Spec refinement requiring cross-functional review before build begins. Use when you have a draft spec.md and need architecture, security, frontend, and business validation in parallel.

**Mode**: Parallel background agents (read-only review) + orchestrator synthesis.

**Teammates**:
| Role | Default Agent | Specialist Upgrade | Lens |
|------|--------------|-------------------|------|
| Architecture Reviewer | spec-architect-v11 | backend-architect, database-engineer | Endpoints, schema, Docker, pipeline |
| Security Reviewer | spec-security-v11 | security-engineer, auth-specialist | Threat model, encryption, compliance |
| Frontend Reviewer | spec-reviewer-v11 | frontend-specialist, App-Design | Routes, components, UX, performance |
| Business Reviewer | spec-planner-v11 | Excel-AI, Explore | Roadmap, unit economics, legal, KPIs |

**Task Flow**:
```
All 4 reviewers launch in parallel (background agents)
  │
  Each produces:
  │  1. Specialist report (saved to docs/research/)
  │  2. Proposed spec.md additions (concrete text)
  │  3. Blockers found (if any)
  │
  ▼
Orchestrator synthesizes:
  - spec.md vN+1 (incorporating all 4 reviews)
  - ROADMAP.md (if business reviewer produced timeline)
  - Updated docs/INDEX.md
  - Task list enriched with review findings
```

**Specific Rules**:
- All reviewers are READ-ONLY (they analyze, not implement)
- Each reviewer gets a focused prompt with their specific lens
- Orchestrator writes ALL output files (reviewers produce text, orchestrator saves)
- spec.md version number increments after synthesis (v1 → v2 → v3)
- Document every blocker as a task with `metadata.risk = "high"`
- Reference detailed docs in spec.md rather than duplicating content

**Key Patterns (learned from KeyMakers.ai deployment)**:
- Architecture reviewer found 3 blockers that would have cost weeks if found during build
- Security reviewer identified 5 P0 findings (RS256 not HS256, admin MFA, UUID external IDs)
- Frontend reviewer produced 40+ route map that prevented scope creep
- Business reviewer created 12-month operational playbook
- Total synthesis time: 20 min for work that would take days manually
- The Explore agent output must be saved by orchestrator (it cannot write files)

**When NOT to use**:
- Spec is <50 lines (too thin for meaningful review)
- Single-layer project (only backend or only frontend)
- Bug fix or small feature (use lightweight-feature instead)

---

## Formation Selection Flowchart (Updated)

```
Is this a new business/product launch?
  YES → business-launch formation (if business planning needed)
       → all-hands-planning formation (if spec review needed)
  NO ↓

Is this a new project?
  YES → new-project formation
  NO ↓

Is the root cause unknown?
  YES → bug-investigation formation
  NO ↓

Is this a security audit?
  YES → security-review formation
  NO ↓

Is this performance work?
  YES → perf-optimization formation
  NO ↓

Is this a code review?
  YES → code-review formation
  NO ↓

Is this 1-3 tasks, single file?
  YES → single-file formation
  NO ↓

Is this 4-8 tasks, single layer?
  YES → lightweight-feature formation
  NO ↓

Default → feature-impl formation
```

---

## Formation 12: codebase-audit

**When**: Full codebase review from multiple angles — security, performance, code quality, database, test coverage. Pre-build assessment, quarterly audit, post-incident review, or optimization planning.

**Mode**: Parallel background agents (default) or Agent Team for coordinated audits.

**Teammates**:
| Role | Default Agent | Specialist Upgrade | Lens |
|------|--------------|-------------------|------|
| Security Auditor | spec-security-v11 | security-engineer | OWASP Top 10, secrets, auth, injection, CORS |
| Code Quality Reviewer | spec-reviewer-v11 | code-quality-engineer | SOLID, tech debt, smells, duplication |
| Performance Profiler | spec-optimizer-v11 | performance-optimizer | N+1 queries, bundle size, caching gaps, bottlenecks |
| Database Inspector | spec-implementer-v11 | database-engineer | Schema, indexes, migrations, connection pooling |
| Test Coverage Analyst | spec-tester-v11 | testing-engineer | Coverage gaps, untested paths, E2E deficits |

**Optional 6th Role** (for large codebases >500K LOC):
| Architecture Reviewer | spec-architect-v11 | backend-architect | Service boundaries, API contracts, scalability |

**Task Flow**:
```
Phase 0: Scope (orchestrator, 2 min)
  → Scan directory, estimate LOC, detect tech stack
  → Select agent roster based on stack
  → Create finding task template for agents

Phase 1: Discovery (5 parallel agents, 10-15 min)
  → Each agent scans full codebase through their lens
  → Each creates TaskCreate with metadata.type="finding"
  → Output: ~20-50 raw findings per agent

Phase 2: Synthesis (orchestrator, 5 min)
  → Run: ./scripts/synthesize-findings PROJECT
  → Deduplicate by file:line_start:category
  → Reconcile severity (3+ agents = high confidence)
  → Generate issues.md + issues.json

  ──── GATE: User reviews backlog ────

Phase 3: Spec Generation (optional)
  → Run: ./scripts/findings-to-spec PROJECT
  → Convert CRITICAL + HIGH findings into spec.md
  → Select fix formation (security-review, feature-impl, etc.)
```

**Execution Patterns**:

| Pattern | When | Cost | Duration |
|---------|------|------|----------|
| **A: Parallel background agents** | <500K LOC, routine audit | $3-4 | 12-18 min |
| **B: Agent Team** | >500K LOC, agents need shared context | $6-8 | 20-30 min |

**Pattern A** (recommended — cheaper, faster):
```python
# Spawn 5 parallel background agents
for lens in [security, quality, performance, database, testing]:
    Agent(
        subagent_type=lens.agent,
        prompt=f"""Audit {codebase_path} for {lens.focus}.
        For each finding, create a task:
        TaskCreate(
            subject="[{SEVERITY}] {title}",
            metadata={{
                "project": "{project}",
                "sprint": "sprint-01-audit",
                "risk": "low",
                "type": "finding",
                "severity": "{critical|high|medium|low}",
                "finding": {{
                    "category": "{lens.category}",
                    "location": {{"file": "...", "line_start": N}},
                    "problem": "...",
                    "fix": "...",
                    "impact": "...",
                    "confidence": "high|medium|low"
                }}
            }}
        )""",
        model="sonnet",
        run_in_background=True
    )
```

**Pattern B** (for coordinated audits needing shared findings):
```
TeamCreate → TaskCreate (5 audit tasks) → spawn 5 teammates → heartbeat → synthesis
```

**Specific Rules**:
- ALL audit agents are **READ-ONLY** (readonly tool profile)
- Orchestrator handles ALL file writes (issues.md, issues.json, spec.md)
- Finding tasks use `metadata.type = "finding"` with structured `finding` object
- Each finding must include: category, location (file + line), problem, fix, impact
- Phase 2 synthesis is NOT an agent — it's a script (`synthesize-findings`)
- Phase 3 spec generation is optional (user may want to review backlog first)

**Adversarial Verification**:
- Each auditor defaults to FAIL stance — code must prove correctness
- Findings require file:line citations and confidence levels
- Cross-agent agreement (3+ agents flag same location) auto-promotes to high confidence

**Cost Model**:
| Approach | Agents | Model | Cost | Duration |
|----------|--------|-------|------|----------|
| Parallel (5 Sonnet) | 5 background | Sonnet | $3-4 | 12-18 min |
| Team (5 Opus) | 5 teammates | Opus (lead) | $6-8 | 20-30 min |
| Hybrid (4 Sonnet + 1 Opus architect) | 4 bg + 1 fg | Mixed | $5-6 | 15-22 min |

**When NOT to use**:
- Single-file bug fix (use single-file formation)
- Known bug with clear root cause (use bug-investigation)
- PR review (use code-review formation)
- <100 LOC project (just read it yourself)

---

## Finding Synthesis Protocol

When multiple audit agents produce findings in parallel, the orchestrator synthesizes their output into a unified, deduplicated backlog.

### Finding Task Format

Each audit agent creates findings as tasks with structured metadata:

```python
TaskCreate(
    subject="[HIGH] Shell injection via create_subprocess_shell",
    description="asyncio.create_subprocess_shell() passes LLM-provided commands directly to shell.",
    metadata={
        "project": "nova-forge",
        "sprint": "sprint-01-audit",
        "risk": "low",
        "type": "finding",
        "severity": "critical",
        "finding": {
            "category": "security",
            "location": {
                "file": "forge_agent.py",
                "line_start": 1472,
                "line_end": 1478,
                "context": "asyncio.create_subprocess_shell(cmd, ...)"
            },
            "problem": "Shell execution passes LLM commands directly. RiskClassifier regex is bypassable via base64, variable indirection, hex escapes.",
            "fix": "Run bash commands inside Docker containers, or use command allowlist instead of denylist.",
            "impact": "sandbox-bypass",
            "confidence": "high"
        }
    }
)
```

### Deduplication Rules

1. **Exact match**: Same `file:line_start:category` = duplicate → merge, increment `found_by` list
2. **Same file, different category**: Distinct findings (e.g., security + performance on same file)
3. **Confidence aggregation**: If N >= 3 agents independently flag same location → confidence = high
4. **Near-match**: Same file, lines within 5 of each other, same category → suspected duplicate, flag for review
5. **Cross-file**: Same problem description on different files → group as pattern, not duplicate

### Severity Reconciliation

When multiple agents rate the same finding differently:
- **Majority wins**: 3/5 agents say HIGH → HIGH
- **Escalation bias**: If any agent says CRITICAL, minimum is HIGH (security principle)
- **Confidence weighting**: HIGH-confidence agent's rating weighted 2x vs LOW-confidence

### Ranking Algorithm

```
1. Sort by severity: CRITICAL > HIGH > MEDIUM > LOW
2. Within severity: Sort by agent_count DESC (more agents = higher priority)
3. Within agent_count: Sort by confidence DESC
4. Within confidence: Sort by category priority (security > reliability > performance > rest)
```

### Synthesis Output

The `synthesize-findings` script produces two artifacts:

**issues.json** (machine-readable):
```json
{
  "project": "nova-forge",
  "audit_date": "2026-03-15",
  "agents": ["security-engineer", "code-quality-engineer", "performance-optimizer", "database-engineer", "testing-engineer"],
  "summary": {
    "critical": 1, "high": 12, "medium": 24, "low": 28,
    "total_raw": 57, "total_deduped": 35, "dedup_rate": 0.39
  },
  "findings": [
    {
      "id": "C1",
      "severity": "critical",
      "category": "security",
      "location": { "file": "forge_agent.py", "line_start": 1472, "line_end": 1478 },
      "problem": "Shell injection via create_subprocess_shell",
      "fix": "Run bash commands inside Docker containers",
      "impact": "sandbox-bypass",
      "confidence": "high",
      "found_by": ["security-engineer", "code-quality-engineer"],
      "agent_count": 2
    }
  ]
}
```

**issues.md** (human-readable, matches Nova Forge pattern):
```markdown
# Codebase Audit — {project} ({date})

> {N} agents, {raw} raw findings, {deduped} after deduplication.
> Agents: {agent-list}

---

## CRITICAL ({count})

### C1. {title}
- **File**: {path}:{line_start}-{line_end}
- **Problem**: {description}
- **Fix**: {remediation}
- **Found by**: {agent_1}, {agent_3} (confidence: high)

---

## HIGH ({count})
...

## MEDIUM ({count})
...

## LOW ({count})
...
```

### Findings-to-Spec Pipeline

After synthesis, optionally convert findings to a V11 spec for fix execution:

```bash
./scripts/findings-to-spec PROJECT
```

This generates:
1. `spec.md` with CRITICAL + HIGH findings as tasks
2. Suggests appropriate fix formation:
   - Mostly security findings → security-review formation
   - Mixed findings → feature-impl formation
   - Performance-only → perf-optimization formation
3. Creates sprint tasks with `blockedBy` dependencies where fixes depend on each other

### Finding Task Lifecycle

```
Agent creates finding task (type=finding, severity, structured metadata)
  → sync-tasks hook updates findings_summary in task-state
  → synthesize-findings script deduplicates and ranks
  → findings-to-spec converts backlog to spec.md + sprint tasks
  → Fix formation executes remediation
  → Finding tasks marked completed as fixes land
```

---

## Formation Selection Flowchart (Updated)

```
Is this a full codebase audit?
  YES → codebase-audit formation
  NO ↓

Is this a new business/product launch?
  YES → business-launch formation (if business planning needed)
       → all-hands-planning formation (if spec review needed)
  NO ↓

Is this a new project?
  YES → new-project formation
  NO ↓

Is the root cause unknown?
  YES → bug-investigation formation
  NO ↓

Is this a security audit?
  YES → security-review formation
  NO ↓

Is this performance work?
  YES → perf-optimization formation
  NO ↓

Is this a code review?
  YES → code-review formation
  NO ↓

Is this 1-3 tasks, single file?
  YES → single-file formation
  NO ↓

Is this 4-8 tasks, single layer?
  YES → lightweight-feature formation
  NO ↓

Default → feature-impl formation
```

---

## Formation 13: deep-research

**When**: Parallel research for complex/novel projects requiring broad exploration before committing to an approach. Typically triggered via deep-plan mode (Phase 3-DP).

**Mode**: Parallel background agents (not teams). Research tasks are independent.

**Teammates**:
| Role | Default Agent | Specialist Upgrade | Output |
|------|--------------|-------------------|--------|
| Research Lead | spec-architect-v11 | ai-integration-specialist | Research synthesis, hypothesis refinement, approach recommendation |
| Researcher 1 | spec-implementer-v11 | backend-architect | Technical feasibility analysis, prototype findings |
| Researcher 2 | spec-implementer-v11 | frontend-specialist | UX/interface research, competitive analysis |
| Researcher 3 | spec-implementer-v11 | database-engineer | Data model exploration, scalability research |

**Task Flow**:
```
Wave 0: Research Lead (scope + hypotheses)
  Output: research questions, hypothesis priors, approach options
    |
    v
Wave 1: (Researcher 1 + Researcher 2 + Researcher 3) in parallel
  Each explores one hypothesis or research question
  Output: evidence, updated priors, feasibility assessment
    |
    v
Wave 2: Research Lead synthesizes
  Output: updated .plan-context.json, recommendation for Go/Pivot/Kill
```

**Specific Rules**:
- All researchers are READ-ONLY (no code modifications)
- Research Lead defines questions before researchers start
- Each researcher covers a distinct area (no overlap)
- Outputs saved to `research/` directory in session
- Updated hypothesis probabilities written to `.plan-context.json`
- Gate review after synthesis determines whether to proceed to implementation

**Cost Model**:
| Approach | Model | Cost | Duration |
|----------|-------|------|----------|
| 3 background researchers | Sonnet | ~$2-4 | 10-15 min each |
| Research Lead synthesis | Opus | ~$1-2 | 5 min |
| Total | Mixed | ~$3-6 | 15-20 min wall time |

---

## Formation 14: pm-audit

**When**: Audit research output for gaps, contradictions, and missed perspectives before committing to a plan. Typically used after deep-research (F13) in the deep-plan pipeline (Phase 4).

**Mode**: Parallel background agents (not teams). Audit tasks are independent.

**Teammates**:
| Role | Default Agent | Specialist Upgrade | Lens |
|------|--------------|-------------------|------|
| Research Auditor | spec-reviewer-v11 | code-quality-engineer | Evidence quality, methodology gaps, hypothesis validity |
| Landscape Auditor | spec-planner-v11 | ai-integration-specialist | Market/competitive gaps, prior art, alternative approaches |
| Spec Auditor | spec-planner-v11 | spec-reviewer-v11 | Spec completeness, constraint conflicts, risk coverage |

**Task Flow**:
```
All 3 auditors launch in parallel (background agents)
  |
  Each produces:
  |  1. Audit report (saved to research/)
  |  2. List of gaps found
  |  3. Severity rating per gap (critical/high/medium/low)
  |
  v
Orchestrator synthesizes:
  - Updated .plan-context.json (decisions, kill conditions)
  - Gap report for user review
  - Go/Iterate/Pivot/Kill recommendation
```

**Specific Rules**:
- All auditors are READ-ONLY (they analyze, not implement)
- Each auditor applies ONE lens only (research quality, landscape, spec)
- Auditors default to FAIL stance — research must prove completeness
- Critical gaps block Phase 5 (restructuring) until resolved
- Findings use structured format: gap description + severity + recommendation
- Outputs saved to `research/audit/` directory

**Adversarial Verification**:
- Research Auditor challenges evidence quality and methodology
- Landscape Auditor identifies missed alternatives and prior art
- Spec Auditor validates constraint completeness and risk coverage
- Any CRITICAL gap → mandatory iteration before proceeding

**Cost Model**:
| Approach | Model | Cost | Duration |
|----------|-------|------|----------|
| 3 background auditors | Sonnet | ~$2-3 | 8-12 min each |
| Orchestrator synthesis | Opus | ~$1 | 3 min |
| Total | Mixed | ~$3-4 | 12-15 min wall time |

---

## Formation Selection Flowchart (Complete)

```
Is this deep research for a complex/novel project?
  YES → deep-research formation (Phase 3-DP)
       → pm-audit formation (Phase 4, after research)
  NO ↓

Is this a full codebase audit?
  YES → codebase-audit formation
  NO ↓

Is this a new business/product launch?
  YES → business-launch formation (if business planning needed)
       → all-hands-planning formation (if spec review needed)
  NO ↓

Is this a new project?
  YES → new-project formation
  NO ↓

Is the root cause unknown?
  YES → bug-investigation formation
  NO ↓

Is this a security audit?
  YES → security-review formation
  NO ↓

Is this performance work?
  YES → perf-optimization formation
  NO ↓

Is this a code review?
  YES → code-review formation
  NO ↓

Is this 1-3 tasks, single file?
  YES → single-file formation
  NO ↓

Is this 4-8 tasks, single layer?
  YES → lightweight-feature formation
  NO ↓

Default → feature-impl formation
```

---

*V11 Formations -- Task-Template Recipes (14 formations, V11.11+: apply via metadata.agent + background agents)*
