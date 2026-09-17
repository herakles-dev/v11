# The Claude Journey

**2025-11-07 → 2026-07-27 · 14 framework versions · 158 skills · 135 agents · 20 hooks**

How the framework changed as Claude changed. Companion to [RETROSPECTIVE.md](RETROSPECTIVE.md),
which handles the lead/lag question; this one handles the story.

The arc in four words: **documents → hooks → teams → tasks.**

---

## Act I — The Spec Era

### *Control by document* · 2025-11-07 → 2026-01-17

The framework opens on **2025-11-07**, roughly eight and a half months after Claude Code shipped.
The founding problem is stated plainly in the 1.0.0 changelog's own words — what was wrong with
what came before:

> Hardcoded paths (not portable) · Scattered documentation (no clear entry point) ·
> Manual setup (15–30 minutes) · Unknown spec-agent compatibility · No examples

The answer was a **written contract**: `SESSION_SPEC.yml`, waves, and manual checkpoints. Claude
was steered by a document it was asked to follow.

| | |
|---|---|
| `1.0.0` | 2025-11-09 — origin |
| `3.0.0` | 2025-11-17 — *complete rewrite*, 40+ files → 15 (67% reduction) |
| `4.0.0 → 4.1.1` | 2025-12-15/16 — session continuity, resumption triggers (`continue`, `status`, `where were we?`) |
| `v5` | archived 2026-01-17 |

**Eight days from 1.0.0 to a total rewrite.** That cadence never really slows down.

**The Anthropic context that matters:** hooks (June 2025) and subagents (July 2025) had *already
shipped* and were not in use here. Act I is built entirely out of documents and shell scripts —
the enforcement primitives existed and hadn't been picked up yet.

---

## Act II — The Enforcement Turn

### *Control by hook* · 2026-01-17

The pivot is documented in the framework's own archive note, which is unusually explicit about
what changed and why. `spec_template_v5/.v5_legacy` reads:

> V5 was replaced by V6 Ultra which uses:
> **Protocol-driven behavior (CLAUDE.md) instead of scripts** ·
> **Hook-based enforcement instead of manual checkpoints** ·
> **Semantic state management instead of HTML comments**

That is the whole thesis of Act II in three lines: stop *asking* the model to comply, and start
*enforcing* compliance at the tool boundary. It is the single largest architectural turn in the
entire history — and it is the moment Anthropic's hooks primitive gets absorbed, about seven
months after it landed.

The adoption is not tentative:

| Version | Hooks |
|---|---|
| `v6_Ultra` (2026-01-17) | 3 |
| `V8.0` (2026-02-02) | **17** |

Three to seventeen in sixteen days.

---

## Act III — The Team Era

### *Control by teammate* · 2026-02-02 → 2026-02-17

Act III is the great catch-up. `v10` (2026-02-11) absorbs, in a single version, nearly everything
Anthropic had shipped over the previous fifteen months. Its changelog carries ten `(NEW)` headings:

**MCP Integration · Agent Teams · Skills · Formation Expansion · Parallel Teammate Spawning ·
File Ownership Registry · Extended Task Metadata · Teammate Timeout Protection ·
Adaptive Thinking · Production Metrics**

That is MCP (shipped Nov 2024), subagents (July 2025), and Skills (Oct 2025) all landing at once.
The framework spent Act I and II building its own scaffolding, then took the platform's
primitives in one gulp.

**The counter-move nobody notices:** hooks went *down*, 17 → 11. The catch-up version was also a
consolidation. That instinct — that adding a capability is a reason to cut something else —
becomes the defining habit of Act IV.

---

## Act IV — Tasks as Truth

### *Control by ledger* · 2026-02-17 → present

`v11` begins 2026-02-17 and is still running. It is by far the longest-lived version — five
months against an average of about three weeks — and the reason is that it stopped being a
*framework* and became a *system of record*. One line in its protocol carries the whole idea:

> Tasks are the single source of truth.

**And then it deleted its own predecessor's best idea.** v10 shipped Agent Teams and eight
formations; v11 deprecated `TeamCreate` outright and replaced it with per-task agent assignment
(`metadata.agent`). Formations were demoted from runtime constructs to "task-template recipes."
The team abstraction did not survive contact with real work.

### The explosion

Agents did not exist here at all until February 2026 — eight months after Anthropic shipped
subagents. Then:

```
AGENTS CREATED PER MONTH
2026-02   3   ▏
2026-03  67   ██████████████████████▎
2026-04   4   █▎
2026-05  54   ██████████████████
2026-06  35   ███████████▋
2026-07  37   ████████████▎
```

```
SKILLS CREATED PER MONTH
2025-11   3   █
2025-12   2   ▋
2026-01   8   ██▋
2026-02   5   █▋
2026-03  13   ████▎
2026-04   2   ▋
2026-05  37   ████████████▎
2026-06  18   ██████
2026-07  36   ████████████
```

Two things stand out. **March 2026** — sixty-seven agents in one month, immediately after v11
made per-task assignment the primary model. The abstraction changed, and the ecosystem rushed in
to fill it. And **May 2026** — thirty-seven skills *and* fifty-four agents, the single densest
month on record, during which `v11.17` through `v11.21` all shipped inside four days: smooth
handoff, handoff hygiene, review enforcement, audit subagents, and dual-layer review.

That four-day run is where the framework stopped being about *doing work* and started being
about *checking its own work*.

### Sub-version cadence

Seventeen tracked sub-versions from `v11.17` to `v11.34`, on top of 307 commits. Hooks recovered
from the v10 cut and passed the old high-water mark: **18 tool-event hooks plus 2 git-event
hooks**.

---

## The thread nobody plans: subtraction

Read the four acts together and the pattern is not accumulation. Every major version *removed*
something the previous one was proud of.

| Cut | Version | What was thrown away |
|---|---|---|
| Files | `3.0.0` | 40+ files → 15 (67% reduction) |
| Scripts | `v6_Ultra` | shell scripts → protocol-driven behavior |
| Checkpoints | `v6_Ultra` | manual checkpoints → hook enforcement |
| Hooks | `v10` | 17 → 11 during the biggest feature catch-up |
| Agent Teams | `v11` | `TeamCreate` deprecated one version after it shipped |
| Formations | `v11` | runtime constructs → inert task templates |

The framework is not a story of adding capability as Claude added capability. It is a story of
absorbing each new primitive and then **deleting the local workaround it made obsolete** — which
is why fourteen versions in eight months did not produce fourteen layers of sediment.

---

## What the journey actually says

**On timing:** never first. The retrospective settles this — every primitive arrived here after
Anthropic shipped it, by margins of twenty days to fifteen months.

**On speed:** the absorption gap closes hard over time. Hooks took ~7 months to pick up.
Subagents took ~8. Skills took **20 days**. The learning curve here is not about capability, it
is about *latency* — and latency collapsed as the journey went on.

**On direction:** the interesting work moved steadily away from what Claude does and toward what
Claude *can't check about itself*. Act I steered the model. Act IV audits it — dual-layer
adversarial review, four-layer error attribution, calibration-miss counters, validation tags
enforced at commit. None of that has a native equivalent, and none of it would have been
reachable without first absorbing everything in Acts I–III.

The journey is not "I kept up with Claude." It is **"I stopped rebuilding what Claude ships, so I
could build what it doesn't."**

---

### Evidence

Version dates are changelog- and git-derived (see RETROSPECTIVE.md §6 — `mtime` is unreliable
here and demonstrably lied). Growth curves are file-creation timestamps under `~/.claude/skills`
and `~/.claude/agents`, which *are* mtime-based and therefore indicative of rhythm rather than
exact provenance; monthly totals sum below the current registry counts because some entries
predate or were moved into their present location. Anthropic dates: MCP 2024-11-25 and Agent
Skills 2025-10-16 are primary-sourced; hooks (2025-06) and subagents (2025-07, `v1.0.60`) are
month-granularity from corroborated secondary sources.
