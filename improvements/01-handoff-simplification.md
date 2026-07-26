# V11 Improvement 01 — Handoff: simplify, fewer files, one canonical surface

**Author:** orchestrator (sofly session 2026-06-22)
**Severity:** HIGH — user explicitly flagged "handoffs got a little crazy. I think overcomplicated."
**Scope:** `playbooks/close.md`, `scripts/handoff*`, `scripts/v11-resume-tasks`, session-dir layout

---

## Problem

Handoff currently spans **7+ separate state files** in every session directory:

```
sessions/sofly/
├── handoff.md                          ← human-readable continuation
├── handoff-tasks.json                  ← machine-readable task carry
├── .handoff-fold-manifest.json         ← what was folded into handoff.md
├── .handoff-fold-manifest.json.tmp.689200   ← STALE TMP FILE LEFT BEHIND
├── .handoff-confidence.json            ← confidence scoring per task
├── .handoff-discipline-log.json        ← audit log of handoff actions
├── .handoff-autoemit-at                ← timestamp marker
└── (plus) .session-summary.md, .session-summary.md.prev.md, .session-manifest.json
```

That's 10 files for "what did this session do, what's left." Each was added to solve one symptom; the aggregate is a maintenance burden:

- **User cognitive cost** — "which file should I look at?" The user said it explicitly.
- **Orphan files** — `.handoff-fold-manifest.json.tmp.689200` from a crashed handoff is still present 12 hours later. No GC.
- **Round-trip friction** — V11.17 auto-rehydrate needs to read `handoff-tasks.json` AND respect `.handoff-discipline-log.json` AND check `.handoff-autoemit-at`. Multiple sources of truth.
- **Hooks fan-out** — Multiple hooks write each file independently → race conditions (`.handoff-fold-manifest.json.tmp.689200` is the smoking gun).

## Evidence observed this session

1. The user invoked `/team-orchestrator` and immediately said "the handoffs got a little crazy. I think overcomplicated."
2. Listing `sessions/sofly/` returned 10 handoff-related files (counts above).
3. A `.tmp.689200` orphan from a prior crash sat in the directory — no cleanup.
4. The detect phase has to consult multiple files to decide whether to auto-rehydrate (handoff-tasks.json + .handoff-autoemit-at + V11_AUTO_REHYDRATE env var).

## Proposed change

**Collapse to two files. Make them the only contract.**

```
sessions/<project>/
├── handoff.json    ← canonical machine surface (replaces 7 dotfiles + handoff-tasks.json)
└── handoff.md      ← human-readable rendering, generated from handoff.json on every write
```

### `handoff.json` schema (single source of truth)

```json
{
  "schema_version": 2,
  "session_uuid": "f0c5a01f-...",
  "emitted_at": "2026-06-22T18:41:00Z",
  "previous_handoff_at": "2026-06-22T16:21:00Z",
  "confidence": 0.87,
  "folded_summaries": [
    {"section": "Sprint 11.A", "source_tasks": [42, 43, 44], "lines": 8}
  ],
  "open_tasks": [
    {
      "id_at_handoff": 5,
      "subject": "Sprint 11.C — Feed warmed exterior rows into BiRefNet",
      "status_at_handoff": "in_progress|pending|blocked",
      "metadata": {...},
      "carry_confidence": 0.91,
      "reason_carried": "in_progress + non-trivial complexity"
    }
  ],
  "discipline_log": [
    {"ts": "...", "action": "fold", "task_ids": [40, 41], "reason": "completed sprint"}
  ],
  "next_steps": ["..."]
}
```

### `handoff.md` (generated, never edited by hand)
- First line: `<!-- generated from handoff.json — do not edit directly -->`
- Rendered by `scripts/handoff` from the JSON. The user-readable form. Diffable.

### What goes away
| Removed file | Replaced by |
|---|---|
| `.handoff-fold-manifest.json` | `handoff.json.folded_summaries[]` |
| `.handoff-confidence.json` | `handoff.json.confidence` + per-task `carry_confidence` |
| `.handoff-discipline-log.json` | `handoff.json.discipline_log[]` |
| `.handoff-autoemit-at` | `handoff.json.emitted_at` |
| `handoff-tasks.json` | `handoff.json.open_tasks[]` |
| `.handoff-fold-manifest.json.tmp.*` | atomic write + os.rename — no tmp left behind |

### Atomic write contract
All writes go through `scripts/handoff-write` which writes to `handoff.json.tmp.<pid>` then `os.rename()` to `handoff.json`. Tmp file lives <1s. A pre-commit GC step removes any `*.tmp.*` older than 60s on each `handoff` invocation.

### Migration
1. `scripts/handoff-migrate` reads existing 7 files, produces `handoff.json`, archives old files to `sessions/<project>/.archive/handoff-v1/`.
2. Run via `/v11 update PROJECT` — same upgrade path as hook updates.
3. Old files NOT deleted automatically — moved to archive so a rollback is `mv .archive/handoff-v1/* .`.

## Risk

- **Hooks that write the old files independently** — must update all hooks in one wave. Hook list to audit: `v11/hooks/handoff-*`, `v11/hooks/session-end`, `v11/hooks/sync-tasks`.
- **Backwards compat** — old `scripts/v11-resume-tasks` reads `handoff-tasks.json`. Keep the old name as a shim that reads from `handoff.json.open_tasks[]` for one minor version, then deprecate.
- **The `.retro-counter` file** is separate and stays — it's not handoff state. Same for `.autonomy-state`.

## Rollback

1. `mv sessions/<project>/.archive/handoff-v1/* sessions/<project>/`
2. `rm sessions/<project>/handoff.json sessions/<project>/handoff.md`
3. Revert hooks to v1 by `git revert` on the upgrade commit.

## Acceptance test

```bash
# After /v11 update PROJECT runs handoff-migrate:
ls sessions/sofly/ | grep -E '(handoff|fold|autoemit|confidence|discipline)' | wc -l
# Expected: 2 (handoff.json + handoff.md)
test -f sessions/sofly/.archive/handoff-v1/handoff-tasks.json  # archived
jq '.open_tasks | length' sessions/sofly/handoff.json  # non-zero if there's work
```

## Why this matters

The user's phrasing — "the handoffs got a little crazy" — is the canary. Handoffs are the V11 promise: every session ends with continuable state. When the user feels the state is unmanageable, the promise breaks even when the data is correct. Two files. One JSON, one rendering. Stop adding sidecars.
