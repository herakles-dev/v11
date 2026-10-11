# V11 Improvements — index

Targeted improvement docs for the V11 framework, authored from the orchestrator's lived session experience. Each doc is self-contained: **Problem → Evidence → Proposed change → Risk → Rollback → Acceptance test → Why it matters.**

The format is intentionally consistent so the V11 Claude counterpart agent can consume them directly and produce implementation PRs.

| # | Title | Severity | Author Session |
|---|---|---|---|
| 01 | [Handoff simplification — fewer files, one canonical surface](01-handoff-simplification.md) | HIGH | sofly 2026-06-22 — DEFERRED 2026-09-25: schema v2 frozen, not scheduled (v11-leverage-program S0-T11); v11.35.6 W5 landed the half-handoff fixes (EXIT trap + .bak cap + drift-scan glob + staging pattern kills half-handoff class) |
| 02 | [Match agent type to required tool surface, not to description](02-agent-type-tool-matching.md) | MEDIUM | sofly 2026-06-22 — PARTIAL v11.35.6 (W1: 6 mis-typed spawns fixed in swarm-review + journal; tool-surface matrix added to orchestrate.md; pre-spawn checklist; V11_SPAWN_CHECK hook deferred to W4) |
| 03 | [Review queue: make drainage real (or admit it's optional)](03-review-queue-drainage.md) | MEDIUM | sofly 2026-06-22 — SHIPPED (index corrected 2026-08-20; scout-verified: §A conditional-MUST SKILL.md:346, §B claimed_by+gc review-queue:115/:294, §C dashboard :316, §D backstop :376-531, drain --safe/--force live) |
| 04 | [Retro counter: calibrate threshold or rebuild the trigger](04-retro-counter-calibration.md) | LOW | sofly 2026-06-22 — status unstated in spec |
| 05 | [Orchestrator skill prompt preaches context discipline; should practice it](05-orchestrator-skill-prompt-leanness.md) | MEDIUM | sofly 2026-06-22 — SHIPPED v11.36 W1 (extracted 3 sections; SKILL.md 473→446, then W1-T3 added trigger table 446→470) |
| 06 | [Self-improving loop keystone](06-self-improving-loop-keystone.md) | HIGH | v11-improvements 2026-07-01 — SHIPPED |
| 07 | [v11.29 alignment audit — 5 waves](07-v1129-alignment.md) | HIGH | v11-improvements 2026-07-10 — EXECUTED (W1–W5) |
| 08 | [Layer A self-review actuation (W5-T15 spec)](08-layer-a-actuation.md) | HIGH | v11-improvements 2026-07-11 — SHIPPED v11.30 |
| 09 | [Cross-session verdict fold-back (W5-T16 spec)](09-verdict-foldback.md) | HIGH | v11-improvements 2026-07-11 — SHIPPED v11.30 |
| 10 | [Pre-scope actuation: close the v11.29 pre-scope loop + token measurement](10-prescope-actuation.md) | — | v11-prescope-alignment 2026-07-14/15 — EXECUTED, SHIPPED v11.31 |
| 11 | [Half-wired loop audit (5-lane sweep)](11-halfwired-audit.md) | HIGH | v11-halfwired 2026-07-15 — APPROVED, SHIPPED v11.32 (W4-1 slow-tier triage: 3/4 CLOSED 2026-07-29, W4-2 CLOSED v11.35.6 — timeout budget retuned: 850s→2850s, floor 1067→2600, measured 2371s/2635 passed) |
| 12 | [Spawn contract gaps (field report)](12-spawn-contract-gaps.md) | HIGH | 2026-07-16/17 — H1 SHIPPED (guard-worktree-isolation hook), H2+M2 SHIPPED (report-self-review script + MCP wrapper), M1's own review-queue site still open (not the same as #18's fix), H3/H4-remainder/L1 deferred — all 2026-08-02 |
| 13 | [Session-aware write-gate](13-write-gate-session-aware.md) | — | comedic-study 2026-07-20 — SHIPPED v11.34 (+.1 review remediation) |
| 14 | [Session-scoped write-gate + attribution](14-session-scoped-gate-attribution.md) | HIGH | 2026-07-20 — SHIPPED v11.34.2 (resolves 13 §9 T4) |

**05 evidence addendum (2026-08-18):** independently re-confirmed in a 14-agent session — core now 472 lines + 17 playbooks/4,328 lines, ~20% load-bearing, zero playbooks loaded all session. Recommend severity MEDIUM → HIGH; it is the meta-fix that cheapens every other ticket.

## Current suggested order (2026-09-25): the v11-leverage-program

The open tickets are sequenced by one program: `~/sessions/v11-leverage-program/spec.md` (goals, sprints S0–S5, metrics M1–M12) and `roadmap.md` (per-task rows, files, verify steps). **S0 (v11.45 "Rails") shipped 2026-09-26 (#85, #86, #89, #90). S1 (v11.46 "Stop the Bleeding") closed the same day; S2 leads with #113.** Work from that roadmap; the batch orders below are the historical record of how each batch was first ranked.

## Reading order recommended for the V11 Claude counterpart

1. Start with **05** — it's the meta-improvement that makes future changes easier (a leaner skill prompt = clearer signal-to-noise).
2. Then **01** — user-flagged, highest user-visible value.
3. **02** — fixes a class of spawn-time bugs the orchestrator hits often.
4. **03** — straightforward contract clarification, also fixes a concurrent-session ambiguity.
5. **04** — small fix, but the retro feature is currently invisible in practice.

### 2026-08-18 batch (28-33) — suggested priority

1. **29** first — HIGH, correctness: deliverables silently undelivered; everything else assumes reports arrive. Fix ordering + outbox persistence; codify ping-on-idle-without-report meanwhile.
2. **05** (existing, addendum) — the extraction is still the meta-fix; do it before adding anything else to the core skill.
3. **30** — cheap honesty fix on the handoff (provenance already computed, just not acted on).
4. **28** — fold idle-after-report noise; pairs naturally with 29's work (same subsystem, do together).
5. **31** — prose+schema only; makes context-tiering robust for every future multi-writer session.
6. **32** — roster tiering + the 97-vs-135 validate check (embarrassment-driven priority).
7. **33** — small; do alongside any 01/handoff work.

### 2026-09-25 batch (66-79): Anthropic learnings program. Suggested priority

Theme: V11's gates work (tonight's review caught a path traversal, a ship-worst-attempt fallback and an sRGB bug). The leverage leaks are measurement, silent waits, context exhaustion and unbounded fix loops, and Anthropic's own parallel-agent teams report the same ones. See #66 for sources and the design numbers.

1. **72** first. It's the cost and idle ledger that measures whether the others help.
2. **75** and **76**: small, HIGH/MEDIUM correctness fixes in handoff and write-gate.
3. **70**, **69**, **68**: stop silent stalls, context exhaustion and polluted fix loops (in that order; 68 builds on 69's token parsing).
4. **67**: verifier-first gate for GPU and loop tasks (ship in `warn` mode first).
5. **73**, **71**, **77**, **74**, then **79** and **78**.

### 2026-09-22 batch (53-61) — suggested priority

Theme: two identities are underspecified where they are minted — **task identity** breaks on every re-create (#58) and **project identity** is parsed from raw command text (#59). Most task-state tickets since #17 patched the read side; these fix the write side so read-side code can be deleted (#60).

1. **61** first — small, low risk, and it makes `--regression` meaningful again, which every change below relies on.
2. **59** — two guards plus one deleted `mkdir`; stops new misattribution before the task-state work begins.
3. **58** — the task-status root cause. Replay-test against the ckr ledger; clean up existing duplicates only after it ships.
4. **60** — the removal half: shadow-diff, then delete. Never before #58.
5. **53 + 54** as one change (typed `dispatch_kind`, drop the sentinels and the self-fill); **55** separately.
6. **57** — small and independent; any time.
7. **56** — close, or fold its vocabulary point into #58's `superseded-duplicate` reason.

## How to add a new improvement doc

1. Number sequentially: `NN-short-slug.md`
2. Reuse the section structure (Problem → Evidence → Proposed change → Risk → Rollback → Acceptance → Why)
3. Cite real session evidence, not hypothetical scenarios
4. Add a row to the table above (and mark it SHIPPED/EXECUTED there when it lands — a stale index was itself a review finding, 2026-07-11)
