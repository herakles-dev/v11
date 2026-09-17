# V11 Improvements — index

Targeted improvement docs for the V11 framework, authored from the orchestrator's lived session experience. Each doc is self-contained: **Problem → Evidence → Proposed change → Risk → Rollback → Acceptance test → Why it matters.**

The format is intentionally consistent so the V11 Claude counterpart agent can consume them directly and produce implementation PRs.

| # | Title | Severity | Author Session |
|---|---|---|---|
| 01 | [Handoff simplification — fewer files, one canonical surface](01-handoff-simplification.md) | HIGH | sofly 2026-06-22 — PARTIAL v11.35.6 (W5: EXIT trap + .bak cap + drift-scan glob + staging pattern kills half-handoff class; schema v2 deferred) |
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

## How to add a new improvement doc

1. Number sequentially: `NN-short-slug.md`
2. Reuse the section structure (Problem → Evidence → Proposed change → Risk → Rollback → Acceptance → Why)
3. Cite real session evidence, not hypothetical scenarios
4. Add a row to the table above (and mark it SHIPPED/EXECUTED there when it lands — a stale index was itself a review finding, 2026-07-11)
