# Playbook: Per-Task Adversarial-Lite Review Loop (V11.15 + V11.19 queue)

> The comprehension gate that makes *"every task's output is adversarially verified and attributed to the executing agent"* computable instead of aspirational. Without it: per-agent error blindness, the "errors 100% orchestrator" attribution gap, no signal to tune agents.
>
> **V11.19 update**: the V11.15 mechanism was fully wired but mostly *dark* in practice (9 errors ever logged, zero across V11.16/17/18). Root cause: completed-without-review was a silent state. V11.19 added a durable per-project queue that makes the silent state observable — DETECT shows pending count, sync-tasks emits stderr nudges on every completed-without-review, handoff downgrades label, agent-effectiveness footer reports queue depth. The orchestrator literally cannot skip Phase 4r without seeing it.

This is **distinct from wave-review / swarm-review**. Those are deep, multi-lens, repo-wide audits run at wave/system boundaries. This is a *lite*, single-pass, single-task check run after **every** completed task, scoped to that task's changed files only (~2-3k tokens). "Lite" is a hard requirement — never expand it into the 5-lens swarm.

---

## V11.21 Dual-Layer Workflow (canonical when `V11_AUTO_PAIR_REVIEW=on`)

V11.21 replaces V11.19's queue-driven *out-of-band* review with a **paired-task, in-band** model. Every reviewable work task is shadowed by a sibling review task created in the same orchestrator turn — review is normal V11 work, not an exception.

### Layer A — Self-review (cheap, in-context)

The implementing agent emits a verdict in its OWN `TaskUpdate(completed)` payload at `metadata.artifacts.self_review`:

```json
{
  "severity": "NONE|LOW|MEDIUM|HIGH|CRITICAL",
  "summary": "What I did, what I verified, what I'm uncertain about.",
  "errors": [],
  "reviewed_at": "2026-05-23T08:00:00+00:00",
  "agent_id": "backend-architect"
}
```

This costs ~500 tokens in-context and forces articulation. Honesty is enforced by the **INV-3 calibration miss counter** (below). Without that counter, Layer A is ceremony.

**Layer-A actuation (mechanical, not prose)** — two independent, default-on knobs in `hooks/sync-tasks` + `hooks/completion-hint` make Layer A actually fire rather than merely being requested:
- `V11_SELF_REVIEW_NUDGE=off` disables the **nudge** — the stderr/in-band prompt emitted when a completing task carries no `metadata.artifacts.self_review`.
- `V11_SELF_REVIEW_ACTUATE=off` disables the **actuation** — the path that folds the emitted `self_review` into the per-agent ledgers and the INV-3 calibration join (self-vs-adversarial severity), and lets `completion-hint` surface it on the resolving edit.

Both never fail the hook. Leaving them on is what turns the emitted verdict into measured calibration data; turning `ACTUATE` off keeps the nudge but stops the fold-back (see the SKILL.md Phase-4 rollback-levers list).

### Layer B — Adversarial-lite paired sibling

The orchestrator pairs an `adversarial-lite-reviewer` sibling at TaskCreate (see `playbooks/orchestrate.md` § "V11.21 Routing & Review Protocol"). The sibling:
- Reads parent's `files_changed` + `metadata.artifacts` + `metadata.artifacts.self_review`
- Writes its verdict to its **own** `metadata.artifacts.review` — NEVER to the parent
- Supports two modes: **code-review** (files_changed present), **content-review** (artifacts-only parents, e.g., decisions / designs / spec drafts)
- Carries `metadata.scope: "small"` (v11.32) — auto-paired siblings are bounded single-pass lite checks, so the scope tag both signals their lite budget and keeps the prescope detectors (`V11_SCOPE_WARN`/`V11_PRESCOPE_SMELL`) from flagging them as under-split.

V11.20 attribution traverses `review_task → metadata.review_of → parent → recommended_agents[parent_id]` to credit the originating agent for review findings.

### Status transitions (state machine for review siblings)

| Parent status | Review sibling `parent_status` | Phase 4 dispatch? |
|---|---|---|
| pending | `pending_parent` | NO — filtered out |
| in_progress | `pending_parent` | NO — filtered out |
| **completed** | `pending` (sync-tasks transitions) | YES — orchestrator spawns reviewer |
| deleted | `deleted` (sync-tasks cancels) | NO |
| blocked | `pending_parent` (suspended) | NO until parent un-blocks |

`sync-tasks` writes a V11.16 ledger event on every transition — idempotent on replay. The orchestrator queries the aggregate; it never reads the ledger directly.

### Sequence (happy path)

```
Phase 4: orchestrator TaskCreate(work) → TaskCreate(review, parent_status=pending_parent)
                  ↓
Work agent: TaskUpdate(work, in_progress, owner=W) → [does work]
                  ↓
Work agent: TaskUpdate(work, completed, artifacts={files_changed, self_review={...}})
                  ↓
sync-tasks: parent completed → review sibling parent_status: pending_parent → pending
                  ↓
Phase 4 next loop: dispatch filter sees review sibling status=pending → spawn adversarial-lite-reviewer
                  ↓
Reviewer: read parent, write verdict to OWN metadata.artifacts.review → TaskUpdate(completed)
                  ↓
sync-tasks: emit Layer B agent-errors entries (found_by_layer=lite_adversarial, executor_kind=adversarial)
            + compute calibration miss when self ∈ {NONE,LOW} ∧ adversarial ∈ {HIGH,CRITICAL}
```

### Rollback to V11.19 queue (single env var)

When `V11_AUTO_PAIR_REVIEW=off`, V11.21 falls back to the V11.19 queue-driven workflow documented below. The queue path remains fully functional; orchestrator pairing is layered on top, never replacing it. Per-task mutual exclusion: when a parent has `metadata.review_task_id` set, sync-tasks does NOT enqueue to V11.19 (avoids double-review).

---

## V11.19 Queue-Driven Workflow (fallback path)

The queue (`~/.agent-metrics/review-queue/$PROJECT.jsonl`) is the authoritative work list. Two paths into Phase 4r:

**Path A: As tasks complete (real-time)**:
1. Complete task with `TaskUpdate(status=completed, metadata.artifacts.files_changed=[...])` — review verdict omitted.
2. `sync-tasks` enqueues the task, emits `[V11] REVIEW PENDING: task #N in $PROJECT (pending queue: K). Spawn adversarial-lite-reviewer.` to stderr.
3. Orchestrator MAY immediately drain (see Path B), OR defer and drain later — the queue is durable.

**Path B: Drain on demand (any session)**:
```bash
./scripts/review-queue pending PROJECT                  # see what's owed
./scripts/drain-review-queue PROJECT --limit 5          # XML block with spawn prompts
./scripts/drain-review-queue PROJECT --json             # JSON for tooling
```

For each `<pending-review>` in the drain output:
1. Spawn `adversarial-lite-reviewer` with the embedded `<spawn-prompt>`.
2. Capture the JSON verdict.
3. Severity-route per `.review-config.json`.
4. `TaskUpdate(taskId, metadata.artifacts.review = verdict)` — **out-of-band review verdicts on completed tasks are supported by V11.19**. `sync-tasks` writes the per-agent ledgers AND marks the queue entry done.

### Concurrent-session drainage (improvement 03, 2026-07-01)

Multiple Claude sessions can run against the same project concurrently (one in `photos`, one in `sofly-eyes`, etc.), and the queue mixes their concerns. "MUST drain" and "don't trample on a concurrent agent's in-flight work" used to be in unresolved tension — this makes the resolution mechanical:

```bash
./scripts/review-queue dashboard PROJECT                # honest split: drainable-here vs owned-by-concurrent-session
./scripts/drain-review-queue PROJECT --safe             # drains only unclaimed / non-conflicting entries
./scripts/drain-review-queue PROJECT --force             # drains everything, ignoring concurrent ownership
./scripts/drain-review-queue PROJECT --safe --force-stale # --safe, but first GCs stale claims so they become drainable
```

**Cross-session verdict fold-back (`mark-done --verdict-file`, W5-T16 / improvements/09)** — when THIS session reviews a task that another session completed, fold the full verdict JSON back into the queue + the task's per-agent ledgers with:

```bash
./scripts/review-queue mark-done PROJECT TASK_ID [SEV] [SESSION_UUID] --verdict-file verdict.json
```

`--verdict-file FILE` writes the complete reviewer verdict (not just the severity) into the queue entry, so the fold-back survives the session boundary — the originating agent still gets V11.20 attribution even though a *different* session ran the reviewer. If `SEV` is omitted it is derived as the max severity in the verdict file. This is the cross-session complement to the in-session `TaskUpdate(metadata.artifacts.review = verdict)` path above.

- **Ownership signal**: every pending queue line carries `session_uuid` (authoring session) and `claimed_by` (set when a session drains it). `--safe` skips an entry when either is a DIFFERENT session that is still live (`v11_session_is_live` in `hooks/lib/common.sh` — a session dir touched within the last 15 min), or when its `files_changed` overlaps another live session's pending entry.
- **Claiming**: `--safe` calls `v11_review_queue_claim` on each surviving entry before dispatch, so two concurrent orchestrator sessions never spawn a reviewer for the same task twice.
- **Stale-claim GC**: `./scripts/review-queue gc PROJECT [--max-age MIN]` (default 30 min) releases claims whose owning session died mid-drain. `--force-stale` runs this automatically first.
- **Hard backstop**: `./scripts/review-queue backstop PROJECT` blocks DETECT when pending > `V11_REVIEW_BACKSTOP_COUNT` (default 20) AND oldest > `V11_REVIEW_BACKSTOP_AGE` hours (default 24). Escape hatches: drain (`--safe --force-stale`) or `./scripts/review-queue ack-stale PROJECT --reason "..."` (acknowledges the current snapshot; a NEW pending entry re-arms it). Rollback: `V11_REVIEW_BACKSTOP=off`, independent of `V11_REVIEW_ENFORCEMENT=off`.

**Path C: Backfill** (one-shot or periodic):
```bash
./scripts/backfill-reviews                              # all projects
./scripts/backfill-reviews --project P --dry-run        # preview
./scripts/backfill-reviews --since 2026-04-01           # date filter
```
Idempotent. Trusts the durable ledger as source-of-truth; aggregate-only candidates are skipped to avoid V11.15.5/16-shape contamination.

---

## When the Original V11.15 In-Flight Loop Still Applies

For HIGH-risk tasks where you want the verdict BEFORE the completed transition (CRITICAL severity should block completion, not just report afterwards), use the V11.15 in-flight pattern below. For everything else, the V11.19 queue is sufficient and lower-friction.

Phase 4 sub-step **4r**, as the task approaches completion while still `in_progress`, before the terminal `completed` transition. Governed by `sessions/{project}/.review-config.json`:

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | `true` | `false` = skip the loop entirely |
| `scope` | `all` | `all` = every completed task. `risk-gated` = only risk∈{medium,high} or complexity∈{complex,novel}. `sampled` = every `sample_rate`-th routine task + always complex/novel |
| `sample_rate` | `1` | Used only when `scope=sampled` |
| `severity_autofix` | `["LOW","MEDIUM","HIGH"]` | Severities the orchestrator may auto-dispatch the fixer for (A3+ gated). CRITICAL is never autofixable by contract |
| `severity_escalate` | `["CRITICAL"]` | Severities that create a blocker task + escalate instead of auto-fixing |

Absent file = all defaults = review every completed task (the user-decided default).

---

## The Loop

```
task work done, artifacts written, task STILL in_progress
  → TaskUpdate(in_progress, metadata.artifacts.files_changed=…)  # make scope visible
  → ./scripts/task-review PROJECT TASK_ID        # deterministic reviewer prompt
  → spawn adversarial-lite-reviewer (Sonnet, RO) # files_changed scope ONLY
  → capture JSON verdict
  → severity route (auto-fix BEFORE completion if errors + A3+)
  → TaskUpdate(status=completed, metadata.project=PROJECT,
               metadata.artifacts.review = verdict)                   # TERMINAL — project is load-bearing
  → sync-tasks hook writes the per-agent ledgers automatically
```

> ⚠ **Ordering is load-bearing — do NOT complete-then-review.** Claude Code
> drops a task from the session store the moment it is `completed`:
> `TaskGet`/`TaskUpdate` on a completed task returns **"Task not found"**, so a
> post-completion verdict write is silently lost — `sync-tasks` never sees
> `artifacts.review` and the `agent-errors`/`agent-effectiveness` ledgers are
> never written. Therefore: **review while the task is still `in_progress`**,
> and let the verdict ride the **single terminal `TaskUpdate(status=completed,
> metadata.artifacts.review=…)`**. The completion event IS the ledger trigger.
> (Verified by live dogfood, 2026-05-16.)

### Step 1 — Build the reviewer prompt

```bash
./scripts/task-review PROJECT TASK_ID          # prints the spawn prompt
./scripts/task-review PROJECT TASK_ID --save   # also saves to sessions/PROJECT/reviews/
```

### Step 2 — Spawn the reviewer (READ-ONLY)

```
Agent(
  subagent_type="adversarial-lite-reviewer",
  description="Lite review task <TASK_ID>",
  prompt=<output of scripts/task-review>
)
```

Hard constraints (enforced by the agent definition + guard-enforcement):
- READ-ONLY. The reviewer never edits.
- Scope = the task's `files_changed` + `files_created` only. Never the repo.
- Single fast pass. Not the 5-lens deep swarm.

The reviewer returns JSON matching `task-metadata.schema.json#/$defs/review`:
`{reviewer, task_id, agent_id, difficulty 1-5, error_count, errors[], verdict}`
where `verdict ∈ {PASS, ISSUES_FOUND, BLOCKED}`.

### Step 2b — Batch-claim dispatch (R6, default at depth ≥2)

When the V11.19 queue or the V11.21 pending-sibling set holds **≥2** reviewable entries for the **same project**, batch-claim is the DEFAULT dispatch shape — not the single-spawn path above. Depth 1 still spawns single. This supersedes an earlier idea to re-task an already-running reviewer via `SendMessage` (rationale below); the queue/pairing mechanics (per-parent review tasks, `review_of` attribution join, INV-7 termination) are **untouched** — only the spawn count changes.

**Shape**: ONE `adversarial-lite-reviewer` spawn receives **K≤5** review blocks in its initial prompt, works through them sequentially, and writes each verdict to that block's own distinct review task — never to a shared or parent task. Depth >5 for a project: dispatch multiple batches of ≤5, not one giant batch.

**Batch spawn prompt skeleton:**

```
Agent(
  subagent_type="adversarial-lite-reviewer",
  description="Batch lite review: <PROJECT> (<K> tasks)",
  prompt=f"""
You will review {K} independent tasks for project {PROJECT}, ONE AT A TIME.
Treat each block as if it were a separate spawn — do not let findings,
assumptions, or context from one block bleed into the next.

=== BLOCK 1/{K} — review_task_id: {review_task_id_1} ===
{output of scripts/task-review PROJECT parent_task_id_1}
--- CONTEXT RESET: before starting this block, discard any file contents,
    verdicts, or assumptions held from a prior block in this batch. Read
    ONLY this block's files_changed/files_created — never carry file reads
    forward across blocks. ---
Write your verdict to review_task_id={review_task_id_1}:
TaskUpdate(taskId="{review_task_id_1}", status="completed",
           metadata={{"project": "{PROJECT}",
                      "artifacts": {{"review": <verdict JSON>}}}})

=== BLOCK 2/{K} — review_task_id: {review_task_id_2} ===
... (repeat per block: same CONTEXT RESET ritual, own files, own TaskUpdate)
"""
)
```

Hard constraints (unchanged from single-spawn, applied per-block):
- READ-ONLY. Scope per block = THAT block's `files_changed`/`files_created` only — never the repo, never another block's files.
- Explicit context-reset ritual between blocks (above) — a batch reviewer that carries block-1 findings into block-2's verdict is a cross-contamination bug, not a cost saving.
- Each block's verdict lands on its OWN review task via its own terminal `TaskUpdate(completed)` — the review-while-in_progress ordering rule (Step 4 below) applies per block, independently.

**Dispatch-trace note**: a batch spawn emits **one** `dispatch-trace-append` line covering the whole batch, carrying `--batch-review-ids "id1,id2,...,idK"` (the `batch_review_ids:[...]` schema field is implemented in `schemas/dispatch-trace.schema.json` + `scripts/dispatch-trace-append --batch-review-ids`). Per-block attribution still resolves through the existing `review_task → metadata.review_of → parent` join; the trace line is an observability convenience, not part of that join.

**Rationale — why not `SendMessage` re-tasking**: re-tasking an already-running reviewer via `SendMessage` was evaluated and rejected. It would have broken the `review_task → review_of → parent` attribution join (a re-tasked agent's second verdict has no clean second task to land on), made `caller_kind` inference ambiguous (is the second verdict "the reviewer" or "the orchestrator re-driving the reviewer"?), and leaned on a primitive — mid-flight re-tasking of an already-spawned agent — the protocol treats as deprecated for this purpose. Batch-claim captures the same spawn-cost win (one process instead of K) without touching any of that: it's still K TaskCreate review tasks, K terminal TaskUpdates, K attribution joins; only the number of `Agent()` spawns collapses from K to 1.

**Rollback**: `V11_REVIEW_BATCH=off` (prompt-level lever — followed by the orchestrator LLM, not code-enforced) — always single-spawn (Step 2 above), regardless of queue/sibling depth.

### Step 3 — Severity routing

| Verdict / severity | Autonomy | Action |
|--------------------|----------|--------|
| `PASS` (no errors) | any | Record verdict. Done. |
| LOW / MEDIUM / HIGH errors | **≥ A3** | Spawn `adversarial-lite-fixer` with the error list → it edits ONLY within the task's scoped file set → **re-verify** (re-run the reviewer or the cited test). Record `auto_fix` outcome. |
| LOW / MEDIUM / HIGH errors | **< A3** | Do NOT auto-fix. Surface the verdict to the user with options. |
| Any **CRITICAL** error | any | **No automated edit.** Create a blocker task describing the CRITICAL finding, escalate to the user. `verdict` will be `BLOCKED`. |

**Clean-attribution rule (contract):** the fixer is the dedicated
`adversarial-lite-fixer` agent — *never* `spec-implementer-v11`. Fixer activity
must not pollute the scorecard of the agent being measured.

### Step 4 — Complete the task WITH the verdict (single terminal update)

The verdict is written by the **same `TaskUpdate` that marks the task
`completed`** — not a separate call afterward. This is the only update that is
both still addressable and the `sync-tasks` ledger trigger:

```
TaskUpdate(taskId=TASK_ID,
           status="completed",
           metadata={"project": "<PROJECT>",
                     "artifacts": {"review": <verdict JSON>}})
```

> ⚠ **`metadata.project` is load-bearing on this terminal update — do NOT omit
> it.** `sync-tasks` resolves the project for the per-agent ledgers AND the
> `meta-feedback/{task_id}.json` corpus from `metadata.project` *first*, falling
> back to the **global, mutable `active-project` file** only if absent. That
> file is shared process-wide and drifts whenever any concurrent session — or a
> `Read` of another project's file — fires `detect-project`. If `active-project`
> has drifted, an omitted `metadata.project` silently writes this task's
> `agent-errors`/`agent-effectiveness` lines and its meta-feedback record into a
> *different project's* directory — poisoning that project's Quality-Flywheel
> input and making `agent-effectiveness --project P` undercount. Passing
> `metadata.project` makes `sync-tasks` Strategy 1 win and the ambient state
> irrelevant. (CLAUDE.md §1; verified by live dogfood, 2026-05-16.)

If errors were auto-fixed (Step 3, A3+), do the fix + re-verify while the task
is still `in_progress`, then fold both `review` and `auto_fix` into this one
terminal update. Never `TaskUpdate` a task after it is `completed` — it is gone
from the session store.

The `sync-tasks` hook does the rest deterministically (no orchestrator action):
- one line per error → `~/.agent-metrics/agent-errors.jsonl`
- a rolling 30-day snapshot → `~/.agent-metrics/agent-effectiveness.jsonl`
- a `review_summary` rollup folded into task-state
- `artifacts.meta_feedback` (if present) → `sessions/{project}/meta-feedback/{task_id}.json`

> **Why the orchestrator owns this loop:** hooks cannot spawn agents and
> subagents cannot spawn sub-subagents. The hook only does the deterministic
> JSONL append, riding the existing `metadata.artifacts` → task-state path.
> No new spawning machinery.

---

## The `meta_feedback` Contract

Every task agent is expected to include `artifacts.meta_feedback` in its
completion `TaskUpdate` — its structured self-critique:

```json
"meta_feedback": {
  "system_prompt_rating": 3,                       // 1-5: did my prompt equip me?
  "error_postmortem": "why I produced the errors, in my own words",
  "v11_suggestions": ["concrete prompt/framework tweak that would have prevented this"],
  "prompt_friction": ["parts of my prompt/task that were ambiguous or missing"]
}
```

Spawn prompts for task agents should request this explicitly. It is the input
side of the Quality Flywheel: `./scripts/flywheel-ingest --source meta-feedback`
clusters low-rated prompts + recurring suggestions per agent into actionable
agent-prompt-tuning proposals.

---

## Reading the Scorecard (Phase 5e)

```bash
./scripts/agent-effectiveness                 # per-agent table
./scripts/agent-effectiveness --rank          # worst success-rate first
./scripts/agent-effectiveness --agent X       # single agent
./scripts/agent-effectiveness --project P     # restrict errors to one project
./scripts/agent-effectiveness --json          # machine-readable
```

Columns: tasks reviewed, error-free count, success rate, avg difficulty
(contextualizes the rate), error-type breakdown, 30-day trend.

**Authority is ADVISORY ONLY.** This dashboard and the flywheel proposals
inform; they do not auto-route DAAO. Score-driven auto-routing is an explicit,
separately-approved future phase — out of scope for V11.15.

---

## Cost Discipline

| Item | Budget |
|------|--------|
| Reviewer pass | ~2-3k tokens (changed files only, single pass) |
| Batch reviewer pass (R6, depth ≥2, `V11_REVIEW_BATCH` default on) | ~2-3k tokens **per block**, K≤5 blocks per spawn — one process instead of K, same per-block scope; `V11_REVIEW_BATCH=off` forces single-spawn (prompt-level lever — followed by the orchestrator LLM, not code-enforced) |
| Fixer pass (only if errors + A3+) | scoped to task files |
| Re-verify | the cited test or one more lite reviewer pass |

If review cost is approaching wave-review territory, the scope is wrong — the
reviewer is seeing more than `files_changed`. Re-check `scripts/task-review`
output.

---

## Backward Compatibility

A completed task with **no** `metadata.artifacts.review` behaves exactly as
pre-V11.15 — no ledger writes, identical task-state. The loop is purely
additive. Projects that set `.review-config.json` `enabled:false` opt out
entirely.

---

## V11.21 Implementation-Detail Invariants (absorbed from spec.md)

> The V11.21 spec.md slims to 6 contract-level invariants (INV-1, INV-2, INV-3, INV-7, INV-12, INV-17). The 13 implementation-detail invariants below live here, where engineers can edit them without touching the protocol contract.

### Scope filter regex (`.review-config.json.auto_pair_scope`)

Default scope: pair every reviewable sprint-02+ task whose `complexity ∈ {medium, complex, novel}` OR `risk ∈ {medium, high}`. Sprint-00 (foundation tooling) and sprint-01 (playbook authoring) are NOT in default scope — those are framework machinery (see "A0 framework-machinery rationale" below).

```json
{
  "auto_pair_scope": {
    "sprint_min": "sprint-02",
    "complexity_in": ["medium", "complex", "novel"],
    "risk_in": ["medium", "high"]
  },
  "exempt_agent_patterns": ["adversarial-*"],
  "self_review_required": true,
  "review_budget_per_sprint": null
}
```

### Recursion termination (INV-7 belt-and-suspenders)

Auto-pair is skipped when ANY of these is true on the proposed work task:

1. **Structural** (load-bearing): `metadata.review_of` is set on the task (it IS a review sibling)
2. **Pattern match**: `metadata.agent` matches any entry in `exempt_agent_patterns` (default includes `adversarial-*`, catching `adversarial-lite-reviewer`, `adversarial-reviewer`, `adversarial-lite-fixer`)
3. **Explicit opt-out**: `metadata.skip_review=true`

The structural guard (1) is what makes recursion termination *provable* — even if a new adversarial-* agent is added without updating the exempt list, the `metadata.review_of` field on the review sibling prevents it from being paired with its own grandchild reviewer.

**Unit test contract:** any single `TaskCreate` produces at most ONE paired review. Chain depth >1 fails.

### Reviewer failure counter algorithm

When an `adversarial-lite-reviewer` spawn fails (timeout, crash, schema-invalid verdict), the orchestrator logs a V11.16 ledger event of type `reviewer_failed`:

```json
{"ts": "...", "task_id": "12", "review_task_id": "13", "reason": "verdict_schema_invalid", "attempt": 1}
```

The counter increments per `(review_task_id, reason)`. **2× consecutive failures** for the same `review_task_id` trigger a follow-up task `metadata.review_failed=true` and surface to the user — do NOT silently retry forever. The 2× threshold avoids flake-driven escalation while keeping degraded reviewers visible.

### Lifecycle transitions (block / resume / abandon)

| Parent transition | Sibling action |
|---|---|
| `pending` → `blocked` | Sibling stays `parent_status=pending_parent` (suspended) |
| `blocked` → `pending` | Sibling stays `pending_parent`; no spawn |
| `blocked` → `completed` | Sibling transitions to `pending` (treat as normal completion) |
| `* → deleted` | Sibling marked `synthetic_completion=true` + status `completed` (NONE verdict) — sync-tasks skips ledger writes for synthetic completions |
| Parent abandoned (no completion event for >7d) | Manual: orchestrator may issue synthetic completion via `scripts/quarantine-misstamped-sessions` family |

### Attribution traversal

Review verdict findings credit the **executing agent of the parent task**, not the reviewer:

```
review_task.metadata.artifacts.review.errors[i]
   → review_task.metadata.review_of  (parent task ID)
   → task_state.recommended_agents[parent_id]  (the agent that did the work)
   → agent-errors.jsonl entry with agent_id=THAT agent
```

The reviewer's identity is captured in `agent-errors.found_by` ("adversarial-lite-reviewer") and `executor_kind=adversarial`. Attribution is to the EXECUTOR of the reviewed work, not the reviewer.

### Dispatch-trace schema (one line per Phase 4 spawn)

`~/.agent-metrics/dispatch-trace.jsonl`. Schema: `schemas/dispatch-trace.schema.json`. Required fields: `ts, task_id, project, sprint, recommended_agent, spawned_agent, model, mode, caller_kind, self_review_omitted`. Line cap 4096 bytes, `override_reason` truncated first with `…` marker. FD-9 flock for concurrency. Rollback: `V11_DISPATCH_TRACE=off`.

### Fix-follow-up chain (CRITICAL handling)

A CRITICAL adversarial verdict creates a follow-up `adversarial-lite-fixer` task:

```
Parent task (work) → completed with self_review
   ↓
Review sibling → completed with verdict.severity=CRITICAL
   ↓
Orchestrator: TaskCreate(fix task, agent=adversarial-lite-fixer, metadata.review_of=<review_task_id>)
   ↓
Fixer task is ITSELF reviewable but pairs only ONE level (INV-7 stops the chain at depth 1)
```

The fixer never modifies the original parent task's `artifacts`. Its work goes into a NEW task with its own `artifacts.review` from a new lite-reviewer sibling.

### A0 framework-machinery rationale

Sprint-00 and sprint-01 tasks (framework machinery: tooling scripts, playbooks, schemas) carry `metadata.complexity=routine` or `risk=low` and so are filtered OUT of the auto-pair scope by default. This is intentional — these tasks build the *machinery* of review; reviewing them with that same machinery is bootstrapping ouroboros. They get reviewed at **gate-2 swarm-review** instead (5-lens deep audit).

When sprint-00/01 tasks DO carry `risk=high` or `complexity=complex` (the schema migration in T1 is the canonical example), the orchestrator MAY override and pair them. Set `metadata.skip_review=false` explicitly to opt in.

### Cutover transition policy

When V11.21 ships (env vars flip `off → on`):

1. **In-flight tasks** (status=in_progress at cutover): no retroactive sibling pairing. Existing V11.19 queue path remains for these.
2. **Pre-cutover completed tasks**: no retroactive review. V11.19 backfill (`scripts/backfill-reviews`) handles these on demand.
3. **Post-cutover TaskCreate**: full V11.21 dual-layer protocol applies.

The orchestrator's Phase 4 startup recovery scan respects this — it only synthesizes siblings for work tasks created AFTER the cutover timestamp (read from `.review-config.json.v11_21_cutover_at`, set at first `V11_AUTO_PAIR_REVIEW=on` boot).

### Calibration miss detection algorithm

The INV-3 falsifiability counter, computed by `scripts/agent-scorecard`:

```python
def calibration_miss(parent_task):
    self_sev  = parent_task.metadata.artifacts.self_review.severity      # None if missing
    review_id = parent_task.metadata.review_task_id
    if not review_id:
        return False  # No paired review → no comparison possible
    review = get_task(review_id)
    if review.status != "completed":
        return False  # Not yet measured
    adv_sev = worst_severity(review.metadata.artifacts.review.errors)
    return (self_sev in {None, "NONE", "LOW"}) and (adv_sev in {"HIGH", "CRITICAL"})
```

Per-agent miss count over 30d. **Calibration advisory** fires at >50% miss rate (with ≥4 paired data points, noise floor) — surfaces in `agent-scorecard` output.

**v11-loop-keystone T4 (mechanized, not advisory prose)**: `scripts/check-improve-subagent-triggers PROJECT` reads this exact `agent-scorecard --json` calibration block per candidate agent (anyone in that project's `recommended_agents` or `task_artifacts[*].self_review`) and, on threshold crossing, emits a structured "task-needed" signal — a dashboard line via `scripts/status` (`Calibration miss: {agent} at N% (30d) — run scripts/agent-scorecard {agent} --layer lite and consider TaskCreate for improve-subagent`) and, with `--json`, a `suggested_taskcreate` payload (`metadata.agent="improve-subagent"`, `metadata.trigger="calibration-miss"`, `metadata.candidate_agent={agent}`, `risk="medium"`). This mirrors the `Review queue (durable): N open` dashboard signal exactly (06dd1d4, v11.28.1 loop-audit): a script detects and surfaces, the orchestrator reads it during DETECT and decides whether to `TaskCreate` — never silent auto-actuation, per v11.27 doctrine ("mechanize acknowledgment not actuation"). Dedup: an open task already carrying `metadata.trigger="calibration-miss"` for that `candidate_agent` suppresses unconditionally; otherwise a cooldown marker at `sessions/PROJECT/.improve-subagent-triggered/AGENT.json` suppresses repeat signals for `V11_IMPROVE_SUBAGENT_COOLDOWN_DAYS` (default 7). Rollback: `V11_IMPROVE_SUBAGENT_TRIGGER=off` (default on). Depends on the INV-3 join-key fix in `hooks/sync-tasks` (v11-loop-keystone T1/"Fix 1") landing for real paired data — until then this correctly stays silent (0 paired records) rather than false-firing.
