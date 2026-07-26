# Docker Compose Templates

> Standard docker-compose patterns for V10 projects.

---

## Basic Single-Service Template

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "${PORT:-3000}:8000"
    environment:
      - NODE_ENV=production
      - DATABASE_URL=${DATABASE_URL}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network
    restart: unless-stopped

networks:
  app-network:
    external: true
```

---

## Development Template (Hot Reload)

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.dev
    ports:
      - "${PORT:-3000}:8000"
    volumes:
      - .:/app                    # Hot reload
      - /app/node_modules         # Preserve node_modules
    environment:
      - NODE_ENV=development
      - DATABASE_URL=${DATABASE_URL}
      - LOG_LEVEL=debug
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network
    restart: unless-stopped

networks:
  app-network:
    external: true
```

---

## Full Stack Template (Frontend + Backend + DB)

```yaml
version: '3.8'

services:
  # Database layer
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=${DB_NAME:-app}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app-network
    restart: unless-stopped

  # Backend API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "${BACKEND_PORT:-3001}:8000"
    environment:
      - DATABASE_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/${DB_NAME:-app}
      - JWT_SECRET=${JWT_SECRET}
      - ALLOWED_ORIGINS=${FRONTEND_URL}
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network
    restart: unless-stopped

  # Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    environment:
      - VITE_API_URL=${BACKEND_URL}
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network
    restart: unless-stopped

networks:
  app-network:
    external: true

volumes:
  postgres-data:
```

---

## Microservices Template (Multi-Service)

```yaml
version: '3.8'

services:
  # Shared infrastructure
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=app
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "--auth", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app-network

  # Core service (Layer 2)
  auth-service:
    build:
      context: ./auth-service
      dockerfile: Dockerfile
    ports:
      - "${AUTH_PORT:-3001}:8000"
    environment:
      - DATABASE_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/app
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network

  # Business service (Layer 3)
  user-service:
    build:
      context: ./user-service
      dockerfile: Dockerfile
    ports:
      - "${USER_PORT:-3002}:8000"
    environment:
      - DATABASE_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/app
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
      - AUTH_SERVICE_URL=http://auth-service:8000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      auth-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network

  # API Gateway (Layer 4)
  api-gateway:
    build:
      context: ./api-gateway
      dockerfile: Dockerfile
    ports:
      - "${GATEWAY_PORT:-3000}:8000"
    environment:
      - AUTH_SERVICE_URL=http://auth-service:8000
      - USER_SERVICE_URL=http://user-service:8000
    depends_on:
      auth-service:
        condition: service_healthy
      user-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - app-network

networks:
  app-network:
    external: true

volumes:
  postgres-data:
```

---

## Security Best Practices

### 1. Never Expose Database Ports

```yaml
# BAD: Database accessible from internet
services:
  postgres:
    ports:
      - "5432:5432"  # DANGEROUS!

# GOOD: Internal only
services:
  postgres:
    # No ports section - internal only
    networks:
      - app-network
```

### 2. Use Environment Variables

```yaml
# BAD: Hardcoded secrets
environment:
  - POSTGRES_PASSWORD=mysecret123  # DANGEROUS!

# GOOD: From .env or secrets
environment:
  - POSTGRES_PASSWORD=${DB_PASSWORD}
```

### 3. Bind to Localhost Only (if exposed)

```yaml
# If you MUST expose a port, bind to localhost only
services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"  # Only accessible from host
```

---

## Health Check Patterns

### HTTP Endpoint

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

### PostgreSQL

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U app"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### Redis

```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 5

# With password
healthcheck:
  test: ["CMD", "redis-cli", "--auth", "${REDIS_PASSWORD}", "ping"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### MongoDB

```yaml
healthcheck:
  test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
  interval: 10s
  timeout: 5s
  retries: 5
```

---

## Dependency Management

### Sequential Startup

```yaml
services:
  backend:
    depends_on:
      postgres:
        condition: service_healthy  # Wait for postgres to be healthy
      redis:
        condition: service_started  # Just wait for redis to start
```

### Conditions

- `service_started`: Wait for container to start (default)
- `service_healthy`: Wait for health check to pass (recommended)
- `service_completed_successfully`: Wait for one-shot container to complete

---

## Volume Patterns

### Named Volumes (Persistent Data)

```yaml
services:
  postgres:
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:  # Persists across container restarts
```

### Bind Mounts (Development)

```yaml
services:
  app:
    volumes:
      - .:/app                  # Current directory -> /app
      - /app/node_modules       # Preserve node_modules
```

### Read-Only Volumes

```yaml
services:
  app:
    volumes:
      - ./config:/app/config:ro  # Read-only config
```

---

## Network Patterns

### External Network (Platform Standard)

```yaml
networks:
  app-network:
    external: true  # Created separately, shared across all services
```

### Internal Network (Project-Specific)

```yaml
networks:
  app-network:
    external: true

  project-internal:
    driver: bridge  # Internal to this project only

services:
  gateway:
    networks:
      - app-network   # External access
      - project-internal   # Internal routing

  backend:
    networks:
      - project-internal   # No direct external access
```

---

## Resource Limits (Production)

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
    restart: unless-stopped
```

---

## Logging Configuration

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

*Docker Compose templates for V10 projects*
