# V11 Deep Plan: Massive Project Scaffolding Framework

> **Codename:** Deep Plan — "The Forge"
> **Purpose:** Turn vague ideas into production-ready, deeply-planned research/engineering projects
> **Origin:** Extracted from the the reference project's project build (2026-03-17), where a concept document
> became a 46-file, 19-Athenaeum-doc, 9-gate, hypothesis-driven operational system in one session.

## What This Is

A V11 upgrade proposal and reusable framework for scaffolding massive projects that require:
- Deep technical research before implementation
- Multi-agent coordination across 3+ custom agents
- Hypothesis validation before infrastructure investment
- Gate-based decision-making with structured problem-solving
- Athenaeum integration for persistent research knowledge
- Dynamic workspace switching (research ↔ development ↔ debugging)

## When to Use Deep Plan

| Situation | Use Deep Plan? | Instead Use |
|-----------|---------------|-------------|
| 5+ unsolved research questions | **Yes** | — |
| 3+ custom agents needed | **Yes** | — |
| Joint probability of success < 50% | **Yes** | — |
| Project spans research → implementation | **Yes** | — |
| Known tech, clear requirements | No | Standard `/v11-scaffold` |
| Single-service feature | No | `/scaffold` |
| Bug fix or refactor | No | Direct work |

## Files in This Directory

| File | Purpose |
|------|---------|
| `README.md` | This file — overview and when to use |
| `METHODOLOGY.md` | The complete 7-phase methodology (the "how") |
| `SKILLS.md` | New skills to add to V11 for deep-plan support |
| `SUBAGENTS.md` | Custom agent creation patterns |
| `ATHENAEUM_PROTOCOL.md` | Research library integration patterns |
| `GATE_FRAMEWORK.md` | Problem-solving framework for gate decisions |
| `TEMPLATES.md` | Templates for spec.md, CLAUDE.md, scripts, commands |
| `UPGRADE_SPEC.md` | V11 upgrade specification (tasks, gates, risks) |

## Quick Start

```bash
# When ready to implement as V11 upgrade:
cat /path/to/v11/deep-plan/UPGRADE_SPEC.md

# To use the methodology on a new project now (before V11 upgrade):
cat /path/to/v11/deep-plan/METHODOLOGY.md
```
