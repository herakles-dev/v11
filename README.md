# V11 Protocol

V11 is a governance/discipline layer for multi-agent Claude Code work. It doesn't
write code for you and it isn't a new agent framework — it's the guardrails
around whatever agents you already use: a durable task ledger, hooks that
block risky writes without an authorized task, autonomy tracking that
escalates trust as an agent proves itself, session handoff so context survives
a compaction or a restart, and an adversarial-review loop that checks
completed work before the next task builds on it.

Core idea: **tasks are the single source of truth**. Everything else in this
distribution — write gates, autonomy levels, review queues, handoff — hangs
off the same task-state records.

This is a real, in-use protocol extracted from its host project, not a demo.
It has not been used outside that one deployment before this release, so
treat it as a serious starting point rather than a finished product for every
environment — see **Known limitations** below before you install it somewhere
that matters.

## What's actually in the box

Six mechanisms make up the required loop; everything else in this repo is
optional support around them:

1. **Task system** — `TaskCreate`/`TaskUpdate`/`TaskList` are Claude Code's
   built-in task tools; V11 hooks react to them, they aren't reimplemented
   here.
2. **Write gates** — `guard-write-gates` blocks `Write`/`Edit` when there's no
   in-progress task backing the change.
3. **Task sync** — `sync-tasks` mirrors every task-tool call into on-disk
   state (`task-state.json`, a durable ledger, and the review queue).
4. **Autonomy tracking** — `track-autonomy` + `guard-enforcement` classify
   risk (low/medium/high) per operation and escalate/require approval based
   on a persisted trust level (A0 Manual → A5 Self-Organizing).
5. **Handoff** — `session-end` + `scripts/handoff` snapshot session state
   (open tasks, recent decisions, next steps) so a new session can resume
   instead of re-deriving context.
6. **Review loop** — `task-review` / `review-queue` / `review-daemon` dispatch
   a read-only adversarial-review agent (`agents/adversarial-lite-reviewer.md`
   etc.) against completed work and attribute findings back to the agent that
   produced them.

Everything else — memory indexing, formations (multi-agent topologies),
benchmarking, a full spec-driven-dev agent suite, coding-pattern docs — is
genuinely useful but the six mechanisms above run without it.

## CORE vs OPTIONAL

This distribution ships both tiers so you can see the whole picture, but they
answer different questions:

- **CORE** — required for the six mechanisms above to function at all. If you
  deleted everything CORE except one file, something in the loop would break.
- **OPTIONAL** — real, working features (scorecards, memory search, formation
  recommenders, a benchmark harness, a 9-agent spec-driven-dev pipeline...)
  that layer on top of CORE but aren't load-bearing for it.

`MANIFEST.md` in this directory is the authoritative, file-by-file partition
this distribution was built from — every asset in the upstream project,
bucketed CORE / OPTIONAL / EXCLUDE with a one-line justification each, plus
the exact weld (hardcoded path) fixed for every CORE row that needed it. If
you're deciding what to trim for your own fork, start there, not here.

What got left out entirely (EXCLUDE, not copied into this distribution):
dead/superseded hooks (documented as broken or replaced in the upstream
project's own changelog), one-shot historical migration scripts, a
production-deploy/DNS/nginx toolchain wired to the origin deployment's own
infrastructure, and generated run artifacts (test reports, benchmark
history). None of that is required to run V11 somewhere else.

## Quickstart

```bash
./install.sh /path/to/your/project
# or, from inside the project:
cd /path/to/your/project && /path/to/v11-dist/install.sh
```

The installer is idempotent — re-run it any time; it only adds what's
missing and never duplicates hook entries or clobbers existing state. It
requires `bash` and `jq`. What it does:

1. Copies the framework payload (`hooks/`, `schemas/`, `scripts/`, `agents/`,
   `playbooks/`, `templates/`, `formations/`, `patterns/`, `mcp-tools/`,
   `docs/`) into `<project>/.v11/` — a self-contained copy; the project no
   longer depends on this distribution directory after install.
2. Merges (never overwrites) the hook registrations into
   `<project>/.claude/settings.json`.
3. Bootstraps session-tracking state: a project-name pointer, a per-project
   session directory with a starter `spec.md`, and an initial
   `.autonomy-state` at A0 (Manual).
4. Prints a summary and next steps.

Session/task state defaults to `$HOME/.v11` (override by exporting
`V11_WORKSPACE_ROOT` before running Claude Code or the installer) — this is a
deliberate central location shared across every V11 project on one machine,
mirroring the upstream architecture, not a directory inside your project.

**Important**: Claude Code reads `.claude/settings.json` once at session
boot. If you run the installer while a session is already open in that
project, restart the session to pick up the hooks.

## Known limitations

- **Single-deployment provenance.** This protocol was extracted from one
  server that had been running it for months; the CORE welds that assumed
  a single hardcoded operator home directory have been parameterized to
  portable defaults (`$HOME/.v11`), and the install/verify steps below
  confirm the loop runs end-to-end on a throwaway project — but it has not
  yet been run against a second, independent environment. Expect rough
  edges.
- **Residual references, post-scrub.** An earlier pass found ~172 hits of a
  hardcoded operator path or the origin's own domain across just `hooks/` +
  `scripts/`; a full scrub across every shipped file (including dropping
  `tests/` entirely, the largest single source of the debris) has since
  brought that down to 15 residual hits tree-wide, all reviewed and judged
  non-identifying: a generic `port_registry`-style variable/key name reused
  in a few places, and `localhost:8000` inside Docker `HEALTHCHECK` lines in
  two generic docker-compose example templates (a container-internal port
  check, not a real host-exposed address). `MANIFEST.md` documents the fixes
  applied file-by-file; none are hidden.
- **No invented benchmarks.** This README doesn't quote test-pass rates,
  performance numbers, or adoption metrics for this distribution, because
  none have been measured for it. `benchmarks/` is shipped as OPTIONAL
  tooling you can run yourself, not as a claim. The framework's full test
  suite runs in the development environment; see the project's EVIDENCE.md
  for recorded results.

## Hook index (`hooks/`)

Every hook this distribution ships. CORE hooks are load-bearing for the six
mechanisms above; OPTIONAL hooks are advisory/QoL and never block anything
CORE needs.

| Hook | Tier | What it does |
|---|---|---|
| `detect-project` | CORE | Resolves which project a Read/Bash/session belongs to; every other hook keys off this. |
| `guard-write-gates` | CORE | Blocks `Write`/`Edit` when there's no in-progress task authorizing the change. |
| `guard-enforcement` | CORE | Classifies operation risk (low/medium/high) and enforces/escalates against the persisted autonomy level. |
| `sync-tasks` | CORE | Mirrors every `TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet` call into on-disk task-state, the durable ledger, and the review queue. |
| `track-autonomy` | CORE | Records every Write/Edit/Bash outcome to the audit trail and adjusts the autonomy trust level. |
| `session-end` | CORE | `Stop` hook — saves a session summary and triggers handoff for the next session. |
| `commit-msg-validation` | OPTIONAL | Lints `git commit` messages for a `Validation:` tag (empirical-rigor discipline). |
| `completion-hint` | OPTIONAL | Advisory nudge to mark a task completed after a matching edit; never blocks. |
| `enforce-test-coverage` | OPTIONAL | Blocks deploy-shaped commands under a configurable test-coverage threshold. |
| `guard-agent-stall` | OPTIONAL | Flags a background agent that looks stalled. |
| `guard-effort` | OPTIONAL | Suggests an effort level when dispatching a `Task`/`Agent`. |
| `guard-stale-task` | OPTIONAL | Flags an in-progress task that looks abandoned (zombie-task detector). |
| `guard-validation-lint` | OPTIONAL | Bash-side companion to `commit-msg-validation`'s tag linter. |
| `post-commit-close-tasks` | OPTIONAL | Auto-closes tasks referenced by a commit subject (`TaskUpdate` already closes tasks without this). |
| `post-compact` | OPTIONAL | Re-injects V11 state after a context compaction. |
| `refresh-freshness-tags` | OPTIONAL | Opt-in doc-freshness stamping; mutates files, so it's off by default. |
| `require-producer-script` | OPTIONAL | Blocks commits that ship unverifiable validation artifacts. |
| `track-agents` | OPTIONAL | Logs per-agent metrics/escalations; feeds the (OPTIONAL) scorecard tooling. |
| `verify-syntax` | OPTIONAL | Post-write syntax check; advisory only, never blocks. |
| `git-hooks/commit-msg`, `git-hooks/post-commit` | OPTIONAL | The installed git-event copies `commit-msg-validation`/`post-commit-close-tasks` produce. |
| `lib/common.sh` | CORE | Shared constants + functions sourced by nearly every hook (project detection, task-state I/O, risk classification). |
| `lib/get-chicago-time.sh` | CORE | Business-timezone cache used by `detect-project`; timezone is `V11_BUSINESS_TZ` (default `America/Chicago`), not hardcoded. |
| `lib/validation_lint.py` | OPTIONAL | Validation-tag linter shared by `commit-msg-validation`/`guard-validation-lint`. |

Three hooks from the upstream project are **not** in this distribution at all
(see `MANIFEST.md`): `enforce-subagent` and `guard-teammate-timeout` are
documented in the origin project's own changelog as broken/superseded, and
`fix-team-model`'s own header says it's dead code kept only as a no-op safety
net. Shipping them would just be silent dead weight.

## CORE script index (`scripts/`)

This distribution ships 83 scripts total; the other 73 are OPTIONAL
(scorecards, memory indexing, formation tooling, a SWE-bench harness,
migration/repair utilities, etc.) — see `MANIFEST.md` for the full,
individually-justified list. The 10 CORE ones:

| Script | What it does |
|---|---|
| `audit-query` | CLI for the autonomy audit trail (per-task, per-agent, per-session queries). |
| `autonomy-grant` | Persists an explicit A4/A5 autonomy grant to `.autonomy-state` (auto-escalation only reaches A0→A3). |
| `drain-review-queue` | Orchestrator-side dispatch helper that drains the pending adversarial-review queue. |
| `handoff` | Generates the session-continuation snapshot (open tasks, recent decisions, next steps). |
| `ledger-verify` | Cold-path verdict-hash verification across the durable ledgers backing task sync and review. |
| `plan-sync` | Snapshots task/autonomy state into a Claude Code plan file (`~/.claude/plans/`) so it survives a context clear. |
| `review-daemon` | Headless, unattended consumer of the review queue. |
| `review-queue` | CLI for the per-project adversarial-review queue. |
| `task-review` | Builds the adversarial-review prompt for a single completed task. |
| `v11-bootstrap-session` | Seeds session state (active-project pointer, session dir, `.autonomy-state`, per-session task-state) when hooks weren't loaded at boot — this is what `install.sh` calls. |

## Also included (OPTIONAL, genuinely useful)

- **`agents/`** — the 4 review-loop agents (CORE — `task-review` dispatches
  them) plus a complete 9-agent spec-driven-development pipeline
  (planner → architect → implementer → integrator → optimizer → recovery →
  reviewer → security → tester) and its registry, useful as a template even
  though the CORE loop only needs the review-loop four.
- **`templates/`** — session/spec bootstrap templates (`spec.md`,
  `session-manifest.json`, `roadmap.md`, etc.) consumed by
  `v11-bootstrap-session`.
- **`schemas/`** — 19 JSON Schemas; 9 are CORE (task metadata, task state,
  autonomy state/audit, guard-blocks, session manifest, plan-context,
  review-config, agent-errors), 10 are OPTIONAL refinements (attribution,
  memory-index, formations, scorecards, tool-policy).
- **`docs/`** — reference docs for how the loop actually works
  (`ENFORCEMENT.md`, `HANDOFF_SMOOTH.md`, `STATE_MANAGEMENT.md`,
  `PROTOCOL_FUNDAMENTALS.md`, `CHANGELOG.md`, and others).
- **`playbooks/`** — `per-task-review.md`, the operational playbook the
  review loop follows.
- **`patterns/`** — generic coding-pattern references (TypeScript/Python
  standards, task-claiming discipline, a docker-compose template,
  performance-optimization notes).
- **`formations/`**, **`mcp-tools/`** — a sample multi-agent formation config
  and a memory-search MCP server.
- **`examples/`**, **`deep-plan/`** — walkthroughs and an advanced
  multi-week-sprint planning methodology, including a real case study.
- **`benchmarks/`**, **`improvements/`**, **`pm/`**, **`research/`** — the
  quality/benchmark harness, the project's own engineering retrospectives, a
  ledger-integrity design spec, and background research notes. (The source
  test suite is not part of this distribution; it runs in the development
  environment — see the project's EVIDENCE.md for recorded results.)

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `V11_WORKSPACE_ROOT` | `$HOME/.v11` | Root for session/task/autonomy/audit state. Shared across every V11 project on one machine. |
| `SESSIONS_ROOT` | `$V11_WORKSPACE_ROOT/sessions` | Where per-project session directories (spec.md, autonomy state, handoff) live. |
| `V11_HOME` | auto-detected (the directory containing this `hooks/`) | Where the framework code itself lives — usually `<project>/.v11`, computed automatically; you shouldn't need to set it. |
| `V11_BUSINESS_TZ` | `America/Chicago` | Timezone used for the cached business-hours timestamp `detect-project` maintains. |
| `V11_SESSION_ID` | (set by Claude Code) | Scopes active-project/task-state to the current session for isolation. |

## License

No `LICENSE` file is included in this distribution yet — this build focused
on partitioning and installability, not licensing. Don't redistribute this
package further until that's resolved.
