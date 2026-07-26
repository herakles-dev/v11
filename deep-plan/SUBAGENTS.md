# Custom Subagent Creation Patterns

> How to design, register, and coordinate project-specific agents for deep-plan projects.

## When to Create Custom Agents

| Signal | Action |
|--------|--------|
| 3+ files owned by one domain expert | Create dedicated agent |
| Technology requires deep expertise (CUDA, Neo4j, gRPC) | Create specialist agent |
| Work can be parallelized across domains | Create agents per domain |
| Security-critical code needs isolated review | Create security agent |

## Agent Design Process

### Step 1: Extract from VISION.md

Map each "persona" or "skill area" from the concept document to an agent:

```
VISION.md persona → Agent name → Domain → File ownership → V11 formation role
```

### Step 2: Define File Ownership

Every file in the project MUST have exactly one owning agent. No shared ownership.

```
Agent A owns: services/graph-engine/, services/data-pipeline/
Agent B owns: compute/rust-allocator/
Agent C owns: api/secure-bridge/
```

### Step 3: Write Agent Definition

```markdown
# ~/.claude/agents/{project}-{domain}.md
---
name: {project}-{domain}
description: "{One-line domain expertise}"
model: sonnet
---

You are a specialist in [DOMAIN] for the [PROJECT] project.

## Expertise
- [Specific skill 1]
- [Specific skill 2]
- [Specific skill 3]

## File Ownership
- `path/to/owned/directory/`

## Key Research
- Read `research/NN-topic.md` for context on [TECHNOLOGY]
- Athenaeum search: `curl -s "http://localhost:3000/api/libraries/ID/search?q=QUERY" | jq '.results[].text'`

## Constraints
- Always use `--features mock` for local development
- Never modify files outside your ownership
- Report measurements back to orchestrator for Bayesian updates

## V11 Formation Role
- Formation: {formation-name}
- Role: implementer | security-reviewer | tester | architect
```

### Step 4: Register in Agent Registry

```bash
# Add to ~/.agent-registry/agents.json
jq '.agents += [{"name": "project-domain", "type": "custom", "project": "project-name"}]' \
  ~/.agent-registry/agents.json > tmp && mv tmp ~/.agent-registry/agents.json
```

## Agent Count Guidelines

| Project Complexity | Agents | Rationale |
|-------------------|--------|-----------|
| Single-stack (web app) | 2-3 | Frontend, backend, database |
| Multi-stack (Rust + Python + GPU) | 4-6 | One per technology domain |
| Research-heavy (novel architecture) | 6-8 | Domains + security + RE |
| Platform (many services) | 8-12 | One per service cluster |

## Agent Coordination Patterns

### Pattern 1: Schema-First Coordination
When agents share data structures:
```
1. Orchestrator defines shared schema (proto, Arrow, types)
2. ALL agents implement to the schema
3. No agent modifies the schema without orchestrator approval
```

### Pattern 2: Consumer-First Design
When one agent produces what another consumes:
```
1. Consumer agent defines what it needs (input format, fields, types)
2. Producer agent builds to consumer's specification
3. Integration test validates the handoff
```

### Pattern 3: Constraint-Subordinate
When one agent is the bottleneck:
```
1. Identify bottleneck agent (most sequential work, highest risk)
2. Other agents build to the bottleneck's interface
3. Other agents WAIT rather than pile up un-integrated work
4. Bottleneck agent is never blocked on dependencies
```

## Reference Project Example (6 Agents)

| Agent | Domain | Why Separate? |
|-------|--------|--------------|
| example-project-hpc | Rust + CUDA + memory | Deep systems expertise, dangerous FFI code |
| example-project-ai | Mamba-2 + inference + ggml | ML model expertise, Python/C++ ecosystem |
| example-project-graph | Neo4j + Arrow + Leiden | Data pipeline, graph algorithms |
| example-project-swarm | Formations + orchestration | Multi-agent systems, scheduling |
| example-project-security | Crypto + kill switches | Security isolation, code review |
| example-project-bridge | gRPC + networking | Transport layer, streaming |

Each agent has non-overlapping file ownership and distinct technology expertise.
