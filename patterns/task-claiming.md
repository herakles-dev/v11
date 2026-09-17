# Task Claiming Patterns

> Standard patterns for working with the V10 native Tasks system.

---

## Basic Task Workflow

### 1. Check Task List

```python
# Get all tasks
tasks = TaskList()

# View task details
task = TaskGet(taskId="5")
```

### 2. Claim a Task

```python
# Before starting work
TaskUpdate(
    taskId="5",
    status="in_progress",
    owner="implementer-agent"
)
```

### 3. Complete a Task

```python
# After finishing work
TaskUpdate(
    taskId="5",
    status="completed",
    description="Implemented user login endpoint with JWT authentication. All tests passing."
)
```

---

## Task Creation Patterns

### Basic Task

```python
TaskCreate(
    subject="Implement user login endpoint",
    description="Create POST /auth/login endpoint that accepts email and password, validates credentials, and returns JWT token.",
    activeForm="Implementing user login endpoint"
)
```

### Task with Metadata

```python
TaskCreate(
    subject="Implement user login endpoint",
    description="Create POST /auth/login endpoint with JWT authentication.",
    activeForm="Implementing user login",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-01-foundation",
        "gate": "gate-1-foundation",
        "risk": "medium",
        "agent": "spec-implementer-v10",
        "phase": "implementation"
    }
)
```

### Blocker Task

```python
# Create a blocking task
TaskCreate(
    subject="Fix: Database migration failure",
    description="Migration 003_add_users_table failed with error: column 'email' already exists",
    activeForm="Fixing database migration",
    metadata={
        "type": "bugfix",
        "blocking": "task-05",
        "priority": "high"
    }
)

# Link as blocker
TaskUpdate(taskId="task-05", addBlockedBy=["task-blocker-id"])
```

---

## Metadata Patterns

### Sprint Organization

```python
metadata={
    "sprint": "sprint-01-foundation",  # Foundation work
    "sprint": "sprint-02-features",    # Feature development
    "sprint": "sprint-03-quality"      # Testing & optimization
}
```

### Gate Tracking

```python
metadata={
    "gate": "gate-0-planned",       # Spec and tasks created
    "gate": "gate-1-foundation",    # Infrastructure ready
    "gate": "gate-2-implemented",   # Features complete
    "gate": "gate-3-tested",        # All tests passing
    "gate": "gate-4-deployed"       # Production ready
}
```

### Risk Levels

```python
metadata={
    "risk": "low",      # Read files, run tests
    "risk": "medium",   # Edit code, create files
    "risk": "high"      # Delete data, deploy, auth changes
}
```

### Agent Assignment

```python
metadata={
    "agent": "spec-implementer-v10",  # Code implementation
    "agent": "spec-architect-v10",    # Architecture design
    "agent": "spec-tester-v10",       # Testing
    "agent": "spec-security-v10",     # Security review
    "agent": "spec-integrator-v10"    # Service integration
}
```

### Phase Tracking

```python
metadata={
    "phase": "setup",           # Project setup
    "phase": "implementation",  # Code implementation
    "phase": "testing",         # Testing phase
    "phase": "security",        # Security review
    "phase": "optimization",    # Performance work
    "phase": "deployment"       # Deployment
}
```

---

## Dependency Patterns

### Sequential Tasks

```python
# task-02 must wait for task-01 to complete
TaskUpdate(taskId="task-02", addBlockedBy=["task-01"])

# task-03 waits for task-02
TaskUpdate(taskId="task-03", addBlockedBy=["task-02"])
```

### Parallel Tasks with Common Dependency

```python
# All three wait for task-01, then can run in parallel
TaskUpdate(taskId="task-02", addBlockedBy=["task-01"])
TaskUpdate(taskId="task-03", addBlockedBy=["task-01"])
TaskUpdate(taskId="task-04", addBlockedBy=["task-01"])
```

### Multiple Dependencies

```python
# task-10 waits for multiple tasks to complete
TaskUpdate(taskId="task-10", addBlockedBy=["task-07", "task-08", "task-09"])
```

### This Task Blocks Others

```python
# Mark that task-05 blocks task-10 and task-11
TaskUpdate(taskId="task-05", addBlocks=["task-10", "task-11"])
```

---

## Query Patterns

### Find Available Tasks

```python
# In bash/jq
claude tasks --json | jq '.[] | select(.status == "pending" and (.blockedBy | length) == 0)'

# In Python (pseudo-code showing logic)
tasks = TaskList()
available = [t for t in tasks if t.status == "pending" and not t.blockedBy]
```

### Find Tasks for Specific Agent

```python
claude tasks --json | jq '.[] | select(.metadata.agent == "spec-implementer-v10" and .status == "pending")'
```

### Find High-Risk Tasks

```python
claude tasks --json | jq '.[] | select(.metadata.risk == "high")'
```

### Find Blocking Tasks

```python
# Find tasks that are blocking others
claude tasks --json | jq '.[] | select((.blocks | length) > 0)'

# Find tasks that are blocked
claude tasks --json | jq '.[] | select((.blockedBy | length) > 0)'
```

---

## Progress Reporting

### Update Description During Work

```python
TaskUpdate(
    taskId="task-05",
    description="Implementing user login. JWT middleware complete, working on validation logic."
)
```

### Add Notes for Other Teammates

```python
TaskUpdate(
    taskId="task-05",
    description="Implemented login endpoint. NOTE FOR TESTER: Test entry point is POST /auth/login. Sample request in tests/fixtures/auth.json"
)
```

---

## Error Handling Patterns

### On Type Error

```python
# Don't mark complete - fix the error
if typecheck_failed:
    # Fix the code
    Edit(file_path, buggy_code, fixed_code)

    # Re-verify
    run_typecheck()

    # Only mark complete when passing
    if typecheck_passed:
        TaskUpdate(taskId="task-05", status="completed")
```

### On Test Failure

```python
if test_failed:
    # For quick fixes: fix and retry
    if is_quick_fix:
        fix_code()
        rerun_tests()

    # For complex issues: create blocker task
    else:
        TaskCreate(
            subject="Fix: Test failure in auth endpoint",
            description=f"Test {test_name} failed: {error_message}\n\nStack trace:\n{stack_trace}",
            metadata={
                "type": "bugfix",
                "blocking": "task-05",
                "priority": "high"
            }
        )

        TaskUpdate(taskId="task-05", addBlockedBy=["blocker-task-id"])
```

### On Dependency Issue

```python
if missing_dependency:
    if can_auto_install:
        install_dependency()
        continue_work()
    else:
        # Create task for approval
        TaskCreate(
            subject="Approval needed: Add dependency jsonwebtoken",
            description="Task-05 requires jsonwebtoken npm package for JWT handling. Security implications reviewed.",
            metadata={
                "type": "approval",
                "blocking": "task-05"
            }
        )

        TaskUpdate(taskId="task-05", addBlockedBy=["approval-task-id"])
```

---

## Teammate Coordination Patterns

### Broadcast Message via Task

```python
TaskCreate(
    subject="BREAKING: Docker network configuration changed",
    description="All services now use project-internal network in addition to hercules-network. Update your service configs.\n\nAffected: implementers, integrator, tester",
    metadata={
        "broadcast": True,
        "affected_agents": ["implementer", "integrator", "tester"]
    }
)
```

### Request Help via Task

```python
TaskCreate(
    subject="Question: Best approach for user search?",
    description="Implementing user search (task-08). Should we use PostgreSQL full-text search or integrate Elasticsearch?\n\n@architect: Please advise on scalability trade-offs.",
    metadata={
        "type": "question",
        "directed_to": "spec-architect-v10",
        "related_to": "task-08"
    }
)
```

---

## Gate Validation Pattern

### Check Gate Completion

```bash
# All tasks in gate-1 must be completed
claude tasks --json | jq '[.[] | select(.metadata.gate == "gate-1-foundation")] | all(.status == "completed")'

# Returns true if gate is ready to pass
```

### Mark Gate Complete

```python
# Create gate completion task
TaskCreate(
    subject="Gate 1 validation complete",
    description="All foundation tasks completed:\n- Project structure setup\n- Database schema created\n- Core API endpoints implemented\n\nReady to proceed to sprint-02-features",
    metadata={
        "type": "gate-validation",
        "gate": "gate-1-foundation",
        "status": "passed"
    }
)
```

---

## Sprint Summary Pattern

```python
TaskCreate(
    subject="Sprint 01 retrospective",
    description="""Sprint 01 (Foundation) complete.

Completed tasks: 5/5
Duration: 3 days
Blockers: 1 (database migration issue, resolved)

Key achievements:
- Full project structure scaffolded
- Database schema with migrations
- Authentication system implemented
- Docker compose configured

Next: Sprint 02 (Features) - 7 tasks ready to claim""",
    metadata={
        "type": "retrospective",
        "sprint": "sprint-01-foundation"
    }
)
```

---

## Timeout Protection Patterns

### Prevent Timeout Alerts

```python
# Set file ownership to enable tracking
TaskCreate(
    subject="Implement DTW algorithm",
    description="Add dynamic time warping with Sakoe-Chiba band",
    metadata={
        "file_ownership": "/path/to/operator-home/sessions/audio-suite/src/dtw",
        "estimated_completion": "2026-02-13T15:00:00Z"
    }
)

# If waiting on external dependency, create blocker
TaskCreate(
    subject="Wait for API credentials from admin",
    description="Need production API keys before deployment",
    metadata={"type": "blocker"}
)
TaskUpdate(taskId="deployment-task", addBlockedBy=["api-creds-task"])

# Pause task intentionally (exempt from timeout)
TaskUpdate(
    taskId="task-15",
    metadata={"paused": True, "pause_reason": "Waiting for user feedback"}
)
```

### Respond to Timeout Alert

```python
# Option 1: Message teammate (team lead action)
TaskUpdate(
    taskId="stalled-task-id",
    description="Original description...\n\n[Team Lead Note] Checking on status - are you blocked on anything?"
)

# Option 2: Mark complete if work is done
TaskUpdate(
    taskId="stalled-task-id",
    status="completed",
    description="Work completed by teammate, verified by team lead"
)

# Option 3: Create blocker if stuck
TaskCreate(
    subject="BLOCKER: Missing database migration",
    description="Task stalled because migration 005_add_users was not applied",
    metadata={"type": "blocker", "priority": "high"}
)
TaskUpdate(taskId="stalled-task-id", addBlockedBy=["blocker-task-id"])

# Option 4: Restart with fresh context
TaskCreate(
    subject="Restart: Implement user search",
    description="Previous attempt stalled. Fresh start with context:\n\n[Previous work summary]\n\n[File paths]\n\n[Next steps]",
    metadata={
        "retry_of": "stalled-task-id",
        "retry_count": 1,
        "max_retries": 2
    }
)
```

### Best Practices for Long-Running Tasks

```python
# For tasks >30 min, update periodically
TaskUpdate(
    taskId="task-12",
    description="Implementing DTW algorithm. Progress: 60% complete, band constraint implemented, working on distance matrix optimization"
)

# For compilation/build tasks, set explicit ownership
TaskCreate(
    subject="Build Rust service",
    description="Compile rust-backend service (takes ~20 min)",
    metadata={
        "file_ownership": "/path/to/operator-home/sessions/project/rust-backend",
        "expected_duration_minutes": 25
    }
)

# For external API calls, create blocker pattern
TaskCreate(
    subject="Wait: Training ML model on remote GPU",
    description="Model training in progress on external service. ETA: 45 minutes",
    metadata={"type": "external-wait", "external_url": "https://..."}
)
TaskUpdate(taskId="model-integration-task", addBlockedBy=["training-wait-task"])
```

---

*Task claiming patterns for V10 projects*
