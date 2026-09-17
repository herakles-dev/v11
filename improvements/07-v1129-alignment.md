# 07 — V11.29 Alignment & Hardening: Subagents, Playbooks, Skills

**Status:** EXECUTED (W1–W5) (proposed 2026-07-10) · **Source:** full-surface audit vs v11.29 anchors — coherence gate (5 doc + 3 data-plane lenses), 4 alignment scans, 21-task review-queue drain. Evidence: `sessions/v11-coherence/reports/report-2026-07-10.md` (28 findings: 7 HIGH / 17 MED / 4 LOW).

## Intent
Close the gap between what v11.29 SHIPPED (lane lease, pre-scope, token ledger, worktree default) and what the consumer surface — subagent defs, orchestrator playbooks, satellite skills, docs — still TEACHES. Plus: stop the version-stamp drift treadmill structurally instead of hand-sweeping it a third time.

## Grounding (what the audit proved)
- **Token ledger is half-wired**: `hooks/track-agents:225` validates `V11_TOKENS`/`V11_TOOL_USES`/`V11_DURATION_MS` and writes usage.jsonl, but never passes `--tokens/--tool-uses/--duration-ms/--event completion` to `dispatch-trace-append` → scorecard avg-tokens starves. The headline v11.29 feature only works on one of its two outputs.
- **Stamp sweeps don't hold**: 2026-05-15/18 coherence runs found stamp lag; stamps were swept; today they lag again by 8–18 versions (registry 11.14.4, handoff skill 11.14.5, README "V11.15.0", VERSION.md v11.9.0). Manual sweeps are a treadmill.
- **Editing defs predate worktree-default**: no file-editing subagent def (spec-implementer/security/optimizer/integrator, adversarial-lite-fixer) mentions worktree isolation or commit-before-finish, while the framework now runs them in worktrees where uncommitted branches merge as no-ops = silent loss.
- **Layer A self-review is still collect-never-emit**: ledger shows self_review absent on most completed work tasks; and drained verdicts for prior-session task IDs have NO fold-back path into the ledger (`review-queue mark-done` stores severity only — verdict JSON is dropped).
- **Small live bugs in v11.29 mechanisms**: no lane release on `blocked` (sync-tasks:932); `lanes gc --max-age` double-shift crash (lanes:130); `dispatch-trace-append` rejects schema-legal `caller_kind=daemon` (:233); `drain-review-queue --safe` once misclassified this session's own claims as a concurrent session's.

## Constraints
- Advisory-never-block invariant holds; all behavior changes get env-var rollbacks where they alter defaults.
- Stamp policy change (W2) is decided ONCE and applied everywhere — no per-file discretion.
- Worktree contract language added to defs must be one SHARED block (template or include-by-pointer), not 5 hand-written variants.
- Layer B structural work (W5) is design-first: spec + spike, no big-bang rewiring.

## Waves

### W1 — Functional bug fixes (ship first, each one deliverable)
- T1 `hooks/track-agents`: pass `${V11_TOKENS:+--tokens …} … --event completion` to dispatch-trace-append; test asserting dispatch-trace line carries tokens.
- T2 `hooks/sync-tasks:932`: release lane on transition to `blocked` (or document retention intent + test); mirrors completed-branch release.
- T3 `scripts/lanes:130`: fix gc `--max-age` shift crash; test with bare flag.
- T4 `scripts/dispatch-trace-append`: accept `caller_kind=daemon` per schema; test.
- T5 `scripts/drain-review-queue --safe`: reproduce + fix self-session misclassification (claims by CURRENT session uuid must count as drainable); test.

### W2 — Version-stamp mechanization (kill the treadmill)
- T6 DECISION+impl: stamps become **derived, not asserted**. Options: (a) `scripts/check-stamp-drift` in `run-tests --regression` (soft-block like changelog drift — proven pattern, see `check-changelog-drift`); (b) drop `version:` from defs/skills entirely, replace with "Protocol: see git anchor" pointer. Recommend (a) for registry/README/VERSION.md + (b) for the 20+ SKILL.md/def stamps that convey nothing.
- T7 One-time sweep executed BY the new tool (not by hand): registry, README.md, VERSION.md (or mark historical), handoff/scaffold/v11-* skills, spec-* defs, model refs (Opus 4.6→4.8, Sonnet 4.6→5).

### W3 — Subagent def alignment (contract, not just stamps)
- T8 Author ONE shared "Worktree Contract" block (worktree-default expectation, commit-before-finish, verify-on-own-branch, 2-attempt cap pointer) → inject into the 5 editing defs; lean defs get the pointer form.
- T9 Heavy-def alignment pass: spec-reviewer(269)/security(250)/tester(208) — v11.29 anchor refs only, lean optional per steer; recovery(138)/optimizer(130) stamps + self-review applicability decided (are they work-task emitters?).
- T10 `agent-assignment` def (18 versions behind): align to per-task metadata.agent + DAAO current state or deprecate in favor of `scripts/agent-recommend`.

### W4 — Skills / playbooks / docs alignment
- T11 `docs/ROLLBACK_REFERENCE.md`: add v11.19–v11.29 sections (all env vars incl. the 4 new levers). HIGH — it's the operator's rollback map.
- T12 Hook-count sweep: configuration.md:7, migration.md, v11-update/SKILL.md:37 → teach 17-wired/23-disk/18-asserted triangulation (or better: teach `jq` derivation instead of a literal count — same treadmill argument as W2).
- T13 Token-capture docs: orchestrate.md dispatch-trace section + docs/SCRIPTS.md + rule-21 `V11_PRESCOPE_ADVISORY` cite + ENFORCEMENT.md:11 counts.
- T14 team-orchestrator SKILL.md stamp/footer 11.28.0→11.29 (folds into W2 tooling if (b) chosen).

### W5 — Review-loop structural (design-first) — ✅ EXECUTED 2026-07-11
> Shipped: T15 spec (improvements/08) + impl (hint postamble, missing_self_review absence row, V11_SELF_REVIEW_ACTUATE; 2 latent gate bugs fixed — the V11.22 reviewable gate had never fired). T16 spec (improvements/09) + impl (`ev:review` ledger event, `mark-done --verdict-file`, durable verdict store, V11_REVIEW_LEDGER) — validated in production same session when a second live TaskList wipe hit: all 5 verdicts folded back via the new path, zero loss. T17 skill fixes applied. Adversarial pass: 1 MEDIUM (unresolved-review replay keying) + 1 LOW found+fixed (8434849). Regression 20/20.
> Live evidence 2026-07-10 (this session): mid-session TaskList wipe reproduced — task #43's completion event hit "Task not found"; durable ledger absorbed it, but the wipe phenomenon (previously noted in W1-T7/W3-T13 "recreated after task-list wipe") is now confirmed, not folklore. Fold into T15/T16 design: completion events must be wipe-tolerant end-to-end.
- T15 Spec: **Layer A actuation** — self_review emission is validated at completion chokepoint (sync-tasks advisory exists; decide the actuator: completion-hint nudge? drain-time backfill? scorecard visibility?). The 2026-07-01 keystone closed Layer B joins; Layer A remains collect-never-emit.
- T16 Spec: **cross-session verdict fold-back** — drained verdict JSON for a prior-session task ID must land in the durable ledger (e.g. `review-queue mark-done --verdict-file`, appending an `ev:review` ledger event), not just a severity string. Today the richest review data evaporates at the session boundary.
- T17 `v11-coherence` skill fixes: L6 gate keys on V11 markers (spec.md/.task-state.json) not dir mtime (46 false LEDGER_MISSING); L1 scope adds README.md/VERSION.md (found only via gap-fill); note single-scanner clean bills are unreliable (playbooks scanner returned 0 where L3+review found 3+) → keep dual-lens.

## Agents
| Role | Agent | Waves |
|------|-------|-------|
| Impl (hooks/scripts) | spec-implementer-v11 | W1, W2 |
| Docs/prose | spec-implementer-v11 | W3, W4 |
| Tests | spec-tester-v11 | W1, W2 sibling tasks |
| Design specs | orchestrator (Opus) | W5 |
| Review | adversarial-lite-reviewer | paired per V11.21 |

## Non-goals
- Lean rewrite of the 5 remaining heavy defs (alignment only, per steer — lean stays optional).
- Hard PreToolUse spawn gating (unchanged blocker: spawn→task correlation).
- Real-time cost dashboards (ledger data must accumulate first — and W1-T1 is prerequisite for that data to even exist in dispatch-trace).

## Rollback
W1 fixes are pure-bug; no levers. W2 drift-guard: `V11_STAMP_DRIFT=off`. W3/W4 are docs. W5 ships its own levers at design time.
