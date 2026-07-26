# V10 Vision: Multi-Layer Agent Orchestration

> Foundation document for V10 improvements. Combines technical architecture with research-backed patterns.

**Status**: Complete
**Date**: 2026-02-13
**Purpose**: Define the orchestration models available in V10, document tradeoffs, incorporate external research, and produce an actionable improvement plan.

---

## Part 1: The Three Orchestration Layers

V10 currently documents only one model (2-layer, same-terminal). In practice, three distinct layer configurations exist, each with different strengths.

### Layer 1: Direct Execution

```
┌──────────────────────────┐
│   Claude (this session)  │
│                          │
│   Reads, edits, tests    │
│   Full context available │
│   Zero coordination tax  │
└──────────────────────────┘
```

**Characteristics**:
- No delegation overhead
- Full 1M context for the problem
- Zero communication latency
- Single point of failure = single point of control

**When optimal**:
- 1-5 tasks
- All tasks are sequential (no parallelization benefit)
- Deep reasoning required (architecture, security analysis)
- Context is king — the problem needs holistic understanding

**When it breaks down**:
- >5 tasks with parallelization potential
- Multi-file changes where isolation matters
- Long-running sessions where context compaction loses detail

---

### Layer 2: Orchestrator + Team

```
┌──────────────────────────┐
│   Claude Orchestrator     │
│   - Creates tasks         │
│   - Spawns teammates      │
│   - Reviews output        │
│   - Synthesizes results   │
└─────────┬────────────────┘
          │ Task tool (spawn)
     ┌────┼────┬────────┐
     ▼    ▼    ▼        ▼
   [A]  [B]  [C]      [D]
   Agent teammates (subprocesses)
```

**Characteristics**:
- Orchestrator manages 2-5 teammates
- Shared TaskList for coordination
- SendMessage for real-time communication
- Orchestrator context consumed by: task management, idle notifications, review
- Teammates get separate context windows but share process lifecycle

**When optimal**:
- 6-15 tasks with clear parallelization
- Well-defined file ownership boundaries
- Short-to-medium duration (1-4 hours)
- Tasks are independent enough to parallelize but need coordination

**When it breaks down**:
- Orchestrator becomes a bottleneck reviewing 4-5 teammates' output
- Context fills with coordination messages instead of problem-solving
- A teammate crash or stall blocks the orchestrator's attention
- >15 tasks — orchestrator can't track everything

**The bottleneck problem**: In a 4-teammate formation, the orchestrator spends ~60-70% of its turns on coordination (reviewing, messaging, task updates) and only 30-40% on actual thinking. This is the fundamental ceiling of 2-layer.

---

### Layer 3: Orchestrator + Team Lead + Team

```
┌──────────────────────────┐
│   Claude Orchestrator     │
│   - Strategic direction   │
│   - Gate approvals        │
│   - Cross-team decisions  │
│   - User communication    │
└─────────┬────────────────┘
          │ Spawns team lead (Task tool or xterm)
┌─────────┴────────────────┐
│   Claude Team Lead        │
│   - Day-to-day management │
│   - Task assignment       │
│   - Output review         │
│   - Quality synthesis     │
└─────────┬────────────────┘
          │ Task tool (spawn teammates)
     ┌────┼────┬────────┐
     ▼    ▼    ▼        ▼
   [A]  [B]  [C]      [D]
   Agent teammates
```

**Characteristics**:
- Orchestrator stays strategic, never drowns in coordination
- Team lead absorbs all management overhead
- Orchestrator only sees: gate approvals, blockers, final reports
- Team lead has full tactical control over teammate lifecycle

**When optimal**:
- 16+ tasks across multiple sprints
- Multiple formations needed in sequence
- Orchestrator needs to remain available for user interaction
- Cross-cutting concerns (security, architecture) need oversight layer

**When it breaks down**:
- Small projects — overhead exceeds benefit
- Team lead becomes a single point of failure (same as 2-layer, just moved down)
- Communication latency: orchestrator → team lead → teammate = 2 hops
- If orchestrator and team lead disagree on approach, deadlock

**The delegation tradeoff**: 3-layer buys you strategic freedom at the cost of communication latency. The orchestrator can't course-correct teammates directly — it must go through the team lead.

---

## Part 2: Terminal Models

Orthogonal to layer count is WHERE agents run. Two models exist.

### Model A: Same-Terminal (In-Process)

```
┌─────────────────────────────────────────┐
│  Terminal (single Claude Code session)   │
│                                          │
│  ┌───────────┐  ┌───────┐  ┌───────┐   │
│  │Orchestrator│  │Agent A│  │Agent B│   │
│  │ (parent)   │  │(child)│  │(child)│   │
│  └───────────┘  └───────┘  └───────┘   │
│                                          │
│  Shared: TaskList, SendMessage, lifecycle│
└─────────────────────────────────────────┘
```

**How it works**:
- `Task` tool with `team_name` parameter spawns teammate subprocesses
- All agents share the parent process's lifecycle
- Native `SendMessage` / `TaskList` / `TaskUpdate` for coordination
- `TeamCreate` / `TeamDelete` for lifecycle management

**Technical properties**:
| Property | Value |
|----------|-------|
| Startup time | ~2-5s per teammate |
| Communication | SendMessage (immediate, structured) |
| Context isolation | Separate per agent, shared resource pool |
| Crash behavior | Parent dies → all children die |
| Max practical teammates | 3-5 (coordination overhead) |
| Coordination protocol | Native (TaskList, SendMessage) |
| File conflict prevention | Formation registry + guard-write-gates hook |
| Observability | Inline (idle notifications, task events) |

**Strengths**:
- Tight coordination loop — team lead sees everything in real time
- Structured communication with summaries
- Native task claiming and dependency tracking
- Simple mental model for the orchestrator

**Weaknesses**:
- Lifecycle coupling — no crash isolation
- Context pool shared — heavy teammates starve others
- Idle notification noise fills orchestrator context
- 5-teammate ceiling before coordination tax dominates

---

### Model B: Xterm Dispatch (Out-of-Process)

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Terminal 1   │   │  Terminal 2   │   │  Terminal 3   │
│  Orchestrator │   │  Agent A      │   │  Agent B      │
│  (PID 1001)   │   │  (PID 2002)   │   │  (PID 3003)   │
│               │   │               │   │               │
│  Full 1M ctx  │   │  Full 1M ctx  │   │  Full 1M ctx  │
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                  Shared filesystem
              /sessions/{project}/*
```

**How it works**:
- Each agent is a separate `claude` CLI process in its own terminal (xterm, tmux pane, etc.)
- Communication exclusively through the filesystem
- Each loads its own CLAUDE.md, gets full independent context
- Coordination via shared task files, flag files, lock files

**Technical properties**:
| Property | Value |
|----------|-------|
| Startup time | ~10-15s per terminal |
| Communication | Filesystem (async, poll-based) |
| Context isolation | Complete — full 1M each |
| Crash behavior | Independent — others survive |
| Max practical agents | 10+ (OS is the limit) |
| Coordination protocol | File-based (must be designed) |
| File conflict prevention | File locks + ownership convention |
| Observability | Log files, status files, external monitoring |

**Strengths**:
- True crash isolation — one agent failing doesn't affect others
- Full context per agent — no resource competition
- Scales to 10+ agents (OS process limit, not framework limit)
- Long-running capability — agents can work for hours independently
- Natural fit for 3-layer (team lead in separate terminal)

**Weaknesses**:
- No native coordination — must build file-based protocol
- Polling latency — agents discover updates on filesystem check intervals
- File locking complexity — must prevent race conditions on shared files
- Harder to observe — need external monitoring tooling
- Agent can't "ask" orchestrator a question in real time

---

### Model C: Hybrid (Pragmatic Default)

```
┌─────────────────────────────────────────┐
│  Terminal 1 (Orchestrator)               │
│  ┌───────────┐  ┌───────┐  ┌───────┐   │
│  │Orchestrator│  │Lead A │  │Lead B │   │
│  │            │  │(child)│  │(child)│   │
│  └───────────┘  └───────┘  └───────┘   │
└────────┬────────────────────────────────┘
         │ (xterm dispatch for heavy workers)
    ┌────┴─────┐    ┌──────────┐
    │Terminal 2 │    │Terminal 3 │
    │ Worker A  │    │ Worker B  │
    │ (long job)│    │ (long job)│
    └──────────┘    └──────────┘
```

**How it works**:
- Team leads stay in-process (tight coordination with orchestrator)
- Heavy/long-running workers dispatch to separate terminals
- Coordination: SendMessage for leads, filesystem for dispatched workers
- Best of both: real-time coordination where needed, isolation where needed

**When to use which**:
| Scenario | Terminal Model |
|----------|---------------|
| Quick task, <30 min | Same-terminal |
| Needs real-time Q&A with orchestrator | Same-terminal |
| Long implementation, >1 hour | Xterm dispatch |
| Crash-sensitive (can't afford restart) | Xterm dispatch |
| Multiple independent workstreams | Xterm dispatch |
| Team lead managing workers | Hybrid (lead in-process, workers dispatched) |

---

## Part 3: Decision Framework

### Choosing Layers

```
How many tasks?
  1-5   → Layer 1 (direct)
  6-15  → Layer 2 (orchestrator + team)
  16+   → Layer 3 (orchestrator + team lead + team)

Override: If tasks are deeply interdependent
  and need holistic reasoning → prefer fewer layers
  (deep thinking > parallelization)
```

### Choosing Terminal Model

```
Expected duration per agent?
  <30 min  → Same-terminal
  >30 min  → Xterm dispatch

Need real-time coordination?
  Yes → Same-terminal (or hybrid with lead in-process)
  No  → Xterm dispatch

Crash tolerance needed?
  Yes → Xterm dispatch
  No  → Same-terminal
```

### Combined Decision Matrix

| Tasks | Duration | Interdependency | Recommendation |
|-------|----------|-----------------|----------------|
| 1-5 | <1h | Any | Layer 1, direct |
| 6-10 | <2h | Low | Layer 2, same-terminal |
| 6-10 | <2h | High | Layer 1, direct (holistic reasoning wins) |
| 11-15 | 2-4h | Low-Medium | Layer 2, hybrid |
| 16-30 | 4-8h | Low | Layer 3, hybrid |
| 16-30 | 4-8h | High | Layer 2, xterm (fewer agents, more context each) |
| 30+ | Days | Any | Layer 3, xterm, multi-formation |

---

## Part 4: Research-Backed Patterns

> Synthesized from 20 sources (2024-2026). Full citations in research/multi-agent-patterns.md.

### 4.1 What the Research Validates About V10

These V10 design choices are confirmed correct by multiple independent sources:

| V10 Design Choice | Validated By | Evidence |
|-------------------|-------------|----------|
| **Task-based coordination (not chat)** | MultiAgentBench, MetaGPT, anti-pattern catalogs | Group discussion scored WORST across all metrics. Structured > free-form. |
| **Separate context per teammate** | Anthropic (90.2% improvement), context rot research | Context pollution actively degrades performance. Focused attention per LLM call wins. |
| **File ownership enforcement** | Universal consensus | Same-file multi-agent edits are the #1 cited failure mode. |
| **2-layer hierarchy (lead + workers)** | MultiAgentBench | Tree topology (3+ layers) performed WORST. Star/graph (2-layer) performed best. |
| **Formation-based topology** | 17x Error Trap (2026) | Adding agents without topology amplifies errors 17x. Topology IS the solution. |
| **Graduated complexity (direct < subagent < team)** | Anthropic research system | Simple: 1 agent. Moderate: 2-4. Complex: 10+. Start simple, escalate when needed. |
| **Hook-based verification** | MASFT failure taxonomy | Incomplete verification is one of the 14 most common multi-agent failure modes. |

### 4.2 Critical Research Findings

#### Finding 1: The 3-5 Agent Sweet Spot

**Sources**: MultiAgentBench (ACL 2025), Anthropic engineering, Maxim reliability research, Addy Osmani

- Performance improves from 1 to 3 agents, then degrades beyond that
- Anthropic's production system typically spawns 3-5 subagents
- Coordination latency scales quadratically: 200ms at 5 agents, 2s at 50 agents
- 5-6 tasks per teammate keeps everyone productive (Osmani)

**Implication for V10**: Hard cap at 5 teammates per formation. Current formations already align but this must become a constraint, not a guideline.

#### Finding 2: The 20/20/60 Rule

**Sources**: Addy Osmani, MetaGPT, O'Reilly multi-agent architecture

- Spend 20% of effort on precise task decomposition
- Spend 20% on reviewing teammate outputs
- 60% is delegated execution
- "Spending 20% more time specifying work reduces implementation time by 50%"

**Implication for V10**: Team lead protocol should enforce planning phase before spawning. Currently optional.

#### Finding 3: Context Pollution is the #1 Risk

**Sources**: Google ADK, context rot research, MASFT failure taxonomy

- Expanding context does NOT improve performance — it degrades it ("context rot")
- Multi-agent systems use ~15x more tokens than single-agent chat
- Google ADK enforces "minimum required context per invocation"
- ADK's key innovation: context-as-compiled-view (not raw dump)

**Implication for V10**: Teammates should receive slim context:
- Task-specific subset of spec.md (not the whole file)
- File paths as references (not contents)
- Slim "teammate rules" (not full CLAUDE.md)
- Explicit "do NOT" instructions to prevent overlap

#### Finding 4: Architecture Over Prompts

**Sources**: ChatDev (ACL 2024), O'Reilly, 17x Error Trap

- ChatDev improved correctness from 25% to 40.6% through topology redesign, not prompt engineering
- "You can't prompt your way out of a system-level failure"
- Simple prompt engineering yields inconsistent improvements; structural redesign required

**Implication for V10**: Invest in formation design and hook enforcement rather than increasingly detailed teammate prompts.

#### Finding 5: Structured Artifacts Beat Messages

**Sources**: MetaGPT (ICLR 2024), Google ADK

- MetaGPT's key differentiator: structured artifacts (PRDs, API specs, design docs) passed between agents
- ADK uses narrative casting and action attribution when transferring between agents
- Assembly-line: each role produces structured outputs consumed by the next

**Implication for V10**: Define expected intermediate artifacts at formation boundaries. When architect completes, it produces a design doc — not just task updates.

#### Finding 6: The Blackboard Advantage

**Sources**: Blackboard Architecture Research (2025), Confluent event-driven patterns

- Blackboard paradigm achieves 13-57% improvement over baselines
- Agents independently decide whether to contribute based on capability
- V10's TaskList already functions as a lightweight blackboard

**Implication for V10**: For investigation formations, allow dynamic task claiming (agents self-select) rather than pre-assigning everything.

#### Finding 7: 14 Documented Failure Modes (MASFT)

**Source**: "Why Do Multi-Agent LLM Systems Fail?" (NeurIPS 2025)

Three categories, 14 modes:
1. **Specification failures** (5): ignoring constraints, role overstepping, step repetition, context loss, termination unawareness
2. **Inter-agent misalignment** (6): conversation resets, missing clarifications, task derailment, information withholding, ignoring peer input, reasoning-action mismatch
3. **Verification failures** (3): premature termination, incomplete verification, incorrect verification

**V10's exposure**:
- Role overstepping → mitigated by guard-write-gates
- Step repetition → NOT mitigated (teammates may duplicate searches)
- Information withholding → NOT mitigated (no cross-teammate sharing mechanism)
- Incomplete verification → partially mitigated (syntax only, not logic)
- Premature termination → mitigated by team lead review

#### Finding 8: Diverse Reasoning Beats Homogeneous

**Sources**: Multi-Agent Debate (ICLR 2025), MDPI 2025

- Diverse reasoning approaches per agent outperform homogeneous debate
- "Fixed mental set" problem: same methods with different personas = limited benefit
- Debate works for investigation/review, NOT for implementation

**Implication for V10**: bug-investigation teammates should receive DIFFERENT hypotheses and strategies, not just different file assignments.

### 4.3 Patterns V10 Should Adopt

| Pattern | Source | What It Is | V10 Application |
|---------|--------|-----------|-----------------|
| **Scoped handoffs** | Google ADK | Minimal context per agent, not full transcript | Slim teammate initialization |
| **Narrative casting** | Google ADK | Reframe prior agent output as context, not own work | Team lead reviewing teammate output |
| **Action attribution** | Google ADK | Mark which agent made which changes | Post-formation review |
| **Routines** | OpenAI Swarm | Instructions + tools + expected outputs as unit | Formation role definitions |
| **Circuit breakers** | Production reliability | Isolate failing agents, graduated response | Replace flat 30min timeout |
| **Closed-loop verification** | 17x Error Trap | Verify between stages, not just at end | Wave completion verification |
| **Hybrid parallel-deliberate** | O'Reilly | Fast specialists + slow aggregator | Team lead as deliberate aggregator |

### 4.4 Patterns V10 Should NOT Adopt

| Pattern | Source | Why Not |
|---------|--------|---------|
| **Tree topology (supervisor-of-supervisors)** | MultiAgentBench | Performed WORST in benchmarks |
| **Group discussion / broadcast chat** | MultiAgentBench | Worst across ALL metrics |
| **Full context inheritance on handoff** | Google ADK, context rot | Degrades performance |
| **Market-based task bidding** | Confluent | Overkill for 3-5 agent teams |
| **Swarm self-organization** | AWS Strands | Unpredictable for code implementation |

---

## Part 5: Gap Analysis — Current V10 vs Vision

### What V10 Has Today
- 8 pre-built formations (all 2-layer, same-terminal)
- Task-based coordination (TaskList, TaskUpdate, SendMessage)
- File ownership via formation registry + guard-write-gates hook
- Timeout protection for stalled teammates (30 min)
- Formation selection flowchart

### What V10 Is Missing (Research-Informed)

| Gap | Impact | Research Basis | Priority |
|-----|--------|---------------|----------|
| No teammate context minimization | Context rot degrades teammate performance | Google ADK, context rot research | **Critical** |
| No structured artifact handoffs | Teammates pass task updates, not design docs | MetaGPT structured communication | **High** |
| No closed-loop wave verification | Errors propagate to dependent waves | 17x Error Trap, MASFT FC3 | **High** |
| No step repetition prevention | Teammates duplicate searches/reads | MASFT FC1.3 | **High** |
| No cross-teammate information sharing | Discoveries stay siloed | MASFT FC2.4 (information withholding) | **High** |
| No xterm dispatch protocol | No crash isolation, no long-running agents | Production reliability patterns | **High** |
| No hybrid terminal model | Forces all-or-nothing terminal choice | Hybrid parallel-deliberate (O'Reilly) | **Medium** |
| No 3-layer model documented | Can't scale beyond 15 tasks effectively | MultiAgentBench (tree caution) | **Medium** |
| No cost model documentation | Users don't know formations cost 2-5x more | Maxim (2.9x multiplier), Anthropic (15x) | **Medium** |
| No diverse reasoning in investigations | Homogeneous approaches = limited benefit | Multi-Agent Debate (ICLR 2025) | **Medium** |
| No graduated stall response | Flat 30min timeout too blunt | Circuit breaker patterns | **Medium** |
| No formation chaining | Multi-sprint projects restart context | Checkpointing research | **Medium** |
| No formation-level metrics | Can't measure or improve formation effectiveness | Maxim production metrics | **Low** |
| No routine definitions for roles | Roles described loosely, not as formal units | OpenAI Swarm routines concept | **Low** |

---

## Part 6: Improvement Plan

> Derived from gap analysis + research findings. Ordered by priority and dependency.

### Phase 1: Context & Quality (Critical — Do First)

These address the highest-impact gaps with the lowest implementation risk.

#### 1.1 Slim Teammate Context Protocol

**Problem**: Teammates receive full CLAUDE.md + full spec.md + verbose task descriptions. Context pollution degrades output quality (Google ADK, context rot research).

**Solution**: Define a "teammate context template" that provides:
```
1. Teammate Rules (20 lines max — extracted subset of V10 protocol)
2. Task-specific spec excerpt (NOT full spec.md)
3. File paths to read (NOT file contents)
4. Explicit ownership boundaries ("you own X, do NOT touch Y")
5. Explicit "do NOT" list (prevent overlap with other teammates)
6. Expected output format (what artifact to produce)
```

**Effort**: Medium — requires new template + updating all 8 formation definitions
**Validation**: Compare teammate output quality before/after context reduction

#### 1.2 Closed-Loop Wave Verification

**Problem**: Wave completion triggers next wave automatically. If wave 1 produces errors, wave 2 builds on a broken foundation (17x Error Trap).

**Solution**: After each wave completes, team lead:
1. Reviews each teammate's completed task output
2. Runs validation (syntax + tests if applicable)
3. Creates a "wave-N-verified" checkpoint
4. Only THEN spawns wave N+1

**Effort**: Low — protocol change in team lead behavior, no new tooling
**Validation**: Track error rates in wave 2+ with/without verification gate

#### 1.3 Structured Artifact Handoffs

**Problem**: Formation phases hand off via task status updates. A task marked "completed" doesn't convey WHAT was produced (MetaGPT finding).

**Solution**: Each formation phase defines expected output artifacts:
```
architect phase:
  outputs:
    - architecture-decision.md (decisions + rationale)
    - file-map.txt (which files will be created/modified)
    - api-contract.md (endpoint definitions, if applicable)

implementer phase:
  outputs:
    - implementation report in task description
    - list of files modified with summary of changes
```

**Effort**: Medium — define artifact schemas per formation, update teammate prompts
**Validation**: Measure downstream teammate "confusion" (re-reads, task failures)

#### 1.4 Step Repetition Prevention

**Problem**: Multiple teammates independently search for the same files, read the same configs, or run the same queries (MASFT FC1.3).

**Solution**: Include in each teammate prompt:
- "Agent A is investigating X in files Y. Do NOT duplicate this work."
- "Your scope is ONLY: [specific files/directories]"
- "If you need information outside your scope, create a task requesting it"

**Effort**: Low — prompt updates to formation teammate templates
**Validation**: Monitor for duplicate file reads across teammates in same formation

---

### Phase 2: Coordination & Resilience (High Priority)

#### 2.1 Cross-Teammate Information Sharing

**Problem**: If teammate A discovers something relevant to teammate B's task, there's no mechanism to share it (MASFT FC2.4 — information withholding).

**Solution**: Allow teammates to create "info-share" tasks:
```python
TaskCreate(
    subject="[INFO] API requires auth header — relevant to frontend-impl",
    description="Discovered during backend implementation that /api/v1/* requires Bearer token...",
    metadata={"type": "info-share", "for": "frontend-impl"}
)
```
Team lead routes these to the relevant teammate, or teammates check for info-share tasks addressed to them.

**Effort**: Low — convention, no new tooling
**Validation**: Track info-share task creation and whether it prevented rework

#### 2.2 Graduated Stall Detection

**Problem**: Flat 30-minute timeout is too blunt. Some tasks legitimately take longer; some stalls should be caught earlier.

**Solution**: Three-tier response:
- **15 min**: Advisory — create a "stall-advisory" task visible to team lead
- **30 min**: Warning — team lead prompted to check on teammate
- **45 min**: Escalation — automatic task reassignment option offered

Plus: pattern detection for multiple teammates hitting the same error (retry storm prevention).

**Effort**: Medium — update stall detection hook with graduated thresholds
**Validation**: Measure false positive rate and actual stall recovery time

#### 2.3 Xterm Dispatch Protocol

**Problem**: No formalized way to run agents in separate terminals with filesystem coordination.

**Solution**: Define the protocol:

```
Dispatch:
  1. Create /sessions/{project}/.dispatch/{agent-id}/
     - prompt.md (full initial prompt)
     - config.json (ownership, task IDs, expected artifacts)
     - status (pending|running|completed|failed)

  2. Launch: claude --resume-from /sessions/{project}/.dispatch/{agent-id}/prompt.md
     (or via xterm/tmux split)

  3. Agent writes status updates to its dispatch directory

  4. Orchestrator polls .dispatch/*/status at intervals (or uses inotify)

Coordination:
  - Shared TaskList files in /sessions/{project}/.tasks/
  - File locks via flock() for concurrent writes
  - Agent writes .dispatch/{agent-id}/output.md on completion
  - Orchestrator reads output.md to review results
```

**Effort**: High — new protocol, new scripts, testing required
**Validation**: Run same formation in-process vs dispatched, compare outcomes

#### 2.4 Diverse Reasoning for Investigations

**Problem**: bug-investigation teammates receive different file assignments but use the same reasoning approach (ICLR 2025 debate research — "fixed mental set").

**Solution**: Assign diverse strategies:
```
Investigator 1: "Start from the error message, trace backwards through the call stack"
Investigator 2: "Start from the last known working state, diff forward"
Investigator 3: "Check external dependencies, config, and environment first"
```

**Effort**: Low — prompt changes to bug-investigation formation
**Validation**: Track root-cause-found rate per investigation strategy

---

### Phase 3: Scaling & Efficiency (Medium Priority)

#### 3.1 Formation Cost Documentation

**Problem**: Users don't know that formations cost 2-5x more tokens. They may use a 4-teammate formation for a task that a single agent could handle.

**Solution**: Add to formation selection guidance:
```
| Approach | Token Cost | When Worth It |
|----------|-----------|---------------|
| Direct (1 agent) | 1x | Tasks <5, sequential, deep reasoning |
| 2 teammates | ~2.5x | 6-10 tasks, parallelizable, clear ownership |
| 4 teammates | ~4x | 11-15 tasks, independent workstreams |
| 5 teammates | ~5x | 16+ tasks, diminishing returns beyond this |
```

"Is this task complex enough to justify 3x token cost?"

**Effort**: Low — documentation update
**Validation**: User feedback on whether cost awareness changes formation selection

#### 3.2 Formation Chaining Protocol

**Problem**: When a project needs multiple formations in sequence (e.g., new-project → feature-impl), context is lost between formations.

**Solution**: Define formation boundary protocol:
1. Outgoing formation produces a "formation summary" artifact
2. Summary includes: what was done, what files were modified, what decisions were made, what's left
3. Incoming formation receives the summary as part of its initial context
4. Summary stored at `/sessions/{project}/.formation-history/{N}-{name}.md`

**Effort**: Medium — new protocol + summary template
**Validation**: Compare cross-formation error rates with/without summary handoff

#### 3.3 20/20/60 Team Lead Protocol

**Problem**: Team leads jump straight to spawning teammates without sufficient planning (Osmani 20/20/60 rule).

**Solution**: Formalize the team lead workflow:
```
Phase 1 — Plan (20% of effort):
  - Read spec.md and all relevant source files
  - Decompose into precise tasks with clear boundaries
  - Define file ownership map
  - Identify parallelization opportunities
  - Create all tasks BEFORE spawning anyone

Phase 2 — Execute (60%):
  - Spawn teammates
  - Monitor via TaskList
  - Route info-share tasks
  - Handle blockers

Phase 3 — Review (20%):
  - Verify each teammate's output
  - Run integration validation
  - Synthesize results
  - Report to user/orchestrator
```

**Effort**: Low — protocol documentation + team lead prompt update
**Validation**: Track task decomposition quality (tasks needing mid-formation revision)

#### 3.4 Hybrid Terminal Model

**Problem**: Same-terminal teams have crash coupling and resource limits. Pure xterm has no real-time coordination. Need both.

**Solution**: Formalize the hybrid:
- Team lead stays in-process (real-time coordination with orchestrator)
- Workers that need >30 min OR crash isolation dispatch to xterm
- Team lead coordinates with dispatched workers via filesystem protocol (2.3)
- Team lead coordinates with in-process workers via SendMessage

**Effort**: Medium — combines same-terminal and xterm protocols
**Validation**: Test with a feature-impl formation where backend dispatches, frontend stays in-process

---

### Phase 4: Advanced (Low Priority / Experimental)

#### 4.1 Routine Definitions for Roles
Define each formation role as a formal routine: instructions, allowed tool set, expected input artifacts, expected output artifacts. Following OpenAI Swarm's model.

#### 4.2 Limited Peer-to-Peer Communication
Allow teammates to create tasks addressed to other specific teammates, enabling graph-like information flow while maintaining team lead oversight. MultiAgentBench showed graph > star.

#### 4.3 Formation-Level Metrics
Track per-formation: total tokens, wall clock time, tasks completed/failed, teammate stalls, rework rate. Use data to iteratively refine formation patterns.

#### 4.4 Action Attribution in Reviews
When team lead reviews teammate output, explicitly mark which changes came from which teammate. Prevents context confusion in multi-wave formations. (Google ADK pattern.)

#### 4.5 Formation-Level Summarization
At formation completion, auto-generate a structured summary of all work done before proceeding. Prevents context rot in long-running multi-formation sessions.

---

## Part 7: The 3-Layer Question

Research strongly suggests **caution** on 3-layer:

**Against 3-layer** (strong evidence):
- MultiAgentBench: tree topology performed WORST
- Communication latency doubles with each layer
- Middle management adds overhead without proportional benefit
- LangGraph's supervisor-of-supervisors is not recommended

**For 3-layer** (situational):
- Orchestrator context saturation on >15 task projects
- Orchestrator needs to stay available for user interaction
- Multi-formation projects where the orchestrator manages formation transitions

**Recommendation**: Do NOT implement 3-layer as a default model. Instead:
- Keep 2-layer as the primary model (validated)
- Use xterm dispatch to offload heavy work (crash isolation without adding layers)
- Only consider 3-layer for 30+ task projects where the orchestrator is genuinely context-saturated
- If 3-layer is used, the team lead should be in-process (for real-time coordination) and workers dispatched to xterm

---

## Part 8: Source Summary

| # | Source | Key Takeaway |
|---|--------|-------------|
| 1 | MultiAgentBench (ACL 2025) | Graph > Star > Chain >> Tree. 3 agents optimal. Group discussion worst. |
| 2 | HMAS Taxonomy (2025) | Hybrid centralized-strategy + decentralized-tactics = best paradigm |
| 3 | Anthropic Building Effective Agents | 5 composable patterns. Start simple. Focused attention per call. |
| 4 | Anthropic Multi-Agent Research | 3-5 subagents, 90.2% improvement, 15x token cost |
| 5 | Maxim Reliability | 2.9x context cost, quadratic coordination scaling, 97% vs 99.5% success |
| 6 | MASFT (NeurIPS 2025) | 14 failure modes. Communication breakdowns > individual limitations. |
| 7 | 17x Error Trap (2026) | Topology is the solution, not more agents. 4-agent topology threshold. |
| 8 | MetaGPT (ICLR 2024) | Structured artifacts between agents. SOPs as formation definitions. |
| 9 | ChatDev (ACL 2024) | Topology redesign > prompt engineering. 25-40% correctness. |
| 10 | O'Reilly Multi-Agent Architecture | Fast specialists + slow aggregator. Architecture > prompts. |
| 11 | Google ADK (2025) | Context-as-compiled-view. Minimal context per invocation. Scoped handoffs. |
| 12 | AWS Strands | Graph/Swarm/Workflow. Shared invocation state invisible to LLM. |
| 13 | OpenAI Swarm / Agents SDK | Routines and handoffs. Stateless between calls. |
| 14 | Confluent Event-Driven | Orchestrator-worker, hierarchical, blackboard, market-based |
| 15 | Blackboard Research (2025) | 13-57% improvement. Self-selection > pre-assignment. |
| 16 | Multi-Agent Debate (ICLR 2025) | Diverse reasoning > homogeneous. Debate for review, not implementation. |
| 17 | Addy Osmani Claude Code Swarms | 5-6 tasks/teammate. 20/20/60 rule. Precision > speed. |
| 18 | Framework Comparison (2025-2026) | V10 = CrewAI delegation + LangGraph explicit state. Strong hybrid. |
| 19 | LangGraph Supervisor (2025) | Supervisor-worker validated. Supervisor-of-supervisors NOT recommended. |
| 20 | Context Rot Research (2025) | More context != better. Performance degrades with irrelevant context. |

---

*V10 Vision Document v1.0 — Foundation for orchestration improvements*
*20 research sources, 4 improvement phases, 14 specific actions*
*2026-02-13*
