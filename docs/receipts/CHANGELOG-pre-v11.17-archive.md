# V11 Protocol Changelog — ARCHIVE (pre-v11.17)

> 🗄️ **Archived meta-file.** This is the former root-level `CHANGELOG.md`, frozen at its newest entry v11.9.0 (2026-05-14). It is **not** the live changelog — the canonical, current version history is [../CHANGELOG.md](../CHANGELOG.md) (v11.17.0 → present). Kept for the detailed v11.9.0 "Full-Spectrum Observability" entry and prior-release pointers that predate the canonical file.

Dates are ISO 8601. Each release maps to a tagged commit or range.

## [11.9.0] — 2026-05-14 — "Full-Spectrum Observability"

Session: `sessions/v11-metrics-upgrade/` (10 tasks, 5 waves, 1 adversarial review).

Closes seven observability blind spots surfaced by the claude-engine-vis audit:
which subagents ran for project X, which sessions escalated autonomy, which
writes were blocked, and how long a session ran. Surgical additions only — no
architectural changes. All five hook edits preserve existing exit codes.

### Added

- **`usage.jsonl` project linkage** (`hooks/track-agents`). Every agent spawn now
  records `project` (via `v11_read_active_project`) and `formation` (from
  `sessions/{project}/.formation-registry.json`). Version field bumped to
  `v11.12`. Closes the largest blind spot — 322 historical entries had no
  project field; all going-forward entries do. Enables "agents used per
  session" queries.

- **Project-tagged autonomy changes log** (`hooks/track-autonomy`). Both
  escalation and de-escalation lines now include `[${V11_PROJECT:-unknown}]`
  before the autonomy message. Per-project autonomy trajectories become
  greppable.

- **Guard block audit trail** (`hooks/guard-write-gates`).
  New `~/.agent-metrics/guard-blocks.jsonl` records every `exit 2` from the
  task-state enforcement path. Fields: timestamp, project, file, reason
  (`no-task-in-progress`), detection_method. Flock-guarded 10MB rotation
  matches `autonomy-audit.jsonl` pattern. File path capped at 512 chars.

- **Session-start stamping** (`hooks/detect-project`). First file-touch in a
  session writes `sessions/{project}/.session-start` (ISO-8601, write-once,
  never overwritten). Marks the earliest observable moment of a session for
  duration calculation.

- **Session duration in dumps** (`hooks/session-end`). `last-session.json` and
  `session-log.jsonl` entries now carry `session_start` (nullable string) and
  `duration_secs` (integer, 0 if no start file). Enables wall-clock metrics.

- **App: retro-counter visibility** (claude-engine-vis). `SessionInfo.retroCount`
  surfaces `sessions/{project}/.retro-counter`. SessionCard shows amber badge
  for >5, red for >20. Currently flags 7 overdue projects (mastery-engine: 8406,
  herakles-terminal: 1164, findthering: 146, fiber-tree: 141, political-game:
  121, portfolio-platform: 56, example-project: 16, fiber-tree-v2: 9).

- **App: stall alerts + agents spawned**. Session detail panel reads
  `~/.agent-metrics/stall-alerts-{project}.json` (severity, alert count, age)
  and renders a warning banner. Agents Spawned section filters `usage.jsonl` by
  project — empty for historical sessions, populates as M1 produces new entries.

### New files

- `schemas/guard-blocks.schema.json` — JSON schema for the new audit file.
- `tests/test_metrics_upgrade.py` — 17 tests covering M1–M5 plus `--test` mode
  validation for all five changed hooks.
- `sessions/{project}/.session-start` — per-project session-start stamp.
- `~/.agent-metrics/guard-blocks.jsonl` — written on first block event.

### Modified files

- `hooks/track-agents`, `hooks/track-autonomy`, `hooks/guard-write-gates`,
  `hooks/detect-project`, `hooks/session-end`
- `claude-engine-vis/types/sessions.ts` — added `retroCount`, `stallAlert`,
  `agentsSpawned`, and `LastSessionData.session_start`/`duration_secs`.
- `claude-engine-vis/lib/sessions.ts` — reads `.retro-counter`.
- `claude-engine-vis/components/sessions/SessionCard.tsx` — retro badge.
- `claude-engine-vis/app/api/session-detail/route.ts` — stall + agents reads.
- `claude-engine-vis/components/sessions/SessionDetail.tsx` — two new sections.

### Tests

44 total (17 new + 27 existing E2E), all passing. Adversarial review found
1 HIGH, 3 MEDIUM, 3 LOW — HIGH (schema/spec enum mismatch) and 2 MEDIUM (TOCTOU
race in rotation, conditional test assertions) fixed before merge. Remaining
LOW (duplicated SessionDetailData interface across types/route) noted as
pre-existing drift risk, not introduced by this wave.

### Out of scope (deferred to v11.10)

- **Skill invocation tracking** — requires a `PostSkill` hook event that
  Claude Code does not currently expose. Skills must self-report via a new
  `scripts/track-skill` helper, not in this wave.
- **Read/Grep/Glob counting** — would 2x the write rate to
  `autonomy-audit.jsonl`. Defer to a separate `research-audit.jsonl`.
- **Token/cost tracking** — not exposed to hooks by the Claude Code runtime.

### Upgrade from v11.8.0

- Drop-in. No settings.json changes. No schema migrations.
- New `.session-start` files materialize lazily as each project is touched.
- Old `usage.jsonl` entries remain readable (project field is nullable).

---

## [11.8.0] — 2026-04-21 — "Self-Sharpening Orchestration"

Session: `sessions/v11-sharpening/` (3-sprint, 28 tasks, 3 gates).

### Added

- **Flywheel taxonomy clustering** (`scripts/flywheel-ingest --algorithm taxonomy`).
  Heuristic + optional LLM classifier over an 11-label Dark Code taxonomy
  (invariant-claim-unenforced, silent-fallback, concurrent-access-race, etc.).
  Per-project sample quotes + rationale in the proposal markdown.
  Baseline V11.7 produced 0 clusters on the example-project + v11-dark-code-audit
  corpus; V11.8 produces 4 meaningful cross-project clusters.
  See: `sessions/v11-sharpening/adr-001-flywheel-clustering.md`

- **STR interview hook** (`hooks/sync-tasks` extensions).
  On TaskUpdate(in_progress|completed) for complex/novel tasks with zero
  spec_test_requirements, emits a stderr advisory surfacing top-3 cached
  STR candidates from `spec-requirements-extract`. Cache at
  `sessions/{project}/.str-candidates.json`, invalidated on spec.md mtime.
  Respects `metadata.no_str=true` override (explicit bypass with rationale).
  Completions without STR bump `dark_code_advisories.completions_without_str`
  counter in task-state (readable by Gate 12).
  Schema change: `task-metadata.schema.json` gains `no_str: boolean`.

- **Strict Gate 11** (`scripts/v11-compliance-check`).
  Previously WARN on MODULE.md with status=unvalidated; now FAIL. Silent-skip
  era ends (was the root cause of Bug #6 in v11-dark-code-audit). Remediation
  hint points at `templates/MODULE.md.template`.

- **`scripts/formation-select PROJECT [--json]`** — project-aware formation
  recommender. Inputs: spec.md keywords, task count, complexity distribution,
  optional Cynefin domain. Output: top-3 ranked formations with confidence
  scores and copy-paste create-formation-registry commands. <200ms target
  (measured: ~50ms). Returns `"none — direct mode best"` when no rule
  converges, rather than guessing.
  See: `sessions/v11-sharpening/adr-002-formation-select.md`

- **`scripts/validate-invariants PROJECT [--strict] [--json]`** — static
  checker for MODULE.md invariants against module code. 3 pattern classes:
  crypto-label match (HK-002 family), "called-on-every-X" (HK-007 family),
  "never X" / "read-only" (forbidden-pattern). Cross-module check when
  invariant mentions interop. Non-parseable invariants explicitly reported,
  never silent-skipped. 0 false positives verified on athenaeum +
  claude-trader-pro + herakles-linux-opus.
  See: `sessions/v11-sharpening/adr-003-invariant-parser.md`

- **`scripts/verify-gate0`** and **`scripts/verify-gate1`** — session-specific
  gate scripts packaged with the framework. Each validates relevant STRs,
  full suite green (pre-existing failures tolerated), coverage >= 75.89%.

- **Sprint 0 find-command audit** — adversarial-reviewer walked all
  `find` invocations across `v11/scripts/` and `v11/hooks/`. Converted
  3 `-not -path` anti-pattern instances to `-prune` (`audit-codebase` x2,
  `validate-project-setup` x1). Validated input sanitization on `audit-query`
  (diff_hash + project). Added missing `SESSIONS_ROOT` default to
  `status` script.

### Changed

- `sync-tasks` hook comment describes V11.8 STR advisory behavior; CLAUDE.md
  §13 hook table and §13.1 dark-code table updated.
- `ENFORCEMENT.md` schema table: module-manifest Gate 11 now marked FAIL
  on unvalidated (was WARN).
- `.gitignore` adds `reports/.flywheel-cache.json` + `reports/flywheel-*.md`
  (runtime artifacts).

### Fixed

- **Bug #7 family** — `-not -path '*/foo/*'` pattern (doesn't stop find
  descent, only filters output). All 3 instances converted to `-prune` form.
  Regression test: Gate 0 verify-gate0 greps for new `-not -path` usage.
- `audit-query` input validation — `diff_hash` now required to be 8-hex,
  `project` required to match `^[a-zA-Z0-9._-]+$` before path construction.
- `status` script — explicit `SESSIONS_ROOT` default.

### Notes / Known Limitations

- `validate-invariants` v1 covers ~10-15% of real-world invariants (the rest
  are reported as UNPARSEABLE — natural-language semantic claims, wire
  format byte patterns, etc.). Target ~40% coverage deferred to V11.9 with
  Pattern 4 (wire-format) implementation.
- `formation-select` misses example-project (keyword-density too low for war-room
  domain jargon). Documented as V11.9 iteration target in sprint-2-review.
- `sync-tasks` STR gate is advisory (PostToolUse limitation), not true
  blocking. True blocking would require a new PreToolUse hook — deferred
  if advisory compliance proves insufficient.

### Metrics

- Full test suite: 965/965 → 981/981 (added 6 flywheel + 8 STR + 9
  formation-select + 9 invariant tests).
- Coverage: 75.9% (unchanged ≥ 75.89% floor).
- New scripts: 3 (`formation-select`, `validate-invariants`, `verify-gate0`,
  `verify-gate1`).
- Hook line changes: +44 lines in `sync-tasks`, 0 regressions.

---

## Prior releases

Earlier releases are captured in git history; see
`git log --oneline` for dates and commits.
