# TypeScript Code Standards

> Patterns and best practices for TypeScript code in V10 projects.

---

## Type Definitions

### Interface Pattern

```typescript
// DO: Clear, explicit interfaces
interface User {
  id: string;
  email: string;
  createdAt: Date;
}

interface CreateUserRequest {
  email: string;
  password: string;
  name: string;
}

interface UserResponse {
  id: string;
  email: string;
  name: string;
  // Never include passwordHash in responses
}
```

### Type vs Interface

```typescript
// Use INTERFACE for object shapes (extensible)
interface User {
  id: string;
  email: string;
}

// Use TYPE for unions, intersections, computed types
type UserRole = 'admin' | 'user' | 'guest';
type AuthenticatedUser = User & { role: UserRole };
type ApiResponse<T> = { data: T } | { error: string };
```

### Avoid Any

```typescript
// DON'T: Any types
const user: any = await getUser(id);  // BAD
const response: any = await fetch(url);  // BAD

// DO: Explicit types or unknown
const user: User = await getUser(id);  // GOOD
const response: Response = await fetch(url);  // GOOD

// For truly unknown types
const data: unknown = JSON.parse(input);
if (isUser(data)) {
  // Now TypeScript knows data is User
  console.log(data.email);
}
```

---

## Error Handling

### Try-Catch Pattern

```typescript
// DO: Handle errors explicitly
async function getUser(id: string): Promise<User> {
  try {
    const user = await db.users.findById(id);

    if (!user) {
      throw new NotFoundError(`User ${id} not found`);
    }

    return user;
  } catch (error) {
    if (error instanceof NotFoundError) {
      throw error;  // Re-throw known errors
    }

    logger.error('Database error', { id, error });
    throw new DatabaseError('Failed to fetch user');
  }
}

// DON'T: Silent failures
async function getUser(id: string): Promise<User | null> {
  try {
    return await db.users.findById(id);
  } catch {
    return null;  // BAD: Error info lost
  }
}
```

### Custom Error Classes

```typescript
class NotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NotFoundError';
  }
}

class ValidationError extends Error {
  constructor(
    message: string,
    public field: string
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

class DatabaseError extends Error {
  constructor(
    message: string,
    public originalError?: Error
  ) {
    super(message);
    this.name = 'DatabaseError';
  }
}
```

### Error Middleware (Express)

```typescript
import { Request, Response, NextFunction } from 'express';

function errorHandler(
  error: Error,
  req: Request,
  res: Response,
  next: NextFunction
) {
  logger.error('Request error', {
    path: req.path,
    method: req.method,
    error: error.message,
    stack: error.stack
  });

  if (error instanceof NotFoundError) {
    return res.status(404).json({ error: error.message });
  }

  if (error instanceof ValidationError) {
    return res.status(400).json({
      error: error.message,
      field: error.field
    });
  }

  // Generic server error
  res.status(500).json({
    error: 'Internal server error'
  });
}

// Usage
app.use(errorHandler);
```

---

## Async/Await

### Promise Handling

```typescript
// DO: Await properly
async function processUser(id: string): Promise<void> {
  const user = await db.users.findById(id);
  const enriched = await enrichUserData(user);
  await db.users.update(id, enriched);
}

// DON'T: Unhandled promises
async function processUser(id: string): Promise<void> {
  db.users.findById(id).then(user => {  // BAD: No error handling
    enrichUserData(user).then(enriched => {
      db.users.update(id, enriched);  // BAD: Not awaited
    });
  });
}
```

### Parallel Execution

```typescript
// Sequential (slow)
const user = await getUser(id);
const posts = await getPosts(userId);
const comments = await getComments(userId);

// Parallel (fast)
const [user, posts, comments] = await Promise.all([
  getUser(id),
  getPosts(userId),
  getComments(userId)
]);

// Parallel with error handling
const results = await Promise.allSettled([
  getUser(id),
  getPosts(userId),
  getComments(userId)
]);

results.forEach((result, index) => {
  if (result.status === 'rejected') {
    logger.error(`Promise ${index} failed`, result.reason);
  }
});
```

---

## Validation

### Input Validation

```typescript
import { z } from 'zod';

// Define schema
const CreateUserSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  name: z.string().min(1).max(100)
});

// Validation middleware
function validateRequest<T>(schema: z.Schema<T>) {
  return (req: Request, res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.body);

    if (!result.success) {
      return res.status(400).json({
        error: 'Validation failed',
        details: result.error.errors
      });
    }

    req.body = result.data;  // Now typed!
    next();
  };
}

// Usage
router.post('/users', validateRequest(CreateUserSchema), async (req, res) => {
  const userData = req.body;  // Typed as CreateUserRequest
  // ...
});
```

---

## Null Safety

### Optional Chaining

```typescript
// DO: Use optional chaining
const email = user?.profile?.email;
const firstPost = user?.posts?.[0]?.title;

// DO: Nullish coalescing
const displayName = user?.name ?? 'Anonymous';
const port = process.env.PORT ?? 3000;

// DON'T: Manual null checks everywhere
const email = user && user.profile && user.profile.email;  // Verbose
```

### Non-Null Assertions (use sparingly)

```typescript
// DO: Only when you're absolutely certain
const element = document.getElementById('root')!;  // DOM always has root

// DON'T: Avoid assumptions
const user = await getUser(id)!;  // BAD: Could be null
```

---

## Naming Conventions

```typescript
// Interfaces: PascalCase
interface User {}
interface CreateUserRequest {}

// Types: PascalCase
type UserId = string;
type UserRole = 'admin' | 'user';

// Variables: camelCase
const userId = '123';
const isAdmin = true;

// Constants: UPPER_SNAKE_CASE
const MAX_RETRIES = 3;
const API_BASE_URL = 'https://api.example.com';

// Functions: camelCase
function getUserById(id: string): Promise<User> {}

// Classes: PascalCase
class UserService {}
class DatabaseConnection {}

// Enums: PascalCase (keys UPPER_SNAKE_CASE)
enum UserRole {
  ADMIN = 'admin',
  USER = 'user',
  GUEST = 'guest'
}
```

---

## File Organization

```
src/
├── types/
│   ├── index.ts          # Re-export all types
│   ├── user.ts           # User-related types
│   └── auth.ts           # Auth-related types
├── routes/
│   ├── users.ts          # User endpoints
│   └── auth.ts           # Auth endpoints
├── services/
│   ├── userService.ts    # Business logic
│   └── authService.ts
├── middleware/
│   ├── auth.ts           # Auth middleware
│   └── errorHandler.ts
└── utils/
    ├── logger.ts         # Logging utility
    └── db.ts             # Database connection
```

---

## Import Patterns

```typescript
// DO: Absolute imports (configure tsconfig.json)
import { User } from '@/types/user';
import { logger } from '@/utils/logger';

// DON'T: Deep relative imports
import { User } from '../../../types/user';  // BAD

// DO: Group imports
// 1. External libraries
import express from 'express';
import { z } from 'zod';

// 2. Internal modules
import { User } from '@/types/user';
import { logger } from '@/utils/logger';

// 3. Relative imports (same directory)
import { validateUser } from './validation';
```

---

*TypeScript standards for V10 projects*
