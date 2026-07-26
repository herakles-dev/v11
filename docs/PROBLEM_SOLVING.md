# Problem-Solving Framework (V11 Adaptation)

> V11-adapted synthesis of the Master Problem-Solving Protocol.
> Source: Athenaeum Advanced Problem-Solving Library (23 frameworks).
> Integration points: Phase 3 (planning), Phase 5d (gates), hooks (advisory).

---

## Quick Decision Tree

```
Known solution exists?     → Clear    → Apply directly, skip deep planning
Expert analysis needed?    → Complicated → Analyze → Plan → Execute (feature-impl)
Nobody knows until we try? → Complex    → Probe → Sense → Respond (deep-plan mode)
Everything is on fire?     → Chaotic   → Act → Sense → Respond (bug-investigation)
Not sure?                  → Confused  → Default to Complicated, revisit after research
```

---

## Cynefin → V11 Mapping

| Domain | Formation | Effort | Approach | Example |
|--------|-----------|--------|----------|---------|
| **Clear** | single-file, lightweight-feature | low-medium | Apply known pattern | CI pipeline, config change |
| **Complicated** | feature-impl, security-review | medium-high | Analyze → Plan → Execute | Database optimization, API design |
| **Complex** | deep-research, new-project | high | Probe → Sense → Respond | "Will SSMs process graphs?" |
| **Chaotic** | bug-investigation | high | Act → Sense → Respond | Production outage |
| **Confused** | Start with Explore agent | medium | Gather info, then reclassify | Unknown codebase, vague requirements |

**Key insight**: Complex work resists estimation. Time-box experiments instead of predicting completion dates.

---

## Planning Frameworks (Phase 3 Integration)

### Polya's Method (before any work)

1. **Understand**: What is the gap between expected and actual?
2. **Plan**: What strategy? Have we seen this before?
3. **Execute**: Implement the plan
4. **Review**: Did it work? What did we learn?

> V11 maps Polya to: Phase 3 interview (Understand + Plan) → Phase 4 (Execute) → Phase 5d gates (Review)

### Problem Decomposition (5 strategies)

| Strategy | When | Example |
|----------|------|---------|
| **Functional** | Clear operations/steps | Auth → Validate → Authorize → Log |
| **Data-oriented** | Data transformations | Parse → Transform → Store → Index |
| **Layer-based** | Multi-system | Frontend → API → Service → Database |
| **Temporal** | Sequential phases | Scaffold → Implement → Test → Deploy |
| **Risk-based** | Unknowns present | Highest risk first → validate → continue |

> V11: Use in Phase 3c gap-filling. Choose strategy based on Cynefin domain.
> Complex → Risk-based. Clear → Functional. Complicated → Layer-based.

### Theory of Constraints (during execution)

1. **Identify** the bottleneck (where work piles up)
2. **Exploit** it (never idle, never on low-priority work)
3. **Subordinate** everything else (non-bottleneck agents wait rather than pile up WIP)
4. **Elevate** only if exploit + subordinate aren't enough

> V11: Write current bottleneck to `.plan-context.json`. Update at each gate.
> Formation heartbeat detects idle agents that may signal constraint shifts.

---

## Execution Frameworks (During Implementation)

### Bayesian Reasoning

Update beliefs proportionally to evidence strength:

```
Prior probability × Evidence strength = Updated probability
```

- Strong evidence (test passes/fails) → large update
- Weak evidence (anecdotal) → small update
- Contradictory evidence → don't average, investigate

> V11: Track hypothesis probabilities in `.plan-context.json`.
> Update at gate reviews and when evidence arrives.

### Pre-Mortem (Inversion)

Before starting a phase: "Imagine this failed completely. Why?"

For each failure mode:
- Define preventive action OR detection mechanism
- Flag existential failures → validate FIRST
- Reverse each failure into a design principle

> V11: Kill conditions in `.plan-context.json` are the output of pre-mortem.

---

## Gate Review Protocol (Phase 5d Integration)

### Bias Audit Checklist

Before advancing through a gate, check:

| Bias | Question | Flag If |
|------|----------|---------|
| **Confirmation** | Only looking at supporting evidence? | Ignoring failed tests or edge cases |
| **Planning fallacy** | Estimating optimistically? | "Just one more sprint" repeatedly |
| **Sunk cost** | Continuing because of investment? | Evidence says pivot but resisting |
| **Anchoring** | Stuck on original plan despite new data? | Requirements changed but plan didn't |

**Rule**: If 3+ biases flagged → pause and reframe before continuing.

### Five Whys (on gate failure)

When a gate fails:
1. Why did it fail? → [immediate cause]
2. Why did [cause 1] happen? → [deeper cause]
3. Why did [cause 2] happen? → [root cause candidate]
4. Why did [cause 3] happen? → [systemic issue]
5. Why did [cause 4] happen? → [design flaw or assumption]

> V11: Record root cause and fix in `.plan-context.json` decisions array.

### Gate Decision Matrix

| Evidence | Confidence | Decision |
|----------|-----------|----------|
| All criteria met | High | **Go** — advance to next phase |
| Most met, gaps minor | Medium | **Iterate** — fix gaps, re-run gate |
| Core hypothesis weakened | Low | **Pivot** — change approach, update plan |
| Kill condition triggered | N/A | **Kill** — stop project, document learnings |

---

## Framework Reference Index

| # | Framework | Core Idea | V11 Use |
|---|-----------|-----------|---------|
| 1 | Cynefin | Problem domains need different approaches | Phase 3 Step 0 |
| 2 | Polya | Understand → Plan → Execute → Review | Full session flow |
| 3 | Inversion | Catalog failure before predicting success | Pre-mortem at gates |
| 4 | Decomposition | Break into independent, testable pieces | Phase 3c task creation |
| 5 | Theory of Constraints | Improve the bottleneck, ignore the rest | `.plan-context.json` bottleneck |
| 6 | Fermi Estimation | Order-of-magnitude before committing | Sprint sizing |
| 7 | Bayesian Reasoning | Update beliefs with evidence | Hypothesis tracking |
| 8 | Cognitive Biases | Counter systematic thinking errors | Gate review audit |
| 9 | Five Whys | Find root cause, not symptoms | Gate failure analysis |
| 10 | Socratic Method | Question assumptions | Phase 3 interview |
| 11 | Abstraction Laddering | Solve at the right level | "Why?" up, "How?" down |
| 12 | MECE | Mutually exclusive, collectively exhaustive | Task decomposition |
| 13 | Pareto (80/20) | Focus on highest-impact work | Sprint prioritization |
| 14 | Working Backward | Start from outcome, trace back | Feature design |
| 15 | Analogy | Map to known solved problems | Architecture decisions |
| 16 | Contradiction | Find and resolve tensions | Constraint analysis |
| 17 | Lateral Thinking | Reframe the problem entirely | When stuck at gates |
| 18 | Systems Thinking | See feedback loops and delays | Multi-service architecture |
| 19 | First Principles | Decompose to fundamentals | Novel/complex domains |
| 20 | Red Team | Attack your own solution | Security review formation |
| 21 | Devil's Advocate | Argue against the consensus | Gate bias audit |
| 22 | Scenario Planning | Plan for multiple futures | Kill conditions |
| 23 | Contributing Factors | Multiple causes, weighted | Gate failure analysis |

---

*V11.6 — Problem-Solving Framework Integration*
