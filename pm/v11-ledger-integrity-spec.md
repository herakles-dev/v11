# V11 Ledger-Integrity Improvement Spec — v2 (implementation-grade)

> **Status:** SHIPPED 2026-06-29 (branch `v11.27-ledger-integrity`). T1/T2/T3/T5/T6 implemented + dual-layer reviewed (2 MED + 1 LOW found & fixed); T4 cut to design spike (`sessions/v11-ledger-integrity/T4-spike.md`).
> **Author:** Opus orchestrator (PM), 2026-06-29
> **Source report:** `sessions/sofly/v11-improve-v11-opus-2026-06-29-orchestrator.md`
> **Method:** two recon waves (13 agents total, pinpoint schema) + 3 adversarial lenses. Wave 1 = locate the bug; Wave 2 = prove each fix has a real insertion point, a reused helper, a test home, and no collision. Every claim cites `file:line`.
> **v2 changes vs v1:** T4 (A4 writer) **cut to a design spike** — recon proved it is not safely feasible as scoped. Per-task implementation contracts added. Execution sequencing rewritten around verified `common.sh`/`scripts/status` backend collisions. Success criteria bound to exact test files.

---

## Goal

Close the half-wired control loops in V11's tracking substrate — where an artifact/sensor is **generated, incremented, or read** but the matching **consume / reset / validate / write** half was never built — by mechanizing the *acknowledge/surface* half (safe, read-only) while keeping every *mutate* half gated, propose-only, and default-off.

### Meta-cause hypothesis: **CONFIRMED; cure REFRAMED**

Recon confirms one disease repeated six ways — a control loop with one half wired:

| F | Wired half (file:line) | Missing half | Class |
|---|---|---|---|
| F1 | discipline block generated `handoff:1183` / `handoff-discipline-check:163` | no resume consumer (`v11-resume-tasks:86` reads only `handoff-tasks.json`) | missing-consumer |
| F2 | zombies detected `guard-stale-task` | warn-only by design (docstring: "never auto-edit task state") | warn-only (sibling) |
| F3 | queue counted `detect-project:94` | drain manual; `agent_id` never validated `common.sh:3041` | missing-consumer + no-validation |
| F4 | counter incremented, hooked `session-end:170` | reset discretionary, unhooked `v11-retro:105` | broken-flywheel |
| F5 | `high_risk_history` read to gate A4 `common.sh:1059` | **zero append paths anywhere** | inert-instrumentation (inverse) |
| F6 | families folded in view `handoff:1282` | no merge on ledger (`family_fold.py` only groups) | missing-consumer |

**But the report's proposed cure (auto-drain + auto-close + auto-merge) is rejected by all three lenses and by the test suite itself** (`test_family_fold.py:264` already encodes a known over-merge). The corrected structural fix separates two things the report conflated:

- **Consume / surface / acknowledge** → safe to mechanize now (read-only). → **S1**.
- **Act / mutate** (close, drain, merge, reset, write) → stays individually gated, propose-not-apply, default-off, or **deferred** when unsafe.

---

## Findings → disposition (post both waves + synthesis)

| # | Survives? | Form | Feasibility (Wave 2) |
|---|---|---|---|
| F1 | **partial** | read-only feed into S1; real shipped→close already owned by V11.25 post-commit hook | MED |
| F2 | **no code change** | advisory ceiling permanent; feeds S1 read-only; otherwise discipline note | n/a |
| F3a | **yes (narrowed)** | trace-stamp + WARN on `agent_id="unknown"`; **never reject** (it's a legit fallback `sync-tasks:1238`) | **HIGH** |
| F3b | **yes (via S1)** | DETECT surfaces queue count + unknowns; drain stays manual | MED |
| F4 | **yes** | dashboard sanity guard + **flock the counter** (Wave-2 catch); no auto-reset | **HIGH** |
| F5/T3 | **yes** | legibility warning when A4 + empty history; zero behavior change | **HIGH** |
| F5/T4 | **DEFERRED** | guarded writer — **not safely feasible as scoped** (3 blockers, see below) | **CUT → spike** |
| F6 | **yes (gated)** | propose-only `--reconcile`, sprint-scoped, `--dry-run` default, ledger tombstone | **HIGH (propose-only)** |
| S1 | **yes** | read-only DETECT reconcile surface; one flag; mutates nothing | MED |

---

## The structural fix — S1: DETECT reconciliation surface (read-only)

**Flag:** `V11_DETECT_RECONCILE` (default `off`; sofly pilot → framework-wide once proven).
**Inject point:** `hooks/detect-project:103` (after the existing review-queue/handoff nudges).
**Matcher:** already correct — `detect-project` is wired `PreToolUse:Read` (`settings.json:7-13`), which IS the session-DETECT surface. No matcher change, no new hook → **hook count stays 17** (`CLAUDE.md:272`; `v11-coherence` DC2 computes dynamically, no manual bump).

**Contract — emit one read-only JSON block consolidating four signals:**

| Signal | Source API (verified) | How S1 reads it |
|---|---|---|
| zombie/discipline | `scripts/handoff-discipline-check PROJECT` → JSON `{stale_in_progress_count, nudges[]}` (`:163`) | invoke fresh at DETECT (cheap; avoids stale-by-one-session) |
| review queue | `scripts/review-queue pending PROJECT --json` (`:151`) | invoke fresh; count + `unknown_attribution` tally |
| fold families | `.handoff-fold-manifest.json` (`handoff:1272`) | new `v11_fold_manifest_read()` wrapper + `[ -f ]` guard |
| retro counter | `.retro-counter` plain text (`session-end:170`) | new `v11_retro_counter_read()` wrapper + `[ -f ]` guard |

```json
{ "v11_detect_reconcile": {
    "zombie_tasks":  {"count": N, "ids": [...]},
    "review_queue":  {"pending": N, "unknown_attribution": N},
    "fold_families": {"count": N, "mergeable_candidates": N},
    "retro_counter": {"value": N, "threshold": 5, "flywheel_suspect": <value > 10×threshold>} } }
```

**S1 mutates nothing** (no TaskUpdate, no enqueue, no merge, no reset). The orchestrator's DETECT status report MUST echo the block or state "reconcile clean." This is the consumer the meta-cause was missing — **acknowledgment, not actuation**.

**Coherence proven (Wave 2):** orthogonal to `post-commit-close-tasks` (writes ledger JSONL, S1 reads discipline log — separate files) and to `handoff_state.py` V11.26 (scripts/handoff-internal; `detect-project` never invokes it). First-session guard required: `.handoff-fold-manifest.json` / `.retro-counter` may not exist → `[ -f ]` before read.

---

## Tasks (each: agent · files · complexity/risk · contract · rollback · test home)

### T1 — S1 DETECT reconciliation surface *(P0, structural)*
- **agent:** `backend-architect` · **complexity:** complex · **risk:** medium
- **files:** `hooks/detect-project` (inject @ `:103`), `hooks/lib/common.sh` (new `v11_fold_manifest_read`, `v11_retro_counter_read`)
- **contract:** invoke discipline-check + review-queue `--json` fresh; read fold-manifest + retro-counter from disk with `[ -f ]` guards; emit `v11_detect_reconcile` JSON to stderr; **no writes**.
- **rollback:** `V11_DETECT_RECONCILE=off` (default off)
- **test home:** `tests/test_e2e_v11_pipeline.py` via `fire_hooks()` (`:49`) — SC1/SC2

### T2 — Retro flywheel sanity guard + flock *(P1, cleanest — ship first)*
- **agent:** `backend-architect` · **complexity:** medium · **risk:** low
- **files:** `hooks/session-end` (flock the counter write `:170-182`), `scripts/status` (sanity-guard line)
- **contract:** wrap read-increment-write in `(flock -w 5 201 || exit) 201>"$RETRO_FILE.lock"` — **fd 201**, not 200 (`:96` task-state flock holds 200). Reuse the FD pattern at `common.sh:535`. Dashboard prints `⚠ retro flywheel likely broken (counter=N ≫ 10× threshold, never reset)` when `counter > 10×V11_RETRO_THRESHOLD` (>50). **No auto-reset.**
- **rollback:** `V11_RETRO_SANITY_GUARD=off`
- **test home:** `tests/test_wave1_fixes.py:493` (existing concurrent session-end test) — SC4; new status test — SC3

### T3 — A4 high_risk_history dead-gate legibility *(P1, safe)*
- **agent:** `security-engineer` · **complexity:** medium · **risk:** medium
- **files:** `hooks/track-autonomy` (warn path), `scripts/status` (render)
- **contract:** when `level>=4` AND `high_risk_history==[]`, emit `⚠ high_risk_history never populated — A4 high-risk gate is effectively always-block`. Zero behavior change (gate already blocks on empty — `common.sh:1059` `any()==false → return 2`). **Also add a characterization test** pinning current empty→block behavior (`common.sh:1060-1063` is currently untested) as the landing gate for any future T4 (V11.26 pattern).
- **rollback:** `V11_A4_DEADGATE_WARN=off`
- **test home:** `tests/test_hook_behaviors.py` TestTrackAutonomy (`:264`/`:283`) + `tests/test_common_sh.py` TestCheckAutonomy — SC5

### T5 — review-queue unknown-attribution legibility *(P1)*
- **agent:** `backend-architect` · **complexity:** medium · **risk:** low
- **files:** `hooks/lib/common.sh` (`v11_review_queue_add`, inject @ `:3036`)
- **contract:** keep Rule A (`:2975`) + Rule B (`:2980`) unchanged; for `agent_id=="unknown"` **admit** the entry, add a `trace` field, emit a WARN — **never reject** (`agent_id="unknown"` is a legit orchestrator/bg-agent fallback `:3041`/`sync-tasks:1238`). Gated by existing `V11_REVIEW_ENQUEUE_VALIDATE`.
- **rollback:** `V11_RQ_TRACE_UNKNOWN=off`
- **test home:** `tests/test_review_queue_helpers.py` (`:329/:365/:381` already cover Rule A/B; add trace assertion) — SC7

### T6 — fold-manifest propose-only reconcile *(P2)*
- **agent:** `backend-architect` · **complexity:** complex · **risk:** medium
- **files:** `scripts/lib/family_fold.py` (new `propose_merge()` — none exists, only grouping), new `scripts/fold-reconcile` (propose-only CLI)
- **contract:** `fold-reconcile --dry-run` (default) proposes merges only when `family_size>1 AND same metadata.sprint AND all subjects normalize-equal` (reuse `normalize_subject:80`; add a sprint filter — `fold_families` does not extract sprint today). `--apply --confirm` emits a `reconcile scope=identity` ledger event per non-canonical member (the existing tombstone pattern, `common.sh:2425`, append-only preserved). Never runs in hooks/DETECT. Guards the known over-merge (`family_fold.py:264`).
- **rollback:** default `--dry-run`; `V11_FOLD_RECONCILE=off` disables `--apply`
- **test home:** `tests/test_family_fold.py:264` (extend the known over-merge case to assert dry-run proposes nothing across sprints) — SC8

### T4 — A4 high_risk_history guarded writer *(DEFERRED → design spike, not this sprint)*
**Recon verdict: not safely feasible as scoped.** Three blockers, all `file:line`-verified:
1. `MATCHED_PATTERN` is local to `v11_check_risk()` (`common.sh:1059`) — a writer in `track-autonomy` must duplicate the hard-coded `PATTERNS` assoc-array → drift risk.
2. **No pre→post hook signal** from `guard-enforcement` (pre) to `track-autonomy` (post) — the writer cannot distinguish "human freshly approved" from "A4 re-auto-approved via existing history" → silent duplicate-append.
3. `v11_caller_kind()` returns `unknown` for interactive human sessions (`V11_SUBAGENT`/`V11_PARENT_SESSION_ID` both unset) — **the `caller_kind=human` guard the fix depends on is unreliable**.
Shipping T4 would change A4 semantics (always-block → block-once-then-auto-approve) for existing A4 projects behind an unreliable guard, with the target branch untested. → **Spike first**: design an inter-hook approval token + reliable human detection; re-spec T4 only after. T3 makes the dead gate legible in the meantime.

---

## Execution sequencing (PM — backend-collision-aware)

`feedback_parallel_agent_backend_collision`: two agents editing the same file clobber each other. Wave 2 confirmed the shared surfaces:
- **`hooks/lib/common.sh`** ← T1 (wrappers), T3 (none — T3 is track-autonomy/status), T5 (`:3036`), T6 (import only). Net writers: **T1 + T5**.
- **`scripts/status`** ← T2 + T3.

**Therefore this is NOT a 5-parallel-agent fan-out.** Sequence:

- **Wave A (parallel-safe, disjoint files):** T2 (`session-end`+`status`)… wait — T2 and T3 both write `scripts/status`. Resolve by **assigning T2 and T3 to one agent** (status edits serialized), OR landing T2 first then T3. 
- **Recommended serial-ish plan:**
  1. **T2** (session-end + status sanity guard) — ship first, proves the `fire_hooks` test loop. *(HIGH, low risk)*
  2. **T3** (track-autonomy + append the A4 line to status) — after T2's status edit lands. *(HIGH)*
  3. **T1 + T5** touch `common.sh` — **one agent, serial** (T1 reader wrappers, then T5 enqueue trace), or two agents strictly sequenced. Never concurrent. *(MED/HIGH)*
  4. **T6** (family_fold.py + new CLI — disjoint from all above) — fully parallelizable with step 3. *(HIGH propose-only)*
- Each task pairs with an `adversarial-lite-reviewer` sibling (V11.21 dual-layer).
- Run `scripts/run-tests --regression` only **after** the fan-in (memory: never run regression concurrent with multi-agent fan-out).

---

## Success criteria (each falsifiable by a command; each has a verified test home)

| # | Criterion | Falsifier | Test home |
|---|---|---|---|
| SC1 | `V11_DETECT_RECONCILE=on` → DETECT emits `v11_detect_reconcile` with all four keys; off → none | `fire_hooks(Read)`; grep stderr | `test_e2e_v11_pipeline.py` |
| SC2 | S1 mutates nothing | `md5sum .task-state.json ledger/*.jsonl` before/after | same |
| SC3 | sanity guard prints ⚠ when `counter>50` | seed `.retro-counter=778`; `scripts/status sofly` | new in `test_wave1_fixes.py` |
| SC4 | flock: 2 concurrent `session-end` → counter +=2 (no lost write) | parallel-fire | `test_wave1_fixes.py:493` |
| SC5 | A4 warning iff `level>=4` AND history empty; **+ characterization: empty→block holds** | seed A4+empty; grep "always-block"; assert `return 2` | `test_hook_behaviors.py` / `test_common_sh.py` |
| SC7 | `subject=="unknown" AND files==[]` → rejected (Rule B intact); `agent_id=="unknown"` + valid subject/files → **admitted + trace** | two enqueue calls; assert pending delta=1 | `test_review_queue_helpers.py` |
| SC8 | dry-run proposes merge for same-sprint same-norm pair; nothing across sprints; 0 ledger writes | `fold-reconcile --dry-run` on fixture | `test_family_fold.py:264` |

*(SC6 retired — it belonged to the deferred T4.)* A criterion that cannot be driven to pass/fail by a command does not ship.

---

## Out of scope (operator discipline — demoted, NOT code)

1. **F1/F2 auto-close** — V11.25 post-commit hook owns real shipped→close; auto-close races the agent's own `TaskUpdate(completed)` → `open_tasks` underflow. Discipline: act on the S1-surfaced list.
2. **F4 auto-reset** — manual only; auto-reset risks a reset→accumulate→retro→reset loop.
3. **F3b auto-drain at DETECT** — never at `TaskList`-hook frequency (super-linear spawn across 40+ projects; `feedback_parallel_agent_backend_collision`). Drain at session-end/on-demand.
4. **T4 guarded writer** — deferred to a design spike (see above).
5. **Report's P0 self-fixes** (Haiku probe when spec>30 lines; treat handoff as worklist) — orchestrator discipline; partially mechanized by S1's forced acknowledgment.

---

## References

- Source: `sessions/sofly/v11-improve-v11-opus-2026-06-29-orchestrator.md`
- Memory: `feedback_orchestrator_discipline` (execute the worklist, don't read it as a memo — through-line of all six findings); `feedback_parallel_agent_backend_collision` (drives the sequencing above and the F3b out-of-scope call).
- Wave-1 pinpoints: F1 `handoff:1183`,`handoff-discipline-check:7/163`,`v11-resume-tasks:86`. F2 `guard-stale-task:3/41/91`,`guard-agent-stall:24-27`,`sync-tasks:1875`. F3 `common.sh:2973/2980/3041`,`detect-project:94`,`drain-review-queue:61`,`sync-tasks:1556/1238`. F4 `session-end:170/176`,`v11-retro:27/105`. F5 `track-autonomy:123/95/140-155/241`,`common.sh:1056-1063`. F6 `handoff:1216/1272/1282`,`family_fold.py:196/257/264`.
- Wave-2 contracts: S1 read-APIs (`handoff-discipline-check:163`, `review-queue:151`, inject `detect-project:103`); A4 (`common.sh:1059`, `guard-enforcement:35`, `caller_kind` `common.sh:3249`/`track-autonomy:241`, T4 verdict not-feasible); retro (`session-end:170-182`, flock `common.sh:535`, fd-201, `V11_RETRO_THRESHOLD` `v11-retro:27`); enqueue (`common.sh:2947/3036`, `V11_REVIEW_ENQUEUE_VALIDATE`); fold (`family_fold.py:196`, `normalize_subject:80`, ledger tombstone `common.sh:2425`); harness (`fire_hooks` `test_e2e_v11_pipeline.py:49`); coherence (additive-only, fd-201, `[ -f ]` guard, hook count stays 17).
- Adversarial lenses: skeptic (gap vs operator-error), blast-radius (gate semantics, 40+ project blast), regression (per-fix failure modes + bounding guards).

---

## One-sentence version

Two recon waves confirm one disease — six half-wired loops — and prove the cure is to **mechanize acknowledgment, not actuation**: one read-only DETECT surface (S1, hook count unchanged) plus four verified point fixes (retro flock+guard, A4 dead-gate legibility, enqueue trace, propose-only fold-reconcile), each with an exact insertion point, a reused helper, a named test, and a default-off lever — while the one fix recon proved unsafe (A4 writer) is cut to a design spike rather than shipped on an unreliable guard.
