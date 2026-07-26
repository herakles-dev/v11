# Multi-Agent Orchestration Patterns: Research Findings

> Research date: 2026-02-13
> Purpose: Actionable findings for improving the V10 Agent Team Protocol
> Scope: Production multi-agent systems, academic research, framework analysis (2024-2026)

---

## Table of Contents

1. [Orchestration Topologies](#1-orchestration-topologies)
2. [Team Size and Scaling](#2-team-size-and-scaling)
3. [Communication and Coordination](#3-communication-and-coordination)
4. [Context and Memory Management](#4-context-and-memory-management)
5. [Formation Patterns That Work](#5-formation-patterns-that-work)
6. [Process Isolation and Fault Tolerance](#6-process-isolation-and-fault-tolerance)
7. [Anti-Patterns and Failure Modes](#7-anti-patterns-and-failure-modes)
8. [Framework-Specific Findings](#8-framework-specific-findings)
9. [Synthesis: Recommendations for V10](#9-synthesis-recommendations-for-v10)

---

## 1. Orchestration Topologies

### Source: MultiAgentBench (ACL 2025)
**Paper**: "MultiAgentBench: Evaluating the Collaboration and Competition of LLM agents"
**URL**: https://arxiv.org/abs/2503.01935

#### Pattern: Graph vs Star vs Tree vs Chain Coordination Topologies

**Evidence**:
- Graph-based coordination achieved the best task performance, planning efficiency, AND token efficiency across all topologies tested.
- Star topology yielded comparable task scores to graph but with more centralized bottleneck risk.
- Tree topology performed WORST: high token consumption combined with the lowest task and coordination scores.
- Chain topology showed moderate performance across all metrics.

**Scaling findings**:
- Performance improved from 1 to 7 iterations, then dropped sharply at 10 iterations.
- At 20 iterations, task score recovered but coordination remained flat.
- Moving from 1 to 3 agents improved coordination scores significantly.
- Further increases beyond 3 introduced "additional coordination challenges that counterbalance task performance gains."
- Overall KPI decreased with larger teams in research tasks.

**Planning strategy**:
- Cognitive Evolving Planning demonstrated superior coordination, significantly outperforming alternatives.
- Chain-of-Thought (CoT) performed well for task completion.
- Group Discussion scored worst across ALL metrics. "An overly large planning group hinders effectiveness."

**Applicability to V10**:
- V10's hub-spoke model (team lead to teammates) approximates a star topology. The evidence suggests this is solid but not optimal. Consider allowing limited peer-to-peer communication for graph-like benefits.
- The tree topology failure is critical: V10 should NOT add a middle management layer (supervisor-of-supervisors) without strong justification. Two layers (lead + workers) is the sweet spot.
- Group Discussion failing badly validates V10's approach of avoiding broadcast-heavy coordination. Teammates should communicate through tasks and files, not group chat.
- The 3-agent sweet spot for coordination improvement aligns with V10's typical formation sizes (2-4 teammates per formation).

---

### Source: Taxonomy of Hierarchical Multi-Agent Systems (2025)
**Paper**: "A Taxonomy of Hierarchical Multi-Agent Systems: Design Patterns, Coordination Mechanisms, and Industrial Applications"
**URL**: https://arxiv.org/abs/2508.12683

#### Pattern: Five-Axis Taxonomy for HMAS Design

The paper proposes five fundamental axes:

1. **Control Hierarchy**: Centralized to decentralized authority distribution
2. **Information Flow**: Top-down commands, bottom-up feedback, lateral peer exchange
3. **Role and Task Delegation**: Fixed predetermined roles vs dynamic emergent allocation
4. **Temporal Layering**: Long-horizon strategy at upper levels, short-horizon tactics below
5. **Communication Structure**: Static vs dynamic topology

**Evidence**:
- Hierarchical organizations improve global efficiency at the cost of robustness.
- Fully decentralized "team" organizations maximize resilience but are less efficient in large groups.
- Hybrid approaches combining hierarchical strategic coordination with decentralized tactical execution perform best in modern practical systems.
- Feudal Multi-Agent Hierarchies (FMH) improved performance and scalability compared to fully centralized or distributed learning by separating long-term goal-setting from short-term action execution.
- Communication efficiency improved when agents "share their big picture intent occasionally, rather than every step."

**Applicability to V10**:
- V10's team lead model is a hybrid: centralized strategic planning (team lead creates all tasks, assigns ownership) with decentralized tactical execution (teammates work independently). This aligns with the best-performing paradigm.
- The temporal layering principle is already implicit in V10 (team lead handles sprint/gate-level decisions, teammates handle task-level implementation) but could be made more explicit.
- The "share big picture intent occasionally" finding validates V10's approach where teammates communicate via task updates rather than constant messaging.
- FMH's success with "coarse objectives instead of micromanaging each step" directly supports V10's practice of giving teammates spec.md + task IDs rather than step-by-step instructions.

---

### Source: Anthropic "Building Effective Agents" Guide
**URL**: https://www.anthropic.com/research/building-effective-agents

#### Pattern: Five Composable Workflow Patterns

1. **Prompt Chaining**: Sequential LLM calls with gates between steps. Best for cleanly decomposable fixed subtasks. Trades latency for accuracy.
2. **Routing**: Classifies input, directs to specialized downstream. Best when distinct categories need different handling.
3. **Parallelization**: Two sub-patterns:
   - Sectioning: independent parallel subtasks
   - Voting: same task repeated for diverse outputs
4. **Orchestrator-Workers**: Central LLM dynamically decomposes, delegates, synthesizes. Best when subtasks cannot be predefined.
5. **Evaluator-Optimizer**: Generate-evaluate loop. Best when clear evaluation criteria exist.

**Critical recommendation from Anthropic**: "Start with simple prompts, optimize them with comprehensive evaluation, and add multi-step agentic systems only when simpler solutions fall short."

**Key insight**: "LLMs generally perform better when each consideration is handled by a separate LLM call, allowing focused attention."

**Tool design emphasis**: Anthropic spent more optimization effort on tools than overall prompts for SWE-bench. Absolute filepaths eliminated relative path errors.

**Applicability to V10**:
- V10 formations map well to these patterns. The `bug-investigation` formation uses Parallelization (Voting variant: competing hypotheses). The `feature-impl` formation uses Orchestrator-Workers. The `code-review` formation uses Parallelization (Sectioning: security + performance + coverage reviewers).
- The "focused attention per LLM call" principle validates V10's separate-context-per-teammate design.
- Anthropic's emphasis on tool design over prompts is underexploited in V10. The hook system could serve as the "tool interface" layer that gets the same investment.
- The recommendation to start simple is important: V10 should continue defaulting to direct work for 1-5 tasks and only escalate to formations when complexity warrants it.

---

## 2. Team Size and Scaling

### Source: Anthropic Multi-Agent Research System
**URL**: https://www.anthropic.com/engineering/multi-agent-research-system

#### Pattern: Graduated Subagent Allocation

**Evidence (production system)**:
- Simple fact-finding: 1 agent, 3-10 tool calls
- Direct comparisons: 2-4 subagents, 10-15 calls each
- Complex research: 10+ subagents with divided responsibilities
- Lead agent typically spawns 3-5 subagents in parallel
- Multi-agent system outperformed single-agent Claude Opus 4 by 90.2% on internal research evals
- Token usage explains 80% of variance in performance
- Multi-agent systems consume approximately 15x more tokens than chat interactions
- Parallel tool calling cut research time by up to 90% for complex queries

**Key design decisions**:
- Claude Opus 4 as lead, Claude Sonnet 4 as subagents (cost-performance optimization)
- Synchronous subagent execution (simpler coordination, acknowledged bottleneck)
- Agents start with broad queries, then progressively narrow
- Tool-testing agent reduced task completion time by 40% by rewriting tool descriptions

**Applicability to V10**:
- The 3-5 subagent sweet spot matches V10's typical formation sizes perfectly.
- The graduated allocation model (1 for simple, 2-4 for moderate, 10+ for complex) should be codified in V10's formation selection logic.
- The 90.2% improvement validates the multi-agent approach for complex tasks.
- The 15x token cost is real and should be surfaced in V10's effort/cost guidance.
- V10 already uses Opus as lead and could use Sonnet for teammates. The cost model supports this.

---

### Source: Maxim Production Reliability Research
**URL**: https://www.getmaxim.ai/articles/multi-agent-system-reliability-failure-patterns-root-causes-and-production-validation-strategies/

#### Pattern: Coordination Tax Quantification

**Evidence (production metrics)**:
- Per-interaction handoff latency: 100-500ms coordination overhead
- Context reconstruction costs: 29,000 tokens vs 10,000 for single agent (2.9x multiplier)
- Token multiplier: 2-5x cost increases typical for multi-agent vs single-agent
- Coordination latency scaling: 200ms with 5 agents, 2 seconds with 50 agents (quadratic)
- Error rate: multi-agent systems observe ~97% success vs 99.5% for single-agent
- 15 concurrent agents at 10 req/s = 150 req/s aggregate, exceeding 100/s rate limits
- Document analysis: 8s reduced to 3s processing but added 2s coordination (37% net improvement)
- Parallel execution ratio of 75% = maximum 4x theoretical speedup regardless of agent count

**When multi-agent delivers value**:
- High-volume independent tasks with zero inter-task communication
- Embarrassingly parallel research with read-heavy operations (>10:1 read-write ratio)
- Bounded coordination with explicit state machines and deterministic handoffs

**Applicability to V10**:
- The quadratic coordination scaling (200ms at 5, 2s at 50) confirms that V10's formations should cap at 5-6 active teammates. Anything beyond that hits diminishing returns.
- The 2.9x token multiplier should be documented as expected cost overhead for formations.
- The 97% vs 99.5% success rate gap means V10 needs strong error recovery. The current stall detection (30min timeout) is a start, but the hook-based verification (verify-syntax) is critical.
- The >10:1 read-write ratio heuristic is actionable: formations work best for tasks that are mostly reading/analyzing with targeted writes, not for tasks where every agent is writing to many files.

---

### Source: Addy Osmani on Claude Code Swarms
**URL**: https://addyosmani.com/blog/claude-code-agent-teams/

#### Pattern: 5-6 Tasks Per Teammate

**Evidence**:
- 5-6 tasks per teammate keeps everyone productive and lets the lead reassign work if stuck.
- Small teams (3-5 agents) best for feature work across layers.
- Larger teams for competing hypotheses in debugging.
- Individual specialists for narrow, scoped tasks.
- "Plan before delegating. Spending 20% more time specifying work reduces implementation time by 50%+ through reduced back-and-forth and rework."
- Compound engineering ratio: plan (20%), review (20%), execute (60%).

**Applicability to V10**:
- V10 should adopt the 5-6 tasks per teammate guideline as a hard recommendation in formation planning.
- The 20/20/60 planning ratio should be built into the team lead protocol: spend the first 20% of effort on precise task decomposition and specification before spawning any teammates.
- The finding that specification precision directly correlates with output quality validates V10's approach of requiring spec.md before any work begins.

---

## 3. Communication and Coordination

### Source: O'Reilly "Designing Effective Multi-Agent Architectures"
**URL**: https://www.oreilly.com/radar/designing-effective-multi-agent-architectures/

#### Pattern: Hybrid Parallel-Deliberate Architecture

**Evidence**:
- "Many production systems benefit from hybrid patterns. A small number of fast specialists operate in parallel, while a slower, more deliberate agent periodically aggregates results, checks assumptions, and decides whether the system should continue or stop."
- Performance does NOT increase monotonically with agent count.
- Self-interference emerges without clear structure.
- "You can't prompt your way out of a system-level failure. If your agents are consistently underperforming, the issue likely isn't the wording of the instruction; it's the architecture of the collaboration."
- Research papers on agentic systems: 820 (2024) to 2,500+ (2025).

**Architecture "hiring" framework**:
- Decoder-only models (GPT, Claude): Generators and planners
- Encoder-only models (BERT): Analysts for ranking, filtering, relevance scoring
- Mixture of Experts: Selective compute for specialist tasks
- Reasoning models: Test-time compute for reflection and verification

**Applicability to V10**:
- V10's team lead already serves as the "slower, more deliberate agent" that aggregates. This is validated as the right pattern.
- The non-monotonic scaling warning should be prominent in V10 docs: adding more teammates does NOT always help.
- The "architecture not prompts" insight means V10 should invest in formation design and hook enforcement rather than increasingly detailed teammate system prompts.

---

### Source: AWS Strands Agents Patterns
**URL**: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/

#### Pattern: Three Production Coordination Models

1. **Graph**: Developer-defined flowchart with LLM-driven path decisions at each node. Cycles allowed. Best for conditional logic and branching.
2. **Swarm**: Autonomous team with dynamic handoffs via `handoff_to_agent` tool. Sequential and autonomous. Best for specialized collaboration and exploration.
3. **Workflow**: Pre-defined DAG executed deterministically. Independent tasks run in parallel. No cycles. Best for repeatable operations.

**Key innovation**: Shared `invocation_state` propagates context to all agents and tools but remains invisible to LLM reasoning, preserving separation between configuration and reasoning context.

**Applicability to V10**:
- V10's formation model maps to the Workflow pattern (DAG with parallel independent tasks and sequential dependent ones).
- The `invocation_state` concept (shared context invisible to LLM) is worth adopting. V10 could implement a shared formation registry that teammates access via tools rather than having it injected into their context window.
- V10 does not currently support the Swarm handoff pattern (agent-to-agent transfer). This could be valuable for the `bug-investigation` formation where one investigator discovers something and wants to hand off to a specialist.

---

### Source: Confluent Event-Driven Multi-Agent Patterns (2025)
**URL**: https://www.confluent.io/blog/event-driven-multi-agent-systems/

#### Pattern: Four Event-Driven Coordination Models

1. **Orchestrator-Worker**: Central orchestrator assigns tasks via partitioned topics. Workers pull from assigned partitions. Output to second topic for downstream consumption.
2. **Hierarchical Agent**: Layered agents where higher levels oversee lower levels. Event-driven recursive decomposition.
3. **Blackboard**: Central shared state that agents post to and read from. Agents independently decide whether to contribute based on capability.
4. **Market-Based**: Bid/ask topics with market maker matching. "Eliminates the quadratic connections that otherwise occur between solver agents."

**Applicability to V10**:
- V10's task system (TaskCreate/TaskUpdate/TaskList) already functions as a lightweight blackboard pattern. Teammates post status, the team lead reads it. This is validated as an effective coordination model.
- The market-based pattern's elimination of quadratic connections is interesting for V10's formation scaling. Instead of the team lead individually coordinating with each teammate, tasks could serve as the matching mechanism.
- The event-driven model (Kafka-style) is overkill for V10's process-level coordination, but the principle of decoupled, asynchronous communication via shared state is exactly what V10's task system provides.

---

## 4. Context and Memory Management

### Source: Google ADK Framework (2025)
**URL**: https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/

#### Pattern: Context as Compiled View Over Stateful System

**Evidence**:
- ADK separates storage (Sessions, Memory, Artifacts) from presentation (working context views).
- Each model invocation sees ONLY the minimum required context; agents explicitly request more via tools.
- Context builds through ordered, named processors (not ad-hoc string concatenation).
- Context compaction: LLM summarizes older events over sliding windows, writes summaries back as Session events. Raw events then pruned.
- Artifacts use a handle pattern: large data lives in ArtifactService, agents see lightweight references. On-demand expansion, offloaded after use. Converts "5MB of noise in every prompt" into "precise, on-demand resources."
- Cache-friendliness as hard design constraint: stable prefixes (system instructions, identity) + variable suffixes (latest user turns, tool outputs).

**Multi-agent handoff strategies**:
- Default mode: Full caller working context (sub-agent benefits from entire history)
- None mode: No prior history; only new prompt + minimal context
- Narrative casting: Prior assistant messages recast as context rather than new agent's outputs
- Action attribution: Tool calls from other agents marked/summarized so new agent acts on results without confusing execution

**Applicability to V10**:
- V10's current teammate initialization (spec.md content + relevant file paths + task IDs) maps to ADK's "None mode" handoff. This is correct for most formations.
- The narrative casting technique is valuable: when a teammate finishes and the team lead reviews their work, the lead should reframe the teammate's output as context, not as its own previous actions. V10 should document this pattern.
- The handle pattern for large artifacts is directly applicable. Teammates should reference file paths rather than including file contents in task descriptions.
- Context compaction is handled natively by Claude Code's auto-compaction, but V10 could benefit from explicit summarization at formation boundaries (when all teammates complete, summarize findings before proceeding).

---

### Source: Blackboard Architecture Research (2025)
**Paper**: "LLM-based Multi-Agent Blackboard System for Information Discovery"
**URL**: https://arxiv.org/abs/2510.01285

#### Pattern: Centralized Blackboard for Agent Coordination

**Evidence**:
- Blackboard paradigm achieves 13% to 57% relative improvement over best performing baselines in end-to-end problem solving.
- Central agent posts task descriptions; subordinate agents independently decide whether to contribute based on capability.
- Enables flexible collaboration without explicit agent-to-agent communication channels.

**Applicability to V10**:
- V10's task system is already a partial blackboard. But V10 currently pre-assigns tasks to specific teammates rather than letting them self-select. For the `bug-investigation` formation, allowing agents to claim tasks based on discovered evidence (rather than pre-assignment) could leverage the blackboard advantage.
- The 13-57% improvement is significant enough to warrant experimenting with a more dynamic task-claiming model for investigation-type formations.

---

### Source: Context Pollution and "Context Rot" Research (2025)

#### Pattern: Context Window Saturation Degrades Performance

**Evidence**:
- Expanding context windows does NOT guarantee improved model performance.
- "Context rot": models struggle to effectively utilize information distributed across extremely long contexts. Performance can actually degrade as input tokens increase.
- Irrelevant context actively degrades performance even when the task itself is clear.
- Multi-agent architectures solve this by distributing context across agents with separate windows.

**Applicability to V10**:
- This is the fundamental justification for V10's separate-context-per-teammate design. Each teammate gets a clean context with only task-relevant information.
- V10 should be more aggressive about context minimization in teammate initialization. Currently, teammates receive spec.md + task IDs + file ownership. Consider whether spec.md (which can be 100 lines) is always necessary, or whether a task-specific excerpt would be better.
- The context rot finding argues against V10's current practice of including the full V10 CLAUDE.md protocol in every teammate's context. A slim "teammate rules" subset would be more effective.

---

## 5. Formation Patterns That Work

### Source: MetaGPT (ICLR 2024)
**Paper**: "MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework"
**URL**: https://arxiv.org/abs/2308.00352

#### Pattern: Structured Communication with SOPs

**Evidence**:
- MetaGPT uses structured communication interfaces (not free-form natural language) between agents.
- Agents follow Standard Operating Procedures (SOPs) mirroring real software companies: product manager, architect, project manager, engineer.
- Assembly line paradigm: each role produces structured outputs consumed by the next.
- MetaGPT outperformed single-agent approaches (GPT-Engineer) on complex software tasks.
- Key differentiator: structured artifacts (PRDs, system designs, API specs) passed between agents rather than conversational messages.

**Applicability to V10**:
- V10 should adopt structured artifact handoffs between formation stages. When `spec-architect-v10` completes, it should produce a structured design document (not just task descriptions) that `spec-implementer-v10` consumes.
- The SOP concept maps to V10's formation definitions. Each formation could define expected intermediate artifacts, not just task completions.
- V10's current communication (task updates + file system) is already more structured than free-form chat. This is validated as the correct approach.

---

### Source: ChatDev (ACL 2024)
**Paper**: "ChatDev: Communicative Agents for Software Development"
**URL**: https://aclanthology.org/2024.acl-long.810.pdf

#### Pattern: Waterfall-Model Agent Organization

**Evidence**:
- Simulates a virtual software company with waterfall phases: designing, coding, testing, documenting.
- Agents form organizational structure and collaborate through functional seminars.
- ChatDev outperformed single-agent GPT-Engineer, confirming that "complex tasks are more challenging to solve in a single-step solution."
- However, ChatDev showed correctness rates as low as 25% on some benchmarks (improved to 40.6% with topology redesign).

**Applicability to V10**:
- The waterfall phase model validates V10's `new-project` formation (architect -> scaffold -> implement -> test). Sequential phases with clear handoffs work for greenfield projects.
- The low baseline correctness (25%) and modest improvement (to 40.6%) is a cautionary finding: even well-structured multi-agent software development has high failure rates. V10's verification hooks (verify-syntax, enforce-test-coverage) are essential.
- ChatDev's improvement from topology redesign (not prompt engineering) reinforces the "architecture over prompts" principle.

---

### Source: Multi-Agent Debate Patterns (ICLR 2025 + MDPI 2025)
**URLs**: https://arxiv.org/abs/2408.08435, https://www.mdpi.com/2076-3417/15/7/3676

#### Pattern: Adversarial Debate for Quality Improvement

**Evidence**:
- Multi-agent debate significantly improves mathematical reasoning and reduces factual hallucinations.
- Adversarial debates and voting mechanisms enable cross-verification among agents.
- Diverse Multi-Agent Debate (using different reasoning approaches per agent) outperforms homogeneous debate.
- LIMITATION: debate-driven approaches lack guarantees under adaptive adversarial pressure and may not generalize.
- "Fixed mental set" problem: if agents use the same reasoning methods even with different personas, debate provides limited benefit.

**Applicability to V10**:
- V10's `bug-investigation` formation already uses competing hypotheses (a debate variant). This is validated.
- V10's `code-review` formation could benefit from adversarial elements: one reviewer specifically tasked with finding flaws in another reviewer's assessment.
- The "diverse reasoning approaches" finding is important: V10 teammates in investigation formations should receive DIFFERENT initial hypotheses or investigation strategies, not just different file assignments.
- The debate pattern should NOT be used for implementation tasks (where there is a single correct output), only for investigation, review, and decision-making tasks.

---

### Source: OpenAI Swarm / Agents SDK (2025)
**URL**: https://github.com/openai/swarm

#### Pattern: Routines and Handoffs

**Evidence**:
- Routines: natural language instructions + tool access as a unit.
- Handoffs: agent transfers full conversation context to another agent (like a phone call transfer).
- Stateless between calls: every handoff must include all context the next agent needs.
- Production evolution: OpenAI Agents SDK (March 2025) replaced Swarm as production-ready framework.
- Framework runs on user infrastructure (not hosted), giving full control over execution loop and state.

**Applicability to V10**:
- V10's teammate spawning is a handoff with explicit context (spec.md + task IDs). This aligns with the Swarm model.
- The stateless principle is important: V10 correctly treats each teammate as a fresh session with explicitly provided context rather than assuming shared state.
- V10 could adopt the "routine" concept more explicitly: each formation role could be defined as a routine (instructions + allowed tools + expected outputs).

---

## 6. Process Isolation and Fault Tolerance

### Source: Production Multi-Agent System Reliability (2025-2026)
**URLs**: https://www.getmaxim.ai/articles/multi-agent-system-reliability-failure-patterns-root-causes-and-production-validation-strategies/, https://www.clickittech.com/ai/multi-agent-system-architecture/

#### Pattern: Circuit Breakers and Sandboxed Execution

**Evidence**:
- Sandboxing: isolate execution contexts to prevent rogue agents from corrupting others.
- Circuit breakers: isolate repeatedly failing agents instead of letting them cascade failures.
- Chaos engineering: deliberately inject failures to observe system response.
- Most large-scale production systems in 2026 favor asynchronous coordination combined with timeouts.
- Message passing preferred for enterprise workflows where traceability and isolation are priorities.
- Retry storms: cascading failures trigger exponential load, multiplying by 10x within seconds.
- Thundering herd: 50 agents simultaneously requesting resources create load spikes.
- Production teams report 70% MTTR reduction using comprehensive agent debugging vs log-based approaches.

**Fault tolerance patterns**:
- Checkpointing as foundational requirement for production-grade systems.
- If one agent fails, another can detect, correct, or compensate.
- Rainbow deployments for gradual traffic shifting between versions without disrupting running agents.

**Applicability to V10**:
- V10's stall detection (30min timeout) is a basic circuit breaker. Consider adding graduated responses: warning at 15min, alert at 30min, automatic task reassignment at 45min.
- V10 should implement teammate-level isolation more explicitly. Currently, teammates share the file system (which is the coordination mechanism). The `.formation-registry.json` ownership model provides write isolation, but read isolation (preventing teammates from being confused by other teammates' in-progress work) is not addressed.
- The checkpointing principle maps to V10's task system: each TaskUpdate(status="completed") is a checkpoint. But V10 lacks rollback capability if a teammate's work is found to be incorrect after completion.
- Retry storms are a risk if V10 teammates encounter the same error (e.g., a missing dependency). The team lead should detect when multiple teammates report similar errors and pause the formation for diagnosis rather than letting each teammate retry independently.

---

### Source: Google ADK Multi-Agent Handoffs
**URL**: https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/

#### Pattern: Scoped Handoffs with Context Translation

**Evidence**:
- Two interaction patterns: Agents-as-Tools (focused prompt, no ancestral history) vs Agent Transfer (full control handoff with session inheritance).
- Specialized agents should get MINIMAL context, not inherit a giant transcript.
- Conversation translation on transfer: narrative casting (reframe prior messages as context) and action attribution (mark/summarize other agents' tool calls).
- Fresh working context built from sub-agent's perspective while preserving factual history in the session.

**Applicability to V10**:
- V10's teammate spawning uses Agents-as-Tools pattern (clean context with task-specific info). This is validated for most use cases.
- V10 should implement action attribution when the team lead reviews a teammate's work: clearly marking which changes were made by which teammate before passing context to the next phase.
- For formations with sequential dependencies (architect -> implementer), V10 should implement narrative casting: the architect's output is reframed as "design context" rather than being presented as the implementer's own prior work.

---

## 7. Anti-Patterns and Failure Modes

### Source: "Why Do Multi-Agent LLM Systems Fail?" (NeurIPS 2025)
**Paper**: Cemri, Pan, Yang et al.
**URL**: https://arxiv.org/abs/2503.13657

#### Pattern: MASFT - 14 Failure Modes in Three Categories

**FC1: Specification and System Design Failures (5 modes)**:
1. Disobey task specification: agents ignore constraints
2. Disobey role specification: agents overstep responsibilities
3. Step repetition: unnecessary reiteration of completed tasks
4. Loss of conversation history: context truncation and reversion
5. Unaware of termination conditions: failure to recognize when to stop

**FC2: Inter-Agent Misalignment (6 modes)**:
6. Conversation reset: unwarranted restarts losing progress
7. Fail to ask for clarification: missing critical information
8. Task derailment: deviation from objectives
9. Information withholding: failing to share insights
10. Ignored other agent's input: disregarding peer recommendations
11. Reasoning-action mismatch: discrepancy between logic and execution

**FC3: Task Verification and Termination (3 modes)**:
12. Premature termination: ending before objectives met
13. No or incomplete verification: omitting outcome checking
14. Incorrect verification: inadequate validation

**Evidence**:
- ChatDev correctness rates as low as 25% on tested benchmarks.
- Failures stem primarily from inter-agent communication breakdowns, NOT individual agent limitations.
- No single failure category dominates, indicating systemic issues across all design dimensions.
- Different frameworks show different vulnerability profiles (AG2: more verification issues; ChatDev: more specification/misalignment issues).
- Simple prompt engineering yields inconsistent improvements; structural redesign required.
- Parallels drawn to High-Reliability Organizations (HRO) theory.

**Specific examples**:
- Supervisor failed to communicate API specs to worker, causing incorrect credentials and task failure (information withholding).
- CPO agent assumed CEO's role by making unilateral decisions, violating delegation (role specification violation).
- Verifier only checked compilation without executing programs, allowing defects to propagate (incomplete verification).

**Applicability to V10**:
- V10 is vulnerable to multiple MASFT failure modes:
  - **Role specification violation** (FC1.2): Teammates may exceed their file ownership boundaries. The `guard-write-gates` hook addresses this.
  - **Step repetition** (FC1.3): Multiple teammates might perform the same search or read the same files. V10 should include explicit "do NOT do X" instructions in teammate prompts.
  - **Information withholding** (FC2.4): Teammates only communicate via task updates and files. If a teammate discovers something relevant to another teammate's task, there is no mechanism to share it. Consider allowing teammates to create new tasks with notes for other teammates.
  - **Incomplete verification** (FC3.2): V10's verify-syntax hook catches syntax errors but not logical errors. The enforce-test-coverage hook helps but only for deployments.
  - **Premature termination** (FC3.1): Teammates may mark tasks complete without thorough verification. The team lead review step is the primary defense.
- The HRO parallel is important: V10 should adopt HRO principles of preoccupation with failure (expect teammate errors), reluctance to simplify (verify teammate outputs), and deference to expertise (let specialists handle their domain).

---

### Source: "The 17x Error Trap" (Towards Data Science, 2026)
**URL**: https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/

#### Pattern: Naive "Bag of Agents" Amplifies Errors 17x

**Evidence**:
- Adding agents without topology amplifies errors at roughly 17x severity.
- The solution is "the Topology of Coordination, not simply adding more agents."
- 10 fundamental agent archetypes that most complex systems decompose into.
- Functional plane arrangement with closed-loop error suppression required.
- A structured topology is necessary beyond the 4-agent threshold.

**Applicability to V10**:
- V10's formation system IS the topology. This is the right approach.
- The 4-agent threshold for requiring topology is lower than V10's current guidance (6+ tasks triggers team formation). V10 may want to require explicit formation selection even for 4-5 task projects if they involve multiple agents.
- The "closed-loop error suppression" concept should be implemented: team lead actively validates each teammate's output before allowing dependent work to proceed, not just at formation completion.

---

### Source: Production Anti-Pattern Catalog (Multiple Sources)

#### Consolidated Anti-Patterns with V10 Relevance

| Anti-Pattern | Description | V10 Risk Level | V10 Mitigation |
|--------------|-------------|----------------|----------------|
| **Central bottleneck** | Orchestrator as single point of failure | MEDIUM | Team lead crash = formation stops. Stall detection partially addresses. |
| **Context pollution** | Including irrelevant history degrades performance | HIGH | Teammate prompts should be surgically precise. Reduce spec.md in teammate context. |
| **Unbounded context accumulation** | No summarization before capacity limits | LOW | Claude Code auto-compaction handles this natively. |
| **Synchronous blocking chains** | All tasks serial, no parallelization benefit | MEDIUM | V10's wave-based spawning addresses this, but formation definitions must identify parallel opportunities. |
| **Undifferentiated responsibilities** | Agents duplicate effort without clear ownership | HIGH | File ownership registry addresses this. Task descriptions must be unique and non-overlapping. |
| **Coordination through polling** | Agents repeatedly checking for updates | LOW | V10 uses event-driven task updates, not polling. |
| **Over-coordination** | Too many messages between agents | LOW | V10 teammates communicate only through tasks and files, minimizing message overhead. |
| **The lead implementing** | Orchestrator does work instead of delegating | MEDIUM | Delegate mode (Shift+Tab) restricts lead to coordination tools. |
| **Group discussion** | All agents discussing simultaneously | LOW | V10 does not support broadcast chat. Validated by MultiAgentBench finding that group discussion scored worst. |
| **Same-file multi-agent edits** | Race conditions and overwrites | HIGH | File ownership registry + guard-write-gates hook. CRITICAL to enforce. |

---

## 8. Framework-Specific Findings

### Source: Framework Comparison (DataCamp, Iterathon, 2025-2026)
**URLs**: https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen, https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026

#### Comparative Analysis

| Dimension | LangGraph | CrewAI | AutoGen | V10 Protocol |
|-----------|-----------|--------|---------|--------------|
| **Control model** | Explicit state machine | Role-based delegation | Conversation-driven | Task-based delegation |
| **State management** | Explicit (TypedDict) | Implicit | Implicit | Explicit (TaskSystem) |
| **Debugging** | Excellent | Good | Challenging | Good (hooks + task audit) |
| **Learning curve** | Steep | Moderate | Moderate | Moderate |
| **Human-in-loop** | Manual | Limited | Excellent | Good (risk gates) |
| **Cost efficiency** | High | High | Moderate | High (effort-based) |

**Market context (2026)**:
- 72% of enterprise AI projects involve multi-agent architectures (up from 23% in 2024).
- 86% of copilot spending ($7.2B) goes to agent-based systems.
- Over 70% of new AI projects use orchestration frameworks.

**Applicability to V10**:
- V10's task-based delegation is closest to CrewAI's role-based model but with LangGraph's explicit state management. This is a strong hybrid.
- V10's debugging story (hooks + task audit) is good but could benefit from LangGraph-style explicit state visualization. A `team-status` command that shows the full formation state graph would help.
- V10's human-in-loop (risk gates) is adequate but could be improved by adopting AutoGen's conversation-integration patterns for cases where the user wants to redirect mid-formation.

---

### Source: LangGraph Supervisor Library (2025)
**URL**: https://github.com/langchain-ai/langgraph-supervisor-py

#### Pattern: Supervisor-Worker with Multi-Level Hierarchy

**Evidence**:
- Single supervisor handles all user interactions.
- Supervisor delegates to workers; workers communicate exclusively with supervisor.
- Support for multi-level hierarchies (supervisors of supervisors).
- Orchestrator-Worker pattern via Send API: dynamically create worker nodes with specific inputs, each with own state, all outputs to shared state key.
- Supervisor validates outputs, oversees parallel processes, handles errors.

**Applicability to V10**:
- V10's team lead already implements this pattern. The Send API's "each worker has own state, outputs to shared key" maps directly to V10's "each teammate has own context, outputs to task system."
- LangGraph's support for supervisors-of-supervisors is NOT recommended based on the MultiAgentBench tree topology results (worst performance). V10 should continue with a flat team lead + teammates model.

---

## 9. Synthesis: Recommendations for V10

### High-Priority Changes

1. **Cap active teammates at 5 per formation**. Multiple sources confirm diminishing returns beyond this point (MultiAgentBench, Maxim metrics, Anthropic's 3-5 subagent sweet spot). The current formations already align but this should be a hard constraint.

2. **Implement the 20/20/60 rule for team lead behavior**. Spend 20% of effort on precise task decomposition, 20% on reviewing teammate outputs, 60% delegated execution. This is validated by the finding that "spending 20% more time specifying work reduces implementation time by 50%."

3. **Reduce teammate context size**. Context pollution is the highest-risk anti-pattern for V10. Teammates should receive:
   - A slim "teammate rules" subset (not full V10 CLAUDE.md)
   - Task-specific context only (not full spec.md unless necessary)
   - File paths as references (not file contents in prompts)
   - Explicit "do NOT" instructions to prevent overlap with other teammates

4. **Add closed-loop verification between formation stages**. When a wave of teammates completes, the team lead should verify outputs before spawning the next wave. Currently, V10's wave algorithm spawns the next wave on completion; it should verify first.

5. **Implement action attribution in team lead reviews**. When reviewing teammate work, clearly mark which changes were made by which teammate. This prevents the team lead from confusing teammate outputs with its own prior context.

### Medium-Priority Changes

6. **Allow dynamic task claiming for investigation formations**. The blackboard pattern (13-57% improvement) suggests that `bug-investigation` formations should let agents self-select tasks based on discovered evidence, rather than pre-assigning all investigations.

7. **Add structured artifact handoffs between formation phases**. Following MetaGPT's model, define expected intermediate artifacts (design docs, API specs, test plans) at formation boundaries, not just task completions.

8. **Implement graduated stall response**. Replace the current single 30min timeout with: advisory at 15min, warning at 30min, reassignment option at 45min. Add pattern detection for multiple teammates hitting the same error.

9. **Document the cost model explicitly**. Multi-agent formations cost 2-5x more tokens than single-agent work (confirmed by multiple sources). V10 should surface this in formation selection guidance: "Is this task complex enough to justify 3x token cost?"

10. **Add diverse reasoning strategies to investigation formations**. The debate research shows homogeneous reasoning provides limited benefit. `bug-investigation` teammates should receive DIFFERENT initial hypotheses and investigation strategies, not just different file assignments.

### Low-Priority / Experimental Changes

11. **Experiment with limited peer-to-peer communication**. Graph topology outperformed star in MultiAgentBench. V10 could allow teammates to create tasks addressed to other teammates (not just the team lead) for information sharing, while keeping the team lead as the primary coordinator.

12. **Consider the Arbiter pattern from AWS Strands**. An advanced supervisor that extends basic orchestration with dynamic agent generation, semantic task routing, and blackboard-based coordination. This could evolve V10's team lead role.

13. **Implement formation-level summarization**. At formation completion, generate a structured summary of all teammate outputs before the team lead proceeds. This prevents context rot in long-running multi-formation sessions.

14. **Explore routine definitions for roles**. Following OpenAI's pattern, define each formation role as a routine (instructions + allowed tools + expected outputs) rather than just a role description + task list.

15. **Add formation-level metrics collection**. Track per-formation: total tokens, wall clock time, tasks completed/failed, teammate stalls. Use this data to refine formation selection and team size recommendations over time.

### What V10 Already Gets Right

- **Task-based communication over chat**: Validated by MultiAgentBench (group discussion worst), MetaGPT (structured over free-form), and multiple anti-pattern catalogs.
- **Separate context per teammate**: Validated by Anthropic (90.2% improvement), context rot research, and the fundamental justification for multi-agent architecture.
- **File ownership enforcement**: Validated universally as critical. Same-file multi-agent edits are the most consistently cited failure mode.
- **Two-layer hierarchy (lead + workers)**: Validated by tree topology failure in MultiAgentBench and span-of-control research. Do NOT add middle management.
- **Formation-based topology**: Validated by the 17x error trap research. Topology is the solution, not more agents.
- **Graduated task complexity (direct < subagent < team)**: Validated by Anthropic's graduated allocation and the "start simple" principle.
- **Hook-based verification**: Validated by the incomplete verification failure mode (MASFT FC3) being one of the most common multi-agent failures.

---

## Source Index

| # | Source | Type | Year | Key Contribution |
|---|--------|------|------|-----------------|
| 1 | MultiAgentBench (ACL) | Academic paper | 2025 | Topology benchmarks, iteration scaling |
| 2 | HMAS Taxonomy | Academic paper | 2025 | Five-axis design taxonomy |
| 3 | Anthropic Building Effective Agents | Industry guide | 2025 | Five composable patterns |
| 4 | Anthropic Multi-Agent Research System | Engineering blog | 2025 | Production metrics, 90.2% improvement |
| 5 | Maxim Reliability Research | Industry analysis | 2025 | Coordination tax quantification |
| 6 | MASFT Failure Taxonomy | Academic paper | 2025 | 14 failure modes in 3 categories |
| 7 | 17x Error Trap | Analysis article | 2026 | Topology vs bag-of-agents |
| 8 | MetaGPT (ICLR) | Academic paper | 2024 | Structured communication, SOPs |
| 9 | ChatDev (ACL) | Academic paper | 2024 | Waterfall agent organization |
| 10 | O'Reilly Multi-Agent Architecture | Industry guide | 2025 | Hybrid parallel-deliberate pattern |
| 11 | Google ADK Framework | Engineering blog | 2025 | Context-as-compiled-view |
| 12 | AWS Strands Agents | Documentation | 2025 | Graph/Swarm/Workflow patterns |
| 13 | OpenAI Swarm / Agents SDK | Framework | 2025 | Routines and handoffs |
| 14 | Confluent Event-Driven Patterns | Industry blog | 2025 | Four event-driven models |
| 15 | Blackboard Architecture Research | Academic paper | 2025 | 13-57% improvement over baselines |
| 16 | Multi-Agent Debate (ICLR) | Academic paper | 2025 | Adversarial quality improvement |
| 17 | Addy Osmani Claude Code Swarms | Blog post | 2025 | Practical team size, anti-patterns |
| 18 | DataCamp/Iterathon Framework Comparison | Tutorial/blog | 2025-2026 | Framework comparative analysis |
| 19 | LangGraph Supervisor | Library docs | 2025 | Supervisor-worker implementation |
| 20 | Context Rot Research | Multiple | 2025 | Context window saturation effects |

---

*Research compiled 2026-02-13 for V10 Protocol improvement.*
