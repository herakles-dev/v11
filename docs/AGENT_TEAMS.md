# Execution Approaches — Detailed Reference

> V11.11: Per-task agent assignment is the primary coordination model. TeamCreate is deprecated.
> For formation recipes (which agents handle which roles), see [FORMATIONS.md](FORMATIONS.md).

---

## Execution Approach Selection

| Approach | When | Task List | Model Cost | Example |
|----------|------|-----------|------------|---------|
| **Direct** | 1-3 tasks, sequential | Main list | Main session model | Bug fix, config change |
| **Foreground subagent** | Single deep-expert task, need result before next step | None | Definition model | Security audit, perf profiling |
| **Background agents** | 3-8 independent tasks, no handoffs needed | None | Definition model | Parallel feature work |
| **Per-task agent assignment** | Any task — assign `metadata.agent` to route to the right specialist | Main list | Definition model | All coordinated work (V11.11+) |
| **Agent Team** (deprecated) | Legacy; only when agents need shared task lists + wave dependencies | Team list (separate) | Lead model (Opus) | Avoid — use background agents instead |

**Default for V11.11+**: Assign `metadata.agent` on tasks. Spawn agents as background agents or foreground subagents. Skip TeamCreate unless you have an explicit cross-agent coordination requirement that cannot be met by task metadata.

---

## Per-Task Agent Assignment (Primary — V11.11+)

Instead of creating a formal team with `TeamCreate`, assign the responsible agent directly in task metadata:

```python
TaskCreate(
    subject="Implement auth middleware",
    metadata={
        "project": "my-project",
        "sprint": "sprint-01",
        "risk": "medium",
        "agent": "spec-implementer-v11",   # <-- per-task assignment
        "complexity": "medium",
        "scope": "small"
    }
)
```

When spawning an agent to execute the task, pass the task ID in the prompt so the agent can claim it:

```python
Agent(
    prompt="Claim task T5 (TaskUpdate in_progress, owner=backend-impl), then implement auth middleware. Spec: ...",
    subagent_type="spec-implementer-v11",
    run_in_background=True
)
```

**Benefits over TeamCreate**:
- Tasks stay in the main task list (visible to TaskList without scoping)
- No isolated team list to track separately
- Definition model used (Sonnet), not lead model (Opus)
- No wave synchronization overhead for independent tasks
- File ownership still enforced via `guard-write-gates` (set `metadata.file_ownership`)

---

## Background Agents (Independent Tasks)

For 3-8 independent tasks with no shared state or handoff dependencies, spawn background agents directly — no TeamCreate needed:

```python
# Spawn multiple independent agents in one message
Agent(prompt="...", subagent_type="spec-implementer-v11", run_in_background=True)
Agent(prompt="...", subagent_type="spec-tester-v11", run_in_background=True)
Agent(prompt="...", subagent_type="spec-integrator-v11", run_in_background=True)
```

You are notified when each completes. Review results and proceed.

**When to prefer background agents over TeamCreate**: Always, unless agents need to share discoveries via a common task list or wave dependencies require explicit synchronization.

---

## Model Behavior by Execution Mode

Agent definitions (`~/.claude/agents/*.md`) specify a `model` field (sonnet, opus, haiku). How this field is used depends on execution mode:

| Mode | Model Source | Agent Definition Used? |
|------|-------------|----------------------|
| **Subagent** (foreground) | Agent definition's `model` field | Yes |
| **Background agent** | Agent definition's `model` field | Yes |
| **Team teammate** (deprecated) | Lead's model (Opus 4.6) | No — silently ignored |

**Cost implication**: TeamCreate forces all teammates to run at Opus cost (lead model). Background agents and subagents use their definition model (Sonnet by default), which is cheaper for implementation work.

**Subagent nesting limit**: Subagents cannot spawn sub-subagents, and teammates cannot spawn their own teams. This is a Claude Code hard limit.

---

## Difficulty-Aware Formation Routing (DAAO)

When task metadata includes `complexity` and `scope`, the `guard-effort` hook suggests which formation recipe to apply (which agents, what wave structure). This is advisory — never blocks.

| Complexity | Scope | Suggested Formation Recipe |
|------------|-------|---------------------------|
| routine | small | single-file |
| routine | medium | lightweight-feature |
| medium | small | single-file or lightweight-feature |
| medium | medium | lightweight-feature |
| medium | large | feature-impl |
| complex | any | feature-impl or bug-investigation |
| novel | any | new-project (with architect) |

Formation recipes are in [FORMATIONS.md](FORMATIONS.md). They define agent role assignments and wave structure — no TeamCreate required to follow them.

**Research**: DAAO (Difficulty-Aware Agentic Orchestration, Sept 2025) shows +11.21% accuracy with 36% less compute by routing easy tasks to simpler workflows.

---

## Teammate Rules (when TeamCreate is used)

> These rules apply only to the deprecated Agent Team path.

- Each teammate loads project CLAUDE.md (inherits protocol)
- Teammates do NOT see team lead's conversation history
- Teammates must receive complete context in their initial prompt
- Include: spec.md content, relevant file paths, task IDs to claim, file ownership boundaries
- Tasks must be created AFTER TeamCreate to be visible to teammates

---

## File Ownership

File ownership prevents concurrent write conflicts regardless of whether you use TeamCreate or per-task agents. Set ownership in task metadata:

```python
TaskCreate(
    subject="...",
    metadata={
        "project": "my-project",
        "sprint": "sprint-01",
        "risk": "medium",
        "agent": "spec-implementer-v11",
        "file_ownership": {
            "directories": ["src/routes/", "src/services/"],
            "files": ["src/app.ts"]
        }
    }
)
```

### Legacy: Formation Registry

When using TeamCreate (deprecated), ownership was tracked in `.formation-registry.json`:

```json
{
  "teammates": {
    "backend-impl": {
      "agent": "spec-implementer-v11",
      "ownership": {
        "directories": ["src/routes/", "src/services/"],
        "files": ["src/app.ts"]
      }
    }
  }
}
```

Script: `./scripts/create-formation-registry FORMATION PROJECT`

This file is no longer required for per-task agent assignment. It remains supported for legacy team deployments and as a heartbeat config source.

---

## Teammate Timeout Protection

The system monitors all in_progress tasks with escalating severity. This applies to both TeamCreate teammates and background agents:

| Tier | Threshold | Severity | Action |
|------|-----------|----------|--------|
| 1 | 15 min | Warning | Advisory — consider checking on agent |
| 2 | 30 min | Alert | Message agent or prepare restart |
| 3 | 45 min | Critical | Restart recommended — task likely permanently stalled |

**On stall detection**: A warning task is created automatically. No other action is taken automatically. You have 5 minutes to respond.

**Options**:
- **Message**: Add note to task asking agent for status
- **Restart**: Spawn fresh agent with same task context
- **Complete**: If work is done, review and mark task completed
- **Block**: If stuck on dependency, create blockedBy task

**Configuration** (tunable in hook config):
- STALL_WARNING_MINUTES=15
- STALL_TIMEOUT_MINUTES=30
- STALL_CRITICAL_MINUTES=45
- STALL_ALERT_COOLDOWN_MINUTES=60
- MAX_STALL_ALERTS_PER_TASK=3

Alerts are advisory only, never block active work.

---

## Formation Heartbeat (Legacy TeamCreate Support)

When using TeamCreate formations, run heartbeat checks every N minutes (default: 10):

```
HEARTBEAT CHECK:
1. TaskList -> count by status (pending/in_progress/completed)
2. For each in_progress task:
   - Check owner's last file write timestamp
   - If no activity in 10 min -> ping agent
3. Check system resources (disk/memory)
4. Report: "Formation pulse: 5/12 complete, 2 active, ETA ~20 min"
5. If any agent stuck -> escalate per timeout protocol
```

Script: `./scripts/formation-heartbeat [PROJECT]`

For per-task agent assignment, TaskList serves the same monitoring purpose — no separate heartbeat infrastructure needed.

---

## Wave Review (V11.6+)

After each implementation wave completes, spawn `adversarial-reviewer` (Sonnet, READ-ONLY) to audit wave output:

1. Collect `files_changed` from completed task artifacts
2. Spawn adversarial-reviewer background agent with file list + spec excerpt
3. Reviewer applies 5 lenses: code quality, completeness, integration, security, rationale
4. Returns verdict: PASS / ISSUES_FOUND / BLOCKED
5. If BLOCKED: fix CRITICAL findings before next wave

Script: `./scripts/wave-review {project} {wave-number}`

This works with both TeamCreate formations and per-task agent assignment.

---

## TeamCreate Deprecation Notice

**TeamCreate is deprecated in V11.11.** Use per-task `metadata.agent` assignment with background agents instead.

**What still works**: All TeamCreate infrastructure (`.formation-registry.json`, formation-heartbeat script, team task lists, tool policy resolution) remains functional. Existing team-based sessions continue to operate normally.

**What changed**: New sessions should default to per-task agent assignment. Formation recipes in FORMATIONS.md describe role and wave structure — they do not require TeamCreate to implement.

**Migration**: Replace `TeamCreate → TaskCreate(inside team)` with `TaskCreate(metadata.agent=X)` in the main task list, then spawn agents as background agents.
