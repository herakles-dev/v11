# V11 Protocol Fundamentals

> **Common patterns for all V11 spec agents**. Referenced by all agent .md files to reduce redundancy.

---

## Task Workflow

### Before Any Work

**ALWAYS start with these commands:**

```python
# 1. Check current state
TaskList()

# 2. Get assignment details
task = TaskGet(taskId)

# 3. Claim the task
TaskUpdate(taskId, status="in_progress")
```

**Critical**: Never work without an `in_progress` task. The `guard-write-gates` hook enforces this — but only on a genuine stall (a session that HAD a task in_progress and let it lapse); a fresh/spawned session that hasn't yet touched the task system is guided with a stderr advisory pointing at `/v11`, not blocked (V11.34, `V11_WRITE_GATE`).

### Task Metadata Reference (Phase 4.5)

**When creating tasks**, include extended metadata for smart routing:

```python
TaskCreate(
    subject="Add user timezone support",
    description="Store user timezone preference and convert timestamps",
    activeForm="Adding user timezone support",
    metadata={
        "project": "project-alpha",
        "sprint": "sprint-02-features",
        "gate": "gate-2-api-ready",
        "risk": "low",

        # Extended fields for effort estimation
        "complexity": "medium",      # Known pattern (timezone handling)
        "scope": "medium",           # ~100 lines across 4 files
        "parallelizable": True,

        "agent": "spec-implementer-v11"
    }
)
```

**Metadata Fields**:
- `complexity`: novel|complex|medium|routine (task novelty)
- `scope`: small|medium|large (code change volume)
- `parallelizable`: true|false (can background agents work in parallel?)

See [CLAUDE.md Section 4](../CLAUDE.md#4-state-management) for complete field definitions and validation rules.

### During Work

**Progress reporting pattern:**

When working as an agent, update task description to include progress notes:
```python
TaskUpdate(
    taskId="task-05",
    description="Implementing user login endpoint. JWT middleware complete, working on validation."
)
```

### After Completion

**ALWAYS finish with:**

```python
TaskUpdate(
    taskId="task-05",
    status="completed",
    description="Implemented user login with JWT authentication"
)
```

**On failure or blocker:**

```python
# Create a blocking task
TaskCreate(
    subject="Fix: Test failure in auth endpoint",
    description=f"Test {test_name} failed: {error}",
    metadata={
        "project": "project-alpha",
        "sprint": "sprint-02-features",
        "gate": "gate-2-api-ready",
        "risk": "low",
        "complexity": "routine",  # Bugfix for known issue
        "scope": "small",         # Localized fix
        "type": "bugfix",
        "blocking": "task-05"
    }
)

# Link as blocker
TaskUpdate(taskId="task-05", addBlockedBy=["task-06"])
```

---

## Artifact Handoffs (V11)

### Producing Artifacts (Implementers, Integrators)

When completing a task, include structured artifacts so downstream agents know what changed:

```python
TaskUpdate(
    taskId="task-05",
    status="completed",
    metadata={
        "artifacts": {
            "trace_id": "f3b9e2f4-91d1-4d74-9a32-3c5b48fa2a63",
            "summary": "Added JWT auth with refresh token rotation",
            "handoff_note": "JWT_SECRET env var required. Refresh token test is timing-sensitive.",
            "files_changed": ["src/auth.ts", "src/middleware.ts"],
            "files_created": ["src/models/User.ts"],
            "api_contract": {
                "POST /auth/login": "{ email, password } -> { token, refreshToken }",
                "POST /auth/refresh": "{ refreshToken } -> { token }"
            },
            "test_hints": [
                "Test token expiry at 15min boundary",
                "Test refresh token rotation",
                "Test invalid credentials return 401"
            ],
            "config_changes": {"JWT_SECRET": "Required env var (add to .env)"},
            "breaking_changes": [],
            "dependencies_added": ["jsonwebtoken@9.0.2"]
        }
    }
)
```

### Consuming Artifacts (Testers, Reviewers)

When claiming a task that has `blockedBy` dependencies, check upstream artifacts:

1. The `sync-tasks` hook automatically persists artifacts from completed tasks
2. Read upstream context: `files_changed` tells you what to test/review
3. Use `test_hints` to prioritize test scenarios
4. Check `api_contract` for integration test targets
5. Verify `config_changes` are applied before running tests

### External Storage for Large Artifacts

Artifacts >2KB are stored at `sessions/{project}/artifacts/{task_id}/`:

```python
# When producing large output (API specs, analysis reports):
# Store externally and reference via artifact_refs
metadata={
    "artifacts": {
        "summary": "Full API spec generated",
        "artifact_refs": [
            {
                "name": "api-spec.json",
                "path": "sessions/my-project/artifacts/task-05/api-spec.json",
                "summary": "OpenAPI 3.0 spec for auth endpoints",
                "size_bytes": 4200
            }
        ]
    }
}
```

### What to Include in Artifacts

| Role | Always Include | When Relevant |
|------|---------------|---------------|
| **Implementer** | files_changed, summary | api_contract, config_changes, dependencies_added |
| **Integrator** | files_changed, api_contract | config_changes, breaking_changes |
| **Architect** | summary, handoff_note | artifact_refs (for design docs) |
| **Tester** | summary (test results) | test_hints (for next tester) |

---

## Metadata Usage Examples

### Example 1: Novel Architecture Task

```python
TaskCreate(
    subject="Design GraphQL federation schema",
    description="Design multi-service GraphQL federation using Apollo Federation v2",
    activeForm="Designing GraphQL federation schema",
    metadata={
        "project": "project-beta",
        "sprint": "sprint-01-foundation",
        "gate": "gate-1-architecture",
        "risk": "high",              # Foundational, new pattern
        "complexity": "novel",       # First-time federation
        "scope": "large",            # Affects multiple services
        "parallelizable": False,     # Needs single architect first
        "agent": "spec-architect-v11"
    }
)
```

**Why these choices**:
- `complexity=novel`: No federation in codebase, requires research
- `scope=large`: Multi-service impact, architectural changes
- `parallelizable=false`: Architecture must be designed cohesively
- `risk=high`: Foundational decision with wide impact

### Example 2: Complex Algorithm

```python
TaskCreate(
    subject="Implement DTW algorithm with Sakoe-Chiba constraint",
    description="Add dynamic time warping with band parameter for performance",
    activeForm="Implementing DTW with Sakoe-Chiba constraint",
    metadata={
        "project": "project-gamma",
        "sprint": "sprint-03-algorithms",
        "gate": "gate-2-core-complete",
        "risk": "medium",            # Established algorithm, new to codebase
        "complexity": "complex",     # Intricate implementation
        "scope": "medium",           # ~150 lines, 2 files
        "parallelizable": True,
        "agent": "spec-implementer-v11"
    }
)
```

**Why these choices**:
- `complexity=complex`: Known algorithm but intricate to implement correctly
- `scope=medium`: Moderate code volume, localized to audio module
- `parallelizable=true`: Can work alongside other features
- `risk=medium`: Important for core functionality but not architectural

### Example 3: Routine Boilerplate

```python
TaskCreate(
    subject="Add REST endpoints for CRUD operations",
    description="Generate standard REST endpoints for User, Product, Order models",
    activeForm="Adding REST endpoints for CRUD operations",
    metadata={
        "project": "project-delta",
        "sprint": "sprint-01-scaffold",
        "gate": "gate-1-api-scaffold",
        "risk": "low",
        "complexity": "routine",     # Standard CRUD pattern
        "scope": "large",            # Many endpoints (~300 lines)
        "parallelizable": True,      # Can split by resource
        "agent": "spec-implementer-v11"
    }
)
```

**Why these choices**:
- `complexity=routine`: Copy-paste CRUD pattern from examples
- `scope=large`: Lots of boilerplate code but straightforward
- `parallelizable=true`: Each model can be done independently
- `risk=low`: Well-established pattern, low chance of issues

---

## File Ownership Rules

**V11.11 model**: File ownership is informational, not enforcement-enforced. Each task declares which files it touches via the task description. Background agents coordinate by task boundaries — agents claim a task, then edit only the files described in that task. The `guard-write-gates` hook no longer enforces formation-based file ownership; that cascade has been removed.

The `.formation-registry.json` ownership cascade from earlier V11 versions is legacy/dormant. Do not create or rely on it for new work.

### Typical Ownership by Task Role

| Role | Files Typically Described in Task |
|------|----------------------------------|
| **Architect** | Architecture decision records, system design docs, config templates |
| **Implementer** | Source code in assigned modules, business logic |
| **Integrator** | docker-compose.yml, nginx configs, API contracts, health checks |
| **Tester** | Test files, validation scripts |
| **Security** | Security scan reports, threat models |
| **Reviewer** | Read-only access, review reports |

### Avoiding File Conflicts

When two tasks need to touch the same file, sequence them — mark the second task `blockedBy` the first. Parallel agents must not edit the same file simultaneously.

---

## Agent Coordination Patterns (V11.11)

**V11.11 model**: Orchestrator-coordinated background agents with TaskUpdate-based handoffs. TeamCreate and teammate-to-teammate messaging are deprecated. Agent Teams (SendMessage, broadcast, team lead protocols) are a legacy pattern — see note below.

### Primary Coordination: TaskUpdate Handoffs

Background agents coordinate exclusively through the task system:

1. **Shared Task List**: Create tasks with `blockedBy` to sequence dependencies
2. **Artifact Handoffs**: Use `metadata.artifacts` on TaskUpdate(completed) so downstream agents see what changed
3. **File System**: Write results to agreed paths (e.g., `sessions/{project}/artifacts/`)

### Signaling Completion

```python
# When done, mark completed with structured artifacts
TaskUpdate(
    taskId="task-05",
    status="completed",
    metadata={
        "artifacts": {
            "summary": "Auth module complete. JWT_SECRET must be set.",
            "files_changed": ["src/auth.ts", "src/middleware.ts"],
            "api_contract": {"POST /auth/login": "{ email, password } -> { token }"}
        }
    }
)
```

Downstream agents unblock automatically when their `blockedBy` task completes.

### Signaling Blockers

```python
TaskCreate(
    subject="BREAKING: Docker network change — all services affected",
    description="Docker network changed to project-internal. All services must update docker-compose.yml.",
    metadata={"risk": "medium", "project": "{project}", "sprint": "{sprint}"}
)
# Then link blockers on dependent tasks
TaskUpdate(taskId="task-06", addBlockedBy=["task-07"])
```

---

## Agent Spawn Template

When spawning a background agent, provide this structured context:

```
## Role
{role} — {one-line description}

## Project Context
- Project: {project name}
- Spec: {key intent from spec.md, 2-3 sentences}
- Stack: {tech stack summary}

## Your Tasks
Claim these task IDs from the shared task list:
- Task #{id}: {subject} — {brief description}
- Task #{id}: {subject} — {brief description}

## Files to Touch
- {path or glob pattern relevant to your tasks}

## Key Files to Read First
- {path to main file relevant to tasks}

## Constraints
- {any project-specific constraints from spec.md}
- Do NOT edit files outside your task scope
- Create tasks for discoveries or blockers
```

**What to include**: Role, task IDs, file scope, relevant paths, project constraints.

**What NOT to include**: Full CLAUDE.md (agents inherit it automatically), conversation history, implementation opinions.

---

## Legacy: Agent Teams (Deprecated in V11.11)

The Agent Teams model (TeamCreate, SendMessage, teammate-to-teammate messages, team lead protocols) is deprecated. Existing teams created before V11.11 continue to work but new work should use orchestrator-coordinated background agents instead.

Key differences:

| V11.10 (Teams) | V11.11 (Background Agents) |
|----------------|---------------------------|
| TeamCreate + isolated task list | Main task list, no TeamCreate |
| SendMessage for real-time comms | TaskUpdate artifacts for handoffs |
| Team lead assigns via SendMessage | Orchestrator assigns via task metadata |
| .formation-registry.json ownership | Task description declares file scope |

---

## Verification Steps

### Three-Level Verification

Every code change should pass three verification levels:

#### Level 1: Syntax

```bash
# TypeScript/JavaScript
npm run typecheck 2>/dev/null || npx tsc --noEmit

# Python
python -m py_compile src/main.py
mypy src/main.py
```

**Hook**: `verify-syntax` fires post-Write/Edit

#### Level 2: Logic

```bash
# Unit tests
npm test -- --run 2>/dev/null
pytest tests/unit/

# Lint
npm run lint 2>/dev/null
ruff check .
```

#### Level 3: Integration

```bash
# Service health check
curl -sf http://localhost:${PORT}/health

# Integration tests
npm run test:integration
pytest tests/integration/
```

### On Error Pattern

**DO NOT mark task completed if verification fails:**

```python
if typecheck_failed or test_failed:
    # Fix the issue
    Edit(file_path, buggy_code, fixed_code)

    # Re-verify
    run_verification()

    # If still failing, create blocker task
    if still_failing:
        TaskCreate(
            subject="Fix: Verification failure in task-05",
            description=f"Verification failed: {error_details}",
            metadata={"type": "bugfix", "blocking": "task-05"}
        )
        TaskUpdate(taskId="task-05", addBlockedBy=["blocker-task-id"])
```

### Before/After/On Error Summary

| Phase | Actions |
|-------|---------|
| **Before** | TaskList → TaskGet → TaskUpdate(in_progress) |
| **During** | Read existing files → Make changes → Verify syntax |
| **After** | Verify logic → Verify integration → TaskUpdate(completed) |
| **On Error** | Fix if quick → Create blocker if complex → Never mark completed |

---

## Risk Awareness

All agents must respect the risk matrix:

| Risk Level | Examples | Action |
|------------|----------|--------|
| **Low** | Read files, check status, run tests | Proceed directly |
| **Medium** | Edit code, create files, restart services | Check autonomy grants |
| **High** | Delete data, deploy to production, auth changes | Explicit user approval required |

**Hook**: `guard-enforcement` blocks high-risk actions without approval

---

## Read Before Write

**CRITICAL RULE: Never assume file contents**

```python
# BAD: Assume file structure
Edit(file_path="src/auth.ts", old_string="export const", new_string="...")

# GOOD: Read first, then edit
content = Read(file_path="src/auth.ts")
# Now you know the exact content
Edit(file_path="src/auth.ts", old_string=content.lines[10], new_string="...")
```

**Why**: Files change. Other teammates may have modified them. Git branches may differ.

---

## Adversarial Verification Protocol (V11)

### For Testers (spec-tester-v11)

Two-phase process — never combine judgment with fix suggestions:

| Phase | Action | Output |
|-------|--------|--------|
| 1. JUDGE | Assess task requirements vs code behavior | Discrepancy list |
| 2. REPORT | Document findings with evidence | STATUS: `done` or `retry` |

**Requirements**:
- Every finding cites `file:line`
- Every finding rated `HIGH` / `MEDIUM` / `LOW` confidence
- STATUS is binary: `done` or `retry` (never partial)
- Default position: FAIL until evidence proves success

### For Reviewers (spec-reviewer-v11)

Three-phase behavioral comparison — never combine phases:

| Phase | Action | Output |
|-------|--------|--------|
| 1. SPEC SUMMARY | Summarize what the task requires (no code) | Requirement list |
| 2. CODE SUMMARY | Summarize what the code does (no spec) | Behavior list |
| 3. GAP ANALYSIS | Compare phases 1 and 2 | Discrepancy findings |

**Requirements**:
- Every finding cites `file:line`
- Every finding rated `HIGH` / `MEDIUM` / `LOW` confidence
- VERDICT is binary: `approved` or `rejected`
- One lens per pass (correctness OR security OR performance)

### Research Backing

| Pattern | Accuracy | Source |
|---------|----------|--------|
| Three-phase behavioral comparison | 85.4% RCRR | ASE'25 |
| Single-pass judgment | 52.4% RCRR | ASE'25 |
| Combined judge+explain+fix | 11.0% RCRR | ASE'25 |
| Adversarial critic (hallucination reduction) | 11.3% → 3.8% | Insurance paper (p=0.003) |
| Anti-conformity debate improvement | +13-16.5% | Free-MAD (ICLR 2026) |

---

## Agent Capabilities & Limitations

**Official limitation**: Subagents cannot spawn sub-subagents. Background agents cannot spawn their own agents. This is a Claude Code hard limit.

### What You CAN Do as a Background Agent

| Capability | How |
|-----------|-----|
| Use Skills | Preloaded via `skills:` frontmatter field, invoked with Skill tool |
| Use MCP tools | gmail, github, hugging-face, etc. |
| Use all standard tools | Read, Write, Edit, Bash, Grep, Glob |
| Create/update tasks | In the shared main task list |
| Deep codebase exploration | Use Explore agent type (read-only, allowed) |

### What You CANNOT Do

- Spawn subagents or sub-agents
- See other agents' conversation history

### Workarounds for Complex Subtasks

Instead of spawning a subagent, use these strategies:
1. **Comprehensive prompts**: Ask the orchestrator to include all subtask details in your initial prompt
2. **Skills**: Use preloaded skills for specialized work (e.g., `/test`, `/deploy`)
3. **Blocker tasks**: Create a blocker task asking the orchestrator to spawn a separate agent for the complex work
4. **MCP tools**: Use available MCP tools for external integrations

---

## Summary Checklist

Before claiming a task:
- [ ] TaskList executed
- [ ] TaskGet executed with correct taskId
- [ ] Task is not blocked by dependencies
- [ ] Task is not already claimed by another agent

Before editing a file:
- [ ] File read with Read tool
- [ ] File is within this task's declared scope
- [ ] TaskUpdate(status="in_progress") executed

Before marking task complete:
- [ ] Syntax verification passed
- [ ] Logic verification passed
- [ ] Integration verification passed (if applicable)
- [ ] No verification failures

---

*V11 Protocol Fundamentals — Referenced by all spec-*-v11 agents*
