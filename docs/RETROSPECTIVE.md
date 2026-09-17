# Version Retrospective — Me vs. Anthropic

**Window:** 2025-11-07 → 2026-07-27 · **Method:** dated artifacts vs. primary-source release dates
**Verdict on the original thesis:** *not supported.* See §1.

---

## 1. The thesis did not survive the dates

The retrospective set out to test: *"as Claude changed I changed, sometimes ahead of Claude."*

The first half holds. The second half does not. **On every platform primitive, Anthropic
shipped first — without exception.**

| Primitive | Anthropic shipped | My first artifact | Gap |
|---|---|---|---|
| MCP | 2024-11-25 | 2026-02-17 (`v11/mcp-tools`) | **−14.8 mo** |
| Claude Code itself | 2025-02-24 | 2025-11-07 | **−8.5 mo** |
| Hooks | 2025-06 | 2025-11-16 (`hooks-config.json`) | **−5 mo** |
| Subagents (`/agents`, v1.0.60) | 2025-07 | 2026-02-27 (agent defs) | **−7 mo** |
| Agent Skills | 2025-10-16 | 2025-11-05 (`adaptive-planner`) | **−20 days** |

There is no artifact anywhere on this machine predating **2025-11-07**. The framework
began roughly eight and a half months after Claude Code launched, and *after* hooks,
subagents, and Skills had all already shipped. No amount of re-cutting the evidence
produces a lead on a primitive.

**So the honest headline is not "I was ahead."** It is two other things, both stronger
because they are defensible.

---

## 2. What is actually true: absorption speed

Skills were announced **2025-10-16**. The first skill on this machine — `adaptive-planner` —
is dated **2025-11-05**. **Twenty days.** By 2026-07 the library is **158 skills**.

That pattern repeats. Each primitive gets absorbed and then *industrialised* far past the
reference usage: 158 skills, 135 registered agents (200 definition files on disk), 18 tool-event
hooks plus 2 git-event hooks, and a bespoke MCP server. The distinguishing behaviour is not
arriving first — it is arriving fast and then going much deeper than the feature's default use.

> **Doc drift caught in passing:** `CLAUDE.md` claims 97 agents. The registry reports **135**;
> there are **200** `.md` files. The canonical count is stale in the protocol doc.

---

## 3. Where "ahead" is genuinely defensible: divergence

The real claim is not precedence on primitives. It is that a **governance layer** was built
here that Anthropic still has no native equivalent for as of 2026-07. These are not faster
versions of Claude features — they are things Claude does not do.

| Capability | What it is | Native equivalent |
|---|---|---|
| **A0–A5 autonomy ladder** | Six trust levels with auto-escalation (5/10/25 actions) and error-driven de-escalation | None. Permission modes are static, not an earned ladder |
| **Dual-layer review** | Every work task auto-paired at creation with an adversarial reviewer sibling; Layer A self-review vs Layer B adversarial, with a calibration-miss counter | None |
| **Four-layer attribution** | Errors keyed by SHA256 `project\|task\|file\|line\|error_id` across runtime/lite/wave/swarm, feeding per-agent scorecards | None |
| **Durable task ledger** | Append-only per-project JSONL surviving context loss, with emit-time reconcile | Partial — `/rewind`, checkpoints, `--resume` are session-scoped, not a project ledger |
| **Validation-tag discipline** | `MEASURED` / `HYPOTHESIZED` / `LIVE` enforced at `commit-msg`, with post-commit auto-close cooperating with unmeasured claims | None |

This is the actual contribution: not the primitives, but the **discipline layer wrapped
around them** — provenance, calibration, earned trust, and falsifiability.

---

## 4. Lineage (14 shipped versions, 12 surviving artifacts)

### Era 1 — Spec Template (2025-11-07 → 2026-01-17)

| Version | Date | Evidence |
|---|---|---|
| `architecture-improvement-2025` | 2025-11-07 | oldest file; original `SESSION_SPEC.yml` |
| `1.0.0` | 2025-11-09 | `spec_template_v3/CHANGELOG.md` |
| `3.0.0` (dir `_v2`) | 2025-11-17 | `CHANGELOG.md` |
| dir `_v3` | 2025-11-18 → 11-28 | file range |
| `4.0.0` → `4.1.1` | 2025-12-15 → 12-16 | `CHANGELOG.md` |
| `v5` | archived 2026-01-17 | `.v5_legacy` stub |

### Era 2 — V-Framework (2026-01-17 → present)

| Version | Date | Evidence |
|---|---|---|
| `v6_Ultra` | 2026-01-17 | v5 archived same day |
| `v7` | *lost* | **shipped, no surviving directory** — see §5 |
| `V8.0` / `V8.0.1` | 2026-02-02 | `VERSION.md` |
| `v9` | never shipped | renamed to v10 mid-flight |
| `v10.0.0` → `v10.2.0` | 2026-02-11 → 02-13 | `VERSION.md` |
| `v11` → `v11.34.x` | 2026-02-17 → present | oldest file; 307 commits |

**Cadence:** eight months, fourteen versions — roughly one every 17 days.

---

## 5. Four numbering landmines

1. **Directory number ≠ semver.** `spec_template_v2/CHANGELOG.md` is stamped `[3.0.0]`.
   Arithmetic on folder names is wrong from the start.
2. **v7 shipped and was lost.** `v8/VERSION.md` carries "V7 Migration", "V7 hooks",
   "V7 projects", "V7 legacy". A real version survives only as other versions' migration code.
3. **v9 never shipped.** `v9.backup` diffs against `v10` as *filenames only* — a mid-rename
   snapshot. Counting it inflates the lineage.
4. **`v11.backup.20260413` is not a version.** Reads as 1.4G; ~99% duplicated `swebench-repos/`.

---

## 6. Evidence quality — read before quoting

- **mtime is unreliable and demonstrably lied here.** `spec_template/` stamps 2025-12-04,
  *later* than `spec_template_v2/` at 2025-11-17. Copying resets timestamps. Every date in §4
  is changelog- or git-derived except where noted as a file-range bound.
- **v11's git repo postdates v11.** First commit is 2026-03-08; the directory dates to
  2026-02-17. The repo is a **lower bound**, not an origin.
- **The official Claude Code `CHANGELOG.md` is a rolling window** — it begins at v2.1.178 and
  does not contain original ship dates. Any "earliest mention" read from it is an artifact of
  truncation. Feature dates in §1 come from announcements, not that file.
- **Source tiers.** MCP (2024-11-25) and Skills (2025-10-16) are primary-source dated. Hooks
  (2025-06) and subagents (2025-07, v1.0.60) are month-granularity from corroborated secondary
  sources; they are directionally safe here because the gaps are months, not days.

## Sources

- [Model Context Protocol announcement](https://www.anthropic.com/news/model-context-protocol) — Nov 25, 2024
- [Introducing Agent Skills](https://www.anthropic.com/news/skills) — Oct 16, 2025
- [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code sub-agents docs](https://docs.claude.com/en/docs/claude-code/sub-agents)
- [Claude Code changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) — rolling window, see §6
- [Anthropic Claude timeline](https://github.com/jqueryscript/anthropic-claude-timeline) — secondary corroboration
