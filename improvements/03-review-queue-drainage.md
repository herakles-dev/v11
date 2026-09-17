# V11 Improvement 03 — Review queue: make drainage real (or admit it's optional)

**Author:** orchestrator (sofly session 2026-06-22)
**Severity:** MEDIUM — silent accumulation; the queue protocol's "MUST" is a fiction without enforcement
**Scope:** `playbooks/per-task-review.md`, the DETECT phase of this skill, `scripts/review-queue`, `scripts/drain-review-queue`

---

## Problem

The V11.19 review-queue contract says:

> **The orchestrator MUST drain the queue at DETECT and CLOSE.**

Today I invoked `/v11` on the sofly project. The queue had **17 pending reviews** going back 18+ hours, untouched. The DETECT phase noticed the count (it's in the dashboard signal: "Reviews pending: 17 ⚠"), but nothing forced me to drain before continuing. The user said "leave the photos agent be" — appropriate, since draining would have touched files another agent owns — and I just… kept going.

The protocol says MUST. The lived experience says "soft nudge that you can ignore." That's a contract drift.

## Evidence observed this session

```
$ scripts/review-queue pending sofly --json | jq length
17
$ head -1 ~/.agent-metrics/review-queue/sofly.jsonl
# pending review from 2026-06-22T00:49:09+00:00 — task #5 — bg_removal.py
```

The oldest pending review is 18 hours old. Some of those reviews are for files another agent (photos) is currently working on. The "MUST drain" contract conflicts with the orchestrator's separate "don't trample on concurrent agents" rule.

The two rules are in tension and the resolution is unspecified.

## Root cause

The review-queue contract was written assuming each session is the sole writer for the project. The reality on this Hercules box is that multiple Claude sessions can run concurrently against the same project (one in photos, one in sofly-eyes). The queue mixes their concerns.

There's no per-session scoping, no "skip files owned by a concurrent session," and no graceful "drain what you can, skip what's in flight."

## Proposed change

### A. Make the MUST conditional, with a clear escape hatch

Replace the absolute "MUST drain at DETECT and CLOSE" with:

> **The orchestrator MUST drain the queue at DETECT and CLOSE, EXCEPT for reviews whose `files_changed` intersect files modified by a concurrent active session.** Skipped items remain queued with a `skipped_until` timestamp; another session (or the same session at CLOSE) drains them later.

### B. Per-review session-ownership marker

Add to each queue line:
```json
{"v":1,"ev":"pending","task_id":17,"files_changed":["foo.py"],"session_uuid":"abc-...","claimed_by":null}
```

When a session drains, it sets `claimed_by=<session-uuid>` so concurrent sessions don't double-drain. If a session aborts mid-drain, `scripts/review-queue gc` (run by DETECT) clears stale claims older than 30 min.

### C. Surface the skip honestly in the dashboard

Today's dashboard says:
```
Reviews pending: 17 ⚠
Run scripts/drain-review-queue sofly to spawn adversarial-lite-reviewer for each.
```

Should say:
```
Reviews pending: 17 ⚠  (3 drainable here, 14 owned by concurrent session 'photos-x9')
Drain 3: scripts/drain-review-queue sofly --safe
Drain all anyway: scripts/drain-review-queue sofly --force
```

That gives the orchestrator something to actually DO without violating concurrency.

### D. Hard backstop

If pending count exceeds N (config; default 20) **and** the oldest is >24h, DETECT escalates with a blocker:

```
🛑 Review queue overflowed: 23 pending, oldest 26h.
   Run: scripts/drain-review-queue sofly --safe --force-stale
   Or:  Acknowledge with: scripts/review-queue ack-stale sofly --reason "..."
```

The orchestrator cannot proceed past DETECT without one of those.

## Risk

- **Could block legitimate work** if the backstop is too aggressive. Default to 20 + 24h; expose env var `V11_REVIEW_BACKSTOP_COUNT` and `V11_REVIEW_BACKSTOP_AGE` for override.
- **Concurrent claims** need atomic file writes (`flock` already in use for `.task-state.json.lock`; reuse).

## Rollback

- `V11_REVIEW_ENFORCEMENT=off` already exists. Add `V11_REVIEW_BACKSTOP=off` for the new backstop independently.

## Acceptance test

```bash
# Setup: 21 pending reviews, oldest 25h old, with overlap on files another session owns
$ /v11   # invokes DETECT
# Expected: blocker shown, drain command suggested, drain --safe runs 5 reviews, escalates 16 to user
$ scripts/review-queue pending sofly | wc -l  # 16 (the conflicted ones still queued)
```

## Why this matters

A protocol contract that says MUST but is never enforced trains every future session to ignore it. Either the rule needs teeth (this proposal) or the rule needs to soften to "SHOULD when safe; document why skipped." The status quo — 17 reviews quietly stacking up — is the worst of both: it implies the reviews matter, while the orchestrator behaves as if they don't.
