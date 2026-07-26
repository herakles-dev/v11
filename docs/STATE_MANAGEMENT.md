# State Management — Detailed Reference

> Extracted from V11 CLAUDE.md Section 4. For the summary diagram, see CLAUDE.md.

---

## State Storage Architecture (V11.16 — durable ledger)

The canonical model is in [CLAUDE.md §4](../CLAUDE.md). Summary:

```
TaskCreate/Update/List (per-session Source of Truth, in Claude Code)
  → ~/.agent-metrics/sessions/$UUID/task-state.json   (per-session SCRATCH; session-end rm -rf's it)
  → ~/.agent-metrics/ledger/$PROJECT.jsonl            (V11.16 DURABLE, append-only, never deleted)
      ↓ v11_replay_ledger (deterministic fold; cutover only when ledger ≥ legacy)
  → ~/.agent-metrics/task-state/$PROJECT.json         (derived aggregate — schema unchanged)
  → sessions/$PROJECT/.task-state.json                (mirror)
```

**Why the ledger exists.** Before V11.16 the source of truth was the *ephemeral*
per-session file (deleted by `session-end` every turn) and the only durable
artifact was a lossy fold over already-deleted sessions with no cross-session
task identity — the structural root cause of every handoff bug V11.7→V11.15.
V11.16 makes the durable truth a per-project **append-only task-event ledger**
keyed by identity `(project, normalized-subject, create-seq)`. The aggregate is
*replayed from the ledger* (`v11_replay_ledger`) — same path, same schema, zero
consumer edits.

**History-safe cutover.** A project's aggregate flips from the legacy
session-fold to ledger replay only when the replay is **≥ the legacy aggregate
on both total and completed** (a visible count can never regress). A migrated
project whose de-poisoned baseline is temporarily behind keeps the legacy count
and **auto-promotes** to the ledger the moment normal use makes the replay catch
up. Levers: `.migrated/<project>` (durability+audit marker), `migrate-ledger
--pin` → `.legacy-pinned/<project>` (per-project rollback), `V11_LEDGER_CUTOVER=off`
(global). Cross-session reopen (block in A → terminate A → unblock+complete in B)
is resolved by a bounded reverse-scan of the durable ledger (gate-2 proven).

**Seeding.** `scripts/migrate-ledger PROJECT|--all` idempotently seeds the ledger
from the de-poisoned enumerated aggregate, acceptance-gated (a bad seed →
`.rejected`, project stays legacy). The per-session file is now pure scratch;
the V11.13 per-session ownership rules still govern that scratch tier and the
legacy fallback path.

---

## Task Schema with Metadata

```python
TaskCreate(
    subject="Implement DTW algorithm",
    description="Add Sakoe-Chiba band constraint to audio matching",
    activeForm="Implementing DTW",
    metadata={
        # === REQUIRED (Organizational) ===
        "project": "audio-suite",           # string: project identifier
        "sprint": "sprint-01-mvp",          # string: sprint-NN-LABEL
        "gate": "gate-1-database-ready",    # string: gate-N-LABEL
        "risk": "medium",                   # enum: low|medium|high

        # === OPTIONAL (Recommended Agent) ===
        # sync-tasks extracts this on TaskCreate and writes it to the
        # recommended_agents map in .task-state.json, keyed by task_id.
        # Agents listed here are advisory — native tool_profile handles enforcement.
        "agent": "spec-implementer-v11",     # string: recommended agent

        # === EXTENDED (Smart Routing) ===
        "complexity": "complex",            # enum: novel|complex|medium|routine
        "scope": "medium",                  # enum: small|medium|large
        "parallelizable": True              # boolean: default=true
    }
)
```

### metadata.agent → recommended_agents Flow (V11.11)

When a task is created with `metadata.agent`, the `sync-tasks` hook extracts the value and writes it into `.task-state.json` under `recommended_agents`, keyed by task ID:

```json
{
  "recommended_agents": {
    "T42": "spec-implementer-v11",
    "T43": "backend-architect"
  }
}
```

This replaces the formation-based agent routing that previously relied on `.formation-registry.json` and per-role tool policies. The `recommended_agents` map is the single source for which agent is expected to work a given task. Native agent `tool_profile` (defined in the agent's `.md` definition) handles tool enforcement — `guard-enforcement` no longer reads formation registry for this purpose.

**Why this matters**: Formation teardown removed the link between tasks and agents. `recommended_agents` restores that link without requiring a formation to exist.

### Extended Metadata Fields

| Field | Type | Values | When Required | Purpose |
|-------|------|--------|--------------|---------|
| `complexity` | enum | novel/complex/medium/routine | risk=medium/high | Task novelty classification |
| `scope` | enum | small/medium/large | risk=high (recommended for all) | Code change volume |
| `parallelizable` | boolean | true/false | Optional (default: true) | Parallel work feasibility |

**Complexity Levels**:
- **novel**: New problem, no precedent in codebase (requires research)
- **complex**: Known patterns but intricate implementation (requires expertise)
- **medium**: Standard implementation with known patterns
- **routine**: Boilerplate, formulaic, clear precedent

**Scope Levels**:
- **small**: <50 lines, 1-2 files, single module
- **medium**: 50-200 lines, 3-5 files, 1-2 modules
- **large**: 200+ lines, 5+ files, 3+ modules

**Validation Rules**:
- Novel + low-risk: Warning (unusual, verify classification)
- Routine + medium/high-risk: Error (contradiction, recategorize)
- Risk=high: Requires both complexity and scope fields

---

## Artifact Handoffs

When completing a task, include `metadata.artifacts` to pass structured context to downstream agents:

```python
TaskUpdate(
    taskId="5",
    status="completed",
    metadata={
        "artifacts": {
            "trace_id": "uuid-here",
            "summary": "Implemented JWT auth with refresh tokens",
            "handoff_note": "JWT_SECRET must be set in .env before tests run",
            "files_changed": ["src/auth.ts", "src/middleware.ts"],
            "files_created": ["src/models/User.ts"],
            "api_contract": {
                "POST /auth/login": "{ email, password } -> { token, refreshToken }"
            },
            "test_hints": ["Test token expiry at 15min boundary"],
            "config_changes": {"JWT_SECRET": "Required env var"},
            "breaking_changes": [],
            "dependencies_added": ["jsonwebtoken@9.0.2"],
            "artifact_refs": []
        }
    }
)
```

**Key fields**:

| Field | Purpose |
|-------|---------|
| `trace_id` | UUID carried across all task hops for observability |
| `summary` | Lightweight context for downstream agents |
| `handoff_note` | Explicit instructions for the next agent |
| `artifact_refs` | References to large artifacts stored externally |

**External storage**: Artifacts >2KB use `sessions/{project}/artifacts/{task_id}/` with `artifact_refs`. Artifacts <=2KB inline in metadata.

**Injection**: When a teammate claims a task with `blockedBy` dependencies, `sync-tasks` extracts `metadata.artifacts` from completed blocking tasks.

### Review + meta-feedback artifacts (V11.15)

The per-task review loop adds two optional `artifacts` keys, written by the
orchestrator's post-task review step and consumed by `sync-tasks` for
per-agent metric attribution. Both are **advisory only** — absence means no
review ran (fully backward compatible).

| Field | Written by | Purpose |
|-------|-----------|---------|
| `artifacts.review` | orchestrator (from adversarial-lite-reviewer verdict) | `{reviewer, task_id, agent_id, difficulty 1-5, error_count, errors[], verdict, auto_fix}`. `sync-tasks` fans this out: one line per error → `~/.agent-metrics/agent-errors.jsonl`, a rolling 30-day snapshot → `agent-effectiveness.jsonl`, and a `review_summary` rollup into task-state. `agent_id` is the subject of attribution (falls back to task-state `active_agent_id`). |
| `artifacts.meta_feedback` | the task agent itself, in its deliverable | `{system_prompt_rating 1-5, error_postmortem, v11_suggestions[], prompt_friction[]}`. The agent's structured self-critique of its own system prompt. `sync-tasks` persists it to `sessions/{project}/meta-feedback/{task_id}.json`; `scripts/flywheel-ingest --source meta-feedback` clusters it per agent into prompt-tuning proposals. |

**meta_feedback contract**: task agents are expected to include
`artifacts.meta_feedback` in their completion `TaskUpdate` — a 1–5 rating of
how well their system prompt equipped them, plus concrete `v11_suggestions`
and `prompt_friction`. This is the input side of the Quality Flywheel's
agent-prompt-improvement loop. View attribution with `scripts/agent-effectiveness`.

**Schema**: `schemas/task-metadata.schema.json` (`$defs.review`, `$defs.meta_feedback`),
`schemas/agent-errors.schema.json`, `schemas/agent-effectiveness.schema.json`,
`schemas/review-config.schema.json`

---

## spec.md Format

```markdown
# Project: {name}

## Intent
{one paragraph description}

## Stack
- Backend: {tech}
- Database: {tech}
- Frontend: {tech}

## Constraints
- {constraint 1}

## Agents
| Role | Agent | Rationale |
|------|-------|-----------|
| Lead | Team Lead (Opus 4.6) | Orchestration |
| backend-impl | backend-architect | Complex API design with auth |
| tester | spec-tester-v11 | Standard L1-L4 validation |

## Notes
{free-form notes}

---
Created: {date}
Protocol: V11
Tasks: Use TaskList to see all tasks
```

**Note**: Tasks are NOT listed in spec.md. Use `TaskList` or `./scripts/status`.
**Note**: The `## Agents` section records which specialists were chosen for each role during the planning interview (DAAO hybrid routing).

---

## Finding Tasks & Audit Reports (V11.5)

Finding tasks represent audit results from multi-agent codebase reviews. They use structured metadata for automated deduplication, ranking, and report generation.

### Creating Finding Tasks

```python
TaskCreate(
    subject="[CRITICAL] Shell injection via create_subprocess_shell",
    description="asyncio.create_subprocess_shell() passes LLM commands directly to shell.",
    metadata={
        "project": "nova-forge",
        "sprint": "sprint-01-audit",
        "risk": "low",
        "type": "finding",
        "severity": "critical",
        "finding": {
            "category": "security",
            "location": {"file": "forge_agent.py", "line_start": 1472, "line_end": 1478},
            "problem": "Shell execution passes LLM commands directly. Regex denylist is bypassable.",
            "fix": "Run bash commands inside Docker containers or use command allowlist.",
            "impact": "sandbox-bypass",
            "confidence": "high"
        }
    }
)
```

### Finding Metadata Schema

| Field | Required | Type | Purpose |
|-------|----------|------|---------|
| `category` | Yes | enum | security, performance, reliability, maintainability, correctness, integration, test-coverage, observability |
| `location` | Yes | object | `file` (required), `line_start`, `line_end`, `context` |
| `problem` | Yes | string | Clear description (max 500 chars) |
| `fix` | Yes | string | Concrete remediation (max 500 chars) |
| `impact` | Yes | enum | sandbox-bypass, data-loss, build-failure, security-exploit, performance-degradation, code-quality, developer-experience, test-gap |
| `confidence` | No | enum | high, medium (default), low |
| `found_by` | No | array | Agent IDs that found this (populated during synthesis) |
| `dedup_of` | No | string | Task ID of canonical finding (set during synthesis) |

### Severity Levels

| Severity | Meaning | Fix Priority |
|----------|---------|-------------|
| **critical** | Complete safety/security/data breach | Immediate |
| **high** | Directly causes failures or security exploits | This sprint |
| **medium** | Degrades correctness, performance, or security posture | Next sprint |
| **low** | Nice-to-have improvements | Backlog |

### Audit Pipeline

```
1. Audit agents create finding tasks (5 parallel, READ-ONLY)
   → sync-tasks hook updates findings_summary in task-state
2. ./scripts/synthesize-findings PROJECT
   → Deduplicates, ranks, generates issues.md + issues.json
3. ./scripts/findings-to-spec PROJECT (optional)
   → Converts CRITICAL+HIGH findings into spec.md for fix execution
4. Fix formation executes remediation
   → Finding tasks marked completed as fixes land
```

### Task State: findings_summary

When finding tasks exist, `task-state.json` includes:

```json
{
  "findings_summary": {
    "critical": 1,
    "high": 12,
    "medium": 24,
    "low": 28,
    "total_raw": 57,
    "total_deduped": 35,
    "dedup_rate": 0.39
  }
}
```

See [FORMATIONS.md](FORMATIONS.md) for the codebase-audit formation and Finding Synthesis Protocol.

---

## Auto-Memory Integration

V11 leverages Claude Code's native auto-memory:
- Project conventions, patterns → auto-memory (persists across sessions)
- Task progress, status → TaskList (source of truth)
- Session handoff → auto-memory handles implicit context
- Explicit notes → spec.md Notes section
