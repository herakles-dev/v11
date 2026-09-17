# Deep Plan Methodology: 7 Phases

> How to turn a vague idea into a production-ready, deeply-planned project.
> Each phase produces artifacts consumed by the next. Skip nothing.

## Overview

```
Phase 1: CAPTURE    → VISION.md (raw concept, unvalidated)
Phase 2: SCAFFOLD   → Project structure, agents, docker, Cargo/package.json
Phase 3: RESEARCH   → Athenaeum library, 10-20 research documents
Phase 4: AUDIT      → PM audit: gaps, contradictions, missing risks, scope issues
Phase 5: RESTRUCTURE→ Hypothesis-driven spec, gates, belief tracker, constraint map
Phase 6: PROTOCOL   → Gate execution protocol, skills, commands, workspace scripts
Phase 7: ALIGN      → Full cross-reference verification, git init, ready to execute
```

---

## Phase 1: CAPTURE (30 minutes)

**Input:** Vague idea, conversation, concept document, whiteboard sketch.
**Output:** `VISION.md`

### What to Capture

Write the raw vision without filtering for feasibility. Include:

1. **Architecture sketch** — even if hand-wavy, draw the boxes and arrows
2. **Core hypothesis** — what must be true for this to work?
3. **Tech stack** — what technologies are you betting on?
4. **Agent personas** — who does what? (will become formal agents in Phase 2)
5. **Testing methodology** — how will you know it works?
6. **Success criteria** — what does "done" look like?

### Rules

- Do NOT edit for realism. Capture the ambition.
- Do NOT design the implementation. That's Phase 5.
- Do NOT estimate timelines. Complex work isn't estimable.
- DO mark assumptions explicitly: "Assumes NVLink-C2C works as documented."

### Template

```markdown
# [PROJECT NAME]: [Tagline]

## Architecture
[Boxes and arrows, even ASCII art]

## Core Hypothesis
[What must be true for this to work?]

## Tech Stack
[Languages, frameworks, databases, hardware]

## Agent Personas
[Who does what — informal descriptions]

## Testing Methodology
[How do you validate success?]

## Success Criteria
[What does "done" look like?]

## Assumptions
[Everything you're taking on faith]
```

---

## Phase 2: SCAFFOLD (1-2 hours)

**Input:** `VISION.md`
**Output:** Full project structure, custom agents, docker-compose, workspace config

### Actions

1. **Create project directory** at `~/project-name/`
2. **Scaffold code structure** — directories matching architecture from VISION.md
3. **Write stub files** — `lib.rs` / `index.ts` / `__init__.py` with type definitions only
4. **Create docker-compose.yml** — databases, services needed for dev
5. **Design custom agents** — extract agent personas from VISION.md, formalize as agent definitions
6. **Register agents** — add to `~/.agent-registry/agents.json`
7. **Create CLAUDE.md** — initial version with architecture, agents, quick start, rules
8. **Create spec.md** — Sprint 00 tasks only (setup tasks)
9. **Set up `.claude/`** — athenaeum.json, settings.json, commands/

### Agent Design Pattern

For each agent persona from VISION.md:

```yaml
# Agent definition (~/.claude/agents/project-agent.md)
---
name: project-agent-name
description: "Domain expertise description"
model: sonnet  # Sonnet for implementation, Opus for architecture
---

You are a specialist in [DOMAIN]. You own [FILES/DIRECTORIES].

## Expertise
- [Skill 1]
- [Skill 2]

## File Ownership
- `path/to/owned/code/`

## Constraints
- Always use [PATTERN] for [REASON]
- Never modify files outside your ownership
```

### Scaffold Checklist

```
□ Project directory created
□ Code stubs with type definitions (no implementation)
□ Docker services configured
□ N custom agents designed and registered
□ CLAUDE.md with architecture, agents, quick start
□ spec.md with Sprint 00 tasks
□ .claude/settings.json with hooks
□ .claude/athenaeum.json with library pin
□ .gitignore (secrets, build artifacts, OS files)
□ requirements.txt / Cargo.toml / package.json
```

---

## Phase 3: RESEARCH (2-6 hours)

**Input:** Scaffolded project, VISION.md assumptions
**Output:** 10-20 research documents in Athenaeum library

### Research Protocol

For every technology, assumption, and unknown in VISION.md:

1. **Create Athenaeum library** for the project
   ```bash
   curl -s -X POST "http://localhost:8140/api/libraries" \
     -H "Content-Type: application/json" \
     -H "Remote-User: hercules@herakles.dev" \
     -d '{"name": "Project Research", "slug": "project-slug", "description": "...", "owner": "hercules", "visibility": "public"}'
   ```

2. **Write research documents** — one per topic
   - Use subagents for parallel writing (3 agents × 3 docs each)
   - Each doc MUST include: code examples, real benchmarks, specific API calls, "Lessons for Project" section

3. **Ingest all docs to Athenaeum**
   ```bash
   for f in research/*.md; do
     curl -s -X POST "http://localhost:8140/api/libraries/ID/upload" \
       -H "Remote-User: hercules@herakles.dev" -F "file=@$f"
   done
   ```

4. **Pin library in project**
   ```json
   // .claude/athenaeum.json
   {"athenaeum": {"pinned_libraries": ["project-slug"]}}
   ```

### Research Document Template

```markdown
# [Topic Title]

> Research document for [PROJECT] project. Last updated: [DATE].

## Overview
[What this is and why it matters to the project]

## [Technical Deep Dive Sections]
[Code examples, architecture diagrams, API walkthroughs]

## Benchmarks & Real Numbers
[Published benchmarks, measured values, NOT estimates]

## Lessons for [PROJECT]
[How this research applies to our specific architecture]

## Further Research Needed
- [ ] [Specific question that needs answering]

## References
[Papers, docs, repos]
```

### Research Topic Selection

Every project needs research on:
- **Core technology** — deep dive on the primary tech (e.g., GH200, SSMs)
- **Prior art** — who has solved similar problems? (e.g., cuGraph, Gunrock)
- **Integration points** — how do the pieces connect? (e.g., Arrow IPC + GPU)
- **Failure modes** — what has gone wrong for others? (e.g., quantization destroying quality)
- **Scale behavior** — what happens at 10x, 100x, 1000x? (e.g., Neo4j at 10M nodes)

---

## Phase 4: AUDIT (1-2 hours)

**Input:** Research library, spec.md, CLAUDE.md
**Output:** Structured findings report

### The Three Parallel Audits

Launch 3 agents simultaneously:

**Audit 1: Research Quality**
- For each research doc: are claims backed by evidence?
- Rate each: Sufficient / Needs Update / Insufficient
- List contradictions between documents
- List critical topics completely absent

**Audit 2: OSS Landscape**
- For each technology: are we reinventing solved problems?
- Which libraries/tools should we evaluate?
- Are any dependencies deprecated or unmaintained?

**Audit 3: Spec/Gate/Risk Review**
- Are gates too coarse? (milestones vs intermediate validation)
- Can you fail fast? Or must you complete large phases first?
- Are gate criteria measurable?
- Are sprints too large? (>10 tasks = warning)
- Are dependency chains too deep? (>4 sequential = bottleneck)
- Is scope realistic?
- What risks are missing?

### Audit Output Template

```markdown
## PM Deep Audit Report

### Research Quality: [SCORE]
| Document | Rating | Critical Gap |

### Missing Research Topics
1. [Topic] — blocks [Gate X]

### Contradictions Found
| Issue | Documents | Resolution |

### Gate Structure: [Assessment]
- Current: [N] gates
- Recommended: [N+M] gates (intermediate validation)
- Key additions: [list]

### Risk Register Gaps
| Missing Risk | Impact | Likelihood |

### Scope Assessment
[Realistic / Too wide / Needs narrowing]
```

---

## Phase 5: RESTRUCTURE (2-4 hours)

**Input:** Audit findings
**Output:** Hypothesis-driven spec.md with gates, risks, belief tracker

### Key Transformations

**1. Identify Core Hypothesis**
Every ambitious project is a conjunction of sub-hypotheses. Make them explicit.

```markdown
| # | Sub-Hypothesis | Validated By | Prior |
|---|---------------|-------------|-------|
| H1 | [First assumption] | Gate [X] | 0.XX |
| H2 | [Second assumption] | Gate [X] | 0.XX |
```

Calculate joint prior: `P(all) = P(H1) × P(H2) × ... × P(Hn)`

If joint prior < 20%, you MUST have a "Validate or Kill" phase before any infrastructure.

**2. Restructure Phases**
- Phase 0: Validate or Kill (cheap spikes for existential risks)
- Phase 1A/1B/1C: Build incrementally with gates between
- Phase 2+: Scale and integrate
- Each phase answers specific questions, not just "builds things"

**3. Add Per-Phase Metadata**

For every phase:
```markdown
## Phase X: [Name]

> **Cynefin: [Complex/Complicated/Clear]**
> **Approach:** [Probe→Sense→Respond / Sense→Analyze→Respond / Sense→Categorize→Respond]

### What This Phase Answers
| Question | How We Answer It | Kill Condition |

### Constraint
[Bottleneck identification + exploit/subordinate strategy]

### Pre-Mortem (Inversion)
[How this phase fails + prevention for each]
```

**4. Create Belief Tracker**

```markdown
| Belief | Prior | After G0 | After G1 | ... |
|--------|-------|----------|----------|-----|
| H1     | 0.XX  | ___      | ___      | ... |
```

**5. Create Constraint Map**

```markdown
| Phase | Constraint | Exploit | Subordinate |
```

**6. Expand Risk Register**
Every risk needs: Impact, Likelihood, Gate that validates, Concrete mitigation.

---

## Phase 6: PROTOCOL (2-3 hours)

**Input:** Restructured spec.md
**Output:** Gate protocol, skills, commands, workspace scripts

### Build Gate Execution Protocol

Pull raw content from Athenaeum's Advanced Problem-Solving library (ID: 42):

```bash
# Get framework content programmatically (NEVER use /chat endpoint)
for doc_id in 290 291 309 312 313 316 321 323 324 325; do
  curl -s "http://localhost:8140/api/libraries/42/documents/$doc_id" | jq -r '.full_text'
done
```

Synthesize into an 8-layer protocol stack:
1. **Classify** (Cynefin) — what domain is this?
2. **Understand** (Polya) — restate unknowns
3. **Invert** (Pre-Mortem) — catalog failure modes
4. **Decompose** (Problem Decomposition) — independent, testable tasks
5. **Constrain** (Theory of Constraints) — find bottleneck
6. **Size** (Fermi Estimation) — order-of-magnitude unknowns
7. **Execute** (Bayesian Reasoning) — update priors with evidence
8. **Review** (Cognitive Biases + Five Whys) — audit for distortions

Write to `docs/GATE_PROTOCOL.md`.

### Create Project Commands

```bash
mkdir -p .claude/commands/
```

**Required commands for deep-plan projects:**

1. **`project-gate.md`** — gate execution protocol (start/review/harden)
2. **`athenaeum.md`** — programmatic research with mission types

### Create Workspace Script

`scripts/project.sh` with modes:
- `research "query"` — Athenaeum search
- `research-list` — list documents
- `research-ingest` — batch ingest
- `build` — compile/lint
- `test` — run tests
- `ci` — full CI pipeline
- `up` / `down` — docker services
- `status` — project overview
- `gate` — protocol help

### Update CLAUDE.md

Final CLAUDE.md must include:
- Claude's role (PM + orchestrator, not coder)
- All skills with triggers
- All subagents with domains and ownership
- Co-processor routing (gcop/pcop)
- Gate table with status
- Athenaeum policy (programmatic only, never /chat)
- Research doc index
- Constraint map reference
- Critical rules (MUST/NEVER)

---

## Phase 7: ALIGN (30-60 minutes)

**Input:** Everything from Phases 1-6
**Output:** Verified, driftless, ready-to-execute project

### Alignment Verification Script

Run these checks:

```bash
# 1. File structure
echo "Root files: $(ls *.md *.toml *.yml .gitignore | wc -l)"
echo "Research docs: $(ls research/*.md | wc -l)"

# 2. No stale references
grep -r 'OLD_LIBRARY_ID' --include='*.md' . | wc -l  # expect 0
grep -r 'chat.*endpoint' --include='*.md' . | grep -v 'NEVER' | wc -l  # expect 0

# 3. V11 config
jq '.' .claude/settings.json > /dev/null && echo "settings: VALID"
jq '.' .claude/athenaeum.json > /dev/null && echo "athenaeum: VALID"

# 4. Cross-document consistency
# Agent names match everywhere
# Gate numbers are sequential
# Risk register is complete
# Library IDs are correct

# 5. Athenaeum live check
curl -s "http://localhost:8140/api/libraries/ID" | jq '{documents: .document_count, chunks: .chunk_count}'
```

### Git Init

```bash
git init
git add -A
git commit -m "Initial scaffold: [PROJECT] — [N] research docs, [N] agents, [N] gates

Phase 0-N defined. Hypothesis-driven spec with Bayesian belief tracking.
Athenaeum library [ID] with [N] docs, [N] chunks.
Gate execution protocol from 8 problem-solving frameworks.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### Ready Signal

Project is ready when:
```
□ 0 stale references across all documents
□ 0 contradictions between documents
□ All numbers are derivable from first principles
□ Every assumption has a gate that validates it
□ Every gate has measurable pass/fail criteria
□ Every gate has a fail action (not just "fix it")
□ .claude/settings.json loads without errors
□ .claude/commands/ contains project-specific commands
□ Athenaeum library is live and populated
□ Git repo initialized with comprehensive .gitignore
□ Workspace script is executable and all modes work
```

---

## Timing Summary

| Phase | Duration | Parallelizable? |
|-------|----------|-----------------|
| 1. Capture | 30 min | No |
| 2. Scaffold | 1-2 hr | Partially (agents can scaffold code) |
| 3. Research | 2-6 hr | Yes (3 agents × N docs) |
| 4. Audit | 1-2 hr | Yes (3 parallel audits) |
| 5. Restructure | 2-4 hr | No (requires audit results) |
| 6. Protocol | 2-3 hr | Partially (skills + scripts in parallel) |
| 7. Align | 30-60 min | No |
| **Total** | **10-18 hr** | **~40% parallelizable** |

For a well-defined concept, a single Claude Code session can complete Phases 2-7 in one sitting.
