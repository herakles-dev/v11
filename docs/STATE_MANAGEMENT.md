# State Management — Detailed Reference

> Extracted from V11 CLAUDE.md Section 4. For the summary diagram, see CLAUDE.md.

---

## State Storage Architecture (V11.16 — durable ledger)

The canonical model is in CLAUDE.md §4. Summary:

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

## TaskList Epochs (v11-leverage-program S2, #113 / #111)

**Problem.** A task id is local to one Claude Code TaskList, and a hook
session can hold several TaskLists. When a conversation resumes, it keeps its
hook `session_id` but can get a new TaskList whose ids start again at 1. An
in-process `/resume` moves the store to `~/.claude/tasks/session-<launch8>`. So
`(session_uuid, task_id)` can name several tasks. Session a059e6ae of
v11-leverage-program holds four TaskLists. Design:
`sessions/v11-leverage-program/artifacts/s2-t0-epoch-design.md`, amended by
review #19 (§11).

**Epoch record** `$METRICS_DIR/tasklist-epochs/<session_uuid>`. The file is
append-only: every TaskCreate appends one snapshot line, and readers take the
LAST complete line.
```
v1 <tl_epoch> <fresh|reuse|seed> <pid:starttime|-> <last tool_use_id|-> <,id:tu8,id:tu8,...,> <max id|-> <,sitting,...,> <,id,...,> <-|from:,id,...,>
```
The last three fields (review #26) are the sitting set, the pending ids and
the carry. A line without them (written before review #26, or by
`task-epoch-seed`) still parses: its sitting set is its one sitting, nothing is
pending, nothing is carried. The next create writes the full line.
- `tl_epoch` is `${EPOCHREALTIME}` in µs at the open: an opaque int that is only
  ever matched, never compared.
- `tu8` is the last 8 characters of each create's `tool_use_id`, so a
  re-fired PostToolUse for any create is recognised (C2).
- **Opening an epoch.** A session's first TaskCreate opens a `fresh` epoch.
  Later, a create opens a `reuse` epoch when either:
  - it returns an id the current epoch already created, under another
    `tool_use_id`; or
  - it comes from a claude process (the *sitting*: `CLAUDE_PID` plus `/proc`
    starttime) that is not in the epoch's sitting set, with an id not above
    the epoch's max (C1).
- **Sitting set.** The sittings that created in this epoch, oldest first, at
  most 8. Two processes that share one session id (a tmux teammate, a nested
  `claude -p --resume $SID`) interleave their creates without opening an
  epoch, because each is already in the set.
- **Pending ids and the carry.** After a resume, a parallel batch of the new
  TaskList can deliver an id above the old max first (ids 1, 2, 3 arriving as
  3, 1, 2). The 3 joins the old epoch, because nothing shows yet that the
  TaskList changed. The record keeps the ids created by the newest sitting since it
  joined the epoch (`pending`; empty while only the opener created). When an
  id reuse by that same sitting opens a new epoch, the pending ids are
  carried: they join the new epoch's id set, and the carry field names them
  with the epoch they were created in (`from:,3,`).
  - **Stamp.** A carried task keeps `from` as its stamp: its ledger lines are
    already written with it, and `(session, from, id)` still names exactly one
    task, since `from`'s id set never held that id before.
  - **Current-state lookups.** `v11_tl_epoch_read SESSION TASK_ID` (bash) and
    `task_epoch.epoch_for_task` (Python) return `from` for a carried id. The
    identity ladder (C7), Strategy 1.6, the dispatch-trace dedupe (C8),
    track-agents' dispatch rows, the `dispatch-trace-append` and
    `dispatch-advise` defaults and R4 all agree with the task's create.
    History is never rewritten, so readers of history need nothing new.
  - **No carry.** A reuse of an id the sitting created itself carries nothing.
- **Seed line.** `seed` (tl_epoch 0) is written by `scripts/task-epoch-seed`
  for a session that was live at rollout, and by the first create after an
  unreadable record (below). Its id set is complete, but its events stay
  unstamped until the next epoch opens.
- **Unreadable record.** An empty or garbled last line, or a torn only line,
  reads as unknown: no epoch opens and nothing is stamped. The next create
  appends an epoch-0 seed line holding its id, so tracking resumes by itself
  (a later id reuse opens an epoch as usual). No manual reseed is needed.
- **Compaction.** Only the last line is ever read. Once the record passes
  ~64 KB, the writer rewrites it to that line (a tmp file `.<session>.compact`
  plus a rename, under FD-201), so a reader sees the old file or the new one.
- **Readers and writer.** Only `hooks/sync-tasks` writes the record, under
  FD-201 (`hooks/lib/common.sh` `v11_tl_epoch_on_create`). The readers are
  `v11_tl_epoch_read` (bash, builtins only) and
  `scripts/lib/task_epoch.py` `read_epoch_record` (the current epoch plus
  `carry_from`/`carried`) / `record_epoch` (the raw tl_epoch, 0 = seed).
  `scripts/rotate-metrics` removes a record 30 days after its last write
  (`--tasklist-epoch-ttl-days N`, N >= 1; 0 or less is refused with exit 2,
  since it would delete live records).

**Stamps** (all additive; history is never rewritten):
- **Ledger.** `tl_epoch` (int) is on every event sync-tasks appends; the
  opening create also carries `tl_open`. It is never on `review` rows or on
  other processes' events (folds, post-commit, align-aggregate).
- **Per-session STATE.** `open_tasks[id]._tl_epoch`, `_terminal_idk[id]._tl_epoch`,
  `recent_completed[]`/`blocked_tasks[]` `tl_epoch`, and the live snapshot's
  `tl_epoch`. The TaskUpdate identity ladder trusts only entries of the current
  epoch (C7): a carried task's `from`, and any entry at all when the epoch
  opened `fresh` (no reuse was seen, so a record lost while STATE survived
  keeps its stamped entries). `open_tasks[id]._created_at` is the create's ts.
- **Review queue.** The pending row carries `parent_identity {subject_norm,
  create_seq}` and `tl_epoch`.
- **Dispatch trace.** Rows carry `session_uuid` and `tl_epoch`. The
  completion-time auto-emit dedupes on (project, session_uuid, tl_epoch,
  task_id) (C8). A row without a session (written before the rollout) matches
  (project, task_id) when its ts is at or after the task's create:
  `_created_at`, else the task's create in the project ledger. The ledger is
  read only when such a row exists. Timestamps are compared as instants.
- **`handoff-tasks.json`** (S2-T0b-4):
  - `live_sitting`: only when the writer is the live session;
  - `live_tl_epoch`: the record's epoch, 0 = seed;
  - `task_store`, `task_store_basis`, `task_store_verified`: a team config
    first (verified), else a content match (unverified);
  - per entry, `tl_epoch` (of its latest create) and
    `metadata.review_task_id` (the identity's latest `pair_` shadow;
    `V11_HANDOFF_REVIEW_TASK_ID`, on since S2-R1). The rehydrated task mints
    no second shadow, and at completion sync-tasks keeps its V11.19 queue row,
    since the shadow is in the old session's scratch.

**One resolver.** `scripts/lib/task_epoch.py` `TaskIndex.resolve` is the
resolver; its bash wrappers are `v11_resolve_identity` and
`v11_ledger_resolve_by_task_id`. It turns `(session, task_id)` plus the row's
context into an identity. Rules, in order (ambiguous only on a real tie):
- **R0 explicit identity.** `--identity SN:CS` or a queue row's
  `parent_identity` binds when the ledger knows it.
- **R1 session and epoch.** It binds the one create of that epoch at or before
  the row. With none, it falls back as follows:
  - an epoch opened `fresh`: inference restricted to the positions before the
    epoch;
  - an epoch opened `reuse`: unresolved, since its create was never ledgered.
- **R2 session, no epoch (legacy rows).** It binds the latest create at or
  before the row, preferring one whose names include the row's subject. It
  uses 2 s of slack for non-ledger rows only when nothing fits strictly.
- **R3 no session.** It binds only when one identity carries the id across
  sessions.
- **R4 current-state query.** R1 on the session's current epoch (for a
  carried task, the epoch it was created in).

**Claims.** Only `created` events claim an id. Review, prescope and voided rows
never do, and rehydrate aliases are folded in. Readers routed through the
resolver: handoff, mark-done, the replay keying (`task_key.claim_key`),
wave-check, agent-scorecard, cost-ledger, dispatch-advise, review-daemon,
task-cancel, status and sync-tasks Strategy 1.6.

**Legacy behaviour.**
- **Unstamped history.** Every pre-S2 ledger and every seeded session keeps
  resolving by inference (R2). Epochs derived by the id-reuse rule are used
  for display and the store finder only.
- **`V11_TASK_RESOLVER=legacy`.** Every reader takes its v11.46 path, for one
  sprint.
- **`V11_TASKLIST_EPOCH=off`.** No record and no stamps: sync-tasks lines keep
  their v11.46 shape. `handoff-tasks.json` then has no `live_sitting`, so the
  self-nudge check never matches (fail toward nudging).

**#111 rehydrate identity.** A rehydrated TaskCreate carries
`metadata.rehydrated_from.identity`. `v11_ledger_append` keys it on that
identity (`continues:true`) while the identity's last status event is still
open and it is the task the handoff named: a create of it, or of a legacy
alias of it, was made in `rehydrated_from.session` under `rehydrated_from.id`.
Otherwise the target is refused (`rehydrate_target_refused`: `unknown`,
`mismatch` or `terminal`) and the create is keyed on its own subject.
Legacy aliases come from `$METRICS_DIR/ledger/<project>.aliases.json`, written
by `task-epoch-seed` (rollback `V11_REHYDRATE_IDENTITY_WRITE=off`).

**Self-nudge.** `hooks/detect-project` and `hooks/post-compact` skip the
rehydrate nudge (and L2.3) only when all of these hold:
- the file's `live_session_uuid` is this session;
- `live_sitting` is this claude process;
- `live_tl_epoch`, when set, is still the record's epoch.

The check is `v11_handoff_self_sitting`. `V11_HANDOFF_SELF_NUDGE_SUPPRESS=session`
brings back the S1 session-only match.

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
