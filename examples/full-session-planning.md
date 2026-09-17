# Example: Full Session Planning

> Complete example of how spec-planner-v10 transforms user intent into spec.md and Tasks.

---

## User Input

```
"I want to build a photo organizer app with AI tagging"
```

---

## Interview

```
Q1: "What features are essential for MVP?"
A1: "Upload photos, auto-tag with AI, search by tag, albums"

Q2: "Any specific tech preferences or constraints?"
A2: "React frontend, Python backend, PostgreSQL, must run in Docker"
```

---

## Generated spec.md

```markdown
# Project: photo-organizer

## Intent
Build a web application for organizing photos with AI-powered automatic tagging.
Users can upload photos, which are automatically tagged using computer vision,
then search and organize photos into albums.

## Success Criteria
- Photos can be uploaded via drag-and-drop
- AI tagging completes within 5 seconds per photo
- Search returns results in under 1 second
- Albums can contain unlimited photos

## Stack
- Frontend: React 18 + TypeScript + Vite
- Backend: Python 3.11 + FastAPI
- Database: PostgreSQL 15
- AI: OpenAI Vision API
- Infrastructure: Docker, nginx reverse proxy

## Constraints
- Must run in Docker containers
- Hot reload required for development
- Follow Hercules platform conventions

## Integrations
- OpenAI Vision API for image tagging
- S3-compatible storage for photos

## Notes
- Interview depth: Production
- Estimated tasks: 12
- Estimated sprints: 3

---
Created: 2026-02-02
Protocol: V10
Tasks: Use TaskList to view all tasks
```

---

## Generated Tasks

### Sprint 1: Foundation

```python
TaskCreate(
    subject="Setup project structure",
    description="Initialize React frontend with Vite, FastAPI backend, PostgreSQL database. Configure Docker Compose for all services.",
    activeForm="Setting up project structure",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-01-foundation",
        "gate": "gate-1-foundation",
        "risk": "low",
        "agent": "spec-implementer-v10"
    }
)

TaskCreate(
    subject="Design database schema",
    description="Create PostgreSQL schema for photos, tags, albums, users. Include proper indexes and foreign keys.",
    activeForm="Designing database schema",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-01-foundation",
        "gate": "gate-1-foundation",
        "risk": "medium",
        "agent": "spec-implementer-v10"
    }
)

TaskCreate(
    subject="Implement file upload API",
    description="Create FastAPI endpoint for photo upload. Handle multipart form data, validate file types, store in S3-compatible storage.",
    activeForm="Implementing file upload API",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-01-foundation",
        "gate": "gate-1-foundation",
        "risk": "medium",
        "agent": "spec-implementer-v10"
    }
)
```

### Sprint 2: Features

```python
TaskCreate(
    subject="Integrate OpenAI Vision for tagging",
    description="Connect to OpenAI Vision API. Process uploaded photos, extract tags, store in database.",
    activeForm="Integrating OpenAI Vision",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-02-features",
        "gate": "gate-2-implemented",
        "risk": "medium",
        "agent": "spec-integrator-v10"
    }
)

TaskCreate(
    subject="Build photo search functionality",
    description="Implement full-text search on tags. Create search API endpoint and React search component.",
    activeForm="Building photo search",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-02-features",
        "gate": "gate-2-implemented",
        "risk": "low",
        "agent": "spec-implementer-v10"
    }
)

TaskCreate(
    subject="Create album management",
    description="Implement album CRUD operations. Allow users to create albums and add/remove photos.",
    activeForm="Creating album management",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-02-features",
        "gate": "gate-2-implemented",
        "risk": "low",
        "agent": "spec-implementer-v10"
    }
)

TaskCreate(
    subject="Build React UI components",
    description="Create PhotoGrid, PhotoUpload, SearchBar, AlbumList components with proper styling.",
    activeForm="Building React components",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-02-features",
        "gate": "gate-2-implemented",
        "risk": "low",
        "agent": "spec-implementer-v10"
    }
)
```

### Sprint 3: Quality

```python
TaskCreate(
    subject="Write integration tests",
    description="Create pytest tests for API endpoints. Test upload, tagging, search, albums.",
    activeForm="Writing integration tests",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-03-quality",
        "gate": "gate-3-tested",
        "risk": "low",
        "agent": "spec-tester-v10"
    }
)

TaskCreate(
    subject="Security audit",
    description="Review authentication, file upload security, API rate limiting. Check for OWASP Top 10.",
    activeForm="Running security audit",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-03-quality",
        "gate": "gate-3-tested",
        "risk": "medium",
        "agent": "spec-security-v10"
    }
)

TaskCreate(
    subject="Performance optimization",
    description="Optimize image processing, database queries, frontend bundle size. Target <1s search.",
    activeForm="Optimizing performance",
    metadata={
        "project": "photo-organizer",
        "sprint": "sprint-03-quality",
        "gate": "gate-3-tested",
        "risk": "low",
        "agent": "spec-optimizer-v10"
    }
)
```

---

## Task Dependencies

```python
# Sequential foundation tasks
TaskUpdate(taskId="task-02", addBlockedBy=["task-01"])
TaskUpdate(taskId="task-03", addBlockedBy=["task-02"])

# Features depend on foundation
TaskUpdate(taskId="task-04", addBlockedBy=["task-03"])
TaskUpdate(taskId="task-05", addBlockedBy=["task-02"])
TaskUpdate(taskId="task-06", addBlockedBy=["task-02"])
TaskUpdate(taskId="task-07", addBlockedBy=["task-03"])

# Quality gate blocks on feature completion
TaskUpdate(taskId="task-08", addBlockedBy=["task-04", "task-05", "task-06", "task-07"])
TaskUpdate(taskId="task-09", addBlockedBy=["task-04", "task-07"])
TaskUpdate(taskId="task-10", addBlockedBy=["task-08", "task-09"])
```

---

## Key Takeaways

1. **Spec.md stays focused**: Intent, stack, constraints only. No task lists.
2. **Tasks capture all work**: Each task has metadata for organization
3. **Sprint structure**: Foundation → Features → Quality
4. **Dependencies**: Sequential foundation, parallel features, blocking quality gates
5. **Agent assignment**: Each task recommends an appropriate specialist agent

---

*Example from spec-planner-v10 documentation*
