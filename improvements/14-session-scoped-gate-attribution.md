# Improvement 14 — Session-Scoped Write-Gate + Attribution

- **Status:** SHIPPED (2026-07-20) — commits 48f6436 (F1), 107388a (F2); fixtures 12/12 + 3/3, regression 17/17
- **Version label:** v11.34.2 (deliberately a patch on the v11.34 arc — keeps the stamp-drift anchor at 11.34, no consumer-stamp sweep needed)
- **Provenance:** T4 finding from the v11.34 post-ship adversarial review (`improvements/13` §9). Reproduced by the workflow-integration reviewer.
- **Primary workflow protected:** the user runs **multiple concurrent sessions in different projects** — the case where the aggregate is *always* non-idle.

---

## 1. The problem (reproduced, pre-existing)

`guard-write-gates` and `track-autonomy` both read the **project AGGREGATE** (`~/.agent-metrics/task-state/{project}.json`, the union of ALL sessions) for two per-session decisions:

1. **Masking** — the gate's block decision reads aggregate `.in_progress` (`guard-write-gates:136`, gated `:138`). So whenever *any* sibling session holds a task in_progress, `in_progress ≥ 1` project-wide and the gate goes **completely silent for every other session** — a genuine stall in session B is invisible. v11.34 only fixed the `in_progress==0` case (nobody mid-task), the *least* dangerous moment.
2. **Misattribution** — `track-autonomy` resolves the audit row's `task_id`/`agent_id` from the aggregate's `.active_task_ids[0]` / `.active_agent_id` (`track-autonomy:207,209,216`). So session B's edit — **even an erroring one** — gets stamped with session A's `task_id` and `agent_id`, and `agent-scorecard` Layer 1 (keys purely on `agent_id`, `agent-scorecard:271`) **counts B's error against agent A**.

This is not a v11.34 regression — it predates the whole arc — but it means **"v11.34 shipped" ≠ "multi-session attribution is trustworthy."**

## 2. Why it's safe to fix now (recon-grounded)

The **per-session** task-state file (`$METRICS_DIR/sessions/$(v11_session_uuid)/task-state.json`, resolved by `v11_session_state_path` at `common.sh:124-126`) **already carries** `.in_progress`, `.pending`, `.total`, `.active_task_ids`, and `.active_agent_id` on every non-empty session (`common.sh:84`: "one Claude session owns one file"). So both fixes are **source-swaps with no new plumbing**, and downstream consumers already tolerate the result:

- `agent-scorecard:271` filters on `agent_id` only → a `null` agent_id (session with no active task) correctly counts against **nobody** instead of a sibling.
- `audit-query:100,115,171` treats `task_id` as an honest coverage denominator / optional filter / `-` display → a `null` drops the numerator honestly, no join breaks.

## 3. Design thesis

**A session should be gated on ITS OWN discipline and attributed to ITS OWN work — never the project aggregate.** The aggregate stays the right source for *"is this a task-bearing project at all"* (the `TOTAL ≥ 2` trigger) and for *"is the project globally complete"* (the completion exemption). But the two *per-session decisions* — block-or-not, and who-did-this-edit — move to the session's own file.

Single-session behavior is unchanged (aggregate ≡ session when there's one session). The only *new* blocking is a session editing while neglecting **its own** created-but-unstarted tasks — which is satisfiable (it owns them) and is exactly the discipline the gate exists to enforce.

## 4. Fix set

**F1 — Session-scoped block decision (`guard-write-gates`).**
- `:136` — read `.in_progress` from `$(v11_session_state_path)` instead of the aggregate `$TASK_STATE`; numeric-sanitize (missing own-file → 0). Entry to the block region becomes "THIS session isn't mid-task", not "nobody is".
- Leave the `v11_session_has_open_work` discriminator (`:152`) as the fresh/finished-vs-stall sub-decision (own `pending==0` → advisory; own `pending≥1` → block per mode).
- Keep `TOTAL` (`:122,124`) and the completion exemption (`:125`) aggregate-scoped (project trigger).
- Reword the two block/advisory messages that hardcode "0 in_progress" (`:187,:203`) → "0 in_progress (this session)". The aggregate-sourced pending count at `:158/:168` already says "in the project aggregate" — leave it.

**F2 — Session-scoped attribution (`track-autonomy`).**
- `:207` — point `TASK_STATE_F` at `$(v11_session_state_path)` instead of `$TASK_STATE_DIR/${V11_PROJECT}.json`; relax the `V11_PROJECT` guard (`:206-208`) since the session file is project-independent (self-identifies via `.project`).
- Keep the `.active_task_ids[0]` (`:209`) and `.active_agent_id` (`:216`) reads, now against the session file. The emit block already maps `""` → `null` (`:296-297`), so a session with no active task yields `null` — **no sibling borrowing**.
- `V11_AGENT_ID` env still preferred (`:214`) when present.

## 5. Non-goals

- No change to the aggregate/ledger model, sync-tasks, or the per-session file schema (all keys already exist).
- No downstream consumer changes (verified compatible).
- Not touching the `total<2` / completion exemptions — those are correctly project-scoped.

## 6. Test plan

**F1 (masking fixed)** — extend `tests/test_write_gate_session_aware.sh`; fixtures now drive the decision via the SESSION file:
1. `masking-fixed-stall`: aggregate `in_progress=1` (sibling A active), THIS session own `in_progress=0, pending=1` → BLOCK under default (previously silent). The core proof.
2. `session-active-allow`: own `in_progress=1` (regardless of aggregate) → allow.
3. `fresh-under-active-sibling`: no own file + aggregate `in_progress=1, total≥2` → allow + advisory (not blocked).
4. Update the existing 9 cases so their fixtures set the SESSION file's `in_progress`/`pending` (not just the aggregate) to drive the decision; all stay green.

**F2 (attribution fixed)** — new `tests/hooks/test-track-autonomy-session-attr.sh`:
5. `no-sibling-borrow`: aggregate `active_task_ids=["task-A"], active_agent_id="agent-A"`; THIS session own `active_task_ids=[]` → audit row `task_id:null, agent_id:null` (NOT task-A/agent-A).
6. `own-attribution`: own `active_task_ids=["T7"], active_agent_id="backend-architect"` → row attributed to T7/backend-architect.

Then `run-tests --regression` → 17/17, drift gates clean (v11.34.2 patch keeps anchor 11.34).

## 7. Files touched

| File | Fix | Change |
|------|-----|--------|
| `hooks/guard-write-gates` | F1 | `:136` in_progress read → session file; messaging `:187,:203` |
| `hooks/track-autonomy` | F2 | `:207` attribution source → session file; relax `:206-208` guard |
| `tests/test_write_gate_session_aware.sh` | F1 | session-driven fixtures + 3 masking cases |
| `tests/hooks/test-track-autonomy-session-attr.sh` | F2 | new: no-borrow + own-attribution |
| `docs/CHANGELOG.md` | — | v11.34.2 sub-entry |
| `improvements/13` §9 T4 / `improvements/README.md` | — | mark T4 resolved-by-14 |
