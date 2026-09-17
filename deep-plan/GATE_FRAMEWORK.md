# Gate Execution Framework

> The 8-layer problem-solving protocol for gate decisions.
> Source: Athenaeum Advanced Problem-Solving Library (ID: 42, 25 documents, 1,040 chunks).

## The Protocol Stack

| Layer | Framework | Doc ID | Core Principle |
|-------|-----------|--------|----------------|
| 1. Classify | Cynefin | 309 | Not all problems respond to the same methodology |
| 2. Understand | Polya | 290 | Understand → Plan → Execute → Review (never skip 1-2) |
| 3. Invert | Inversion/Pre-Mortem | 324 | Easier to catalog failure than predict success |
| 4. Decompose | Problem Decomposition | 316 | Independent, testable, composable, balanced |
| 5. Constrain | Theory of Constraints | 313 | Improving non-constraints is waste |
| 6. Size | Fermi Estimation | 325 | Order-of-magnitude before committing resources |
| 7. Execute | Bayesian Reasoning | 312 | Update beliefs proportionally to evidence strength |
| 8. Review | Biases + Five Whys | 321, 323 | Counter distortions, find root causes |

## When to Run

```
PHASE START:  Layers 1-6 (Classify → Size)
DURING PHASE: Layer 7 (Bayesian updates as evidence arrives)
GATE REVIEW:  Layer 8 (Bias audit → Evidence → Decision)
GATE FAILURE: Five Whys → Contributing Factor Analysis → Fix → Re-run
```

## Layer Details

### Layer 1: Cynefin Classification

Determine the domain BEFORE choosing an approach:

| Domain | Cause-Effect | Approach | Example |
|--------|-------------|----------|---------|
| **Clear** | Obvious | Sense → Categorize → Respond | Setting up CI pipeline |
| **Complicated** | Requires expertise | Sense → Analyze → Respond | Database optimization |
| **Complex** | Only visible in retrospect | Probe → Sense → Respond | "Will SSMs process graphs?" |
| **Chaotic** | None | Act → Sense → Respond | Production is down |

**Key insight for deep-plan projects:** Most research phases are Complex.
Stop asking for estimates on Complex work. Time-box experiments instead.

### Layer 2: Polya (Understand)

Before ANY work begins, answer:
1. What is the unknown?
2. What data do we have?
3. What conditions must hold?
4. Can we restate the problem differently?
5. Have we seen this before? Is there an analogous problem?

### Layer 3: Inversion (Pre-Mortem)

"Imagine this phase failed completely. Why?"

For each failure mode:
- Define a preventive action OR detection mechanism
- Flag existential failures (→ must validate FIRST)
- Reverse each failure into a design principle

### Layer 4: Problem Decomposition

Break work into sub-tasks. Validate:

```
✓ Independence: Can different agents work in parallel?
✓ Testability: Can each sub-task produce a verifiable result?
✓ Composability: Do sub-tasks combine naturally?
✓ Balanced: No sub-task 10x larger than others?
```

Prefer risk-based decomposition (highest risk first) and vertical slices (thin E2E over horizontal layers).

### Layer 5: Theory of Constraints

1. **Identify** the bottleneck (where work piles up)
2. **Exploit** it (never idle, never on low-priority work)
3. **Subordinate** everything else (non-bottleneck agents wait rather than pile up WIP)
4. **Elevate** only if exploit+subordinate aren't enough
5. **Repeat** (constraint shifts after resolution)

### Layer 6: Fermi Estimation

For every unknown, estimate to order-of-magnitude:
1. Break into sub-estimates
2. Estimate each component
3. Combine
4. Sanity-check from different angle
5. Identify which sub-estimate you're most sensitive to

Being within 10x is success. Being within 2-3x is excellent.

### Layer 7: Bayesian Reasoning

Maintain beliefs as probabilities. Update with evidence:

```
P(hypothesis | evidence) ∝ P(evidence | hypothesis) × P(hypothesis)
```

Rules:
- Start with multiple hypotheses, honest priors
- Seek discriminating evidence (distinguishes hypotheses, not just confirms favorite)
- Update proportionally to evidence strength
- Set decision thresholds before collecting evidence
- Don't anchor on first result

### Layer 8: Cognitive Bias Audit

At every gate review, run this checklist:

```
□ CONFIRMATION BIAS   — Am I only looking at supporting evidence?
□ PLANNING FALLACY    — Am I estimating optimistically?
□ SUNK COST           — Am I continuing because of investment, not evidence?
□ ANCHORING           — Am I stuck on the original plan despite new data?
□ OPTIMISM BIAS       — Am I assuming we're special and risks don't apply?
□ SURVIVORSHIP        — Am I citing only successful examples?
□ AUTHORITY BIAS      — Am I trusting source over data?
□ AVAILABILITY        — Am I overweighting recent/memorable events?
```

If 3+ flagged → mandatory pause, reframe decision from scratch.

## Gate Decision Matrix

| Evidence State | Decision |
|---------------|----------|
| All criteria pass, no biases flagged | **Go** |
| Most criteria pass, fixable gaps | **Iterate** (fix specific issues, re-run) |
| Fundamental assumption invalidated | **Pivot** (change approach) |
| Core hypothesis disproven | **Kill** (document findings, stop) |

## How to Generate Project-Specific Protocol

```bash
# 1. Pull raw frameworks from Athenaeum (programmatic, NEVER /chat)
for doc_id in 290 291 309 312 313 316 321 323 324 325; do
  curl -s "http://localhost:8140/api/libraries/42/documents/$doc_id" | jq -r '.full_text' >> /tmp/frameworks.md
done

# 2. Claude synthesizes into project-specific protocol
# (gate-specific Cynefin mappings, Bayesian priors, constraint IDs)

# 3. Write to docs/GATE_PROTOCOL.md

# 4. Create .claude/commands/project-gate.md
```
