# V11 Improvement 05 — The orchestrator skill prompt preaches context discipline; it should practice it

**Author:** orchestrator (sofly session 2026-06-22)
**Severity:** MEDIUM — the meta-violation that undermines every other context rule
**Scope:** `~/.claude/skills/team-orchestrator/SKILL.md` (and its playbooks)

---

## Problem

The orchestrator skill prompt — what loads into the model when the user types `/v11` or `/team-orchestrator` — is ~40-50KB of decision tree + situation playbook + behavior rules + agent list + skill list + version metadata. The text *explicitly* says:

> **Hard rule:** the orchestrator NEVER reads more than 2 content-heavy files directly. Multi-file question = Haiku swarm, always.

And:

> **Context discipline (priority — overrides Execution defaults)**:
> 13. Tier work by model
> 14. Never read >2 content-heavy files directly
> 15. Pinpoint schema mandatory

Yet the skill prompt itself is one big "content-heavy file" that the model reads on every invocation. The first sentence the user types lands in a model already carrying ~40KB of skill content + the registered tool definitions + the full agent list (97 agents) + the full skill list (~150 skills). The orchestrator preaches dieting and arrives carrying lunch.

## Evidence observed this session

- Skill prompt content loaded on `/team-orchestrator` invocation: **~45KB** (Decision Router + Subcommand Router + Situation Playbook + Phase 1-6 + Behavior Rules + Reference Playbooks table + Integration table + version metadata).
- Agent list loaded as a system reminder: **~38KB** for the full 97-agent block.
- Skill list loaded as a system reminder: **~12KB** for ~150 skills.
- Project CLAUDE.md (platform root + sofly): **~6KB**.
- MEMORY.md auto-loaded: **~1KB**.

**Before the user's first character of intent reaches the model: ~100KB of contextualizing material already present.** Each subsequent tool result + agent transcript stacks on top.

The skill's own context-tiered rule ("NEVER read >2 content-heavy files directly") cannot be true; the skill itself is content-heavy file #1, the agent registry is #2, and we're already at the budget before doing any work.

## Root cause

The skill grew by accretion. V11.15 added per-task review. V11.17 added auto-rehydrate. V11.19 added review-queue drainage. V11.20 added attribution honesty. V11.21 added dual-layer review + DAAO routing. Each landed as new paragraphs in the same `SKILL.md`. Nothing is ever subtracted.

Playbooks were introduced to be "loaded on demand" but the skill prompt still inlines:
- A 30-line Subcommand Router table that lists every subcommand
- A 25-line Situation Playbook with every "if user says X, do Y" hint
- All the V11.21 rollback levers and acceptance criteria
- 18 numbered Behavior Rules

Each entry made sense individually. The aggregate is bloated.

## Proposed change

### A. Aggressive playbook extraction

Move out of `SKILL.md` into existing `playbooks/`:
- The full Subcommand Router → `playbooks/subcommand-router.md`. Replace inline with: "All subcommand routing: `playbooks/subcommand-router.md`."
- The full Situation Playbook → `playbooks/situations.md`. Same treatment.
- All V11.21 mid-session troubleshooting hints → `playbooks/v11-21-routing.md`.

### B. Keep in `SKILL.md` only the always-on core

Should remain inline (≤8KB total):
1. Triggers table (1 row per trigger)
2. The 4-line "Default Mode — Context-Tiered Operation" reminder + a pointer to the playbook
3. Decision Router (the tree)
4. The 18 Behavior Rules (these are the actual contract)
5. Reference Playbooks table (the index — already exists; keep)
6. One-line "Integration" table
7. Version footer

Everything else loads on demand via the existing `playbooks/` mechanism.

### C. Version metadata as a footer, not a banner

Currently versions are scattered throughout ("V11.21 Phase 4 sequence," "V11.21 Routing & Review Protocol," etc.). Consolidate to a single footer paragraph: "Current version: 11.21. New since 11.20: dual-layer review, DAAO routing. Migration: `/v11 update PROJECT`. Rollback levers: `V11_AUTO_PAIR_REVIEW=off`, `V11_SELF_REVIEW_REQUIRED=off`, etc."

Everything version-specific that the orchestrator might need MID-session goes into `playbooks/v11-21-routing.md` and is loaded only when the orchestrator is making a V11.21-specific decision.

### D. Pre-flight context cost reporter

Add to the DETECT phase a single line:

```
Context budget: skill 8.2k + agents 38k + skills 12k + project 6k = 64.2k loaded before work begins
```

This is honest and prompts the team to keep the loaded baseline visible.

## Risk

- **Dropping content the orchestrator silently relied on** — must audit which Situation Playbook entries get triggered in practice (grep the transcripts) before removing.
- **First-time users hit a thinner prompt and miss subcommands** — mitigated by the Reference Playbooks index staying inline, plus `/v11 help` printing the full Triggers + Subcommand Router on demand (already a trigger).

## Rollback

Pure refactor. `git revert` on the extraction commit restores the prior monolith.

## Acceptance test

```bash
# After extraction:
$ wc -c ~/.claude/skills/team-orchestrator/SKILL.md
# Expected: <8500 bytes (~8KB)

# A fresh /v11 invocation should still resolve all current triggers, just with one extra
# playbook load when the situation actually fires.
$ /v11 dark-code-check sofly   # subcommand defined ONLY in playbooks/subcommand-router.md
# Expected: resolves correctly, with one extra Read in the trace
```

## Why this matters

The orchestrator's most-quoted rule is "never read >2 content-heavy files." The skill enforces this on others; the skill itself is the largest content-heavy file in the chain. If the skill is allowed to ignore the rule because it's "the skill," every new contributor reads that as "the rules are for the agents you spawn, not for you." That's the wrong lesson. The orchestrator should be the leanest thing in the conversation, not the heaviest.
