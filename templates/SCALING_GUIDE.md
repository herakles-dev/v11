# V11 Scaling Guide

> How to structure projects of different sizes using V11 Protocol.

---

## Project Size Classification

| Size | Tasks | Active build¹ | Structure | Formation |
|------|-------|----------|-----------|-----------|
| **Tiny** | 1-10 | <1 evening | Flat task list | Direct work, no formation |
| **Small** | 11-50 | 1 evening – a few active-days | Sprint metadata | Single formation |
| **Medium** | 51-150 | a few active-days | Sprint + gates | Multiple formations |
| **Large** | 151-500 | 1-3 active-weeks | Multi-sprint + gates | Formation chains |
| **Enterprise** | 500+ | multi-week+ | Multi-project split | Consult orchestrator |

> ¹ **Active build** = hands-on work time (empirical — see [docs/BUILD_TIMING.md](../docs/BUILD_TIMING.md)), NOT calendar span. Calendar runs longer only when blocked on external gates (deploy, human review, funded spend). Estimating in calendar weeks is the 4–8× over-estimation this replaces.

---

## Tiny Projects (1-10 tasks)

**Structure**: Flat task list, no metadata needed.

```python
TaskCreate(subject="Add login button", description="...")
TaskCreate(subject="Style login form", description="...")
```

**Approach**: Work directly, no formation. Single session.

---

## Small Projects (11-50 tasks)

**Structure**: Group tasks by sprint using metadata.

```python
TaskCreate(
    subject="Implement user auth",
    metadata={"sprint": "sprint-01-mvp", "project": "myapp"}
)
```

**Approach**: Single formation (usually feature-impl). One team handles all sprints sequentially.

**Query by sprint**:
```bash
./scripts/status --sprint sprint-01-mvp
```

---

## Medium Projects (51-150 tasks)

**Structure**: Sprint metadata + gate definitions.

### Sprint Organization
```
sprint-01-foundation (tasks 1-15)
  -> gate-1-foundation (schema migrated, connection pool configured)
sprint-02-features (tasks 16-40)
  -> gate-2-implemented (all features complete)
sprint-03-quality (tasks 41-55)
  -> gate-3-tested (all tests passing)
```

### Gate Definitions (gates.md)
```markdown
## Gate 1: Foundation Ready
**Criteria**:
- Schema migrated and verified
- Connection pool configured
- Health checks passing
**Unlocks**: sprint-02-features

## Gate 2: Implemented
**Criteria**:
- All feature tasks completed
- No critical bugs open
**Unlocks**: sprint-03-quality
```

### Formation Strategy
- Sprint 1: **new-project** formation (architect + 2 implementers)
- Sprint 2: **feature-impl** formation (backend + frontend + integrator + tester)
- Sprint 3: **code-review** + **security-review** formations

### Agent Teams for Medium Projects
```
Formation 1 (Sprint 1): new-project
  -> architect designs, implementers scaffold
  -> Gate 1 validation

Formation 2 (Sprint 2): feature-impl
  -> backend + frontend in parallel
  -> integrator wires services
  -> tester validates
  -> Gate 2 validation

Formation 3 (Sprint 3): code-review + security-review
  -> reviewers audit code
  -> security team audits
  -> Gate 3 validation
```

---

## Large Projects (151-500 tasks)

**Structure**: Everything from Medium, plus:

### Multi-Formation Chains
Run multiple formations per sprint when tasks are parallelizable:

```
Sprint 2: Features
  Formation 2a: feature-impl (user management)
    -> backend-impl, frontend-impl, integrator, tester
  Formation 2b: feature-impl (content management)
    -> backend-impl, frontend-impl, integrator, tester
  Formation 2c: feature-impl (notifications)
    -> backend-impl, integrator, tester
```

### Task Dependencies Across Formations
```python
# Formation 2b depends on Formation 2a's API contracts
TaskUpdate(taskId="content-api-task", addBlockedBy=["user-api-task"])
```

### Progress Tracking
```bash
# Overall progress
./scripts/status myproject

# Sprint progress
./scripts/status myproject --sprint sprint-02

# Team status
./scripts/team-status
```

### Gate Validation
Gates become critical checkpoints:
1. Team lead validates gate criteria
2. All tasks in gate sprint must be completed
3. No blocker tasks open
4. Security review passed (if applicable)
5. Test coverage meets threshold

---

## Enterprise Projects (500+)

**Strategy**: Split into sub-projects.

```
main-project/
  auth-service (50 tasks)
  api-gateway (30 tasks)
  user-service (40 tasks)
  content-service (60 tasks)
  notification-service (25 tasks)
  frontend (80 tasks)
```

Each sub-project:
- Has its own spec.md
- Has its own task list
- Uses its own formations
- Coordinates via API contracts (managed by integrator)

---

## Critical Rules for Scaling

1. **Tasks are source of truth** -- Never manually track progress in state.md
2. **Use metadata.sprint** -- Groups tasks without separate sprint files
3. **Use metadata.gate** -- Links tasks to gate requirements
4. **Max 5 teammates per formation** -- Beyond this, coordination overhead exceeds benefit
5. **One tester per 3 implementers** -- Maintain quality ratio
6. **Gate validation before sprint transition** -- Don't skip gates
7. **Recount via TaskList** -- No regex parsing of state files

## Formation Selection by Scale

| Scale | Formation Count | Concurrent Teams |
|-------|----------------|-----------------|
| Tiny | 0 | 0 (direct work) |
| Small | 1 | 1 |
| Medium | 2-3 | 1-2 |
| Large | 4-8 | 2-3 |
| Enterprise | Per sub-project | Per sub-project |

---

*V11 Scaling Guide -- Agent Teams at Scale*
