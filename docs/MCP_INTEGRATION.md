# MCP Integration — Detailed Reference

> Extracted from V11 CLAUDE.md Section 15. For the tool summary table, see CLAUDE.md.

---

## Usage Examples

**Service Discovery**:
```json
{
  "tool": "platform_port_registry_query",
  "args": {
    "query_type": "by_service",
    "value": "ice-rights-api"
  }
}
```

**Check Observability Health**:
```json
{
  "tool": "platform_observability_status",
  "args": {
    "component": "all",
    "include_coverage": true
  }
}
```

**Query Recent Errors**:
```json
{
  "tool": "platform_query_logs",
  "args": {
    "service": "ice-rights-api",
    "level": "error",
    "since": "1h",
    "limit": 50
  }
}
```

**Safe Deployment with Dry Run**:
```json
{
  "tool": "platform_deployment_trigger",
  "args": {
    "operation": "restart",
    "service": "moody-time-machine",
    "options": {
      "dry_run": true
    }
  }
}
```

---

## When to Use MCP vs Scripts

| Scenario | Use MCP | Use Scripts |
|----------|---------|-------------|
| Agent workflows | Yes | No |
| Service discovery | Yes | Either |
| Log analysis | Yes | Either |
| Manual ops | No | Yes |
| Performance critical | No | Yes |

---

## Authorization

- **READ tools** (registry, status, logs, metrics): No approval required
- **ACTION tools** (deployment_trigger):
  - Development environment: Auto-approved
  - Production environment: Requires user approval (MEDIUM risk)
  - Dry run: Always safe, no approval needed

---

## Primary Consumers

Agents that should prefer MCP tools:
- `monitoring-specialist` (observability_status, query_logs, get_metrics)
- `log-analyst` (query_logs, observability_status)
- `ci-cd-architect` (deployment_trigger, port_registry_query)
- `system-apps-manager` (all tools for health monitoring)
- Team Leads (all tools for orchestration)

---

## Configuration

MCP server configured in `~/.config/.mcp.json`:
```json
{
  "mcpServers": {
    "platform-mcp": {
      "command": "node",
      "args": ["/path/to/.mcp-servers/platform-mcp/dist/index.js"]
    }
  }
}
```

**Source**: `/path/to/.mcp-servers/platform-mcp/`
