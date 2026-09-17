# V11 Improvement 04 — Retro counter: calibrate threshold or rebuild the trigger

**Author:** orchestrator (sofly session 2026-06-22)
**Severity:** LOW (single-symptom) but high signal — the retro feature is invisible in practice
**Scope:** `playbooks/journal.md`, `scripts/v11-retro`, the auto-prompt in DETECT

---

## Problem

The retro-counter on sofly reads **226**. The default auto-prompt threshold is **5**. The threshold has been blown past by 45x and no retrospective has been auto-prompted in this session, the previous session, or (per the journal) the 20 sessions before that.

The DETECT auto-prompt has gates: "skip if invocation has direct action verb / sub-command." Almost every `/v11` invocation has one of those gates. The threshold check effectively never fires.

Net: the retro system exists in code, claims to be auto-triggered, but is dead in practice.

## Evidence observed this session

```bash
$ cat /path/to/operator-home/sessions/sofly/.retro-counter
226
$ grep V11_RETRO_THRESHOLD /path/to/v11/playbooks/journal.md
# default 5
$ ls /path/to/operator-home/sessions/sofly/retros/ 2>/dev/null || echo "no retros dir"
no retros dir
```

The directory the retro system would write to doesn't exist. The counter has run away. The gate logic ensures the auto-prompt never fires for normal usage.

## Root cause

Three contributing factors:

1. **Threshold too low for an active project.** 5 task-completions triggers a prompt. On sofly we've done ~226 tasks. If we'd ever surfaced the prompt at 5, the user would have said "not now" and the counter would reset — but the gating prevents the prompt from showing at all.

2. **Gate logic blocks the prompt every time.** The gate says skip auto-prompt when the invocation has any direct action verb (build/fix/orchestrate/continue/audit/etc.). Sofly's actual sessions are almost always one of those — the gate fires on every realistic invocation.

3. **No backpressure surface.** When the gate skips, there's no "deferred to CLOSE" follow-through; the prompt is simply never offered.

## Proposed change

### A. Re-calibrate the threshold per project, with sane default

Move from a global default-5 to a per-project setting that defaults higher (50 or 100). Allow override via `sessions/<project>/.retro-config.json`:

```json
{"threshold": 100, "skip_until": "2026-07-01", "frequency": "monthly"}
```

### B. Replace the action-verb gate with a "defer to CLOSE" promise

When the auto-prompt would fire mid-session but the user is in flight:

- Drop a marker `sessions/<project>/.retro-prompt-deferred`
- At CLOSE phase, BEFORE writing handoff.md, check the marker and run the auto-prompt then (when the user is at a natural stopping point)
- If user dismisses at CLOSE, reset counter and clear marker

This gives the system one guaranteed prompt opportunity per session above-threshold instead of zero.

### C. Counter-aware nudge in the dashboard

When the counter is >2x the threshold and no prompt has fired in the last N sessions, add a single dashboard line:

```
Retro: counter 226 (threshold 100). Last retro: never. /v11 retrospective sofly
```

Visible but not interruptive. Sometimes the user is the right one to decide.

### D. Auto-rotation on /v11 retrospective success

Already proposed in the playbook (rule 18: "Reset is automatic on retro success"). Make sure it actually runs — verify the hook fires after `scripts/v11-retro --due` completes successfully.

## Risk

- **Threshold change is purely default-config.** Existing projects unaffected unless they opt in via `.retro-config.json`.
- **Defer-to-CLOSE marker** could be lost if CLOSE phase is skipped (user kills session abruptly). Acceptable — counter just keeps growing; next session re-evaluates.

## Rollback

`V11_RETRO_AUTOPROMPT=off` env var to disable entirely. Already supported by the marker file `sessions/<project>/.no-auto-retro` per the playbook.

## Acceptance test

```bash
# A project with counter=226 and threshold=100
$ /v11 status sofly
# Expected dashboard line: "Retro: counter 226 (threshold 100). Last retro: never. /v11 retrospective sofly"

# At CLOSE phase
$ /handoff sofly
# Expected: AskUserQuestion fires with retro prompt BEFORE handoff.md is written

# User declines → counter resets to 0, marker cleared
# User accepts → background retro agent spawns, writes sessions/sofly/retros/YYYY-MM-DD.json, counter resets
```

## Why this matters

A signal that says "you should reflect" but never gets seen is worse than no signal. The current implementation is a Maxwell's demon — perfectly designed to never disturb the user even when reflection is overdue. Calibrate the threshold OR give the user a real chance to see the prompt at a natural moment. Don't ship a feature that's invisible in practice.
