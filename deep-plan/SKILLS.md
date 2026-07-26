# Deep Plan Skills

> New skills and commands to add to V11 for deep-plan project support.

## Skill: `/v11-deep-plan`

**Location:** `~/.claude/commands/v11-deep-plan.md` (global — works across all projects)

**Purpose:** Orchestrate the full 7-phase methodology for massive project scaffolding.

```markdown
---
name: v11-deep-plan
description: "Scaffold a massive project requiring deep research — full 7-phase methodology from concept to ready-to-execute"
---

# V11 Deep Plan

Orchestrate the creation of a deeply-planned, research-backed project.

Parse args: $ARGUMENTS

## Phase Detection

If no args, start from Phase 1 (interview). If project directory exists, detect current phase
and resume from there.

## Phase 1: CAPTURE
1. Interview user (max 5 questions):
   - What's the core idea?
   - What technologies are involved?
   - What are the biggest unknowns?
   - How many distinct domains need separate agents?
   - What does success look like?
2. Write VISION.md from answers
3. Ask user to confirm before proceeding

## Phase 2: SCAFFOLD
1. Run internal scaffold logic:
   - Create project directory
   - Write stub files per technology
   - Create docker-compose.yml
   - Design N custom agents from VISION.md personas
   - Write initial CLAUDE.md and spec.md
   - Configure .claude/ (settings.json, athenaeum.json, commands/)
2. Create Athenaeum library via API
3. Report: "Scaffold complete. N agents, N crates/modules. Proceed to research?"

## Phase 3: RESEARCH
1. Extract research topics from VISION.md assumptions + tech stack
2. Launch N background agents (3 docs per agent, parallel)
3. Each agent writes research docs to research/ directory
4. Batch ingest all docs to Athenaeum library
5. Report: "N docs written, N chunks in Athenaeum. Proceed to audit?"

## Phase 4: AUDIT
1. Launch 3 parallel audit agents:
   - Research Quality auditor
   - OSS Landscape auditor
   - Spec/Gate/Risk auditor
2. Synthesize findings into structured report
3. Present findings to user
4. Report: "N gaps, N contradictions, N missing risks. Proceed to restructure?"

## Phase 5: RESTRUCTURE
1. Identify core hypothesis and sub-hypotheses
2. Calculate joint prior probability
3. If joint < 20%: add Phase 0 (Validate or Kill)
4. Restructure spec.md:
   - Hypothesis table with priors
   - Cynefin domain per phase
   - Pre-mortem per phase
   - Constraint map
   - Belief tracker
   - Kill conditions per gate
5. Expand risk register with audit findings
6. Write new research docs to fill gaps (if any)

## Phase 6: PROTOCOL
1. Pull raw content from Athenaeum problem-solving library (ID: 42)
   - Cynefin (309), Decomposition (316), TOC (313), Inversion (324)
   - Polya (290), First Principles (291), Biases (321), Bayesian (312)
   - Five Whys (323), Fermi (325)
2. Synthesize into docs/GATE_PROTOCOL.md
3. Create project commands (.claude/commands/)
4. Create workspace script (scripts/project.sh)
5. Update CLAUDE.md with all skills, agents, protocol reference

## Phase 7: ALIGN
1. Run full cross-reference verification
2. Check for stale references, contradictions, missing files
3. Init git if not already
4. Report final status
5. Suggest: "/project-gate start phase-0" to begin

## Athenaeum Policy
ALL Athenaeum access is programmatic. NEVER use /chat endpoint.
Use search API to pull raw text, synthesize yourself.
```

---

## Skill: `/athenaeum`

**Location:** Project-scoped (`.claude/commands/athenaeum.md`) — copied during scaffold.

See `<project-root>/example-project/.claude/commands/athenaeum.md` for the reference implementation.

### Mission Types

1. **deep-dive** — comprehensive study across multiple libraries
2. **contradiction-scan** — find inconsistencies in a document
3. **gap-discovery** — find missing research topics
4. **evidence** — gather gate decision support
5. **cross-library** — synthesize across N libraries

---

## Skill: `project-gate` (Template)

**Location:** Project-scoped (`.claude/commands/{project}-gate.md`) — generated during scaffold.

See `<project-root>/example-project/.claude/commands/example-project-gate.md` for the reference implementation.

### Modes

1. **start \<phase\>** — run 6-step phase start protocol
2. **review \<gate\>** — run gate review with bias audit
3. **harden \<document\>** — run documentation hardening checklist

---

## Skill: `/pm-deep-plan`

**Location:** `~/.claude/skills/pm-deep-plan.md` (global — works on any project)

Already exists. Codifies the PM audit process (Phase 4) as a standalone skill.

---

## Integration with Existing Skills

| Existing Skill | Deep Plan Enhancement |
|---------------|----------------------|
| `/v11-scaffold` | Add `--deep-plan` flag for enhanced scaffold |
| `/status` | Show belief tracker + constraint map for deep-plan projects |
| `/handoff` | Include belief tracker state in handoff context |
| `/discover` | Run gap-discovery Athenaeum mission during discovery |
| `/test` | Show gate criteria in test output for deep-plan projects |

---

## Athenaeum Document IDs (Problem-Solving Library, ID: 42)

These are pinned for gate protocol generation:

| Doc ID | Framework | Protocol Layer |
|--------|-----------|----------------|
| 290 | Polya Method | Understand |
| 291 | First Principles | Decompose (strip assumptions) |
| 309 | Cynefin Framework | Classify |
| 312 | Bayesian Reasoning | Execute (update priors) |
| 313 | Theory of Constraints | Constrain (find bottleneck) |
| 316 | Problem Decomposition | Decompose (agent tasks) |
| 321 | Cognitive Biases | Review (bias audit) |
| 323 | Five Whys | Review (root cause on failure) |
| 324 | Inversion Thinking | Invert (pre-mortem) |
| 325 | Fermi Estimation | Size (estimate unknowns) |
