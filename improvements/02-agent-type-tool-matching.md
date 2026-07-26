# V11 Improvement 02 — Match agent type to required tool surface, not to description

**Author:** orchestrator (sofly session 2026-06-22)
**Severity:** MEDIUM — burned 4 agent spawns this session; partial recovery cost ~3k tokens of orchestrator context
**Scope:** `playbooks/orchestrate.md`, `playbooks/context-tiered-mode.md`, the agent registry, this skill's spawn templates

---

## Problem

I spawned 4 background `subagent_type=Explore` agents to research Reddit communities. Each was told to **Write a JSON report to disk**. Three of the four failed at the Write step because `Explore` agents have a restricted tool surface: `All tools except Agent, ExitPlanMode, Edit, Write, NotebookEdit`.

The mismatch:

- **My choice:** "Explore" — chosen because the work was *exploratory* (research, no code edits).
- **What the prompt actually required:** Web fetch + structured JSON file output.
- **What "Explore" is for per its description:** "Locating code. Find files by pattern, grep for symbols. Do NOT use it for code review, design-doc auditing, cross-file consistency checks, or open-ended analysis."

Reddit research is "open-ended analysis" — explicitly NOT what Explore is for. I picked it on the vibe of the word, not the contract.

## Evidence observed this session

1. Cluster A agent: produced inline domain synthesis (~250 words) but could not Write the JSON. Orchestrator captured manually to disk.
2. Cluster B agent: same — produced inline synthesis, no Write.
3. Cluster C agent: refused outright, returned "I'm in read-only mode and cannot create files… Would you like me to A/B/C?" — bounced the work back to orchestrator.
4. Cluster D agent: Write succeeded (because the agent disregarded the implicit constraint and tried anyway — but D's spawn was the same `subagent_type`).

Three of four returned partial output. The fourth succeeded only because the agent ignored the constraint. That's not a tool-surface guarantee; it's luck.

## Root cause

The orchestrator's mental model is "pick agent by topic." The harness's contract is "agent type defines tool surface." These don't align.

`playbooks/orchestrate.md` says "delegate to Explore for research" but doesn't say "Explore CANNOT WRITE." `playbooks/context-tiered-mode.md` says "Haiku Explore swarms for locate/count/verify/list/extract" — the *list of verbs* doesn't include "write a report."

## Proposed change

### A. Add a "required tools" axis to spawn-template selection

Every Agent() call in this skill's playbooks should specify both:
1. The TOPIC (what's the work about)
2. The REQUIRED TOOL SURFACE (what tools must succeed: Read+WebFetch only? Read+Write? Read+Bash+Edit?)

Then the agent-type recommendation matrix becomes:

| Required surface | Topic = research/explore | Topic = build/edit |
|---|---|---|
| Read-only (return inline) | `Explore` | n/a |
| Read + Write to disk | `general-purpose` | `general-purpose` or specialist |
| Read + Bash + Edit | `general-purpose` or specialist | specialist by domain |

### B. Embed this in the spawn-template helpers

`playbooks/context-tiered-mode.md` has a `PINPOINT_PROMPT` template that goes to Explore agents. Add a second template `WRITE_PINPOINT_PROMPT` for cases where the agent must write a deliverable to disk. The second template defaults to `subagent_type=general-purpose` and pins the expected output path.

### C. Validation at spawn time

The orchestrator skill could check: if the prompt body contains "Write your full report to:" AND `subagent_type=Explore`, refuse the spawn with a clear error: "Explore lacks Write; use general-purpose or specify return-inline."

This is a 10-line check in the orchestrator's spawn helper. Cheap.

### D. Update agent-registry descriptions

The `Explore` agent description says: "Use it to find files by pattern... grep for symbols or keywords." Add explicitly: **"This agent CANNOT write files. If your task needs disk output, use general-purpose."**

Same for any other read-only specialist (`code-reviewer`, `adversarial-*`, `coherence-reviewer` — all have `Tools: All tools except Write, Edit, Bash`).

## Risk

- **None at the protocol level** — this is documentation + a validator. No behavior change unless the orchestrator hits the new check.
- **Specialist agents with intentionally read-only surfaces** — must not regress. The fix is *clearer signaling*, not granting Write to read-only agents.

## Rollback

Pure documentation + an optional spawn-time check. Revert is one commit.

## Acceptance test

A fresh `/v11` session spawning an Explore agent with a "Write your report to X" prompt should either:
- Hit the validator and rewrite the prompt before spawning, OR
- Surface a clear warning in the result that the spawn was likely mis-typed.

```bash
# Manual test: this should warn or refuse
echo "Spawn Explore with Write requirement" | v11-spawn-check
# Expected: "WARN: Explore lacks Write tool. Switch to general-purpose? [Y/n]"
```

## Why this matters

The user said "before you assign an agent — think and assess. make sure it has everything it needs in its context." I assessed the *topic* but not the *tool surface*. The agent-registry's description should make that surface impossible to miss, and the playbooks should pair agent-type with required-tools at the spawn template level. Otherwise this kind of miss will recur every time the orchestrator picks an agent by vibe.
