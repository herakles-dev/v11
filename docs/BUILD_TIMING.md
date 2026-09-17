# Build-Timing Calibration

> **Estimate in active-hours / active-days, never calendar weeks.** This agent-orchestrated pipeline builds 4–8× faster than traditional hand-coding intuition. Anchor every "how long" answer to the table below, not to gut feel.

**Source of truth for planning estimates.** Re-derive any time: `./scripts/build-timing` (reads the durable ledger). The `/v11 retrospective` flow re-derives per-project automatically. Rollback the STEP 4c estimate line: `V11_TIMING_ANCHOR=off`.

---

## Anchors — use these

| Unit of work | Tasks | Actual build time | Notes |
|---|---|---|---|
| **Single task** | 1 | **30–60 min** | p75 ~2h, p90 ~6h; ~56% finish same day |
| **Point release / fix-batch** | 3–10 | **<1 hr – ~1 evening** (1–3 active-hrs) | one sitting |
| **Named sprint / version** | 10–20 | **an evening or two** (3–7 active-hrs, 1–2 active-days) | median v11 effort |
| **App / MVP** | 20+ | **a few active-days** (7–25 active-hrs, 2–5 active-days) | |
| **Flagship** | 100+ | weeks of active work | the exception, not the norm |

**The gap that fools the estimate:** a v11 version *spans* a median **19 calendar days** but is only **~4 active-days / ~3.5 active-hours** of work. Calendar feel is 4–8× the effort. Only stack calendar time when genuinely blocked on an external gate (deploy, human review, funded spend).

---

## Evidence (ledger + git, 2026-05 → 2026-09)

**V11 framework efforts** (27 in window) — median: **4 active-days · 3.5 active-hrs · 10 tasks** vs **19 calendar-days** span. Recent commit-to-commit build windows:
- **v11.38 = 10 commits in 14 min** · v11.40 = 5 commits in 9 min · v11.42 = 3 in 37 min.
- **v11.36 → v11.40 — five versions — all shipped in one ~12-hour overnight window** (Aug 28 18:09 → Aug 29 06:06).
- Busiest single day: **82 commits**. Work lands on ~36% of calendar days, in bursts.

**Product / MVP builds** (active-hrs / active-days / tasks):
- HAM 24h / 5 days / 219 tasks · donkeys 8h / 5 days / 72 · keymakers-club 6.8h / 2 days / 33 · nightjar 24h / 19 days / 107.
- Flagship: example-project 120h / 50 active-days (months) — the ceiling, not the median.

**Single-task cycle time** (created→completed, same-day): median **~36 min**, p75 ~2h, p90 ~6h. Cross-session "created weeks ago" durations are rehydrate/dormancy artifacts — reported separately as `dormant_*`, never in the median.

---

## Methodology

`scripts/build-timing` reads `~/.agent-metrics/ledger/*.jsonl` and computes:
- **Task cycle time** — `created`→`completed` matched by `(project, create_seq)`. **Same-day only** is the headline (both events same calendar date); dormant pairs are excluded from the median.
- **Active-days** — distinct calendar dates with any ledger event.
- **Active-hours** — Σ of inter-event gaps, each clamped at 30 min (`IDLE_CAP_SEC`) so an away-gap doesn't count as work.

These are proxies from event timestamps, not stopwatch data — read them as bands, not precision. When the live aggregate drifts materially from the anchor table above, refresh this doc (`./scripts/build-timing --since 120d`).

**Consumers:** planning interview STEP 4c (wall-clock band), `task-patterns.md` per-task anchors, `templates/SCALING_GUIDE.md` timeline column, and the `/v11 retrospective` JSON. Related: `[[feedback_build_timing_calibration]]` memory.
