# V11 Improvements — index

Targeted improvement docs for the V11 framework, authored from the orchestrator's lived session experience. Each doc is self-contained: **Problem → Evidence → Proposed change → Risk → Rollback → Acceptance test → Why it matters.**

The format is intentionally consistent so the V11 Claude counterpart agent can consume them directly and produce implementation PRs.

> **Note on provenance.** These are early dogfooding retrospectives — findings surfaced while using V11 to build real projects, kept here as the origin record of how the framework earned each change. The "Author Session" column names the project the finding came out of. The framework has advanced considerably since these were written; they document the *why* behind design decisions, not the current feature set.

| # | Title | Severity | Author Session |
|---|---|---|---|
| 01 | [Handoff simplification — fewer files, one canonical surface](01-handoff-simplification.md) | HIGH | sofly 2026-06-22 |
| 02 | [Match agent type to required tool surface, not to description](02-agent-type-tool-matching.md) | MEDIUM | sofly 2026-06-22 |
| 03 | [Review queue: make drainage real (or admit it's optional)](03-review-queue-drainage.md) | MEDIUM | sofly 2026-06-22 |
| 04 | [Retro counter: calibrate threshold or rebuild the trigger](04-retro-counter-calibration.md) | LOW | sofly 2026-06-22 |
| 05 | [Orchestrator skill prompt preaches context discipline; should practice it](05-orchestrator-skill-prompt-leanness.md) | MEDIUM | sofly 2026-06-22 |
| 06 | [Self-improving loop keystone](06-self-improving-loop-keystone.md) | HIGH | v11-improvements 2026-07-01 — SHIPPED |
| 07 | [v11.29 alignment audit — 5 waves](07-v1129-alignment.md) | HIGH | v11-improvements 2026-07-10 — EXECUTED (W1–W5) |
| 08 | [Layer A self-review actuation (W5-T15 spec)](08-layer-a-actuation.md) | HIGH | v11-improvements 2026-07-11 — SHIPPED v11.30 |
| 09 | [Cross-session verdict fold-back (W5-T16 spec)](09-verdict-foldback.md) | HIGH | v11-improvements 2026-07-11 — SHIPPED v11.30 |
| 10 | [Pre-scope actuation: close the v11.29 pre-scope loop + token measurement](10-prescope-actuation.md) | — | v11-prescope-alignment 2026-07-14/15 — EXECUTED, SHIPPED v11.31 |
| 11 | [Half-wired loop audit (5-lane sweep)](11-halfwired-audit.md) | HIGH | v11-halfwired 2026-07-15 — APPROVED, SHIPPED v11.32 |
| 12 | [Spawn contract gaps (field report)](12-spawn-contract-gaps.md) | HIGH | 2026-07-16/17 — PROPOSED, not triaged (§H2 resolved-by-13) |
| 13 | [Session-aware write-gate](13-write-gate-session-aware.md) | — | comedic-study 2026-07-20 — SHIPPED v11.34 (+.1 review remediation) |
| 14 | [Session-scoped write-gate + attribution](14-session-scoped-gate-attribution.md) | HIGH | 2026-07-20 — SHIPPED v11.34.2 (resolves 13 §9 T4) |

## Reading order recommended for the V11 Claude counterpart

1. Start with **05** — it's the meta-improvement that makes future changes easier (a leaner skill prompt = clearer signal-to-noise).
2. Then **01** — user-flagged, highest user-visible value.
3. **02** — fixes a class of spawn-time bugs the orchestrator hits often.
4. **03** — straightforward contract clarification, also fixes a concurrent-session ambiguity.
5. **04** — small fix, but the retro feature is currently invisible in practice.

## How to add a new improvement doc

1. Number sequentially: `NN-short-slug.md`
2. Reuse the section structure (Problem → Evidence → Proposed change → Risk → Rollback → Acceptance → Why)
3. Cite real session evidence, not hypothetical scenarios
4. Add a row to the table above (and mark it SHIPPED/EXECUTED there when it lands — a stale index was itself a review finding, 2026-07-11)
