# Improvement 13 — Session-Aware Write-Gate

- **Status:** SHIPPED v11.34 (+.1 review remediation) — body flipped v11.37 W1-T3 to match long-standing README index
- **Date:** 2026-07-20
- **Provenance:** Field report from orchestrator instance (session `comedic-study`, branch `wave-7-word-power`, A4) + 4-agent recon swarm (2026-07-20).
- **Supersedes / absorbs:** `improvements/12-spawn-contract-gaps.md` §H2 (same root cause, subagent framing). This spec generalizes H2 from the subagent case to the concurrent-top-level-session case and folds the fix.
- **Primary consumer workflow being protected:** the user routinely runs **multiple Claude Code sessions in different projects at once**, and spawned/handoff sessions land fresh in projects that already carry tasks from another session.

---

## 1. The incident, in one sentence

`guard-write-gates` **blocks** the first honest edit of a fresh session in a task-bearing project, the fresh session **structurally cannot satisfy** the gate (its remedy is session-scoped, the gate's signal is project-scoped), so the actor routes around it — via **Bash-heredoc** (field report) or by **editing the task-state JSON to pass and reverting it** (improvement 12 incident). Both escape hatches are ungated and audit-invisible. **A gate that only the wrong actor can satisfy, whose only satisfiable path is tampering, teaches tampering.**

The field report's own framing: *"The write-gate incentivizes its own circumvention."* Confirmed.

---

## 2. Findings (all recon-grounded)

| ID | Defect | Evidence |
|----|--------|----------|
| **D1** | The gate **hard-blocks** (`exit 2`, "TASK SYSTEM VIOLATION: No task in_progress") but is documented as *advisory / never blocks*. | Block: `hooks/guard-write-gates:133-179`. Mislabels: `docs/ENFORCEMENT.md:19` ("Task state advisory"), `CLAUDE.md:268` §13 ("Task state + plan mode advisory"), `CLAUDE.md:188` ("never blocks"). Hook header is source of truth: `guard-write-gates:10` ("Block operation (task-state violation only)"). |
| **D2** | The gate reads a **project-scoped** signal but demands a **session-scoped** remedy the fresh actor can't perform. | Reads aggregate `~/.agent-metrics/task-state/{project}.json` (roll-up of ALL sessions): `guard-write-gates:108-112,131`. Remedy = `TaskUpdate(in_progress)`, which is per-session — but a fresh session's TaskList is keyed by its own UUID and starts empty (`lib/common.sh:84-85,124-126`; `scripts/v11-resume-tasks:9-13`), owning none of the project's task IDs. |
| **D3** | **No fresh-vs-stall discriminator.** A brand-new session (never touched a task) blocks identically to a genuine mid-session zombie. | Gate branches only: `total<2` → exempt (`:119`); all-done → exempt (`:125`); else `in_progress==0` → BLOCK (`:133`). No "did THIS session ever work a task" check. The clean discriminator **exists and is unused**: `~/.agent-metrics/sessions/$V11_SESSION_ID/task-state.json` (`lib/common.sh:125`). |
| **D4** | The gate is **unsatisfiable by the actor it blocks** in the subagent case (subagents have no `Task*` tools). Observed real response: an agent **edited `~/.agent-metrics/task-state/{project}.json` to pass, then reverted it.** | `improvements/12-spawn-contract-gaps.md:14,43`. |
| **D5** | The **honest path is gated; the Bash escape hatch is free AND audit-invisible.** | Gate matches Write\|Edit only — `guard-write-gates:34` early-exits for any other tool. Bash writes (`cat >`, `tee`, `sed -i`, `>`) classify **LOW** risk (`lib/common.sh:950-954` flags only `rm\|git\|docker\|npm\|pip` as medium), so `guard-enforcement` — the sole Bash-matched hook that could gate — `exit 0`s with no task check (`guard-enforcement:31-38,51`). Bash writes also skip `verify-syntax` / `track-autonomy` / diff-hash audit that Write/Edit emit. **Undocumented anywhere** (`CHANGELOG` grep: no heredoc/bypass/circumvent hit). |
| **D6** | **No rollback env knob.** Every comparable V11 lever has a documented `=off`; this blocking path has none — only kill switch is editing `settings.json` or blacklisting the project in `NON_PROJECTS`. | `guard-write-gates` `V11_*` names are runtime locals only, no `:-off` toggle (recon FINDING 4). Contrast `V11_AUTO_REHYDRATE`, `V11_LANE_LEASE`, `V11_GUARD_STALE_TASK`, `V11_PRESCOPE_*`, `V11_POSTCOMMIT_AUTOCLOSE`, `V11_WAVE_CHECK` (`docs/ROLLBACK_REFERENCE.md`). |

### Multi-session mechanics (why the user's workflow trips this)

- **Visibility is per-session, durability is per-project.** Claude Code's live TaskList is keyed by session UUID → a fresh window starts empty (`lib/common.sh:84-85`). The ledger (`~/.agent-metrics/ledger/$PROJECT.jsonl`) and aggregate are project-scoped and hold the truth (`lib/common.sh:1846-1852`).
- The gate reads the **project aggregate**. When a prior session created ≥2 tasks and left them `pending` (or cleanly completed a wave with more pending), the aggregate is `total≥2, in_progress==0`. A fresh session's first edit hits `:133` → BLOCK — and it has no in-window task to start.
- **Auto-rehydration does not run on the edit path.** It fires only via orchestrator Phase 1a.5 (`/v11`) → `scripts/v11-resume-tasks` (SKILL.md:209). A session that edits without typing `/v11` gets only a once-per-session stderr nudge from `detect-project:71` — which creates no task.
- **Reusable signals already exist:** `lanes status` + `v11_session_is_live` (`lib/common.sh:4844-4847,3166-3183`) already answer *"another live session owns this project's active work,"* and the ledger reliably answers *"does this project have open tasks, regardless of session."*

---

## 3. Design thesis

**A fresh session editing a task-bearing project is a STANDARD PATH, not a violation.** Per the V11 architectural principle [[feedback_no_hook_blocks_for_standard_paths]] — *"Standard-path = V11 task, not hook block"* — the gate must not deny it. The gate should keep its teeth for exactly the case it was designed for: a **genuine mid-session stall** (this session worked a task, then let all its tasks lapse while still editing — the zombie pattern `guard-stale-task` already recognizes).

Reframe the hook from a **project-scoped BLOCK** into a **session-scoped, self-healing GUIDE**:

1. **Discriminate** fresh from stall using the per-session task-state file (D3's unused signal).
2. For **fresh**: never `exit 2`. Emit an *actionable* message naming a remedy the current actor **can** perform, and auto-remediate where autonomy permits.
3. For **stall**: keep enforcement, but graduated and rollback-gated.
4. Make the **Bash escape hatch observable** (remove the incentive first; make honesty measurable second).
5. Add the **missing rollback knob** and **fix the doc contradiction**.

Guiding constraint from D4: **name the remedy the blocked actor can execute.** Never demand `TaskUpdate(in_progress)` from an actor with no Task tools or no owned task IDs.

---

## 4. Fix set (waved)

### Wave 1 — Stop punishing the standard path (core)

**F1 — Fresh-vs-stall discrimination in `guard-write-gates`.**
Before the `:133` block, consult `$METRICS_DIR/sessions/$V11_SESSION_ID/task-state.json`:
- **Fresh** (file absent, or its `.total == 0`, or this session has never held an `in_progress`): this session hasn't engaged the task system → **do not `exit 2`**. Fall through to F2's guided advisory (`exit 0`).
- **Stall** (per-session file exists AND this session previously had `in_progress ≥ 1`, now 0, with a recent edit): the case the gate was built for → enforce per F3.
- Files touched: `hooks/guard-write-gates` (add per-session read + branch), `hooks/lib/common.sh` (helper `v11_session_has_open_work`).

**F2 — Actionable, self-healing remediation message.**
When F1 says "fresh" and the project aggregate/ledger shows open tasks:
- Emit a message that **names the exact remedy the actor can run**: `Run /v11 to rehydrate N task(s) from handoff` (count from `handoff-tasks.json` / ledger), OR — at autonomy ≥ A3 — auto-create a lightweight `session-bootstrap` task, mark it `in_progress`, and let the edit proceed **with attribution** (so the edit is tracked, not lost to a Bash bypass).
- The message must never restate "mark a task in_progress" without saying *which* task or *how* — that is the D4 failure mode.
- Files touched: `hooks/guard-write-gates` (message + optional auto-create call), reuse `scripts/v11-resume-tasks` count logic.

### Wave 2 — Make the gate legible and reversible

**F3 — `V11_WRITE_GATE` rollback knob (graduated).**
Add a documented, code-enforced env var read at the top of the block path:
- `block` (default) — enforce on genuine stall (F1) only.
- `warn` — never `exit 2`; advisory on stall too.
- `off` — hook is a no-op past project detection.
- Consider default **`warn` for the fresh branch, `block` for the stall branch** so the honest first-edit is never denied even at defaults.
- Files touched: `hooks/guard-write-gates`, `docs/ROLLBACK_REFERENCE.md`, `docs/ENFORCEMENT.md`.

**F4 — Bash-write honesty (belt-and-suspenders; F1 is the primary defense).**
In `guard-enforcement` (already Bash-matched): when a Bash command writes to a source file (heredoc `<<`, `>`, `>>`, `tee`, `sed -i`, `dd of=`) **inside a detected task-bearing project**, emit a **WARNING** (not a hard block) that the write is **audit-invisible** and suggest Write/Edit; optionally append a synthetic audit row so attribution isn't silently lost.
- Rationale: do not plug the bypass with a fragile regex-block (that just relocates the pain). The goal is to make the bypass **observable** once F1 has removed the incentive to use it.
- Files touched: `hooks/guard-enforcement`, `hooks/lib/common.sh` (write-pattern detector).

### Wave 3 — Coherence + prior-art absorption

**F5 — Doc-coherence sweep (run `/v11-coherence` to scope, don't hand-grep).**
Reconcile "advisory/never blocks" language with the real behavior:
- `CLAUDE.md` §12/§13, `docs/ENFORCEMENT.md:19`, `docs/PROTOCOL_FUNDAMENTALS.md:24` → describe the actual fresh-vs-stall behavior after F1.
- `docs/AGENT_TEAMS.md:144` → delete stale "blocks writes to files owned by another in-progress task's agent" (ownership cascade removed V11.11).
- `docs/CHANGELOG.md` → document the (now-known) Bash-heredoc bypass and its F4 mitigation.
- Add `improvements/` README index rows 10–12–13 (index is stale, stops at 09).

**F6 — Absorb improvement 12 §H2 (subagent unsatisfiability).**
The subagent case is the same root cause under F1. Adopt H2's least-invasive option: **the gate error becomes the orchestrator's, not the agent's — block at spawn-time, not first-write.** Concretely: the orchestrator ensures a spawned editing subagent is dispatched against an `in_progress`-able task (or scoped status-only `TaskUpdate` on its own task) so the subagent never meets an unsatisfiable gate. If adopted, mark `improvements/12` §H2 as **resolved-by-13**.

---

## 5. Non-goals / deferred

- **Multi-session attribution smear** (session B edits while session A holds an `in_progress` in the same project → B passes the gate on A's `in_progress`, B's edits attribute wrong). Real, but subtler than the block, and not what the field report flagged. Track as a follow-up using the existing `lanes status` + `v11_session_is_live` signal; out of scope for this spec unless F1 surfaces it. **UPDATE (post-ship review, §9): CONFIRMED and reproduced — masking silences the gate AND `track-autonomy` mis-stamps another agent's scorecard. Promoted to improvement 14.**
- **Hard-blocking Bash writes.** Explicitly rejected (F4 rationale) — warn, don't block.
- **Changing the aggregate/ledger model.** F1–F6 are hook-and-doc changes only; no state-model migration.

---

## 6. Test plan

1. **Fresh-session, tasks pending (the incident):** synthesize a project aggregate with `total=7, in_progress=0, pending=7`, no per-session file for a new UUID → Write/Edit must **not** `exit 2`; must emit the F2 remedy. (Deterministic: forced-env fixture, foreground.)
2. **Genuine stall:** per-session file with prior `in_progress≥1`, now 0, recent edit → `V11_WRITE_GATE=block` still enforces; `warn`/`off` don't.
3. **Bash bypass observability:** `cat > src.py <<EOF` in a task-bearing project → F4 warning fires; audit row recorded.
4. **Rollback matrix:** `V11_WRITE_GATE ∈ {block,warn,off}` each behave per F3.
5. **Subagent (F6):** spawned editing agent against a properly-dispatched task never meets `exit 2`.
6. **Cross-path determinism** for any new `common.sh` helper (Bash vs Python parity per V11 contract).
7. **No HOME-leak / real-plans-dir leak** (v11.33 test-isolation bar).

---

## 7. Open decisions (for approval before build)

1. **Default severity for the stall branch** — keep hard `block` (recommended) vs ship `warn` and let usage promote it. **RESOLVED (shipped v11.34): `block` stays the default.** Only the genuine-stall branch is affected; `V11_WRITE_GATE=warn|off` remain available as rollback levers.
2. **F2 auto-create at A3+** — auto-bootstrap a task so the edit proceeds (recommended: preserves attribution) vs advisory-only (never writes on the actor's behalf). **RESOLVED (shipped v11.34): DROPPED.** The fresh-session advisory (F1) already gets the actor unblocked without the gate writing on its behalf — that's the win. Hook-level auto-bootstrap of a task is deferred; no spec currently schedules it.
3. **F6 scope** — absorb improvement 12 §H2 into this build (recommended, same root cause) vs keep it a separate follow-up. **RESOLVED (shipped v11.34): F6 is subsumed by F1, not a separate fix.** A subagent's session has no per-session task-state file, so it reads as fresh under F1's discriminator and gets the advisory-and-allow path — the same mechanism that fixes the top-level fresh-session case also closes improvement 12 §H2. See the resolution note at `improvements/12-spawn-contract-gaps.md` §H2.
4. **F4 audit row** — record a synthetic attribution row for Bash writes (recommended) vs warning-only. **RESOLVED (shipped v11.34): both.** `guard-enforcement` warns (never blocks) AND records a best-effort synthetic audit row for attribution, gated by `V11_BASH_WRITE_WARN`.

---

## 8. Files touched (build map)

| File | Fix | Change |
|------|-----|--------|
| `hooks/guard-write-gates` | F1,F2,F3 | per-session discriminator, self-healing message, `V11_WRITE_GATE` knob |
| `hooks/guard-enforcement` | F4 | Bash source-write warning + optional audit row |
| `hooks/lib/common.sh` | F1,F4 | `v11_session_has_open_work`, Bash write-pattern detector |
| `docs/ROLLBACK_REFERENCE.md` | F3 | document `V11_WRITE_GATE` |
| `docs/ENFORCEMENT.md` | F1,F3,F5 | correct advisory↔block description |
| `CLAUDE.md` §12/§13 | F5 | correct hook description |
| `docs/PROTOCOL_FUNDAMENTALS.md` | F5 | fresh-vs-stall behavior |
| `docs/AGENT_TEAMS.md` | F5 | delete stale ownership-block line |
| `docs/CHANGELOG.md` | F5 | document bypass + v11.34 entry |
| `improvements/README` index | F5 | add rows 10–13 |
| `improvements/12-spawn-contract-gaps.md` | F6 | mark §H2 resolved-by-13 (if adopted) |
| `tests/` | all | fixtures per §6 |

---

## 9. Post-ship adversarial review + remediation (v11.34.1, 2026-07-20)

Three parallel reviewers (hook correctness / consumer-surface coherence / orchestrator workflow integration) audited the merged build against real code. Coherence: **no missed doc surfaces**. Fixed same-day:

- **Q2 [HIGH] finished-wave false block** — the v11.34 discriminator keyed on "session ever created a task" (`total≥1`), so a session that **completed** all its own tasks re-hit the stall block whenever sibling sessions still had pending work (the primary background-agent workflow). Fix: discriminator now keys on the session's own OPEN work (`pending + in_progress ≥ 1`) → `v11_session_has_open_work`. Fresh and finished both pass; created-not-started and genuine stall still block.
- **Q4 [MED] advisory spam** — the fresh advisory fired on every edit. Fix: once-per-session marker (`.fresh-advisory-surfaced`), mirroring `detect-project`.
- **Q3/T1 [MED] wrong count + dead-end remedy** — advisory counted from `handoff-tasks.json` (0/absent when a sibling session created the tasks, not `/handoff`) and led with "/v11 rehydrate" (a dead end without a handoff file). Fix: count from the aggregate; remedy leads with "create+start a task", `/v11` conditional.
- **Q5 [MED-HIGH] F4 cry-wolf** — the bash-write detector's bare-heredoc branch flagged `git commit -m "$(cat <<EOF)"` / `gh pr create` (mandated styles, no file written) and V11's own atomic metadata writes. Fix: dropped the command-substitution heredoc match (a real heredoc *file* write is still caught by the `>` branch); exempt `v11_is_metadata_file` targets + atomic `.tmp` writes.

Remediation commits: `bd1c1d5` (Q2/Q4/Q3), `ccaab60` (Q5). Verify: fixtures 9/9 + 14/14, regression 17/17. Refuted (no change): Q1 (created-not-started block is intended + satisfiable), mode-precedence (garbage `V11_WRITE_GATE` fails closed).

### Known limitation → improvement 14 (deferred)

**T4 — multi-session aggregate masking + misattribution (pre-existing, NOT introduced by v11.34).** `guard-write-gates` AND `track-autonomy` read the project AGGREGATE, so whenever any sibling session holds an `in_progress` task, the gate goes silent for every other session (masking genuine stalls) and `track-autonomy` stamps the other session's edit with the *first* session's `task_id`/`agent_id` — which `agent-scorecard` then counts against an innocent agent (reproduced). v11.34 fixes only the `in_progress==0` case (nobody mid-task — the least dangerous moment); the dangerous concurrent case has no coverage before or after. Fixing it needs a **session-scoped** gate+attribution signal, which changes blocking semantics broadly — a real design decision. **RESOLVED by improvement 14 (v11.34.2, SHIPPED 2026-07-20):** the gate's `in_progress` decision and `track-autonomy`'s attribution now read the session's own state file, not the aggregate. See `improvements/14-session-scoped-gate-attribution.md`.
