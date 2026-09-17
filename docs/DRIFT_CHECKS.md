# V11 Drift Checks

> Canonical index of the `check-*-drift` script family: mechanized guards that catch a
> specific class of doc/code/state drift that a manual sweep used to catch (and eventually
> stopped catching). Same shape, same conventions — see `## Pattern` below.

All family members (currently 8 wired + 1 on-demand — see index below) share this contract:
- Standalone, `set -uo pipefail` bash or Python, safe to run directly or from a hook/CI step.
- One dedicated `V11_*_CHECK=off` (or `V11_*_DRIFT=off` for the two pre-suffix members)
  rollback lever (documented per-check below and in
  [ROLLBACK_REFERENCE.md](ROLLBACK_REFERENCE.md)) that no-ops the check to exit 0.
- Findings print to **stderr** (`say()` / `print(..., file=sys.stderr)`), never stdout —
  safe to wire into an output-sensitive caller without polluting captured stdout.
- Wired as a **soft-block** into `scripts/run-tests --regression`/`--regression-extended`
  (never shadows a real pytest failure — precedent: `check-changelog-drift` /
  `check-stamp-drift` / `check-class-included` propagate FAIL to `PYTEST_EXIT`, while
  advisory-only checks like `check-git-tasklist-alignment` / `check-hotkey-sync` never
  do so by design). All 8 wired members (see `## Wiring sites` below) are also invoked
  by `scripts/handoff:1443` at the pre-handoff drift-check site;
  only `check-class-included`'s FAIL blocks `--spawn` (unless `--spawn-anyway`), while
  `check-stamp-drift`'s FAIL is deliberately WARN-only at that site to avoid framework-wide
  blocking on known pre-existing stamp drift (#39 v11.38 deferred).

## Pattern

The family originated with `check-changelog-drift` (commit `c7bab28`, v11.28.1): a durable
guard against `v11/CLAUDE.md` §17 re-accumulating an inline changelog instead of staying a
pointer to `docs/CHANGELOG.md`. Every later sibling — `check-stamp-drift` (`152335c`,
W2-T6) through the three W2 additions below — copies its shape: derive or load a ground
truth, extract the claimed state from each surface, diff, and report via stderr with a
FAIL/WARN/PASS exit code. This is the canonical drift-check-as-hook pattern referenced
whenever a new one is proposed.

## Index

| Script | Purpose | Exit codes |
|---|---|---|
| [`check-changelog-drift`](#check-changelog-drift) | `CLAUDE.md` §17 stays a pointer, not an inline changelog | 0 / 1 |
| [`check-stamp-drift`](#check-stamp-drift) | Version stamps across the repo agree with a git-derived anchor | 0 / 1 |
| [`check-class-included`](#check-class-included) | A referenced class/function has a matching `#Include`/import | 0 / 1 / 2 |
| [`check-git-tasklist-alignment`](#check-git-tasklist-alignment) | Git-modified/untracked files map to a completed task's artifacts | 0 / 2 |
| [`check-hotkey-sync`](#check-hotkey-sync) | A hotkey defined on one surface exists on every configured surface | 0 / 2 |
| [`check-index-body-status-consistency`](#check-index-body-status-consistency) | `improvements/README.md` index rows agree with ticket-body `**Status:**` lines (v11.37 W2-T1) | 0 / 1 / 2 |
| [`check-rollback-lever-drift`](#check-rollback-lever-drift) | `V11_*` env var reads in code vs documented rows in `ROLLBACK_REFERENCE.md` (v11.37 W2-T2) | 0 / 1 / 2 |
| [`check-registry-drift`](#check-registry-drift) | 3-way disk / `agents.json` / ledger label reconciliation for `~/.claude/agents/` (v11.37 W2-T3) | 0 / 1 / 2 |

---

### check-changelog-drift

`v11/scripts/check-changelog-drift`

**Purpose**: catches `v11/CLAUDE.md` §17 re-accumulating full version-entry headings
(INLINE_DRIFT) instead of staying a single-line pointer, and catches the pointer's
`**Current: v11.X**` version having no matching entry in `docs/CHANGELOG.md`
(CHANGELOG_STALE).

**Config**: none — always runs against `v11/CLAUDE.md` and `v11/docs/CHANGELOG.md`.

**Lever**: `V11_CHECK_CHANGELOG_DRIFT=off` (no-op, exit 0).

**Exit codes**: `0` PASS, `1` FAIL (INLINE_DRIFT and/or CHANGELOG_STALE).

**Example**:
```bash
./scripts/check-changelog-drift
# ✓ check-changelog-drift: §17 is a clean pointer and docs/CHANGELOG.md carries Current v11.36.
```

---

### check-stamp-drift

`v11/scripts/check-stamp-drift`

**Purpose**: compares version stamps across `agents/V11_AGENT_REGISTRY.json`
(`metadata.version` + every `agents[*].version`), `README.md` ("## Current Version:"),
`VERSION.md` (newest "## v11.x" heading), and `CLAUDE.md` ("**Current: v11.x**") against a
git-log-derived anchor (never an in-repo string). Also runs an independent per-project
phase (W2-T1): every project's `sessions/{project}/.stamp-drift-extra.json` entries must
agree with each other (e.g. an AHK client build number vs. a Python server build number in
the same project) — this phase has no relationship to the git-anchor comparison.

**Config**: per-project, optional — `sessions/{project}/.stamp-drift-extra.json`:
```json
{
  "version_files": [
    {"label": "client", "path": "client/VERSION", "pattern": "VERSION\\s*=\\s*\"([0-9.]+)\""},
    {"label": "server", "path": "server/version.py", "pattern": "__version__\\s*=\\s*\"([0-9.]+)\""}
  ]
}
```
Paths are relative to the project dir and validated (`/`-absolute or `..`-traversal
rejected before the file read). Absent config = no-op for that project's extension phase;
the git-anchor comparison always runs regardless.

**Lever**: `V11_STAMP_DRIFT=off` (no-op, exit 0 — disables BOTH the anchor comparison and
the per-project extension phase; see [ROLLBACK_REFERENCE.md](ROLLBACK_REFERENCE.md)).

**Exit codes**: `0` PASS, `1` FAIL (anchor mismatch and/or per-project version mismatch).

**Example**:
```bash
./scripts/check-stamp-drift
# check-stamp-drift: anchor = v11.36 (derived from git log)
# ...
# ✓ check-stamp-drift: all surfaces match anchor v11.36.
```

---

### check-class-included

`v11/scripts/check-class-included`

**Purpose**: flags a class/function constructor call (e.g. `ControlCenterGUI(...)`)
referenced in source whose `#Include`/import line is missing or was commented out — the
failure mode that survives at runtime in dynamic languages (AHK, Python) with no
parse-time catch (improvements/35-pre-handoff-drift-check.md, case #2).

**Config**: per-project, optional — `sessions/{project}/.class-scan-config.json`:
```json
{
  "scans": [
    {"lang": "ahk", "root": "client/Main.ahk",
     "reference_pattern": "([A-Z][A-Za-z0-9]+)\\(",
     "include_pattern": "^#Include\\s+\"lib\\\\\\1\\.ahk\""}
  ]
}
```
`\1` in `include_pattern` is a template placeholder substituted with the matched
identifier BEFORE regex compilation — not a live backreference. Absent config = no-op
(exit 0) for that project. `root` is relative to the project dir and validated
(`/`-absolute or `..`-traversal rejected before the file read, WARN — CLOSE-T5 fix).

**Lever**: `V11_CLASS_INCLUDED_CHECK=off` (no-op, exit 0).

**Exit codes**: `0` PASS/skip, `1` FAIL (confirmed missing include), `2` WARN (heuristic
miss, e.g. an attribute/method call that can't be confirmed as needing its own include, or
a config problem). FAIL takes priority when both occur in the same run.

**Example**:
```bash
./scripts/check-class-included --project my-ahk-app
# ❌ CLASS_NOT_INCLUDED[my-ahk-app]: class ControlCenterGUI referenced at client/Main.ahk:42 but not included (scan #0, ahk).
```

---

### check-git-tasklist-alignment

`v11/scripts/check-git-tasklist-alignment`

**Purpose**: flags modified/untracked files (`git status --porcelain=v1 -z`) at
session-end time that aren't tied to any completed task's `metadata.artifacts` —
advisory drift signal, not a correctness violation (improvements/35, case #3).

**Config**: none — auto-detects. Only checks a project when
`sessions/{project}/.git` exists (project's own working tree lives directly under its
session dir). Cross-references against every string under a `files_changed`,
`files_created`, or `files_touched` key anywhere inside `.task-state.json`'s
`task_artifacts` (any nesting depth). Both sides normalized via `os.path.realpath` before
comparison.

**Lever**: `V11_GIT_TASKLIST_CHECK=off` (no-op, exit 0).

**Exit codes**: `0` PASS/skip (clean, or nothing to cross-reference), `2` WARN (unmapped
files found). Never FAILs.

**Example**:
```bash
./scripts/check-git-tasklist-alignment --project claude-ahk
# ⚠ GIT_TASKLIST_DRIFT[claude-ahk]: 2 of 5 modified/untracked file(s) not tied to any task's metadata.artifacts.
#    - client/scratch.ahk
```

---

### check-hotkey-sync

`v11/scripts/check-hotkey-sync`

**Purpose**: flags a hotkey defined on one configured surface (e.g. `Config.ahk`) but
missing from another (e.g. the `CLAUDE.md` hotkey table) — catches a partial edit that
ships silently when adding a hotkey touches N surfaces by convention and nothing enforces
parity (improvements/35, case #4).

**Config**: per-project, optional — `sessions/{project}/.hotkey-sync-config.json`:
```json
{
  "surfaces": [
    {"path": "client/Config.ahk", "hotkey_pattern": "^([A-Z][a-zA-Z]+):=\\s*\\{"},
    {"path": "client/Main.ahk", "hotkey_pattern": "^([A-Z][a-zA-Z]+)_Hotkey"},
    {"path": "CLAUDE.md", "hotkey_pattern": "\\| ([A-Z][a-zA-Z]+) \\|"}
  ]
}
```
Requires at least 2 surfaces to cross-reference; a surface file missing on disk is
skipped (not treated as "missing every hotkey"). Absent config = no-op (exit 0). Each
surface's `path` is relative to the project dir and validated (`/`-absolute or
`..`-traversal rejected before the file read, WARN — CLOSE-T5 fix).

**Lever**: `V11_HOTKEY_SYNC_CHECK=off` (no-op, exit 0).

**Exit codes**: `0` PASS/skip, `2` WARN (at least one hotkey missing from at least one
surface, or a config/surface problem). Never FAILs.

**Example**:
```bash
./scripts/check-hotkey-sync --project claude-ahk
# ⚠ HOTKEY_DRIFT[claude-ahk]: 'ToggleOverlay' defined in client/Config.ahk but missing from CLAUDE.md, client/Main.ahk.
```

---

### check-index-body-status-consistency

`v11/scripts/check-index-body-status-consistency` (v11.37 W2-T1, ticket #42)

**Purpose**: catches drift between `improvements/README.md` table row status text and
each `improvements/{N}-*.md` body `**Status:**` line. The v11.36 W1-Rev sweep fixed one
direction (body-SHIPPED but index-PROPOSED); the v11.37 alignment review's L3 lens found
8 drifts in the reverse direction (index-SHIPPED but body-PROPOSED). This check catches
recurrence going forward.

**Config**: none — always runs against `v11/improvements/`.

**Schema**: per the [Index-body canonical status schema](#index-body-canonical-status-schema-v1137-w1-t5--w2-t1) below.
Multi-phase tickets resolve to `PARTIAL` when both SHIPPED and PROPOSED appear on the same
surface. `EXECUTED` and `APPROVED` are canonicalized to `SHIPPED`.

**Lever**: `V11_INDEX_BODY_CHECK=off` (no-op, exit 0).

**Exit codes**: `0` PASS/skip, `1` FAIL (missing ticket file OR missing README row for
either surface), `2` WARN (status token divergence, >1 Status line in body, unrecognizable
token).

**Example**:
```bash
./scripts/check-index-body-status-consistency
# ⚠ INDEX_BODY_DRIFT[WARN]: #34: status token drift — body says PROPOSED, README says SHIPPED
```

---

### check-rollback-lever-drift

`v11/scripts/check-rollback-lever-drift` (v11.37 W2-T2, ticket #44)

**Purpose**: catches (a) rollback env vars documented in `ROLLBACK_REFERENCE.md` with
ZERO code reads across `scripts/`+`hooks/` (doc-lies — a user who sets the lever gets
nothing), and (b) `V11_*` env vars read as behavior gates in code with no doc row
(silent levers — an operator debugging a hooked behavior cannot discover them). The
v11.37 audit surfaced `V11_CANCELLED_FILTERS_REPLAY` as the archetype doc-lie (now
downgraded via v11.37 W1-T4) plus 5 documented silent levers (v11.37 W1-T5).

**Config**: none. Scans hard-coded exclusions for inter-hook state channels (`V11_AGENT_ID`,
`V11_CALLER_KIND`, etc.), test seams (`V11_TEST_*`), and environment vars (`V11_HOME`,
`V11_SCHEMA_DIR`). Prompt-only levers (`V11_DAAO_ROUTING`, `V11_SPAWN_NOTIFY_ON_IDLE`,
`V11_WORKTREE_DEFAULT`) are recognized by phrase-match on their doc row ("prompt-level lever",
"docs-level policy", "Doc-only", "no hook reads", etc.) and skipped. Strikethrough
(`~~V11_FOO~~`) rows are treated as HISTORICAL and skipped.

**Lever**: `V11_ROLLBACK_LEVER_CHECK=off` (no-op, exit 0).

**Exit codes**: `0` PASS, `1` FAIL (doc-lie), `2` WARN (silent lever).

**Example**:
```bash
./scripts/check-rollback-lever-drift
# ⚠ ROLLBACK_LEVER_DRIFT[FAIL]: V11_CANCELLED_FILTERS_REPLAY — documented in ROLLBACK_REFERENCE.md but ZERO code reads (doc-lie)
```

---

### check-registry-drift

`v11/scripts/check-registry-drift` (v11.37 W2-T3, ticket #38-F2)

**Purpose**: 3-way join of `~/.claude/agents/*.md` (maxdepth 1, archive/ excluded)
frontmatter `name:` values vs `~/.agent-registry/agents.json` keys vs
`~/.agent-metrics/ledger/*.jsonl` distinct actor labels (last 30d). Catches the class
that v11.37 W1-T1 reconciler cleaned once (`adversarial-lite-reviewer` and 5 v11.36 W2
drift-agent siblings were live but unregistered). Also flags ledger-active labels with no
`.md` (rename/alias drift) and registered entries with no `.md` (dead registrations).

**Config**: none. Task-like ledger labels (`W1-T*`, `S76-*`, `CLOSE-T*`, `Sprint*`, etc.)
and composite labels (`foo+bar`) are filtered as attribution-noise, not real agent
identities. Claude Code built-ins (`Explore`, `general-purpose`) and meta-labels
(`self`, `main`, `orchestrator`, etc.) are also skipped.

**Lever**: `V11_REGISTRY_CHECK=off` (no-op, exit 0).

**Exit codes**: `0` PASS, `1` FAIL (disk `.md` missing from registry — CRITICAL, blocks
`--spawn` at the handoff wire), `2` WARN (dead registry entry OR ledger orphan).

**Example**:
```bash
./scripts/check-registry-drift
# ⚠ REGISTRY_DRIFT[FAIL]: adversarial-lite-reviewer — on disk (maxdepth 1) but MISSING from ~/.agent-registry/agents.json. Run: scripts/reconcile-agent-registry --dry-run
```

---

## Debug

Every script honors `V11_DRIFT_CHECK_DEBUG=on` for verbose per-scan/per-surface output on
stderr. All four project-scoped checks accept `--project NAME` to scope to one project;
omitted, they scan every `sessions/*/`.

## Wiring sites

- `scripts/run-tests --regression` / `--regression-extended`: **all five** run alongside the
  test suite as soft-blocks (see `## Pattern` above for the WARN-vs-FAIL branch handling).
  `check-class-included`, `check-git-tasklist-alignment`, and `check-hotkey-sync` are invoked
  with `--project v11` here (CLOSE-T5 fix, v11.36) — regression output must be deterministic
  and about the framework itself, not whatever unrelated project happens to have drift right
  now; the unscoped default (scan every `sessions/*/`) was surfacing WARN noise for other
  active projects. `sessions/v11/` has no project-root `.git` or per-project config today, so
  in practice these three currently no-op in regression — `check-stamp-drift` keeps its
  deliberate framework-wide, unscoped anchor scan (see its own entry above).
- `scripts/handoff` (v11.36 W2 + v11.37 W2-T4 family expansion): **eight** run at the
  pre-handoff drift-check site (`scripts/handoff:1425`, same place as
  `handoff-discipline-check`): `check-stamp-drift`, `check-class-included`,
  `check-git-tasklist-alignment`, `check-hotkey-sync`, `check-changelog-drift` (rewired
  v11.37 W2-T4), `check-index-body-status-consistency` (new v11.37 W2-T1),
  `check-rollback-lever-drift` (new v11.37 W2-T2), `check-registry-drift` (new v11.37 W2-T3).
  Only `check-class-included`'s FAIL and `check-registry-drift`'s FAIL block `--spawn`
  (unless `--spawn-anyway`) — a missing class import or a live-but-unregistered agent
  are correctness concerns downstream. Other FAILs (stamp/changelog/index-body/rollback-lever)
  report but don't block — they're hygiene, not correctness.
- **UX (v11.37 W2-T4)**: pre-handoff drift block emits a **1-line summary** by default
  (`drift checks: N ran, P PASS, W WARN, F FAIL`). Full per-check WARN/FAIL blocks are
  gated by `V11_DRIFT_VERBOSE=on`. FAIL blocks always print regardless of verbose.
- **Recovery (v11.37 W2-T4)**: pass `--skip-drift-checks` (or `V11_SKIP_DRIFT_CHECKS=1`)
  to `scripts/handoff` to bypass the ENTIRE family in one flag — useful when the operator
  is debugging drift and the checks would otherwise soft-block a diagnostic handoff.
  Per-check env-var levers (`V11_STAMP_DRIFT=off` etc.) still work at the script level.

## `~/.claude/agents/archive/` policy (v11.37 W1-T5)

`~/.claude/agents/archive/*.md` files are **inactive-by-convention**. They exist on disk
as historical/rejected agent definitions kept for reference, not for invocation. Every
disk-scan-based drift check MUST use `-maxdepth 1` when enumerating `~/.claude/agents/`:

- Archived agents are EXCLUDED from `~/.agent-registry/agents.json`.
- `check-registry-drift` (v11.37 W2-T3) does NOT flag archived agents as "missing from registry".
- `reconcile-agent-registry` (v11.37 W1-T1) skips archived agents when computing the add/prune plan.
- `~/CLAUDE.md`'s "N specialized agents" count reflects the maxdepth-1 count (96 as of v11.37 W1-T1), NOT the recursive count (149 including archive/).

An archived agent that is later resurrected should be `mv`-ed back to `~/.claude/agents/` (out
of `archive/`) and then `reconcile-agent-registry --apply` re-adds it. The reverse move
(demotion) implicitly removes it from the registry on the next reconcile pass.

## `check-improve-subagent-triggers` — on-demand (v11.37 W1-T5)

`scripts/check-improve-subagent-triggers` is documented here as an **on-demand** check
(v11.37 W2-T5 decision: F2b). It is NOT wired into `scripts/handoff` or
`scripts/run-tests --regression`. It is intentionally invoked by the orchestrator during
session DETECT to read `scripts/agent-scorecard`'s `self_review_miss` calibration signal
and emit "task-needed" hints for improvements. Per v11.27 doctrine ("mechanize
acknowledgment, not actuation"), this check never runs improve-subagent itself — it only
surfaces the signal for a Claude session to decide.

Usage during session start:

```bash
check-improve-subagent-triggers PROJECT --json    # JSONL task-needed signals
check-improve-subagent-triggers PROJECT           # human-readable dashboard lines
```

## Index-body canonical status schema (v11.37 W1-T5 → W2-T1)

Consumed by `scripts/check-index-body-status-consistency` (v11.37 W2-T1). Defines the
contract between `improvements/README.md` table col-2 and `improvements/{N}-*.md` body
`**Status:**` line.

**Contract:**

1. Every ticket file has EXACTLY ONE `**Status:**` line in its frontmatter block (the first
   `**Status:**` line encountered wins; presence of a SECOND emits WARN — a Landing-section
   status addendum is a drift smell).
2. The primary status token is one of: `PROPOSED`, `OPEN`, `PARTIAL`, `SHIPPED`, `DEFERRED`,
   `HISTORICAL`.
3. Multi-phase tickets (F0/F1/…/Fn) encode per-phase state inline as
   `<TOKEN> {<phase-list>}` — example: `SHIPPED {F0, F1} · PARTIAL {F2} · PROPOSED {F3-F5}`.
4. `check-index-body-status-consistency` compares the FIRST token of body Status against the
   PRIMARY token surface in the README row (READMEs row is single-line prose; the check
   scans for any SHIPPED / PROPOSED / OPEN token). WARN when they diverge on the top axis.
5. When either surface uses PARTIAL, the check requires the PARTIAL to appear on BOTH sides
   (otherwise WARN).
6. A canonical rewrite pass under v11.37 W1-T3 already brought all 8 drifted tickets
   (#13/#15/#27/#32/#34/#35/#36/#37) into schema conformance; the check-drift regression
   catches future recurrence.

**Non-goals for the check:**

- Does NOT parse per-phase state past the top-line token (heavy natural-language variation).
- Does NOT verify commit SHAs, dates, or wave-mapping in status text.

**Rollback:** `V11_INDEX_BODY_CHECK=off` disables the check (exit 0 always).
