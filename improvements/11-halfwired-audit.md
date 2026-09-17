# Improvement 11 — Half-Wired Loop Audit (5-lane sweep, 2026-07-15)

> Status: APPROVED 2026-07-15 — all waves (user-approved v2). Executing on branch v11.32-halfwired.
> v2: revised after a 3-agent adversarial interference review (hook-activation / data-plane / test-ops). Two fixes redesigned (M1, M3), one re-scoped (H1), one flock requirement added (H4). Waves reordered by activation risk, not severity.
> Method: 5 read-only audit lanes + inline criterion-#3 measurement; every finding live-verified. False positives filtered with evidence (prescope-check, check-stamp-drift, review-daemon, diff_hash, review_severity, ev:prescope all confirmed WIRED).

## Ranked Findings (unchanged from v1)

### HIGH
| # | Finding | Live evidence |
|---|---|---|
| H1 | Git-event hooks layer (v11.25) never installed in ANY project or the v11 repo; CLAUDE.md names the installer wrong (`install-postcommit` vs `install-postcommit-hook`) | 0 hooks across all sessions; documented command errors |
| H2 | dispatch-trace routing calibration write-only: 2,364 rows, 1,879 with real override divergence, zero readers of any routing field; SKILL.md's "calibration loop reads override rates" is false | jq counts; grep = writer only |
| H3 | guard-effort hook dead: matcher + internal check test legacy `Task`; modern spawns emit `Agent` | synthetic payload both ways |
| H4 | review-queue-maintenance (normalize+GC) has zero callers; queue grows unbounded (121 open / 24 projects, ~832K) | --stats live run |
| H5 | V11_AUTO_REHYDRATE documented 6× as THE rehydration off-switch; zero code reads it | exhaustive grep |

### MEDIUM
| # | Finding |
|---|---|
| M1 | verdict_sha integrity hashes (36 rows) computed + folded, never re-verified |
| M2 | sync-tasks auto-pair creates review siblings without `scope` → pollutes criterion-#3 metric (all 12 post-v11.31 misses are pair_N; status:278-287 denominator has no review_of exemption) |
| M3 | `--regression` = 20 test functions in 4 of 101 files (marker-based, no manifest; 0 collection-broken); "20/20 green" reads as whole-suite health |
| M4 | V11_DAAO_ROUTING presented as 1 of "three independent levers" but never read (siblings ARE enforced); V11_REVIEW_BATCH + V11_WORKTREE_DEFAULT likewise zero-consumer |
| M5 | ledger-archive undiscoverable (absent from SCRIPTS.md); first --apply pending since 2026-07-02 |

### LOW
| # | Finding |
|---|---|
| L1 | unattributed-findings.jsonl: 1 synthetic row ever, surfaced nowhere — contradicts "never silently dropped" |
| L2 | backfill-agent-errors-task-id: one-shot tool, dead by design — header note only |

## Criterion #3 (v11.31): orchestrator-created scope adoption **100%** (20/20, target MET); overall 62.5% — all misses are pair_N siblings (→ M2). ev:prescope reader confirmed live (status:302).

## Interference Review Verdicts (v2 inputs)

| Fix | Verdict | Key constraint |
|---|---|---|
| H3 | ENABLE-AS-IS (LOW) | Volume bounded 0–1 advisory/spawn; never blocks. Latent tab-collapse field-shift bug + unreachable metadata branch noted → optional cleanup, separate task |
| H1 | NEEDS-GUARD (MED) | TWO installers (spec v1 omitted `install-validation-lint-hook`); its `core.hooksPath` default silently disables ALL pre-existing non-V11 git hooks — switch default to tested symlink method BEFORE any backfill. Blast radius otherwise low: warn-only matrix already live via guard-validation-lint; v11 repo 20/20 tag-compliant canary |
| H4 | NEEDS-MITIGATION (HIGH) | Script takes NO flock and rewrites files whole — concurrent flock-guarded append is silently dropped into the .bak sidecar. Must flock the same `${project}.jsonl.lock` across read+rewrite (or convert GC to append-only tombstones); do NOT share review-daemon's 03:30 cron slot; concurrency test required before cron wiring |
| H5 | SAFE (LOW) | Gate the `--block` emission path only (`--json`/`--list`/`--test` untouched — harness.py:295 probes --json directly); unset default MUST preserve today's behavior; don't confuse with unrelated V11_ZEUS_AUTO_REHYDRATE |
| M1 | REDESIGN (HIGH if inline) | v11_replay_ledger fold fires unconditionally on EVERY task-tool call (sync-tasks:2794) and re-reads the whole ledger — verification there = re-hash N files per TaskList per session. Move to cold path: new `scripts/ledger-verify`, operator/audit-run only |
| M2 | SAFE (LOW) | Stamp exactly `scope:"small"` — test_prescope_check proves the review_of exemption is asymmetric (suppresses missing-scope only, NOT scope==large) so "large" would fire false advisories. Existing tests additive-safe |
| M3 | REDESIGN (MED) | --regression has ZERO automated callers — risk is habit erosion (14.3s → 45s–4min gets skipped). Hidden costs invisible to item counts: Hypothesis max_examples=200 with 100× subprocess fan-out in ONE item (test_handoff_state_invariants.py:446); `-m regression` lacks `not slow` → naive tagging re-imports excluded slow tests. Two-tier design below |
| H2 | SAFE (LOW) | Land as `agent-scorecard --routing` — same file already iterates dispatch-trace (:496-652); 2,364/2,364 rows carry all routing fields, no null hazard |
| M4/M5 | SAFE (LOW) | No drift-checker reads these docs. Watch-out: H1's CLAUDE.md edit must not touch the §17 "Current v11.x" pointer line check-stamp-drift parses |

## Revised Waves (risk-ordered: docs → contained code → guarded activation → redesigns)

**Wave 0 — docs-only, zero activation risk**
- W0-1: CLAUDE.md §13 + configuration.md: correct BOTH installer names (preserve §17 pointer line byte-exact)
- W0-2: M4 re-label prompt-level levers (SKILL.md:186,321; ROLLBACK_REFERENCE.md:95) — honest "prompt-level, not code-enforced" annotation
- W0-3: M5 SCRIPTS.md rows for ledger-archive + review-queue-maintenance; L2 header note on backfill tool

**Wave 1 — contained code, no dormant activation**
- W1-1: H3 guard-effort matcher `Task|Agent` (settings.json) + internal check (track-agents:17 pattern) + test sibling
- W1-2: H5 gate v11-resume-tasks `--block` path on V11_AUTO_REHYDRATE (unset=on) + test sibling (off→no block, unset→unchanged)
- W1-3: M2 stamp `scope:"small"` at sync-tasks auto-pair site (:889-901) + test sibling
- W1-4: H2 `agent-scorecard --routing` (override-rate rollup) + test sibling; fix SKILL.md claim to point at it
- W1-5: L1 unattributed-findings count in scripts/status

**Wave 2 — guarded activation (each step gated on the previous)**
- W2-1: H4a flock `${project}.jsonl.lock` across read+backup+rewrite in review-queue-maintenance (or tombstone rewrite) + concurrency test (append mid-rewrite, row survives)
- W2-2: H4b wire into review-cadence AFTER the review-daemon loop (same wrapper, sequential — never a parallel slot)
- W2-3: H1a fix install-validation-lint-hook default → symlink method (mirror install-postcommit-hook's tested preservation) + test
- W2-4: H1b canary: install BOTH hooks on v11 repo (20/20 compliant, provable no-op); observe one real commit
- W2-5: H1c wire both installers into scaffold + `/v11 configure`; per-project backfill one at a time with V11_POSTCOMMIT_DRYRUN=on first; STRICT stays off

**Wave 3 — redesigned fixes**
- W3-1: M3 two-tier markers: `regression` = deterministic fast core <30s (audit the 100×-subprocess Hypothesis test first — mark slow or cap examples); `regression-extended` = full ~566 with slow/hypothesis re-marked; document both in SCRIPTS.md
- W3-2: M1 new `scripts/ledger-verify` (cold path): re-hash verdict_ref files vs verdict_sha, report mismatches; SCRIPTS.md row; NEVER in the replay fold
- W3-3 (optional): guard-effort tab-collapse field-shift fix (per-field jq reads) — only if we keep the metadata branch at all

**Standing constraints**: advisory-never-block; one deliverable per task; tests as siblings; worktree-isolated Sonnet editing spawns; independent rollback var per new gate; full regression green before each wave commit; branch `v11.32-halfwired` off current.

## Coverage gaps (future lanes)
- Per-hook payload-shape audit vs real Claude Code event schemas (only Task/Agent axis + camelCase precedent checked)
- ~230 internal per-script V11_* vars spot-checked only
- No enumeration of which session projects carry pre-existing non-V11 git hooks (moot if W2-3 symlink default lands first)

## W4 (added during execution)

Not part of the original 5-lane audit or the Wave 0-3 plan above — this wave was created mid-execution as a direct consequence of shipping **W3-1** (the M3 two-tier regression redesign). W3-1 split `--regression` (deterministic fast core, 17 tests, <30s) from a new `--regression-extended` tier (full suite via `-m "not benchmark"`, ~2,500 tests). Running `--regression-extended` for the first time ever surfaced **24 pre-existing slow-tier test failures** — all outside the default fast tier, so none had ever been visible to the standard regression gate.

- **W4-1**: Triage the 24 pre-existing slow-tier failures surfaced by the first `--regression-extended` run. **Status: 3 of 4 CLOSED 2026-07-29; 1 genuinely open, separately tracked.** Drained 24 → 3 → 1. Three triaged and fixed: two were stale test arranges (`test_roadmap_advisory_at_10_tasks`, `test_guard_blocks_jsonl_created_on_exit2` seeded only the project aggregate, so v11.34's session-aware gate correctly took the fresh-session exit before reaching the asserted branch — arrange seeded with per-session state, assertions untouched); one was genuinely undocumented scripts (`audit-project-attribution`, `migrate-autonomy-level-schema` → `docs/SCRIPTS.md`). Commit 8275d38.

  **Correction (same day):** this was initially reported as CLOSED 4/4 — wrong. The 4th failure, `test_e2e_task_review_loop.py::TestRegressionGate::test_full_suite_green_and_grown`, was mistakenly folded into "derivative, should reflect the other fixes" and never independently re-verified before the closure claim shipped. Direct isolated verification (zero concurrent agents, correct `-m slow` invocation) shows it fails on its own, unrelated cause: the suite has grown to ~2570 tests (this test's own floor assertion is `passed >= 1067`) but its nested run is hard-coded **serial** (`-n0`, required — parallel-inside-a-parallel-worker crashes) with an 850s `subprocess.run` timeout. A parallel (8-worker) run of the same suite takes ~1458s; serial is far slower. The timeout budget is stale relative to current suite size — not a regression from today's work (today's session added ~2 tests, negligible against this gap), not fan-out contamination (verified in isolation), and not fixed by the other three items. Tracked as a new, separate item below.

- **W4-2** (new, 2026-07-29): `test_full_suite_green_and_grown`'s serial-run timeout (850s) no longer fits the suite's current size (~2570 tests, vs. the 1067 floor the test was written against). **Status: OPEN.** Needs a measured real serial-runtime number before the timeout can be re-tuned with honest headroom (a guessed bump risks either flaking again as the suite keeps growing, or silently masking a genuine future hang). Not fixed same-session — flagged, not swallowed.

This item exists only in `CLAUDE.md` §17 ("v11.32 half-wired loop audit … — W4-1 slow-tier triage still open") and `docs/CHANGELOG.md`'s v11.32 entry ("first-ever full run surfaced 24 pre-existing slow-tier failures … → W4-1 triage") — it was never backfilled into this spec's own Wave plan. This section closes that gap.
