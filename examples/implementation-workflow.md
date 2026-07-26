# Example: Implementation Workflow

> Complete example showing spec-implementer-v10 end-to-end workflow with checkpoints and handoff.

---

## Scenario

Task assigned: "Implement JWT authentication with login/register endpoints"

---

## Step 1: Claim Task

```python
# Check current state
TaskList()

# Get task details
task = TaskGet(taskId="task-05")

# Claim the task
TaskUpdate(taskId="task-05", status="in_progress", owner="implementer")
```

---

## Step 2: Checkpoint 1 - Implementation Plan

```markdown
## IMPLEMENTATION PLAN

### Task: Implement JWT authentication

### Understanding
- Goal: Create login and register endpoints with JWT token generation
- Acceptance criteria:
  - POST /auth/login returns JWT token
  - POST /auth/register creates user and returns JWT token
  - JWT tokens include user ID and email
  - Tokens expire in 24 hours
- Risk: medium (auth changes)

### Changes Required
| File | Action | Description |
|------|--------|-------------|
| src/routes/auth.ts | Create | JWT authentication endpoints |
| src/middleware/auth.ts | Create | Auth middleware for protected routes |
| src/types/auth.ts | Create | Auth type definitions |
| package.json | Edit | Add jsonwebtoken and bcrypt dependencies |

### Approach
1. Create auth types (User, AuthPayload, LoginRequest, RegisterRequest)
2. Implement JWT generation/validation functions
3. Create login endpoint (validate credentials, return JWT)
4. Create register endpoint (hash password, create user, return JWT)
5. Add auth middleware for protected routes
6. Verify with type check and quick test

### Dependencies
- jsonwebtoken (npm)
- bcrypt (npm)

PROCEED WITH IMPLEMENTATION?
```

---

## Step 3: Implementation

### Read Before Write

```python
# Read existing files to understand patterns
Read(file_path="/src/routes/users.ts")  # See existing route pattern
Read(file_path="/src/types/index.ts")   # See existing type pattern
Read(file_path="/package.json")         # Check dependencies
```

### Create Files

```typescript
// src/types/auth.ts
export interface User {
  id: string;
  email: string;
  passwordHash: string;
  createdAt: Date;
}

export interface AuthPayload {
  userId: string;
  email: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
}

export interface AuthResponse {
  token: string;
  user: {
    id: string;
    email: string;
    name: string;
  };
}
```

```typescript
// src/routes/auth.ts
import { Router } from 'express';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import type { LoginRequest, RegisterRequest, AuthResponse } from '../types/auth';

const router = Router();
const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret';

router.post('/login', async (req, res) => {
  const { email, password }: LoginRequest = req.body;

  // Validate input
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  try {
    // Find user
    const user = await db.users.findOne({ email });
    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // Verify password
    const valid = await bcrypt.compare(password, user.passwordHash);
    if (!valid) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // Generate JWT
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    const response: AuthResponse = {
      token,
      user: { id: user.id, email: user.email, name: user.name }
    };

    res.json(response);
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

router.post('/register', async (req, res) => {
  const { email, password, name }: RegisterRequest = req.body;

  // Validate input
  if (!email || !password || !name) {
    return res.status(400).json({ error: 'Email, password, and name required' });
  }

  try {
    // Check if user exists
    const existing = await db.users.findOne({ email });
    if (existing) {
      return res.status(409).json({ error: 'User already exists' });
    }

    // Hash password
    const passwordHash = await bcrypt.hash(password, 10);

    // Create user
    const user = await db.users.create({
      email,
      passwordHash,
      name,
      createdAt: new Date()
    });

    // Generate JWT
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    const response: AuthResponse = {
      token,
      user: { id: user.id, email: user.email, name: user.name }
    };

    res.status(201).json(response);
  } catch (error) {
    console.error('Register error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

export default router;
```

```typescript
// src/middleware/auth.ts
import jwt from 'jsonwebtoken';
import type { Request, Response, NextFunction } from 'express';
import type { AuthPayload } from '../types/auth';

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret';

export async function authMiddleware(req: Request, res: Response, next: NextFunction) {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'No token provided' });
  }

  const token = authHeader.substring(7);

  try {
    const payload = jwt.verify(token, JWT_SECRET) as AuthPayload;
    req.user = payload;
    next();
  } catch (error) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}
```

---

## Step 4: Verification

### Syntax Check

```bash
npm run typecheck
# ✓ No type errors found

npm run lint
# ✓ No linting errors
```

### Logic Check

```bash
npm test -- src/routes/auth.test.ts --run
# ✓ POST /auth/login - valid credentials - returns token (45ms)
# ✓ POST /auth/login - invalid credentials - returns 401 (38ms)
# ✓ POST /auth/register - new user - creates user and returns token (52ms)
# ✓ POST /auth/register - existing email - returns 409 (29ms)
# All tests passed (4/4)
```

---

## Step 5: Checkpoint 2 - Implementation Complete

```markdown
## IMPLEMENTATION COMPLETE

### Task: Implement JWT authentication

### Changes Made
| File | Lines | Description |
|------|-------|-------------|
| src/routes/auth.ts | +85 | Login/register endpoints with validation |
| src/middleware/auth.ts | +25 | JWT verification middleware |
| src/types/auth.ts | +30 | User, AuthPayload, Request/Response types |
| package.json | +2 | Added jsonwebtoken and bcrypt |

### Verification
- Type check: PASS
- Lint: PASS
- Unit tests: PASS (4/4 tests)

### Task Updated
- Status: completed
- Description: "Implemented JWT authentication with login/register endpoints. All tests passing."

### Next Steps
- Integration tests needed (spec-tester-v10)
- Security review recommended (spec-security-v10)

HANDOFF: spec-integrator-v10 (for service integration) or spec-tester-v10 (for testing)
```

---

## Step 6: Complete Task

```python
TaskUpdate(
    taskId="task-05",
    status="completed",
    description="Implemented JWT authentication with login/register endpoints. Includes password hashing, token generation, and auth middleware. All tests passing (4/4)."
)
```

---

## Handoff Format

```json
{
  "agent": "spec-implementer-v10",
  "version": "9.0.0",
  "status": "completed",
  "task_id": "task-05",

  "implementation": {
    "files_created": [
      "src/routes/auth.ts",
      "src/middleware/auth.ts",
      "src/types/auth.ts"
    ],
    "files_modified": ["package.json"],
    "lines_added": 142,
    "dependencies_added": ["jsonwebtoken", "bcrypt"]
  },

  "verification": {
    "typecheck": "pass",
    "lint": "pass",
    "tests": "pass (4/4)"
  },

  "next": {
    "recommended_agent": "spec-tester-v10",
    "reason": "Integration tests needed for auth flow",
    "suggested_tests": [
      "Full login flow with database",
      "Token expiration handling",
      "Protected route access"
    ]
  },

  "metrics": {
    "files_read": 5,
    "files_written": 4,
    "duration_seconds": 420
  }
}
```

---

## Error Handling Patterns

### On Type Error

```python
if typecheck_failed:
    # Fix the code
    Edit(file_path="src/routes/auth.ts", old_string=buggy_code, new_string=fixed_code)
    # Re-verify
    run_typecheck()
    # Only mark complete when passing
```

### On Test Failure

```python
if test_failed:
    # Analyze failure
    # If quick fix: fix and retry
    # If complex: Create blocker task
    TaskCreate(
        subject="Fix: Test failure in auth endpoint",
        description=f"Test {test_name} failed with error: {error_message}",
        metadata={"type": "bugfix", "blocking": "task-05"}
    )
    TaskUpdate(taskId="task-05", addBlockedBy=["task-blocker-id"])
```

---

*Example from spec-implementer-v10 documentation*
