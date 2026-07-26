# V11 Upgrade Spec: Deep Plan Integration

> Add deep-plan scaffolding as a first-class V11 capability.
> Enables: `/v11-deep-plan` skill, research-aware formations, Athenaeum-native workflows.

## Why

V11 currently excels at **implementation orchestration** — coordinating agents to build things.
But it has no framework for **pre-implementation planning** — the phase where vague ideas become
validated, gate-structured, hypothesis-driven roadmaps.

The reference project's build proved that rigorous planning (7 phases, 8 problem-solving frameworks,
Athenaeum-backed research) is the difference between building on sand and building on evidence.

This upgrade makes that process repeatable for any massive project.

## What Changes

### New Skill: `/v11-deep-plan`

**Trigger:** `/v11-deep-plan`, "deep plan", "plan massive project", "research-first project"

**Behavior:**
1. Interview user to capture vision (Phase 1)
2. Run scaffold (Phase 2) — reuses `/v11-scaffold` internals
3. Launch parallel research agents (Phase 3)
4. Launch parallel PM audit agents (Phase 4)
5. Restructure spec with Bayesian belief tracking (Phase 5)
6. Build gate protocol from Athenaeum problem-solving library (Phase 6)
7. Verify alignment (Phase 7)

**Replaces:** Manual execution of the 7-phase methodology
**Depends on:** Athenaeum API (localhost:3000), agent registry, existing scaffold skill

### New Formation: `deep-research`

```yaml
name: deep-research
teammates:
  - research-lead: Coordinates research strategy, identifies gaps
  - researcher-1: Writes research documents (batch 1)
  - researcher-2: Writes research documents (batch 2)
  - researcher-3: Writes research documents (batch 3)
  - auditor: PM audit (runs after research complete)
wave_dependencies:
  - wave-1: [researcher-1, researcher-2, researcher-3]  # parallel
  - wave-2: [auditor]  # after all research
  - wave-3: [research-lead]  # synthesize findings
```

### New Formation: `pm-audit`

```yaml
name: pm-audit
teammates:
  - research-auditor: Grades research quality, finds gaps/contradictions
  - landscape-auditor: OSS landscape review, prior art check
  - spec-auditor: Gate/risk/scope review
wave_dependencies:
  - wave-1: [research-auditor, landscape-auditor, spec-auditor]  # all parallel
```

### New Template: `spec-hypothesis.md.template`

Extends existing `spec.md.template` with:
- Core hypothesis table with Bayesian priors
- Belief tracker (updated at each gate)
- Constraint map (bottleneck per phase)
- Cynefin domain classification per phase
- Pre-mortem failure modes per phase
- Kill conditions (not just fail actions)

### New Template: `gate-protocol.md.template`

Reusable gate execution protocol built from Athenaeum problem-solving library (ID: 42):
- 8-framework protocol stack
- Cognitive bias checklist
- Agent delegation template
- Documentation hardening checklist
- Gate-specific protocols (filled in per project)

### New Template: `project-commands/`

Project-scoped Claude commands:
- `{project}-gate.md` — gate protocol invocation
- `athenaeum.md` — research mission types
- Configurable per-project

### New Template: `example-project.sh.template` → `workspace.sh.template`

Generic workspace manager script:
- Research mode (Athenaeum search, list, read, ingest)
- Development mode (build, test, check, ci)
- Infrastructure mode (up, down, status)
- Gate protocol mode (start, review, harden)

### Enhanced Scaffold Script

Extend `scripts/scaffold` to accept `--deep-plan` flag:

```bash
./scripts/scaffold --deep-plan \
  --name "project-name" \
  --subdomain "project.example.com" \
  --stack rust \
  --agents 6 \
  --research-topics "topic1,topic2,topic3"
```

When `--deep-plan` is set:
1. Standard scaffold runs first (structure, docker, ports)
2. Athenaeum library created automatically
3. Research document stubs generated from `--research-topics`
4. Gate protocol template copied and configured
5. Project commands installed to `.claude/commands/`
6. Workspace script generated
7. spec.md uses hypothesis template (not standard template)

### Athenaeum Integration Points

| Integration | Current | After Upgrade |
|-------------|---------|---------------|
| Library creation | Manual curl | `./scripts/scaffold --deep-plan` auto-creates |
| Research ingestion | Manual curl loop | `./scripts/workspace.sh research-ingest` |
| Research search | Manual curl | `/athenaeum search "query"` command |
| Contradiction scan | Manual | `/athenaeum mission contradiction-scan` |
| Gap discovery | Manual | `/athenaeum mission gap-discovery` |
| Gate evidence | Manual | `/athenaeum mission evidence gate-N` |
| Problem-solving library | Pull raw docs | Gate protocol template pre-synthesized |

### V11 CLAUDE.md Changes

Add to V11's root CLAUDE.md:

```markdown
## Deep Plan (Massive Project Scaffolding)

For projects requiring deep research before implementation:

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/v11-deep-plan` | New massive project | Full 7-phase methodology |
| `/v11-scaffold --deep-plan` | Project with research | Enhanced scaffold |

### When to Use Deep Plan
- 5+ unsolved research questions
- 3+ custom agents needed
- Joint success probability < 50%
- Research → implementation pipeline

### Deep Plan Phases
1. CAPTURE → VISION.md
2. SCAFFOLD → Project structure + agents
3. RESEARCH → Athenaeum library (10-20 docs)
4. AUDIT → PM audit (3 parallel agents)
5. RESTRUCTURE → Hypothesis-driven spec
6. PROTOCOL → Gate execution framework
7. ALIGN → Verification + git init
```

---

## Tasks

### Phase 1: Templates & Formations (1-2 days)

| ID | Task | Effort |
|----|------|--------|
| 1.1 | Create `spec-hypothesis.md.template` | Low |
| 1.2 | Create `gate-protocol.md.template` | Low |
| 1.3 | Create `workspace.sh.template` | Low |
| 1.4 | Create `project-commands/` template set | Low |
| 1.5 | Define `deep-research` formation in formations/ | Low |
| 1.6 | Define `pm-audit` formation in formations/ | Low |

### Phase 2: Scaffold Enhancement (1 day)

| ID | Task | Effort |
|----|------|--------|
| 2.1 | Add `--deep-plan` flag to scaffold script | Medium |
| 2.2 | Auto-create Athenaeum library in scaffold | Medium |
| 2.3 | Generate research doc stubs from topics | Low |
| 2.4 | Install project commands during scaffold | Low |
| 2.5 | Generate workspace script from template | Low |

### Phase 3: Skill Development (2-3 days)

| ID | Task | Effort |
|----|------|--------|
| 3.1 | Write `/v11-deep-plan` skill (full 7-phase orchestration) | High |
| 3.2 | Write `/athenaeum` skill (research missions) | Medium |
| 3.3 | Write `project-gate` command template | Medium |
| 3.4 | Test skill on a real project (validation) | Medium |

### Phase 4: Documentation & Integration (1 day)

| ID | Task | Effort |
|----|------|--------|
| 4.1 | Update V11 CLAUDE.md with deep-plan section | Low |
| 4.2 | Update ROADMAP.md with Phase 11: Deep Plan | Low |
| 4.3 | Write migration guide (existing projects → deep plan) | Low |
| 4.4 | Add deep-plan to formation quality benchmark | Medium |

**Total: ~5-7 days, 16 tasks**

---

## Gate Structure

| Gate | Criterion | Fail Action |
|------|-----------|-------------|
| G1 | Templates render correctly with variable substitution | Fix templates |
| G2 | `--deep-plan` scaffold produces working project | Debug scaffold |
| G3 | `/v11-deep-plan` completes all 7 phases on test project | Debug skill |
| G4 | Second project scaffolded from scratch validates methodology | Iterate |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Athenaeum offline during scaffold | Medium | Degrade gracefully — create library later |
| Problem-solving library (ID:42) changes | Low | Pin document IDs in template |
| Research agent quality varies | Medium | Template enforces structure (benchmarks, code examples required) |
| 7 phases too rigid for small-ish projects | Medium | `/v11-deep-plan --lite` skips Phase 4 audit for medium projects |

---

## Success Criteria

1. New massive project can go from concept to ready-to-execute in one Claude Code session
2. Methodology is repeatable — second project is faster than first
3. All documents are driftless — no contradictions, no stale references
4. Gate protocol catches real issues (not just ceremony)
5. Athenaeum library is live and useful for gate evidence gathering
