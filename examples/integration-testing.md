# Example: Integration Testing & Docker Patterns

> Complete example showing spec-integrator-v10 multi-service setup with docker-compose patterns.

---

## Scenario

Task: "Configure docker-compose for auth-service, user-service, and api-gateway with proper networking and health checks"

---

## Step 1: Service Discovery

```bash
# Check the port registry for available ports
jq '.allocations' ~/config/port-registry.json

# Check active containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check app-network
docker network inspect app-network | jq '.[].Containers | keys'
```

---

## Step 2: Checkpoint 1 - Integration Plan

```markdown
## INTEGRATION PLAN

### Task: Configure multi-service docker-compose

### Services Involved
| Service | Role | Port | Network |
|---------|------|------|---------|
| api-gateway | Entry point, routing | 3000 | app-network |
| auth-service | Authentication | 3001 | app-network |
| user-service | User management | 3002 | app-network |
| postgres | Shared database | internal | app-network |
| redis | Session storage | internal | app-network |

### Integration Points
1. api-gateway -> auth-service (JWT validation)
2. api-gateway -> user-service (user CRUD)
3. user-service -> auth-service (token refresh)
4. All services -> postgres (data persistence)
5. All services -> redis (caching)

### Changes Required
| File | Action | Description |
|------|--------|-------------|
| docker-compose.yml | Create | Multi-service orchestration |
| nginx/project.conf | Create | Reverse proxy configuration |
| .env.example | Create | Environment variable template |

### Health Check Strategy
- All services: `/health` endpoint (liveness)
- All services: `/health/ready` endpoint (readiness with dependency checks)
- Docker healthcheck configured for all services
- Proper dependency ordering via `depends_on` with conditions

PROCEED WITH INTEGRATION?
```

---

## Step 3: Docker Compose Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Layer 1: Databases (no dependencies)
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
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app-network

  # Layer 2: Core service (auth)
  auth-service:
    build:
      context: ./auth-service
      dockerfile: Dockerfile
    ports:
      - "3001:8000"
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

  # Layer 3: Business service (depends on auth)
  user-service:
    build:
      context: ./user-service
      dockerfile: Dockerfile
    ports:
      - "3002:8000"
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

  # Layer 4: Gateway (depends on all)
  api-gateway:
    build:
      context: ./api-gateway
      dockerfile: Dockerfile
    ports:
      - "3000:8000"
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

## Step 4: Service Health Endpoints

### Python (FastAPI) Pattern

```python
# health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from redis import Redis
import httpx

router = APIRouter()

@router.get("/health")
async def health():
    """Basic liveness check"""
    return {"status": "healthy", "service": "auth-service"}

@router.get("/health/ready")
async def readiness(
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    """Full readiness check with dependencies"""
    checks = {}

    # Database check
    try:
        db.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"

    # Redis check
    try:
        redis.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"

    # Upstream service check (for user-service checking auth-service)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://auth-service:8000/health", timeout=5)
            checks["auth_service"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception as e:
        checks["auth_service"] = f"unhealthy: {str(e)}"

    all_healthy = all(v == "healthy" for v in checks.values())

    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks
    }
```

---

## Step 5: Nginx Reverse Proxy

```nginx
# nginx/project.conf
upstream api_gateway {
    server 127.0.0.1:3000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name myproject.example.com;

    ssl_certificate /etc/letsencrypt/live/myproject.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myproject.example.com/privkey.pem;

    # API routes
    location /api/ {
        proxy_pass http://api_gateway/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint (for monitoring)
    location /health {
        proxy_pass http://api_gateway/health;
        access_log off;
    }
}
```

---

## Step 6: Verification

### Start Services

```bash
# Load environment variables
source ~/.secrets/app.env

# Start all services
docker-compose up -d

# Watch logs
docker-compose logs -f
```

### Verify Connectivity

```bash
# Check all services are healthy
docker ps --format "table {{.Names}}\t{{.Status}}"

# Test inter-service connectivity
docker exec api-gateway curl -sf http://auth-service:8000/health
docker exec api-gateway curl -sf http://user-service:8000/health

# Test readiness checks
curl -sf http://localhost:3000/health/ready | jq .
curl -sf http://localhost:3001/health/ready | jq .
curl -sf http://localhost:3002/health/ready | jq .
```

---

## Step 7: Checkpoint 2 - Integration Complete

```markdown
## INTEGRATION COMPLETE

### Task: Configure multi-service docker-compose

### Services Configured
- api-gateway: 3000 ✓
- auth-service: 3001 ✓
- user-service: 3002 ✓
- postgres: internal ✓
- redis: internal ✓

### Connectivity Verified
| From | To | Status |
|------|----|--------|
| api-gateway | auth-service | ✓ verified |
| api-gateway | user-service | ✓ verified |
| user-service | auth-service | ✓ verified |
| auth-service | postgres | ✓ verified |
| auth-service | redis | ✓ verified |

### Health Checks
- All services: healthy ✓
- Dependencies: connected ✓
- Network: app-network ✓

### Files Created
- docker-compose.yml (120 lines)
- nginx/project.conf (35 lines)
- .env.example (8 lines)

### Startup Order Verified
1. postgres + redis (healthy in 5s)
2. auth-service (healthy in 8s)
3. user-service (healthy in 10s)
4. api-gateway (healthy in 12s)

HANDOFF: spec-tester-v10 for L3 integration tests
```

---

## Handoff Format

```json
{
  "agent": "spec-integrator-v10",
  "version": "9.0.0",
  "status": "completed",
  "task_id": "task-06",

  "integration": {
    "services_configured": 5,
    "networks": ["app-network"],
    "ports_allocated": [3000, 3001, 3002],
    "health_checks": "all_passing"
  },

  "connectivity": {
    "verified_connections": 5,
    "failed_connections": 0,
    "startup_time_seconds": 12
  },

  "files": {
    "created": ["docker-compose.yml", "nginx/project.conf", ".env.example"],
    "modified": []
  },

  "next": {
    "agent": "spec-tester-v10",
    "action": "Run L3 integration tests",
    "focus": "Service-to-service communication, health checks, error handling"
  },

  "metrics": {
    "services_integrated": 5,
    "health_checks_added": 5,
    "duration_seconds": 600
  }
}
```

---

## Troubleshooting Patterns

### Container Can't Reach Another Container

```bash
# Check network membership
docker network inspect app-network | jq '.[].Containers'

# Test DNS resolution
docker exec api-gateway nslookup auth-service

# Test connectivity
docker exec api-gateway curl -v http://auth-service:8000/health
```

### Port Conflict

```bash
# Check what's using the port
lsof -i :3001
netstat -tlnp | grep 3001

# Find available port
jq '.metadata.port_ranges' ~/config/port-registry.json
```

### Health Check Failing

```bash
# Check container logs
docker logs auth-service --tail 50

# Check health check command
docker inspect auth-service | jq '.[].State.Health'

# Run health check manually
docker exec auth-service curl -f http://localhost:8000/health
```

---

*Example from spec-integrator-v10 documentation*
