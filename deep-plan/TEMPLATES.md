# Deep Plan Templates

> Starter templates for all files generated during deep-plan scaffolding.
> Each template uses `{{variable}}` substitution.

## Template: spec-hypothesis.md

```markdown
# {{project_name}} V11 Spec

> Living operational document. Updated at every gate review.
> Execution protocol: `docs/GATE_PROTOCOL.md` | Skills: `/{{project_slug}}-gate`, `/athenaeum`

## Intent

{{intent_description}}

**This is a research project.** Success is validated learning, not shipped code.

## Core Hypothesis

**"{{core_hypothesis}}"**

| # | Sub-Hypothesis | Validated By | Prior |
|---|---------------|-------------|-------|
| H1 | {{h1}} | Gate {{g1}} | {{p1}} |
| H2 | {{h2}} | Gate {{g2}} | {{p2}} |

**P(all) = {{joint_prior}}**

## Architecture Decisions

| Decision | Choice | Rationale | Locked? |
|----------|--------|-----------|---------|
| {{decision_rows}} |

## V11 Integration

| V11 Concept | Usage |
|-------------|-------|
| Tasks | Source of truth. TaskCreate before starting, TaskUpdate on completion. |
| Agent Teams | For coordinated 3+ agent work. Background agents for independent tasks. |
| Autonomy | Level 2 for early phases. Level 3 after Gate {{trust_gate}}. |
| Hooks | PostToolUse on code changes. PreToolUse on cloud/external operations. |

## Agents

| Role | Agent | Owns | Formation Role |
|------|-------|------|--------------------|
| {{agent_rows}} |

---

## Phase 0: Validate or Kill

> **Cynefin: Complex** | **Approach:** Probe → Sense → Respond

### What This Phase Answers
| Question | How | Kill Condition |
| {{phase0_questions}} |

### Constraint
**{{phase0_constraint}}**

### Bayesian Decision Matrix
[Generated from sub-hypotheses]

### Gate 0: Go/No-Go
| Criterion | Target | Measured |
| {{gate0_criteria}} |

---

[Phases 1-N generated from project requirements]

---

## Belief Tracker

| Belief | Prior | After G0 | After G1 | ... |
|--------|-------|----------|----------|-----|
| {{belief_rows}} |

## Constraint Map

| Phase | Constraint | Exploit | Subordinate |
| {{constraint_rows}} |

## Risk Register

| # | Risk | Impact | P | Gate | Mitigation |
| {{risk_rows}} |

## Research Library

Athenaeum library `{{library_slug}}` (ID: {{library_id}}). {{doc_count}} documents.
```

## Template: CLAUDE.md (Orchestrator)

```markdown
# {{project_name}}: {{tagline}}

> {{one_line_description}}

## Claude's Role: PM + Orchestrator

You coordinate {{agent_count}} custom subagents, manage gate transitions via structured protocol,
and delegate work using problem-solving frameworks. You plan, decompose, delegate, review, decide.

## Quick Reference

\`\`\`bash
source ~/.secrets/{{project_slug}}.env
docker compose up -d
{{build_command}}
{{test_command}}
\`\`\`

## Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/{{project_slug}}-gate start <phase>` | Phase start | 6-step protocol |
| `/{{project_slug}}-gate review <gate>` | Gate decision | Bias audit + decision |
| `/athenaeum` | Research | Programmatic research missions |

## Subagents

| Agent | Domain | Owns |
|-------|--------|------|
| {{agent_rows}} |

## Gates

| Gate | Phase | Criterion | Status |
| {{gate_rows}} |

## Athenaeum

| Property | Value |
|----------|-------|
| Library ID | {{library_id}} |
| Slug | `{{library_slug}}` |
| Documents | {{doc_count}} |

**ALL access programmatic. NEVER use /chat endpoint.**

\`\`\`bash
curl -s "http://localhost:3000/api/libraries/{{library_id}}/search?q=QUERY&mode=hybrid&limit=10" | jq '.results[] | {doc: .document_title, text: .text}'
\`\`\`

## Critical Rules

### MUST
- Load secrets before docker
- Read files before editing
- Run `/{{project_slug}}-gate start` before beginning any phase
- Use Athenaeum programmatically only
- Delegate domain work to owning subagent

### NEVER
- Use Athenaeum chat endpoint
- Commit secrets
- Code directly when a subagent should own the work
- Skip gate review before proceeding
```

## Template: .claude/settings.json

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'FILE=\"$CLAUDE_FILE_PATH\"; EXT=\"${FILE##*.}\"; if [[ \"$EXT\" == \"rs\" || \"$EXT\" == \"ts\" || \"$EXT\" == \"py\" ]]; then echo \"[{{project_slug}}] Source modified: $FILE\"; fi'"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'if echo \"$CLAUDE_TOOL_INPUT\" | grep -qiE \"lambda|ssh.*cloud|aws|gcloud\"; then echo \"BLOCKED: Cloud operation — get approval\" >&2; exit 2; fi'"
          }
        ]
      }
    ]
  },
  "permissions": {
    "allow": [
      "Bash({{build_tool}} *)",
      "Bash({{test_tool}} *)",
      "Bash(docker compose*)",
      "Bash(curl*localhost*)",
      "Bash(git *)",
      "Bash(ls *)",
      "Bash(wc *)",
      "Bash(jq *)"
    ]
  }
}
```

## Template: .claude/commands/project-gate.md

See `<project-root>/example-project/.claude/commands/example-project-gate.md` — replace `example-project` with project slug, library ID 113 with project library ID.

## Template: .claude/commands/athenaeum.md

See `<project-root>/example-project/.claude/commands/athenaeum.md` — update library IDs and project context.

## Template: scripts/workspace.sh

See `<project-root>/example-project/scripts/example-project.sh` — replace project-specific references (library ID, build commands, test commands).

## Template: .claude/athenaeum.json

```json
{
  "athenaeum": {
    "pinned_libraries": ["{{library_slug}}"]
  }
}
```
