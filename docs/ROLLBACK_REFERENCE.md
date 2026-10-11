# V11 Rollback Reference

> Quick lookup for all env-var rollback levers. Each can be toggled independently.

## Unreleased — S1 field-review fixes (2026-09-30)

From the example-project agent's field review (tasks #1, #3, #4, #5; project v11-leverage-program, sprint S1-field-review).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_WORKTREE_BASE_CHECK` | on | `off` turns off both worktree-base checks. One is `guard-worktree-isolation`'s spawn-time `WORKTREE BASE ADVISORY` (local HEAD ahead of `origin/HEAD` or `origin/<branch>`). The other is `worktree_registry.py`'s resolve-time `WORKTREE BASE STALE` (a worktree created for the spawn sits N commits behind HEAD-at-spawn). |
| `V11_WORKTREE_BASE_WARN_MIN` | 1 | Smallest ahead-count that triggers the spawn-time advisory. |
| `V11_WORKTREE_GUARD_CONTEXT` | on | `off` makes `guard-worktree-isolation` output plain text only (transcript-only). By default it also emits one `additionalContext` JSON object, so the model receives the advisory, `STALE-REF`, `WORKTREE BASE STALE` and `ISOLATION ALERT`. Before this, none of them reached the model. |
| `V11_HANDOFF_REASONING_STAMP` | on | `off` restores the plain `## Reasoning Context` header. When on, the header shows the `.plan-context.json` mtime and says STALE once the file is past the max age. |
| `V11_HANDOFF_REASONING_MAX_AGE_DAYS` | 14 | Age in days after which the Reasoning Context header says `STALE: N days old`. |
| `V11_HANDOFF_ACTIVE_FROM_OPEN_SET` | on | `off` takes `Active tasks:` from the state file's `active_task_ids` again, which can be stale. When on, it lists the `in_progress` entries of the #75 live open set. |
| `V11_HANDOFF_REVIEW_SEG_SCOPE` | on | `off` shows the `Review-pending: N` segment for aggregate state sources again. The number is total minus the other counts summed across all sessions, which is how the field review got 347. Per-session sources are unaffected. |

No new lever for the `Key Decisions` fix: decisions whose title or chosen is null or empty are dropped before the last-3 cut. Rollback = revert commit `cec482f`. No new lever for sync-tasks Strategy 1.7's `cwd-hercules-root-match` fallback: `V11_TASK_PROJECT_AUTODEFAULT=off` still skips all of 1.7.

## v11-leverage-program S2 — Fast Core (unreleased)

### S2-R5 Session-End Project Binding

No lever for the session-id rule: `hooks/lib/common.sh` `v11_valid_session_id` (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`, builtins only) replaces the old `^[a-zA-Z0-9._-]{1,64}$` everywhere a session id becomes a `sessions/<id>` path. `v11_parse_input`, `hooks/session-end`, `hooks/enforce-subagent` and `hooks/completion-hint` drop an id that fails it (it reads as no id; session-end logs `why=invalid-session-id` and does no per-project work). `v11_read_active_project` tier 1, `v11_write_active_project` (scoped file and owner line), `v11_session_uuid`, `v11_session_is_live`, the session-end sitting marker, the exactly-once claim, the scratch retirement and the fold use the same check. `scripts/handoff` and `scripts/lib/context_tracker.py` carry the same rule inline. `.`, `..` and dot-names (`.gc-quarantine`) are rejected: with the old ERE, a `SessionEnd` with id `.gc-quarantine` under `V11_SESSION_GC_MODE=remove` deleted the quarantine, and `..` wrote the sitting marker into the metrics dir. Rollback = revert the commit.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_SESSION_END_REQUIRE_BINDING` | on | Side finding SF1 (#85 class). `hooks/session-end`, on a `Stop` or `SessionEnd` payload with a `session_id`: the per-project work (`last_session_end` stamp, discipline check, `last-session.json`, auto-emit of `handoff.md`/`handoff-tasks.json` incl. steer consumption, session-log row, retro counter, `.session-manifest.json`, plan-sync, align-aggregate) runs only for a project the session is bound to: its scoped `sessions/<sid>/active-project`, the global file's owner line (a resumed sitting whose scratch was quarantined), its own `task-state.json` stamp, or a `"session_uuid":"<sid>"` row in `ledger/<project>.jsonl`. A `SessionEnd` with `reason=resume` (a launch session replaced by an in-process `/resume`) needs the task-state or ledger evidence. Otherwise the work is skipped and `session-end.log` gets `handoff_skipped_unbound session=<sid> reason=<r> project=<p> why=no-binding\|resume-no-work`; the session's own scratch still retires (quarantine) and the GC and orphan detector still run. align-aggregate no longer falls back to the raw global file. Payloads without `hook_event_name` or `session_id` (hand runs) keep the global fallback. `=off` → the project comes from `v11_read_active_project` alone, global fallback included (pre-S2-R5). Test: `tests/test_session_end_binding.py` (regression-marked cases fail on the pre-S2-R5 hook). |

### S2-R6 guard-worktree-isolation Single Pass

The TaskList reconcile of `hooks/guard-worktree-isolation` is one `python3 -I -S hooks/lib/worktree_registry.py` pass over the host-global `$METRICS_DIR/worktree-expectations.jsonl` (was 4-6 `jq` + a `date` per row: 580 forks / ~8.9 s per TaskList on a 150-row fixture of the live registry; now 32 / ~0.34 s for the whole hook, of which the reconcile is 3 forks and ~30 ms, and 29 forks are the shared start-up). Same rules and the same alert / stale-ref text and rewritten rows, byte for byte; a value `json.dumps` cannot print as jq 1.6 does (float, integer ≥ 10^15, `-0`, DEL, lone surrogate or invalid UTF-8) goes through the old per-row `jq` call. Lines only jq 1.6's lenient number parser accepts (`01`, `.5`, `+1`, `inf`) are copied rather than judged. The hook runs `git` only when a row can still be pending (one `rev-parse --show-toplevel HEAD`, one `worktree list`) and rewrites the file (tmp + rename) only when something changed. The single pass has no lever: rollback is a revert of the S2-R6 commit. Tests: `tests/test_guard_worktree_isolation.py` (`TestSinglePassReconcile`, `TestRegistryPrune`, `TestRepoScope`, `TestForkBudget`, `TestTimestampParsing`, `TestExoticRows`).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_WORKTREE_REGISTRY_TTL_DAYS` | 14 | S2-R6. The TaskList pass drops `alerted`/`resolved` rows whose `ts` is more than this many days old (parsed as `date -d` would; a row whose `ts` does not parse stays). Pending rows and rows with any other status are never pruned. `0` = never prune (pre-S2-R6); a non-integer falls back to 14. |
| `V11_WORKTREE_GUARD_SCOPE` | repo | S2-R6. `repo`: a pending row is judged only by a TaskList whose repo toplevel (`git rev-parse --show-toplevel`, else the cwd — the rule the spawn side records `repo_root` with) equals the row's `repo_root`; another repo's rows are copied untouched until that repo's own TaskList. A row with no `repo_root` is judged anywhere. `=all` → every pending row is judged against the current repo's worktree count and HEAD, whichever repo recorded it (pre-S2-R6: another project's spawn was alerted, or resolved, against the wrong worktree list, and the alert went to the wrong session). |
| `V11_WORKTREE_ISOLATION_GUARD` | on | improvements/12 H1 (documented at S2-R6; was silent). `=off` → the hook exits before recording a spawn or reconciling at TaskList. |
| `V11_WORKTREE_GRACE_SECONDS` | 120 | improvements/12 H1 (documented at S2-R6; was silent). Tuning knob: a pending row younger than this stays pending. S2-R6: a non-integer falls back to 120 (it used to judge every row at once, with a bash error per row). |
| `V11_WORKTREE_PENDING_TTL_DAYS` | 30 | Review #11 MED-1. `V11_WORKTREE_REGISTRY_TTL_DAYS` only prunes terminal (`alerted`/`resolved`) rows, and a pending row is otherwise judged only by a TaskList that sees `NEED_GIT` and, under `V11_WORKTREE_GUARD_SCOPE=repo`, matches its `repo_root` — a repo that never runs `TaskList` again leaves its pending row in the host-global registry forever. This cap prunes any pending row past this many days regardless of scope or `NEED_GIT`, silently (no alert: there is nothing to report on a row no repo is coming back to reconcile). `0` = never prune on this cap (falls back to the pre-existing behavior: pending rows are pruned only if this cap is nonzero); a non-integer falls back to 30. |
| Locking (no lever) | — | Review #11 LOW-2. The TaskList reconcile's read-compute-replace of the registry and the Task\|Agent spawn's append to it both take a non-blocking `flock` on a sibling `$REGISTRY.lock` (the reconcile via `fcntl.flock` in `hooks/lib/worktree_registry.py`, the append via the `flock` binary, bounded at 2s). The reconcile skips its whole pass (no read, no alert, no rewrite) if it can't get the lock — a TaskList must never block on it, and the registry is retried whole next time. The append runs either way, lock or not: dropping the expectation row would be worse than the rare clobber the lock guards against. Rollback: revert the commit (no env var; this is a correctness fix, not a tunable). |

### S2-T4 Single-Pass `v11_parse_input` + sync-tasks Metadata Fold (+ review-#14 fixes, task #15)

`hooks/lib/common.sh` `v11_parse_input` collapses its 7-9 per-field `jq` forks (`tool_name`, `file_path`, `command`, `session_id`, `error`, `cwd`, and the `tool_response`/`tool_output` fallback with its string-unwrap) into one `jq -j` pass whose fields are NUL-delimited and read back with one `read -r -d ''` per field (not `@tsv`: it would escape embedded tabs/newlines in free-text fields like task descriptions instead of passing them through). `hooks/sync-tasks` does the same for the 7 `metadata.*` fields it reads per task (`complexity`, `spec_test_requirements` length, `agent`, `scope`, `deliverable_of`, `review_of`, `blocker`). `V11_CWD` is now populated from `.cwd // .working_directory` (previously `.working_directory` only, which real payloads never set — `V11_CWD` was always empty pre-S2-T4, so every `${V11_CWD:-...}` fallback silently always took its `else` branch). This activates `V11_CWD` fleet-wide for the first time, including in `sync-tasks` Strategy 1.7 (cwd-sessions-match, pre-existing V11.36 logic that was dead until now) and `hooks/guard-worktree-isolation`'s `_repo_root()` / TaskList `REPO_ROOT` line. No lever for the single-pass rewrite itself: rollback is a revert of the commit. Tests: `tests/test_common_sh.py` (`TestParseInput`), `tests/test_v11_parse_input_parity.py` (review-#14 E2, below), `tests/test_sync_tasks_fork_budget.py`, `tests/test_sync_tasks_taskget_tasklist_skip.py`.

Review #14 (task #15) found and fixed four issues in the S2-T4 merge:

- **HIGH (E1), fixed.** The single-pass `tool_response` branch used a `strize` helper (`if type == "string" then . else tojson end`) that stripped quotes from a bare non-JSON `.tool_response` string (`"hello"` → unquoted `hello`), producing invalid JSON where the pre-S2-T4 code (`jq -c '.tool_response // empty'`) always emitted a validly-quoted string. Fixed by always `tojson`-ing the `tool_response` branch's result (never `strize`); `strize` now only guards the legacy `.tool_output` raw-text fallback, where the value must stay unquoted. Verified byte-for-byte against the old `jq -c` + unwrap logic across bare-string, object, array, number, `null`, `false`, empty-string and S81-W0-2 JSON-string-wrapper `.tool_response` shapes.
- **MEDIUM (E2), fixed.** No checked-in regression test compared `v11_parse_input`'s output field-for-field against the pre-S2-T4 implementation. `tests/test_v11_parse_input_parity.py` embeds the frozen pre-S2-T4 function body (from `dc5b227^1`, not read from git history at test time) and runs both parsers over a real-shaped payload corpus (TaskCreate/TaskUpdate/TaskGet/TaskList/Agent/Read/Bash/Stop/SessionEnd/PreCompact/SubagentStop/UserPromptSubmit shapes; bare-string/object/array/number/null/false/wrapped-JSON-string `tool_response`; newline/tab/backslash/unicode/quote payloads; missing fields), asserting every `V11_*` var matches except the one deliberate difference (`V11_CWD`, see below). Fails on `dc5b227` (pre-fix) for the E1 case; passes after the fix.
- **MEDIUM (E3), resolved by keeping `.cwd`.** `hooks/guard-worktree-isolation`'s `_repo_root()` (`${V11_CWD:-$(pwd)}`) and the TaskList branch's `REPO_ROOT=${V11_CWD:-$PWD}` were dead-code fallbacks that S2-T4 activates fleet-wide. Decision: keep `.cwd` — it is the harness's own report of the *calling* session's cwd (the orchestrator's, for the Task\|Agent PostToolUse this hook fires on; the calling session's, worktree-isolated or not, for TaskList), which is exactly what this hook needs to compare worktree counts in the right repo, and it is decoupled from whatever directory the hook subprocess itself happens to be launched from (existing precedent: `hooks/session-end`'s project-dir resolution already falls back to the stdin `cwd` over relying solely on `$CLAUDE_PROJECT_DIR`/pwd). `tests/test_guard_worktree_isolation.py::TestPayloadCwdPrecedence` pins this: it fires both the spawn-time and TaskList-reconcile payloads with `.cwd` pointing at one repo while the hook subprocess's own OS-level cwd is a *different* repo, and asserts `repo_root`/`REPO_ROOT` resolve from `.cwd`. No lever: revert the commit to go back to `$(pwd)`-only.
- **LOW (E4), documented (no code change).** `hooks/sync-tasks`'s `META_BLOCKER` extraction changed from `jq -r '.blocker // ""'` (pretty-printed multi-line JSON when `.blocker` is an object) to the single-pass `if type == "string" then . else tojson end` (compact single-line). Confirmed: `META_BLOCKER` is only ever read in truthy checks (`-n`, `!= "null"`, `!= "false"`, `!= "0"`) — no downstream consumer line-anchors on its formatting, so this is safe as-is.

## Unreleased — v11-leverage-program S2 (Fast Core)

### S2-T1 Measured baseline

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_SYNC_TASKS_PROFILE` | off | Opt-in profiler, not a rollback lever. `hooks/sync-tasks`: on only for `1`/`on` (→ `$METRICS_DIR/sync-tasks-profile.jsonl`) or an absolute path; any other value (`0`, `false`, `no`, `off`, empty, a relative path) is off. When on, every invocation appends one JSONL row at exit: `{ts, t0_us, pid, tool, task_id, ms, marks_us}`, with seven phase marks (init, resolve, load, branch, write, ledger, aggregate). Builtins only, so it adds 0 forks; off costs one `case` and no file IO. It does not count forks — `tests/forktrace.py` does, from outside. Test: `tests/test_sync_tasks_fork_budget.py`. Baseline: `sessions/v11-leverage-program/recon/S2-baseline.md`. |

### S2-T2 TaskGet Early Exit + No-op TaskList Skip

`hooks/sync-tasks` forks at minimal / live scale (`tests/forktrace.py`, S2-T1 fixtures): TaskGet 126 / 195 → 27 / 27 (jq 33 / 79 → 8 / 8); a TaskList that repeats the last one 201 / 270 → 74 / 74 (jq 57 / 103 → 16 / 16); a TaskList that changed 201 / 275 → 189 / 263. Two changes carry no lever and change no output: the heartbeat computes the session id with `v11_session_uuid`'s rule inline and runs `mkdir` only for a missing dir (−2 forks on every call), and the TaskList pass reads "is the output the structured form" once instead of six times (−10). Tests: `tests/test_sync_tasks_taskget_tasklist_skip.py`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_TASKGET_EARLY_EXIT` | on | S2-T2. A TaskGet refreshes the session heartbeat (`sessions/<sid>/.heartbeat`) and exits. It no longer loads or rewrites the session scratch (its `last_updated` and mtime stay: a read is not progress, #87), writes the active-project files, drains a v11.33 `.needs-reconcile` marker (the next locked TaskCreate/TaskUpdate/TaskList does), rebuilds the aggregate, or records a context-tracker `task` event (~300 estimated tokens per TaskGet, and its threshold line on stdout). TaskGet never wrote a ledger line or a live snapshot. `=off` → the full pre-S2 pipeline on TaskGet. |
| `V11_TASKLIST_NOOP_SKIP` | on | S2-T2. A full TaskList pass writes `sessions/<sid>/.tasklist-fp` after its scratch write: one header line (`s2t2-v1`, project, TOTAL_ACTUAL, structured 1/0, the list filter, joined on `\x1f`) and the `tool_response` it reconciled. A later TaskList is a no-op when that file holds its project and `tool_response` byte for byte (and its filter, when the list had tasks), and the scratch loaded valid, is not newer than the fingerprint, had no reconcile marker drained by this call, and FD-201 was held. The no-op still writes the live snapshot (`ledger/<project>.live-snapshot.json`, fresh `ts`; `scripts/handoff` reads it) and still runs the discipline nudge, active-project write and context tracker; it skips the recount and orphan-id trim, the findings recompute, the scratch write (its `last_updated` and mtime stay) and the aggregate rebuild (`aggregate_built_at`, the mirror's mtime and, on a legacy-fold project, `last_updated` move only with a real change). A changed list, another filter or project, a missing, invalid or since-rewritten scratch take the full pass, which repopulates the scratch. A full pass whose rebuild fails removes the fingerprint. `=off` → every TaskList takes the full pass and no fingerprint is written. |

### S2-T3 Progress Clock (#87)

`guard-agent-stall` measured elapsed time from `.last_updated`, but `hooks/sync-tasks` also bumps `.last_updated` on every TaskList (full pass) and, pre-S2-T2, every TaskGet — a passive poll, not progress. Because Claude Code runs matching hooks in parallel, whenever `sync-tasks` won the race against `guard-agent-stall` on the same TaskList, the stall clock read ~0: stall detection measured "time since the orchestrator last polled", not "time since progress". Fix: `hooks/sync-tasks` now also stamps `.last_progress_at` at the same six sites that already write `.last_updated` for a real state transition — TaskCreate, and the TaskUpdate status arms `in_progress`, `completed`, `blocked`, and both `deleted` branches (cancelling a live task and removing an already-completed one) — as one extra `.last_progress_at = $now` stage appended to each existing jq filter (0 new forks). It is never written by TaskList, TaskGet, or the field-only TaskUpdate arm (subject/description change with no status flip). `hooks/lib/common.sh`'s `v11_reapply_terminal_fold` (the v11.33 scratch-reconcile marker drain, a recovered lost completed/blocked write) stamps it the same way.

The per-session field alone does not reach `TASK_STATE_DIR/<project>.json` (what `guard-agent-stall` reads) on its own — `v11_rebuild_project_aggregate` derives the aggregate from scratch on every call, two different ways depending on whether the project's ledger has cut over (`V11_LEDGER_CUTOVER`, on by default once a project's ledger catches up to its legacy fold):
- **Legacy fold** (no/behind ledger, or the lever off): folds every contributing session's `last_progress_at` with `max()`, exactly like `last_updated`, falling back to that session's own `last_updated` when it predates #87.
- **Ledger cutover** (the common case): `v11_replay_ledger`'s replay output never carries `last_progress_at` — deliberately left out of that function's ADR-governed determinism contract (same reason it is in the `WALLCLOCK` exclusion set alongside `last_updated`/`aggregate_built_at`, so the shadow-reconciliation diff does not flag it as drift on every rebuild). Left alone, cutover would silently regress every project to the pre-#87 fallback the moment its ledger caught up. The cutover write derives it instead as an additive jq pass over the ledger file — max `ts` across every status-changing event (`created`/`in_progress`/`completed`/`blocked`/`cancelled`) — merged onto the replay before writing, `--rawfile` + a per-line `try fromjson catch null` inside the **same** jq process that already writes the aggregate (0 new forks; tolerates one malformed ledger line instead of aborting the whole parse, matching `v11_replay_ledger`'s own per-line tolerance).

Tests: `tests/test_hook_behaviors.py::TestGuardAgentStall` (progress-clock field-preference cases against hand-authored state), `tests/test_stall_progress_clock.py` (end-to-end via real hook calls: legacy-fold hook-order independence, and the ledger-cutover path deriving + preserving the field across a passive TaskList), `tests/test_shadow_diff.py` + `tests/test_ledger_replay.py` (WALLCLOCK exclusion unaffected), `tests/forktrace.py` via `tests/test_sync_tasks_fork_budget.py` (fork/jq-exec counts must stay unchanged — this is what caught the first draft's extra `jq -rs`/`--slurpfile` fork).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_STALL_PROGRESS_CLOCK` | on | S2-T3 (#87). `guard-agent-stall` reads `.last_progress_at // .last_updated` instead of `.last_updated` alone, so a TaskList/TaskGet poll that happens after the last real status change cannot reset the stall clock — the reported elapsed time is since the last TaskCreate/TaskUpdate status change, whatever order the hooks ran in. `=off` → reads `.last_updated` only (today's pre-S2-T3 behavior; a passive poll can still re-arm the clock). |

### S2-T0b-2 TaskList Epoch Write Side + Rehydrate Identity (#113, #111)

Design: `sessions/v11-leverage-program/artifacts/s2-t0-epoch-design.md` §3, §6, §10 steps 2-3, amended by review #19 (§11 C1-C9). Deploy step: `scripts/task-epoch-seed --apply` (dry run without `--apply`) seeds the epoch records of sessions live at rollout and materialises the legacy alias sidecars; re-run its `--aliases` part after any period with `V11_REHYDRATE_IDENTITY_WRITE=off`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_TASKLIST_EPOCH` | on | #113 write side. `hooks/sync-tasks` keeps `$METRICS_DIR/tasklist-epochs/<session>` (append-only, one snapshot line per TaskCreate, the last complete line counts: `v1 <tl_epoch> <fresh|reuse|seed> <sitting|-> <tool_use_id|-> <,id:tu8,...,> <max|-> <,sitting,...,> <,pending id,...,> <-|from:,carried id,...,>`, the last three fields optional on read (review #26); rewritten to its last line past ~64 KB (tmp + rename); `hooks/lib/common.sh` `v11_tl_epoch_read` / `v11_tl_epoch_on_create`, bash builtins only) and opens a TaskList epoch at a session's first TaskCreate (`fresh`) or when a TaskCreate reuses an id of the current epoch with a different `tool_use_id`, or comes from a claude process (`CLAUDE_PID` + `/proc` starttime) not in the epoch's sitting set (at most 8; processes sharing a session id never open one by interleaving) with an id not above the epoch's max (`reuse`). An id reuse by the sitting that joined last carries the ids it created since joining into the new epoch; a carried task keeps the epoch it was created in as its stamp (`v11_tl_epoch_read SESSION TASK_ID`, `task_epoch.epoch_for_task`). A re-fired PostToolUse for any create of the epoch opens nothing; an empty or garbled record opens nothing and stamps nothing, and the next create appends an epoch-0 seed line so tracking resumes. Every event sync-tasks appends carries `tl_epoch` (an int; `v11_ledger_append` stamps it, never on `review` rows, never for other processes); the opening create carries `tl_open`. Also: `open_tasks[id]._tl_epoch`, `recent_completed[].tl_epoch`, `blocked_tasks[].tl_epoch`, `_terminal_idk[id]._tl_epoch`, the live snapshot's `tl_epoch`; the review-queue pending row's `parent_identity {subject_norm, create_seq}` + `tl_epoch` (and "already pending" ignores a row naming another `parent_identity`); dispatch-trace rows' `session_uuid` + `tl_epoch` (`scripts/dispatch-trace-append --session-uuid/--tl-epoch`, passed by sync-tasks and `hooks/track-agents`; when a caller passes neither, as the orchestrator's own Phase 4 call does, they default to `$V11_SESSION_ID`/`$CLAUDE_CODE_SESSION_ID` and that session's current epoch, or a carried task's own). The TaskUpdate identity ladder (Steps 1-2 and the prior-bucket lookup) trusts only entries of the current epoch (or any entry when the epoch opened `fresh`); the completion-time dispatch-trace auto-emit dedupes on (project, session_uuid, tl_epoch, task_id), and a row without a session matches (project, task_id) when its ts is at or after the task's create (`open_tasks[id]._created_at`, else the ledger create); Strategy 1.6 takes the current epoch's create from any ledger, else the latest by ts, and pre-populates its identity only when it is current or the epoch is unset/`fresh`. `scripts/rotate-metrics` deletes records not written for 30 days (`--tasklist-epoch-ttl-days N`, N >= 1; 0 or less exits 2). `=off` → no record, no stamps, no `parent_identity` or `_created_at`, the bare-id ladder, auto-emit key and Strategy 1.6 pick (the oldest create of the first matching ledger): v11.46 behavior and line shapes. History is never rewritten. Tests: `tests/test_sync_tasks_tasklist_epoch.py`. |
| `V11_REHYDRATE_IDENTITY_WRITE` | on | #111 write side. `hooks/sync-tasks` copies a rehydrated create's `metadata.rehydrated_from.identity`, with `rehydrated_from.session` and `.id`, into the ledger event as `rehydrate_target` (an input-only field; `v11_ledger_append` drops it from the line). `v11_ledger_append`'s continuation pass keys the create on that identity while its alias-folded last STATUS event is not `completed`/`cancelled` and a create of it (or of a sidecar alias of it) was made in that session under that id (review #26) (`continues:true`, the target's `subject_norm`, the new `subject` text kept); otherwise the line carries `rehydrate_target_refused: "unknown"|"mismatch"|"terminal"` and is keyed on its own subject as before. It prints `create_seq<TAB>subject_norm` for such a create, and sync-tasks' second STATE write patches both into `_idk`. The same pass decides "open" on the last status event (review, prescope and field_update rows never count, review #19 C5) and counts legacy aliases from `$METRICS_DIR/ledger/<project>.aliases.json` (written once by `scripts/task-epoch-seed` from the replay's identity view; an unreadable sidecar means no aliases), for the plain same-subject continuation too. `=off` → every create is keyed on its own subject and "open" means the last event of any kind, no aliases (v11.46). `V11_REPLAY_REHYDRATE_ALIAS` still heals old ledgers read-side. Tests: `tests/test_ledger_rehydrate_identity.py`. |


### S2-T0b-1 / T0b-3 Shared Task Resolver (#113)

Design: `sessions/v11-leverage-program/artifacts/s2-t0-epoch-design.md` §4 (rules R0-R4), amended by review #19 (§11 C10-C14). One resolver, `scripts/lib/task_epoch.py` `TaskIndex.resolve` (keying rule shared with the replay through `scripts/lib/task_key.py` `claim_key`), turns `(session, task_id)` into a task identity `(subject_norm, create_seq)` for every reader.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_TASK_RESOLVER` | shared | #113 read side. `shared`: the readers bind a bare task id through `task_epoch.py` — an explicit identity binds (R0); a row stamped with a TaskList epoch binds in that epoch (R1); an unstamped row binds the latest create at or before its position, preferring its subject (R2); a row without a session binds only when one identity carries the id across sessions (R3); a current-state query uses the session's current epoch (R4). Ambiguous only on a real tie. Readers: `scripts/handoff` (claims from `created` events only, open records by identity/epoch), `review-queue mark-done` (`--identity`, else the queue row's `parent_identity`, `tl_epoch`, ts + subject; "already done" scoped to session + identity), the replay's `(session, tl_epoch, task_id)` keying and `key_norms` sibling link (`hooks/lib/common.sh`), `scripts/wave-check`, `scripts/agent-scorecard --routing` (stamped rows by epoch; legacy trace rows keep the liveness window, S2 decision), `scripts/cost-ledger --by task` (group key `sn#cs`; `?<tid>` for a tie, `unresolved:<sid8>:<tid>` for none), `scripts/dispatch-advise --task-id` (`--session`/`--epoch`; exit 2 on a tie), `scripts/review-daemon`, `scripts/task-cancel`, `scripts/status` (prescope rows by identity) and the review-queue enqueue's "already pending" check. `=legacy` → every reader keeps its v11.46 code path (bare ids, completed-wins, sticky AMBIGUOUS, `epoch_owner`, the scorecard window alone, cost-ledger v1 bytes). Kept for one sprint as the byte-identity baseline (T9), then deleted with the legacy paths at S3/S4 after a soak. Tests: `tests/test_task_epoch.py`, `tests/test_task_epoch_readers.py`. |
| `V11_TASKS_ROOT` | `<config>/tasks` | Path override, not an on/off lever. `scripts/lib/task_epoch.py` store finder (`find_task_store`, `task_epoch.py store`, `scripts/handoff` `task_store`): the directory holding Claude Code's TaskList stores. Default `$CLAUDE_CONFIG_DIR/tasks`, else `~/.claude/tasks`. Tests point it at a fixture tree. |
| `V11_TEAMS_ROOT` | `<config>/teams` | Path override, not an on/off lever. Same finder: the directory of agent-team configs (`<team>/config.json` `leadSessionId`/`createdAt`) checked before the content match (review #19 C14). Default `$CLAUDE_CONFIG_DIR/teams`, else `~/.claude/teams`. |

### S2-T0b-4 Self-Nudge Sitting + Handoff TaskList Stamps (#113 design §5)

`scripts/handoff` adds to `handoff-tasks.json`: `live_sitting` (the writer's `CLAUDE_PID:starttime`, only when the writer is the live session: the hook's own session under `hooks/session-end`, else `CLAUDE_CODE_SESSION_ID`), `live_tl_epoch` (the live session's epoch record; `0` for a seed line), `task_store` + `task_store_basis` + `task_store_verified` (the `~/.claude/tasks/<dir>` holding the live TaskList: a team config first and verified, else a content match, unverified; absent with no match or under `V11_TASK_RESOLVER=legacy`), and per entry `tl_epoch` (its latest create's). `live_sitting`, `live_tl_epoch` and the entry `tl_epoch` follow `V11_TASKLIST_EPOCH` (`=off` → not written, so the self-nudge check below never matches: fail toward nudging). The self-nudge rule itself is the `V11_HANDOFF_SELF_NUDGE_SUPPRESS` row under S1-T3.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_REVIEW_TASK_ID` | on | #101 rider (design §6.7; T0b-4 shipped it opt-in, S2-R1 turned it on). `scripts/handoff` writes the open identity's latest `pair_` review shadow into its entry's `metadata.review_task_id` (an id already in the metadata is kept); `v11-resume-tasks` copies metadata, so the rehydrated task's TaskCreate carries it and `hooks/sync-tasks` auto-pair guard 3 mints no second shadow. That shadow lives in the old session's scratch, so at `TaskUpdate(completed)` sync-tasks sees a `review_task_id` naming a `pair_` shadow absent from this session's `open_tasks`: it skips the (no-op) activation and keeps the V11.19 queue row (`_V21_SUPPRESS_QUEUE=no`, stderr `[v11.21-auto-pair] ... is not in this session`), without `.review-config.json`'s scope filter since auto-pair minted the shadow without it; the row carries `parent_identity`, and the old shadow resolves in `scripts/handoff`/`scripts/wave-check` once its identity closes. A shadow this session holds activates as before, with no queue row. `=off` → no stamp: a rehydrated paired task gets a fresh shadow that activates at completion, an unpaired one its queue row (v11.46 behaviour); the completion rule stays (it only fires on a foreign shadow). Tests: `tests/test_handoff_tasklist_stamps.py` (the rehydrate → completion chain, lever on and off), `tests/test_v11_21_auto_pair.py` (`TestAutoPairForeignShadow`). |

## v11.46 — Stop the Bleeding (v11-leverage-program S1) — 2026-09-26

Every S1 and Lane D (D0) lever, one subsection per roadmap row. The rows added these as they merged, and the S1 CLOSE added the missing ones (S1-T9, S1-T11, S1-T16, D0-1/D0-2) plus the pre-existing silent `V11_STEER_MAX_CHARS`. Full entry: `docs/CHANGELOG.md` § v11.46.
Rows with no env lever: S1-T12 (`V11_REGISTRY_CHECK`, unchanged), S1-T15 (Gate 13 path argument, meta-test, pipefail fixes), S1-P3, S1-R4, D0-3, D0-5 (`V11_REGISTRY_RECONCILE`, unchanged). Each is a revert of its commit. The live data changes (S1-P1 waivers, S1-P3 correction rows, the D0-5 registry sync) are undone as `docs/CHANGELOG.md` § v11.46 "Rollback levers" describes.
The last fix round: fix task #71 (S1-T1 review #69) added `V11_HANDOFF_SOURCE_BUDGET_SECS` (S1-T1 subsection); `V11_SESSION_ID_SOURCE`, which `hooks/session-end` sets, is a state channel, not a lever. Fix task #72 (S1-T2 review #70) and the S1-T3 review #73 fix change behaviour under their existing levers, and their rows say how. S1-R2 added `V11_TEST_HOME_GUARD` (its own subsection).

### S1-T5 Write-Gate Scratch Exemption

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_WRITE_GATE_SCRATCH_EXEMPT` | on | improvements/76. `hooks/guard-write-gates`, block path only (this session owns open work but has 0 tasks in_progress): `hooks/lib/common.sh` `v11_is_write_gate_exempt` lets the write through when the path, canonicalized with `realpath -m` (relative paths, `..` and symlinks resolved), is under the harness scratchpad (`V11_SCRATCHPAD_ERE`, `^/tmp/claude-[0-9]+/[^/]*/[^/]*/scratchpad/.+$`, the same ERE `v11_rm_is_scratchpad_only_delete` uses) or is exactly `$SESSIONS_ROOT/<project>/<name>` with `<name>` one of `.session-summary.md`, `.handoff-steer.md`, `.handoff-addendum.md`, `handoff.md`, `handoff-tasks.json`, `peers.json` (no nested dirs, no `handoff.md.bak`). `v11_is_metadata_file` is unchanged, so detect-project, verify-syntax and guard-enforcement behave as before. `=off` → those paths block again (pre-S1-T5 behavior). Test: `tests/test_write_gate_scratch_exempt.py`. |

### S1-T7 Background Wait Contract

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_BG_WAIT_CONTRACT` | on | improvements/70. `hooks/guard-agent-stall` (Post:TaskList), right after the active-project lookup and BEFORE the `in_progress==0` exit: scans up to `STALL_WAIT_MAX_MARKERS` (20, newest mtime first) `~/.agent-metrics/waiting/<project>/<agent>-waiting.json` markers (`{what, pid?, path?, pid_or_path?, started?, expect_by?, done_marker?}`; legacy `pid_or_path` = pid when all digits, else an absolute log path; timestamps ISO-8601 or epoch seconds). Nudges as PostToolUse `additionalContext` when the pid is gone (a zombie, or reused: `/proc/<pid>/stat` start time later than the marker's mtime + 5s), a literal `done_marker` string appears in the last 64KB of the log (live pid or not), the log's last non-empty line matches `TERMINAL_RE` (`ALL_CAPS_(DONE\|FAILED\|FINISHED\|COMPLETE\|COMPLETED\|ABORTED)` sentinels and the pytest summary line; ignored while the pid is alive, since a multi-phase run prints a summary per phase), or `expect_by` has passed; a live pid within `expect_by` stays silent. A marker gets at most `STALL_WAIT_MAX_NUDGES` (3) nudges, `STALL_WAIT_RENUDGE_MINUTES` (30) apart, then one `WAIT MARKER STALE` line and silence (covers an agent that finished without removing its marker); a marker whose file is older than `STALL_WAIT_STALE_HOURS` (24) goes straight to STALE if it is nudge-worthy, or if it is silent but has no `expect_by` (a live job whose waiting agent may be gone); malformed markers are reported once. Rewriting a marker (new mtime) re-arms it. State: `<waiting dir>/.reported` (name, mtime, code, ts, count; read regular-file-only with O_NONBLOCK); `<waiting dir>/.reported.lock` (flock) makes a concurrent scan skip instead of duplicating lines. The nudge is flushed by explicit `_stall_exit` calls, not an EXIT trap. Runs only on the orchestrator's TaskList: when the orchestrator makes no tool calls, nothing scans (R-2 pins the hook to TaskList; an event-driven trigger would be new wiring). The scan is one python3 pass, spawned only when a marker exists. Skipped when the TaskList came from a subagent (`agent_id` in the hook input). When the stall advisory fires in the same call it folds into the same JSON. `=off` → no scan (pre-S1-T7 behavior). Test: `tests/test_stall_wait_contract.py`. |

### D0-4 Dispatch-Advise Wiring (prompt-only)

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_DISPATCH_ADVISE` | on | Ticket #88 (D0-4). Prompt-only lever: no hook or script reads it, and the orchestrator LLM follows it. It governs two places in the team-orchestrator skill. The first is the Phase 3 STEP 3 advice table (`SKILL.md`, `playbooks/interview.md`). The second is the Phase 4 spawn step (`playbooks/orchestrate.md` §"DAAO routing" + §"Dispatch trace"): run `scripts/dispatch-advise --task-id ID --project P --json`, then pass its top-1 (`.advice[0].route.agent`) as `--recommended-agent` and its `advice_id` as `--advice-id` to `scripts/dispatch-trace-append`. `=off` → the orchestrator skips `dispatch-advise` and routes on its own judgement, using the skill's DAAO fallback tables. Trace lines then carry the orchestrator's own pick as `--recommended-agent` and no `advice_id` key (pre-D0-3 shape). The same fallback applies with the lever on whenever the script prints `no advice (…)`, errors, or returns a null `route.agent`. `scripts/dispatch-advise` itself is unaffected; its side log has a separate knob. |

### S1-T6 Honest Block Messages

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_BASH_WRITE_WARN` | on | improvements/82. The #13 F4 advisory in `hooks/guard-enforcement` (`_v11_bash_is_source_write`) also matches interpreter file writes: a `python*`/`node` command word outside heredoc bodies and quotes, plus `open(<path>, 'w'\|'a'\|'x'…)`, `.write_text(`/`.write_bytes(` or `writeFile`/`appendFile(Sync)(`, and `perl -i`/`-pi`/`-i.bak`. Advisory only, exit 0 always. `=legacy` → the pre-#82 matching (redirects, `tee`, `sed -i`, `dd of=`). `=off` → no advisory at all (unchanged). The HIGH-block hints (heredoc data → Write/Edit; recursive `rm` on a `$var` path → literal scratchpad path) and the `guard-write-gates` "Possible half-applied change" line are message text with no lever; exit codes are unchanged, rollback is a revert of the S1-T6 commit. Tests: `tests/test_block_honest_alternative.py`, `tests/hooks/test-bash-write-warn.sh`. |

### S1-T10 Cost Line in scripts/status

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_COST_STATUS` | on | improvements/72 (M6). `scripts/status` prints one `Cost: $X (sprint S: $Y) · capture N/M · API list-price equiv, subagents only` line in the Progress block from `cost-ledger PROJECT --by sprint --json` (the caveat is the JSON's `pricing.basis`/`scope`; a sprint with no matching group reads `n/a`). A copy at `$METRICS_DIR/cost-ledger/PROJECT.status.json` younger than `V11_COST_STATUS_FRESH` s is used without a run; otherwise one setsid-detached refresh runs at a time per project (flock on `.PROJECT.lock`; a second call joins the run in flight), waited on for at most `V11_COST_STATUS_TIMEOUT` s (1-3, default 3). A late run replaces the copy, which later calls show with `· as of Nm ago` (ignored after a day); no usable result reads `Cost: unavailable`. `V11_COST_LEDGER` overrides the binary (tests). `=off` → no line and no cost-ledger run. Test: `tests/test_status_cost_line.py`. |
| `V11_COST_STATUS_TIMEOUT` | 3 | Seconds `scripts/status` waits for the cost-ledger refresh in flight before printing (integer 1-3; anything else → 3). The refresh itself keeps running past it. Not a disable lever: `V11_COST_STATUS=off` is. |
| `V11_COST_STATUS_FRESH` | 300 | Seconds a cached cost-ledger copy counts as fresh: `scripts/status` shows it without starting a refresh (non-negative integer; anything else → 300; `0` → refresh on every call, still single-flight). |
| `V11_COST_LEDGER` | `scripts/cost-ledger` | Path of the binary the cost line runs (tests point it at a stub). Unset → the repo's `scripts/cost-ledger`. Not executable → no run, the line falls back to the cached copy or `Cost: unavailable`. |

### S1-R3a lint-test-honesty Hard Gate

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_LINT_HONESTY_GATE` | hard | s0-close finding 7. `scripts/run-tests`, every mode except `--fast` (so `--regression` and `--regression-extended` alike): a `scripts/lint-test-honesty` violation, or a missing/non-executable lint script (review #59 E3; not with `V11_LINT_TEST_HONESTY=off`), prints `FAIL … (hard gate)`, sets the exit code to the lint's (1) when pytest passed (a pytest failure keeps its own code), and prints `lint-test-honesty HARD GATE: FAIL` on stderr after the summary. The lint/check phase exports `V11_HOME=$V11_ROOT` (after pytest, so the suite's environment is unchanged), so every lint/check scans the tree `run-tests` lives in. Before, the `V11_HOME` readers (`lint-test-honesty`, `check-rollback-lever-drift`, `check-index-body-status-consistency`) defaulted to `/path/to/v11` and a worktree run checked master (how S0-T6's review fix got two `case` blocks without `*)` into `hooks/session-end` past a green `--regression`). `=soft` → the lint failure prints `WARN` and never touches the exit code. The `V11_HOME` scoping has no lever. `V11_LINT_TEST_HONESTY=off` still skips the lint entirely. Test: `tests/test_run_tests_lint_gate.py`. |

### S1-R3b Unwired Session Dirs + Weekly Wiring-Parity Report

No env lever. improvements/98. `scripts/check-wiring-parity`'s unwired-session-dirs section is read-only and never changes the exit code unless `--strict-unwired` is passed. Rollback for the schedule: `scripts/check-wiring-parity --uninstall-cron` removes the `# v11-wiring-parity` cron line (Sun 04:30) and backs up the crontab to `~/.v11-backups/crontab.*` first; every other crontab line is kept byte-for-byte. Old reports in `~/.agent-metrics/wiring-parity/` are left in place. Test: `tests/test_check_wiring_parity.py`.

### S1-R1 Session GC: Quarantine + Process Liveness

S0 sprint-close findings 1 and 2. The S0-T6 `SessionEnd` GC deleted 64 dirs on its first real run (no backup, no soak), and it judged liveness only by file mtime (a 15-minute top-level check, then a 24 h TTL), so it could delete the scratch of a session left idle for more than 24 h. That scratch (`~/.agent-metrics/sessions/<uuid>/task-state.json`) is the only copy of the review verdicts the ledger drops (#102). `hooks/session-end` `_v11_gc_session_dirs` now keeps a UUID-named dir while the first of these holds: `live-current` (the session running the hook), `live-heartbeat` (`v11_session_is_live`, the 15-minute check, used only to mark a dir live, never dead), `live-by-process` (a running claude process owns the id), `live-by-mtime` (the newest file anywhere in the tree is younger than the TTL). Otherwise the dir is `expired`. Process ownership comes from Claude Code's `${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json` (`sessionId`, `procStart`). An entry counts only when `/proc/<pid>` exists and is not a zombie, and `procStart` equals the starttime field (22) of `/proc/<pid>/stat`, so a recycled pid is not counted. `/proc/<pid>/environ` is not used: its `CLAUDE_CODE_SESSION_ID` is inherited from the spawner, and environ holds secrets. Headless `claude -p` runs write no pid file; the TTL covers them. Non-UUID names are still never touched. `hooks/session-end --gc-preview` prints one row per decision: `live-*`, `spared-non-uuid`, `expired-quarantine`/`expired-remove`, and `quarantined-kept`/`quarantined-purge` rows for quarantine runs, plus a counts line. The `SessionEnd` log line carries the same counts (`~/.agent-metrics/session-end.log`: `gc_quarantined_id=`, `gc_removed_id=`, `gc_purged=`, `gc_quarantine_failed_id=`). To restore a quarantined session: `mv ~/.agent-metrics/sessions/.gc-quarantine/<utc-ts>/<uuid> ~/.agent-metrics/sessions/`. The first run after this change deletes nothing, because the quarantine starts empty.

Review #58 closed the remaining `rm` paths:
- **SessionEnd teardown.** `_v11_remove_scratch` used to `rm -rf` the ending session's scratch. It now follows `V11_SESSION_GC_MODE`: the default moves it to `.gc-quarantine/<utc-ts>/<id>/` (log `scratch_quarantined_id=`), `remove` deletes it (`scratch_removed_id=`), and `off` leaves it in place (`scratch_kept_id=`). When a scratch stays in place (`off`, or a refused move logged as `scratch_quarantine_failed_id=`), its `.sitting` marker is removed, so a resumed sitting still counts as new.
- **Stop.** A `Stop` never removes or moves the scratch, not even on the FULL Stop path (unsynced projects, an untimed `SessionEnd` entry, `V11_STOP_SPLIT=off`, a payload without `hook_event_name`): the session is live.
- **Every move.** Moves go through `_v11_quarantine_dir`. It refuses, moves nothing and never falls back to `rm` when the source, `.gc-quarantine` or the run dir is a symlink, when the target exists, or when the run dir is on a different filesystem from the source (`stat -c %d`). A cross-device `mv` would degrade to a non-atomic copy plus unlink.
- **GC scan and timing.** Each dir's tree walk runs under `timeout 5`, and a walk that times out counts as live (`live-scan-timeout`). The GC does not start after 50 s of hook time (`gc_skipped=late`, from bash `SECONDS`) and stops at 55 s.
- **Manual runs.** `hooks/session-end --gc-run` runs the GC once outside a SessionEnd and echoes its log lines.
- **`scripts/rotate-metrics --sessions`** (opt-in, not in the weekly cron) no longer runs `rm -rf` on every `sessions/*` child by dir mtime. It calls `--gc-run` (`--gc-preview` with `--dry-run`) with `V11_SESSION_GC_TTL_HOURS` set to `--sessions-ttl` × 24, so only the GC's rules apply. It skips with a message when `METRICS_DIR` does not end in `/.agent-metrics`, because the GC resolves `sessions/` from `HERCULES_ROOT`.

Tests: `tests/test_session_end_split.py` (`test_session_end_scratch_follows_gc_mode` regression-marked, `test_quarantine_refuses_a_symlinked_quarantine_root`, `test_gc_scan_timeout_counts_as_live`, `test_gc_run_skips_when_started_late`) and `tests/test_session_scoped_active_project.py` (`TestSessionEndCleanup`, `TestRotateMetricsSessions`).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_SESSION_GC_MODE` | quarantine | `hooks/session-end`: the `SessionEnd` GC and (review #58) the `SessionEnd` teardown of the ending session's own scratch. `quarantine` → an expired dir is moved (`mv -T`, same filesystem) to `~/.agent-metrics/sessions/.gc-quarantine/<UTC %Y%m%dT%H%M%SZ>/<uuid>/`. A failed move is logged and the dir stays; the GC never falls back to `rm`. `remove` → an expired dir, and the ending session's scratch, is deleted (the S0-T6 behaviour, with the new liveness checks and TTL; add `V11_SESSION_GC_TTL_HOURS=24` for the S0 TTL too). `off` → no GC, and the ending scratch stays in place (without its `.sitting` marker). An unknown value → `quarantine`. Test: `tests/test_session_end_split.py` (regression-marked: `test_gc_keeps_process_owned_session_past_ttl`, `test_gc_first_run_never_deletes_and_purges_after_seven_days`, `test_gc_spares_shared_identities_older_than_ttl`). |
| `V11_SESSION_GC_TTL_HOURS` | 168 | Age (newest file anywhere in the dir) after which a dir with no live signal is expired. Floor 1 h, `off` disables the GC. When unset, S0's `V11_SESSION_GC_HOURS` is read. The default is 7 d, the same as `scripts/rotate-metrics` `SESSIONS_TTL_DAYS`, so an idle session keeps its scratch for a week even with no process record. |
| `V11_SESSION_GC_QUARANTINE_HOURS` | 168 | Quarantine runs whose `<utc-ts>` name (not mtime: `mv` keeps the dir's old mtime) is older than this are purged (`rm -rf` of the run dir, each id logged `gc_purged=`) at the start of a GC run, in both modes, so no run deletes a dir it quarantined itself. Floor 1 h. `off` keeps quarantine runs indefinitely. Entries under `.gc-quarantine/` with any other name are never touched. |

### S1-T1 Handoff Emission Source Check

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_SOURCE_CHECK` | on | S1-T1 (#75a). `scripts/handoff` builds `handoff-tasks.json` `open_tasks` from the ledger replay (`v11_replay_ledger`) ∪ `ledger/<p>.live-snapshot.json`, scoped to the LIVE session: the hook's own session when `hooks/session-end` passes it (`V11_SESSION_ID_SOURCE=hook-stdin`, taken outright — review #69), else the env session (`V11_SESSION_ID`, then `CLAUDE_CODE_SESSION_ID`) when its last ledger event is within `V11_HANDOFF_LIVE_WINDOW_SECS` of the newest or a running claude process owns it (S1-R1's pid-file rule), else the Claude session (UUID id; tool pseudo-sessions such as `legacy-cli` never win) with the newest ledger event (stderr says why). The snapshot is used only when it belongs to the live session and adds only tasks the ledger never saw. Every entry carries `identity {subject_norm, create_seq}`; ledger entries are stamped `_ledger_auth`, skip the family fold and the stale-session heuristic, and dedupe by identity. The file gains `live_session_uuid`, `open_tasks_source` and `source_check`. A shrink breaker mirrors the 2x growth breaker (prior ≥ 3, new < prior/2, counting `family_members`) and an emission of 0 open tasks exits 2 — both only when a dropped prior task is not completed/cancelled in the ledger (or completed in the live snapshot; a ledger-open identity wins); `--allow-empty` overrides both. Review #69: prior entries match by identity, not subject; only the live session's prior entries count (another session's still-open tasks are listed in `source_check.dropped_foreign` and warned; an idle live session, a fallback emission or no source check counts all); pending_parent review siblings and `pair_` review shadows never count (`dropped_by_policy`). A refused emission promotes no `handoff.md` (the pair stays the last accepted one), writes `.handoff-refused` and a one-line note in the kept `handoff.md`, and `hooks/session-end` stamps the open-set digest so a Stop does not retry it. Projects with no ledger activity keep the per-session/aggregate path (identity still stamped, `create_seq: null`); a replay that fails or times out falls back to that path with a stderr WARN and `open_tasks_source: "legacy-fallback:<reason>"`. `=off` → the pre-S1 emission: no replay, no identity, no new fields, no shrink breaker, no empty refusal. Tests: `tests/test_handoff_source_check.py` (incl. M1 on the three #75 archivestream fixtures in `tests/fixtures/handoff_m1/`). |
| `V11_HANDOFF_LIVE_WINDOW_SECS` | 600 | S1-T1 (#75a). Seconds the env session's last ledger event may trail the newest session's before `scripts/handoff` treats the env session as stale and emits the newest session's open tasks instead. Review #69: not applied to the hook's own session (`V11_SESSION_ID_SOURCE=hook-stdin`) or to an env session a running claude process owns. |
| `V11_HANDOFF_SOURCE_BUDGET_SECS` | 12 | S1-T1 review #69. One time budget (3..14 s) shared by the three S1 steps in `scripts/handoff` — ledger replay, live-set pass, drop audit (1 s floor) — so they end inside `hooks/session-end`'s 20 s kill. Only their own run time counts. A replay killed by it falls back loudly (`open_tasks_source: "legacy-fallback:replay_timeout"`). |

### S1-T2 Handoff Consumers Keyed on Identity

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_IDENTITY_KEYS` | on | S1-T2 (#75b). Task ids are session-local (every session's TaskCreate counter starts at 1; a rehydrated task gets a fresh id), so the handoff consumers key on the S1-T1 identity instead. `hooks/detect-project` rehydrate verification compares the subject_norm multiset of `handoff-tasks.json` (`.identity`) with the live open tasks (a rehydrated task's `metadata.rehydrated_from.identity`, so a task renamed before the handoff still matches; else `._idk`) via `scripts/lib/handoff_identity.py`: a clean rehydrate with fresh ids is a `handoff_ack`, not an `identity_mismatch`, and different tasks that reuse ids are an `identity_mismatch` (`identity_delta` lists subject_norms). If the check cannot run (helper fails, handoff file unreadable) the ack records `identity_matched=false` and stderr says why (review #70) — a real mismatch is always a `rehydrate_missed` event. `scripts/handoff` (`_v11_fill_null_subjects`) and `scripts/v11-resume-tasks --list` recover a null subject by identity alone when the entry has one; an entry without an identity (pre-S1 file) falls back to its task id — by (session, id), then by an id every ledger subject agrees on — never another session's task. `v11-resume-tasks` block payloads for entries with an identity carry `metadata.rehydrated_from {identity, id, session}`; a pre-S1 file rehydrates byte-identical to before. `=off` → id-set comparison, bare-id last-writer subject map, no `rehydrated_from`. Tests: `tests/test_handoff_identity_keys.py`, `tests/test_rehydrate_verification.py`. |

### S1-T4 Handoff Summary Cap

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_SUMMARY_LINES` | 40 | S1-T4 (#57). Line cap for `.session-summary.md` in `handoff.md`, applied by the one helper `_v11_summary_excerpt` in `scripts/handoff` (both read sites: the written summary and the fresh stub). A summary within the cap is passed through byte-for-byte, as before. A longer one keeps every `## ` heading, puts the Blockers / Open Questions sections first after the title, shares the rest of the budget across the other sections (short sections stay whole), and ends with `… [N more lines from <sections> — full summary: <abs path>]`. One stderr `NOTE:` line reports the overage. Before S1-T4 the cap was a silent `head -20`. `=20` → the old 20-line cap (still marked); `=0` → no cap; a non-integer → 40. The #81 half of S1-T4 has no lever: the rehydrate command in the continuation prompt (`handoff.md` Rehydration and Instructions), `handoff-tasks.json` `.rehydration_note` and `scripts/v11-bootstrap-session` is now the absolute `$V11_HOME/scripts/v11-resume-tasks PROJECT`, which runs from any cwd. Tests: `tests/test_handoff_summary_resume.py`. |

### S1-T3 No Self-Nudge

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_SELF_NUDGE_SUPPRESS` | on | S1-T3 (#75c). The Stop hook re-emits `handoff-tasks.json` every turn, stamped (S1-T1) with `live_session_uuid` = the session whose open tasks it carries. When that stamp equals the reading session's id, `hooks/detect-project` skips the "open task(s) in handoff … Run /v11 to auto-rehydrate" nudge and the L2.3 rehydrate verification (no `rehydrate_missed`, no `handoff_ack` — there was no cross-session rehydrate), and `hooks/post-compact` omits its "Handoff waiting" line (session id from the hook's stdin `.session_id`, else `V11_SESSION_ID`). Suppression needs a non-empty session id AND a non-empty matching stamp; a pre-S1 file, a missing id or an unreadable file keep the nudge (fail toward nudging). A different session reading the same file is nudged and verified as before. Review #73: detect-project runs the check only while `.handoff-surfaced` (or, once a baseline exists, `.rehydrate-verify-done`) is missing, and a match writes `.handoff-surfaced`. A repeated Read runs no jq, and another session re-stamping the file mid-session does not nudge the writer. S2-T0b-4 (#113 design §5): a resumed session keeps its id but can hold a new TaskList (an in-process `/resume` switches the store), so the session match alone no longer suppresses. The file must also carry `live_sitting` equal to this hook's claude process (`CLAUDE_PID` + `/proc` starttime) and, when it carries `live_tl_epoch` and the session's epoch record is readable, the record's epoch must still be that one (an id reuse inside the sitting, a #26 wipe, nudges). One jq reads the three stamps; the check is `hooks/lib/common.sh` `v11_handoff_self_sitting` (builtins, no forks). So a resume (new process) is nudged once and L2.3 runs; compaction (same sitting) stays quiet; an S1-format file without `live_sitting` nudges once after the upgrade, and so does a CLI `--resume` whose store continued (decision D2). The nudge and the "Handoff waiting" line end "if TaskList already lists them, ignore this." `=session` → the S1 rule (session match only). `=off` → the pre-S1-T3 nudge/verification for every session. Tests: `tests/test_handoff_self_nudge.py`. |

### S1-R2 Test HOME Guard

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_TEST_HOME_GUARD` | on | improvements/94. Test-suite lever: read only by `tests/conftest.py` (`_real_sessions_dir_guard`, an autouse module-scoped fixture); no hook reads it. Per test module it snapshots the real `~/.agent-metrics/sessions` (fixed from `$HOME` at conftest import) and fails the module when a test-shaped entry (not a UUID, and matching `test-*`, `test_*`, `sess-*`, `*-sess`, `*-session` or `real-session-*`) is new or was written to (newest mtime of the entry or its direct children moved), provided the module owns the name: it appears as a whole token in the module's source, or it embeds the worker's pid. Other test-shaped changes only raise a `UserWarning` (most likely a concurrent run elsewhere). It never deletes anything. `=off` → no snapshot, no failure. The companion fix, `scripts/lib/context_tracker.py` resolving `$METRICS_DIR`, else `$HERCULES_ROOT/.agent-metrics`, else `~/.agent-metrics`, has no lever (`git revert`; unchanged when neither var is set). Test: `tests/test_real_home_isolation.py`. |

### S1-T9 Cost Ledger

`scripts/cost-ledger` has no on/off lever: it is read-only and runs only when invoked (the `scripts/status` cost line has its own switch, `V11_COST_STATUS`, above).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_MODEL_PRICING` | `<repo>/config/model-pricing.json` | improvements/72. Price table (`$`/Mtok per model, `as_of`) that `scripts/cost-ledger` prices transcript tokens with. A model missing from the table prices `null` with a warning; the `$` figures are the API list-price equivalent for subagent spawns only (`pricing.basis`/`pricing.scope` in `--json`). Point it at another file to reprice with different rates; nothing is written. Test: `tests/test_cost_ledger.py`. |

### S1-T11 Scorecard Routing Honesty

`scripts/agent-scorecard --routing` (improvements/53, #99 items 2-3; follow-ups S1-T11b-f). The wrapper hands `--live-window H` (default 2) to the embedded reader as `V11_AS_LIVE_WINDOW_H`. That is a flag, not a lever.

Three levers are listed here as bullets, not table rows. The scorecard's embedded Python reads them through an `env("…")` helper, which `check-rollback-lever-drift` can't see in a bash-wrapped script, so a table row would be a false doc-lie FAIL (S1 CLOSE finding; ticket pending).
- **`V11_AS_ROUTING_RAW`** (default unset). `=true` → `--routing` prints the pre-S1-T11 raw count (each dispatch-trace row's own self-filled `recommended_agent`/`override_reason`). Default: the classified report (ledger `created.metadata.agent` for the task live at the spawn; buckets agreed/diverged/self_executed/companion/unknown; decided-rate headline with coverage and bounds). Test: `tests/test_agent_scorecard.py`.
- **`V11_AS_ROTATED`** (default on). `=off` → the scorecard's ledger reader uses the live `ledger/<project>.jsonl` files only, not the rotated `ledger/<project>.jsonl.bak*` and `ledger/archive/*.jsonl` rows (merged and de-duplicated since S1-T11d).
- **`V11_AS_TRANSCRIPTS`** (default on). `=off` → the served-task search (S1-T11d) skips the session-transcript lookup (the one Agent call whose prompt names `task #N`). Only the ledger plan-name rule remains, and it matches only when unambiguous (S1-T11f).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_AS_TRANSCRIPTS_DIR` | `$HERCULES_ROOT/.claude/projects` | `scripts/agent-scorecard --routing`: where the served-task search reads session transcripts. A missing dir behaves like `V11_AS_TRANSCRIPTS=off`. Test seam. |

### S1-T16 wave-check Ledger Replay

`scripts/wave-check` builds the wave from `v11_replay_ledger`'s identity view (improvements/96; review #34 fixes E1-E9; S1-P3 void rule). The exit contract (0 pass, 2 unreviewed, 3 CRITICAL, 4 cannot verify) and the flock are unchanged.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_WAVE_CHECK_COVERAGE` | on | `=off` → reviewable work tasks with no review evidence are still listed, but `wave-check` does not exit 2 for them (the CRITICAL exit 3 and the exit 4 stay). Test: `tests/test_v11_21_wave_check.py`. |
| `V11_WAVE_CHECK_WAIVER_COVERAGE` | on | A waiver (`outcome=waived`, a shadow cancelled as a waiver, or a review a waived correction points at) covers its parent in its own `waived` bucket; it is never a clean verdict. `=off` → a waived parent is UNREVIEWED (exit 2 unless coverage is off). |
| `V11_WAVE_CHECK_SKIP_REVIEW_STRICT` | off | `skip_review` is an exemption, and a work task at the pairing threshold that carries it is named in a WARNING. `=on` → such a task without `metadata.skip_review_reason` counts as unreviewed. |
| `V11_WAVE_CHECK_EPOCH_BINDING` | on | S1-T2c. A restart that renumbers the TaskList under the same hook session reuses task ids, so a `(session, task_id)` claim alone bound a review to every task that ever held its `review_of` id (Review 69 of old #3 also covered the new #3) and matched a task-state row to two identities (it then stood alone as a duplicate). When two or more identities were created under the id in that session, a review binds to the one created under it last before the review's own `created` (a `pair_` shadow, written just before its parent in the same hook call, also accepts a same-instant parent), and a task-state row takes the id's current holder. Undecidable (a claimant never created under the id, a tie) keeps the claim-only rule. Uses the replay identity view's `created_claims`. `=off` restores claim-only binding. Test: `tests/test_v11_21_wave_check.py`. |
| `V11_REPLAY_EMIT_IDENTITIES` | off | `hooks/lib/common.sh` `v11_replay_ledger`: `=on` adds an identity view listing every identity (completed and cancelled included) with `last_review_*`, `review_summary_delta`, the cancellation's outcome and `created_claims` (every `created` folded into it, S1-T2c). `wave-check` sets it for its own call. Off, the replay output and the aggregate every other caller gets are byte-identical to pre-S1. It is an opt-in view, not a disable lever. |

### D0-1 / D0-2 Live Roster and dispatch-advise

Ticket #88. `scripts/dispatch-advise` and `scripts/lib/roster.py` are advisory and run only when invoked. The orchestrator's use of them is governed by the prompt-only `V11_DISPATCH_ADVISE` (D0-4, above).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_ROSTER_CACHE` | `~/.agent-metrics/roster-cache.json` | `scripts/lib/roster.py`: path of the parsed-frontmatter cache, keyed by (path, mtime_ns, size, realpath). A write failure is non-fatal. `--no-cache` (or `load_roster(use_cache=False)`) bypasses it. Deleting the file only costs a re-parse. Test: `tests/test_roster.py`. |
| `V11_DISPATCH_ADVICE_LOG` | `$METRICS_DIR/dispatch-advice.jsonl` | `scripts/dispatch-advise`: path of the advice log (one flock'd line per advised task, joined to dispatch-trace by `advice_id`). `=off` → no log line is written; the advice is still printed. `--no-log` does the same per call. Test: `tests/test_dispatch_advise.py`. |
| `V11_AGENT_SCORECARD` | `scripts/agent-scorecard` (via `agent-recommend`) | `scripts/dispatch-advise`: the scorecard used for the exact-top-3 tie-break. `=off` → no tie-break lookups (tie-break status `disabled`; ties order by name); a path overrides the scorecard binary. `--no-tiebreak` does the same per call. |

### Pre-S1 silent lever documented at the S1 CLOSE (F27)

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_STEER_MAX_CHARS` | 2000 | v11.40 W2-T2 (#1/#34). `scripts/handoff`: character cap on the `.handoff-steer.md` text copied into the continuation prompt ("## Orchestrator Steer"). A longer steer is cut at N characters and one stderr `WARN: steer truncated at N chars (was M; …) — tail lost: "…"` line quotes the first 80 lost characters. `=0` → no cap. The warning goes to stderr only, so an unattended `Stop`/`SessionEnd` emit truncates silently from the user's view (F25: the S1 steer was cut this way). Keep steers short and point to an artifact. Test: `tests/test_handoff_steer.py`. |

### Sprint-close review fixes (task #12)

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_REVIEW_DAEMON_PARK` | on | `scripts/review-daemon`: when `review-queue mark-done --verdict-file` exits 2, the verdict cannot bind (S1-P3: the task_id names several tasks, and the pending row's session does not pick one out). It would refuse the same way on every run. The daemon then parks the entry: `hooks/lib/common.sh` `v11_review_queue_park` appends a copy of the pending row with `ev:"parked"`, the claim cleared, `parked_at`, `park_reason` (mark-done's stderr, up to 500 chars), `park_rc`, `verdict_kept` (the kept verdict temp file) and `parked_by`. Drain paths select `ev=="pending"` only, so the nightly cadence stops paying for a headless review that cannot bind. Any other non-zero rc leaves the entry pending, since it may be transient. `review-queue dashboard`, `backstop` and `stats` report parked entries separately; the backstop does not count them. `pending --json` is unchanged unless you pass `--include-parked`, which adds the parked rows and a `state` field. There are two ways to un-park. `review-queue unpark PROJECT TASK_ID` makes the entry drainable again, and the next drain re-reviews it. Or fold the kept verdict: `review-queue mark-done PROJECT TASK_ID "" SESSION --verdict-file <verdict_kept>`, since a done event closes a parked entry. A new enqueue of the task also re-pends it. `review-queue park PROJECT TASK_ID --reason "..."` parks by hand. `=off` → the entry stays pending and is re-drained on every run (pre-fix behavior). Test: `tests/test_review_daemon.py`. |

The `hooks/guard-agent-stall` fix in the same task has no lever. WAIT NUDGE/STALE/MALFORMED lines print the marker filename JSON-escaped and capped at 80 characters under the waiting dir, so a newline in a filename cannot start a new context line. Valid `<agent>-waiting.json` names print unchanged. To undo it, revert the commit. Test: `tests/test_stall_wait_contract.py`.

## v11.45 — Rails (v11-leverage-program S0) — 2026-09-26

Every S0 lever, one subsection per roadmap row (consolidated at S0-CLOSE from the per-row sections the rows added on 2026-09-25; no row dropped). Full entry: `docs/CHANGELOG.md` § v11.45.

### S0-T1 Regression Lock

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_REGRESSION_LOCK` | on | improvements S0-T1 / v11-leverage-program. `scripts/run-tests`, right after arg parsing: when `--regression` or `--regression-extended` is passed, an `flock`-based lock (host-global — `${V11_REGRESSION_LOCK_FILE:-$HOME/.cache/v11/regression.lock}`, not repo-relative, so worktrees with different `V11_ROOT`s still serialize against each other) serializes the ENTIRE regression run: pytest, the honesty/drift lints that run alongside it (test-honesty, changelog-drift, stamp-drift, class-included, git-tasklist, hotkey-sync, index-body, rollback-lever, registry), and the `--regression-extended` slow-tier phase 2. A busy lock blocks up to `V11_REGRESSION_LOCK_TIMEOUT` (default 1800s) before exiting 75. `=off` → no lock, concurrent regression runs allowed (pre-S0-T1 behavior — races on `REPORT_FILE`/xdist workers return). `V11_REGRESSION_LOCK_FILE` overrides the lock path; `V11_REGRESSION_LOCK_TIMEOUT` overrides the wait budget (seconds). Test seam: `V11_REGRESSION_LOCK_PROBE=1` prints `REGRESSION_LOCK_ACQUIRED`/`REGRESSION_LOCK_BYPASSED` and exits 0 before pytest runs. Test: `tests/test_run_tests_regression_lock.py`. |
| `V11_REGRESSION_LOCK_FILE` | `$HOME/.cache/v11/regression.lock` | `scripts/run-tests`: path of the host-global regression lock file (see `V11_REGRESSION_LOCK`). Host-global on purpose, so worktrees with different `V11_ROOT`s serialize against each other. Override only to isolate a test run. |
| `V11_REGRESSION_LOCK_TIMEOUT` | 1800 | `scripts/run-tests`: seconds a `--regression*` run waits for a busy lock before exiting 75. |
| `V11_REGRESSION_LOCK_PROBE` | unset | Test seam. `=1` → `scripts/run-tests` prints `REGRESSION_LOCK_ACQUIRED`/`REGRESSION_LOCK_BYPASSED` and exits 0 before pytest runs. Test: `tests/test_run_tests_regression_lock.py`. |

### S0-T4 v11-update Template Diff

`scripts/v11-update` was rebuilt on `scripts/lib/wiring_diff.py` as a template diff (ticket #86): every hook command wired anywhere in `v11/.claude/settings.json` is "managed" and reconciled to match the template's exact `(event, matcher)` wiring; every other command (custom project hooks, opt-in v11 hooks like `enforce-subagent`/`guard-teammate-timeout`/`pg-*`) is "unmanaged" and preserved byte-for-byte. No on/off lever — this replaces the old frozen v11.11 version-ladder implementation outright, whose `--all --dry-run` wrote for real (see ticket #86). Rollback is the per-file backup, not an env toggle.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_UPDATE_TEMPLATE` | `$V11_HOME/.claude/settings.json` | Template settings.json to diff against. Override for canarying a template change against a scratch project before rolling it out. |
| `V11_UPDATE_SCAN_ROOT` | `$HERCULES_ROOT` (`/path/to/operator-home`) | Root `--all` walks recursively for `.claude/settings.json` files that reference `/path/to/v11/hooks/`. Prunes `node_modules`, `.git`, any `*/.claude/worktrees/*`, backup/archive-named dirs, `V11_UPDATE_BACKUP_ROOT`, and the template itself. Test seam — points discovery at a fixture tree. |
| `V11_UPDATE_BACKUP_ROOT` | `~/.v11-backups/v11-update` | Where changed files are backed up before an atomic write, mirrored as `<root>/<UTC timestamp>/<absolute path>`. `--dry-run` never creates this directory or writes into it — zero bytes anywhere, confirmed by `tests/test_v11_update.py::test_all_dry_run_writes_zero_bytes_new_script` (and the paired `test_all_dry_run_fails_on_pre_s0_t4_script`, which runs the frozen pre-S0-T4 script from `tests/fixtures/wiring/v11_update_old_frozen.sh` to prove the bug it replaces). |

Dropped: `--scan` (the frozen version-ladder survey). It now prints a deprecation notice pointing at `scripts/check-wiring-parity` (S0-T5) and exits 0 — not a crash, but not a real report either. `--test` and `--help` are unchanged (still exit 0, still smoke-tested by `tests/test_scripts_smoke.py`). Tests: `tests/test_wiring_diff.py` (pure diff core), `tests/test_v11_update.py` (CLI/fixture-tree level).

Rolling back an apply (review #18 E1): `scripts/v11-update --restore STAMP [STAMP ...]` lists every file backed up under `$V11_UPDATE_BACKUP_ROOT/STAMP` (backup → target, sha256 differs?) and writes nothing; add `--apply` to restore them byte-exact with the backup's mode, after saving the current files under `<root>/<now>-pre-restore/` (undo: `--restore <that stamp> --apply`). Do not use `git checkout` for repos whose settings.json was dirty before the apply. S0-T7's fleet write: `--restore 20260925T223523Z 20260925T223306Z` (97 files). Test: `tests/test_v11_update_restore.py` (regression-marked: `test_restore_round_trip_dry_run_then_apply`).

### S0-T6 Stop/SessionEnd Split

Ticket #90. `hooks/session-end` is wired to both `Stop` (every assistant turn) and `SessionEnd` (once per session) in the template, and dispatches on the stdin `hook_event_name`. A `Stop` takes the CHEAP path (the V11.15.6 aggregate fold, then — only when the project's open-set digest changed, recorded in `sessions/<project>/.handoff-autoemit-digest` — a `last-session.json` refresh and an auto-emit) only when the payload carries a `session_id` AND the project's `$CLAUDE_PROJECT_DIR/.claude/settings.json` (else the stdin `cwd`'s) wires `SessionEnd` to `…/hooks/session-end` with a `timeout` of at least 30 s (an untimed or lower entry is killed at 1.5 s, so that project stays on the FULL path, logged `reason=sessionend-timeout`). Everything else runs the FULL path: projects not yet fleet-synced (S0-T7) keep their per-turn teardown. On `SessionEnd` the critical work runs first — fold, discipline check, `last-session.json`, auto-emit, then the exactly-once claim with one session-log row and one retro increment, manifest, scratch removal — and the optional work last, each step bounded (plan-sync 10 s, align-aggregate 15 s, orphan detector 10 s, GC 10 s). The claim is per sitting: ledger `~/.agent-metrics/.session-end-ended` keys on `session_id` plus the marker `~/.agent-metrics/sessions/<id>/.sitting` written by the sitting's first `Stop`, so a `claude --resume`/`--continue` sitting counts again and a duplicate `SessionEnd` does not. The auto-emit is never gated on the claim. On both paths the auto-emit runs `scripts/handoff` without `--force`, reports a #41 guard refusal as `skipped: hand-edited` (stderr + `~/.agent-metrics/session-end.log`), skips on `Stop` while `.handoff-steer.md` is pending, stamps `.handoff-autoemit-at` / the digest only when the run exits 0, and stamps the digest taken before the run. The 60 s don't-stomp window is bypassed on a sitting's first `SessionEnd` when `handoff.md` is not newer than `.handoff-autoemit-at` (the last write was the hook's own emit, not `/handoff`).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_STOP_SPLIT` | on | `hooks/session-end`: the S0-T6 lever. `=off` → every `Stop` runs the FULL path (retro counter, session-log row, orphan detector, align-aggregate, plan-sync, discipline check, unthrottled auto-emit), and a `SessionEnd` only logs (`mode=off`) and exits: no fold, no session-log row, no retro, no emit, no GC. The lever alone restores the pre-S0-T6 behaviour, even with `SessionEnd` still wired, except that since S1-R1 review #58 no `Stop` removes the live session's scratch or context-estimate. |
| `V11_SESSION_GC_HOURS` | 24 | Superseded in v11.46 (S1-R1): now read only when `V11_SESSION_GC_TTL_HOURS` is unset, the default TTL is 168 h, and expired dirs are quarantined, not removed (`V11_SESSION_GC_MODE`). S0 behaviour: `hooks/session-end`, `SessionEnd` only: removes `~/.agent-metrics/sessions/<id>/` dirs left by sessions that never ran `SessionEnd` (e.g. a killed tmux window) when the dir is named like a session UUID, the newest file anywhere in it is older than N hours AND `v11_session_is_live` says the session is not live. Never the current session's dir, never a non-UUID name (`legacy-cli`, `legacy-bootstrap-<project>`, `self-review-tool`: shared identities that feed the legacy fold), never a dir touched in the last hour (floor applies even at `0`). Each removed id is logged (`gc_removed_id=`). `=off` disables the GC. Read-only preview: `hooks/session-end --gc-preview`. |
| `V11_SESSION_GC_ALL` | off | `=on` makes every dir name GC-eligible, except `legacy-cli`. |
| `V11_SESSION_GC_DRYRUN` | 0 | `=1` → the `SessionEnd` GC changes nothing and logs each change it would make (`gc_would_quarantine_id=` / `gc_would_remove_id=` per `V11_SESSION_GC_MODE`, `gc_would_purge=` for quarantine runs; S1-R1). |

The template's `SessionEnd` entry carries `"timeout": 60`. Claude Code (2.1.282) gives SessionEnd hooks `max(1500 ms, min(largest per-hook timeout, 60000 ms))`, overridable with `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`. Without the timeout the full path (~5 s) is killed on `/exit` before the emit, retro counter and scratch removal (canary 2026-09-25, `sessions/v11-leverage-program/artifacts/s0-t6-canary.md`). Observed reasons: `/exit` → `prompt_input_exit`, `/clear` → `clear`, `tmux kill-session` → `other` (the SIGHUP'd process still ran the hook to completion).

Rollback of the wiring itself: delete the `SessionEnd` entry from `v11/.claude/settings.json` (and, after S0-T7, re-run `scripts/v11-update --all`); with no `SessionEnd` wired, every `Stop` takes the FULL path. Test: `tests/test_session_end_split.py` (regression-marked: `test_m12_ten_stops_without_task_change`, `test_m12_ten_stops_with_seeded_project_ledger`, `test_session_end_full_teardown_exactly_once`, `test_resumed_sitting_counts_again_true_duplicate_does_not`, `test_stop_emit_then_session_end_within_60s_is_current`, `test_task_change_during_the_emit_is_not_stamped_covered`, `test_session_end_entry_without_usable_timeout_keeps_stop_full`, `test_legacy_stop_only_wiring_runs_full_path`, `test_hand_edited_handoff_survives_stop_and_session_end`, `test_gc_spares_shared_identities_older_than_ttl`); `test_stop_split_off_session_end_only_logs` covers the lever.

### S0-T9 Data Rails (rotate-metrics subdir policy + weekly cadence)

Not on/off toggles (there's no unsafe legacy behavior to fall back to here — the whole point of S0-T9 is the ledger safety boundary), but the TTL knobs that gate what `scripts/rotate-metrics` archives in `ledger/` and `outbox/`. `review-queue/` has no knob: rotate-metrics never touches it (report-only by design — see the policy table in the script's header comment).

| Env Var | Default | What it does |
|---------|---------|--------------|
| `LEDGER_BAK_TTL_DAYS` | 14 | `scripts/rotate-metrics`: minimum age (days) a `ledger/*.bak*` / `ledger/*.stale*` file must have before it is archived (moved + gzipped) into `archive/ledger/`. Never applies to `<project>.jsonl`, `<project>.seq`, `<project>.jsonl.lock`, or anything under `ledger/.migrated/`, `ledger/.legacy-pinned/`, `ledger/archive/` — those are excluded structurally (find `-maxdepth 1` + name-pattern match), not by this TTL. `<= 0` archives matching debris regardless of age. Override per-run with `--ledger-bak-ttl-days N`. |
| `OUTBOX_TTL_DAYS` | 30 | `scripts/rotate-metrics`: minimum age (days) an `outbox/<project>/<agent>.md` report must have before it is archived into `archive/outbox/<project>/`. `<= 0` archives all reports regardless of age. Override per-run with `--outbox-ttl-days N`. |
| `THRESHOLD_MB` | 10 | Pre-existing, unchanged by S0-T9: size threshold for top-level `*.jsonl` rotation. Documented here only because it now sits alongside the two knobs above in the same script. |

Rollback: `scripts/install-rotate-cadence --uninstall` removes the weekly cron entry (marker `# v11-rotate-metrics`, default Sun 04:15) that fires `rotate-metrics` unattended; running `rotate-metrics` by hand is unaffected either way. Every install/uninstall backs up the crontab to `~/.v11-backups/crontab.<ISO8601Z>` first. Test: `tests/test_rotate_metrics_subdirs.py` (regression-marked: `test_ledger_jsonl_seq_lock_byte_identical_even_over_threshold`), `tests/test_install_rotate_cadence.py`.

### S0-T3/S0-T8/S0-T9 review-fix levers

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_ORCH_SKILL_REQUIRED` | on | review #19 E2. `scripts/check-stamp-drift`: a missing team-orchestrator `SKILL.md` (path from `V11_ORCH_SKILL_MD`, default `$HOME/.claude/skills/team-orchestrator/SKILL.md`) is a FAIL (non-zero exit) so the surface can't silently drop out of a CLOSE gate. `=off` restores the pre-fix behavior: a missing file only warns and the script still exits 0 on that account. |
| `V11_ORCH_SKILL_MD` | `$HOME/.claude/skills/team-orchestrator/SKILL.md` | S0-T8. `scripts/check-stamp-drift`: path of the team-orchestrator `SKILL.md` whose frontmatter `version:` and footer `current:` pointer are checked against the git-log anchor. The skill lives in its own repo outside `V11_ROOT`, hence an absolute path. Fixture tests point it at a tmp file. |
| `V11_ROTATE_SETTLE_SECS` | 1 | review #20 E1. `scripts/rotate-metrics` `rotate_file()`: seconds to `sleep` after `mv` and before `gzip`, so an in-flight append to the just-renamed inode has time to land. `0` in tests. Only fences top-level `*.jsonl` files that also have a `<file>.lock` sibling the writer holds around its append (`flock -w 10` before the `mv`, skipping that one file with a warning on timeout) — a writer without a lock sibling is not fenced at all; see the TOP-LEVEL CONCURRENCY note in the script's header. |

Test: `tests/test_check_stamp_drift.py` (`test_missing_orch_skill_md_required_exits_nonzero`, `test_missing_orch_skill_md_required_off_warns_and_exits_zero`), `tests/test_rotate_metrics_subdirs.py` (`test_top_level_locked_file_is_skipped_and_left_intact`, `test_top_level_unlocked_file_over_threshold_rotates`).

### S0-T10 Non-git surface backups

`scripts/backup-surface` (ticket #89) makes point-in-time copies of the non-git V11 surfaces (`~/.claude/agents`, `~/.claude/hooks`, `~/CLAUDE.md`, `~/.claude/docs`). No on/off lever: it is a manual tool, nothing runs it unattended. It refuses a path already under git unless `--force`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_SURFACE_BACKUP_ROOT` | `~/.v11-backups/surfaces` | `scripts/backup-surface`: backup root. Each backup lands in `<root>/<YYYYmmdd-HHMMSS>/<absolute path mirrored>`; `--list` and `--restore` read from the same root. Test: `tests/test_backup_surface.py`. |

Rollback of the S0-T10 git-inits: the `~/typesafe` and `~/.claude/skills` repos are local only (no remote); removing `<repo>/.git` and the `.gitignore` S0-T10 added undoes either one; the working files are untouched. The stale `~/.claude/hooks/spawn_claude_window.py` deleted in S0-T10 is restorable with `scripts/backup-surface --restore ~/.v11-backups/surfaces/20260925-212735/path/to/operator-home/.claude/hooks/spawn_claude_window.py`.

## Unreleased — 2026-09-22 triage fixes

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_IDENTITY_CONTINUATION` | on | improvements/58. `v11_ledger_append` (`hooks/lib/common.sh`): a `created` event for a subject that already has an OPEN identity (last ledger event not `completed`/`cancelled`) reuses that identity's `create_seq` and is stamped `continues:true`, instead of minting `create_seq+1`. Rehydrated and re-created tasks therefore continue the same task. `=off` restores always-mint (every re-create is a new identity; old copies stay open). |
| `V11_DELETE_CANCELS` | on | improvements/63. `hooks/sync-tasks` `deleted)` arm: `TaskUpdate(status="deleted")` writes a `cancelled` ledger event (reason `deleted`, `requested_status: "deleted"`), drops the task from the session's `open_tasks`, folds its prior bucket, and tombstones its identity. The replay makes it terminal and a paired review sibling follows. `=off` restores the old field-only handling (the task stays open in every view). |
| `V11_REPLAY_ORDER` | (parsed) | improvements/60. `v11_replay_ledger` `sort_key`: events are folded in parsed-UTC-instant order with `seqno` as tiebreak. The ts string is not an order (the ledger mixes `+02:00` and `+00:00`; a completion sorted before its creation and the task showed open), and `seqno` alone is not either (hand-appended events have none). `=ts-string` restores the old string sort. |
| `V11_NONSTATUS_CREATES_TASK` | off | improvements/60. `v11_replay_ledger`: an event that is not `created`/`in_progress`/`completed`/`blocked`/`cancelled` (e.g. `artifact_warn`, `field_update`) updates an existing task record but never creates one. Before, an identity-less `artifact_warn` became a phantom pending task (+1 total/pending in 6 projects). `=on` restores the phantom. |
| `V11_SIBLING_FOLLOWS_PARENT` | on | improvements/58 item 3. `v11_replay_ledger` (`hooks/lib/common.sh`): an open V11.21 review sibling projects as `cancelled` (reason `parent_cancelled`) when its parents are all cancelled. A parent counts only if it claimed `(session_uuid, metadata.review_of)` in a session the sibling lived in AND its `subject_norm` equals `normalize_subject` of the sibling's subject minus `Review: `; task_id alone is never trusted (sessions reuse ids). Hand-written review subjects never follow. Projection only; the ledger is not written. `=off` restores stranding. |
| `V11_REPLAY_REHYDRATE_ALIAS` | on | S1-T2c. `v11_replay_ledger` (`hooks/lib/common.sh`): a `created` whose `metadata.rehydrated_from.identity` (stamped by `v11-resume-tasks`) names a different identity already folded is an alias: its own identity's events fold into the original. A task renamed before a restart is rehydrated under its new `subject_norm`, so `v11_ledger_append` minted a fresh identity and the original stayed open forever. Only an identity's first event can alias it; a malformed `rehydrated_from`, an unknown target, or a target already completed or cancelled at that point of the fold (a stale handoff rehydrating finished work) is ignored; chains resolve with a loop guard; a sibling of an aliased parent follows it by either norm. The replay reports `alias_count` when an alias fired, and the cutover REGRESSION-GUARD adds it back to the replay total (`alias_carveout` in `ledger-cutover.jsonl`). Read-side: existing ledgers heal with no rewrite. `=off` restores the split. Test: `tests/test_ledger_replay.py` (`TestRehydrateAlias`). |
| `V11_PROJECT_SLUG_GUARD` | on | improvements/59. `hooks/lib/common.sh` `v11_valid_project_slug`: a project name must start with a letter or digit (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`), and a `$HERCULES_ROOT/{name}` capture must be an existing directory. Applied in `_v11_detect_project_from_path` (all conventions) and both tiers of `v11_read_active_project`. `=off` restores the old permissive rule (`.`, `..` and dot-dirs accepted; top-level files count as projects). The `track-autonomy` `mkdir -p` removal is unconditional. |

## v11.44 — Orchestrator Quality

Spec: `sessions/v11-orchestrator-quality/spec.md`. Fold-table: `hooks/lib/actor-canonical.json`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_ORCH_QUALITY` | on | Read-side actor canonicalization. `=off` makes `v11_canonical_actor` the identity, so `agent-scorecard`/`agent-effectiveness` revert to literal-string matching (the orchestrator family splits back into 5 rows). Pure read-side — no data change. |
| `V11_BRIEF_REVIEW` | on | Gates brief grading. `=off` makes `scripts/grade-briefs` a no-op (exit 0), stops `sync-tasks` stamping `cause_kind="execution_defect"` on new lite findings, and skips the `orchestrator-briefing-quality` consumer in `check-improve-subagent-triggers`. Additive fields only — legacy readers unaffected either way. |
| `V11_RUNTIME_ERROR_CAPTURE` | on | Gates the G2 fix in `track-autonomy`. `=off` restores the legacy `.error`-only outcome check (identical pre-v11.44 behavior — the runtime-error layer goes dormant again). `is_error` detection cannot false-positive on a success. |
| `V11_ORCH_BRIEF_DEFECT_THRESHOLD` | 0.30 | Briefing-defect rate at/above which the `orchestrator-briefing-quality` consumer trigger fires. |
| `V11_ORCH_BRIEF_MIN` | 3 | Minimum briefs graded before the consumer trigger can fire (noise floor). |

Deferred (need a `dispatch-trace` v2 `session_uuid` bump): orchestrator/subagent runtime split, per-brief override attribution. Not levers — documented follow-ons.

## v11.43 — Timing Calibration

Anchor doc: `docs/BUILD_TIMING.md`. Re-derivation: `scripts/build-timing`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_TIMING_ANCHOR` | on | Prompt-level lever (like `V11_LIVE_OPS_LANE`). Gates the wall-clock estimate line added to the interview STEP 4c plan-summary (`playbooks/interview.md`). `=off` suppresses the estimate — the gate reverts to task-count-only ("Plan summary: {N} tasks across {formation}. Apply?"). The `scripts/build-timing` script, `docs/BUILD_TIMING.md`, the `task-patterns.md`/`SKILL.md` anchors, and the retro `timing_actual` field are all additive and inert without acting on the estimate, so `=off` is a clean revert of the behavior with no data change. |

## v11.42 (candidate) — Task-State Integrity — Wave 1 + Wave 2

Spec: `sessions/v11-task-state-integrity/spec.md`. Recon+review artifacts: `sessions/v11-task-state-integrity/recon-notes/README.md`.

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_CANCELLED_COUNTER` | on | W1-T1 (RC4). `hooks/lib/common.sh` replay populates aggregate `.cancelled` counter from per-record status sum. `=off` sets `.cancelled=0` unconditionally (pre-v11.42 behavior — the field is still present in the schema, just always zero). Additive; zero downstream consumers per recon-6, so `=off` is a no-op for observed callers. |
| `V11_LEDGER_AUDIT_NOLEDGER` | on | W1-T2 (RC5a). `v11_rebuild_project_aggregate` empty-scan-preserve branch (`common.sh:L280`) appends `{decision:"empty-scan-preserve", has_ledger:bool}` JSONL entry to `~/.agent-metrics/ledger-cutover.jsonl` alongside the existing stderr warn. Makes no-ledger dormant projects programmatically discoverable. `=off` skips the append (stderr signal remains). Never blocks the rebuild. |
| `V11_IDENTITY_HELPER` | on | W1-T3 (RC1). `v11_resolve_identity(project, task_id, session_uuid, subject)` bash helper walks `~/.agent-metrics/ledger/${project}.jsonl` for most-recent `created` event and returns `{create_seq, subject_norm, found}` JSON. Canonical-identity resolution reused by `/align-aggregate` v1.3+ and Wave 2 T3's age-out logic. `=off` makes the helper unconditionally return `{"found": false}` — callers fall back to their own inline logic. |
| `V11_PAIR_ID_DURABLE` | on | W2-T1 (RC3). `hooks/sync-tasks` mints `pair_<sid8>_<seq>_<rand6hex>` where `seq` is sourced from durable ledger max (not per-session STATE_FILE counter). Belt+braces against STATE_FILE reset + `legacy-cli` fallback. `=off` reverts to `pair_<sid8>_<seq>` where seq is the STATE_FILE-local counter (pre-v11.42; retains collision risk). Old pair_ ids stay resolvable as opaque strings under either setting. |
| `V11_REVIEW_SIBLING_AGEOUT` | on | W2-T3 (RC2). `/align-aggregate` skill v1.3 age-out logic — invoked via `hooks/session-end` when `V11_ALIGN_ON_SESSION_END=apply` — cancels V11.21 review siblings whose `metadata.parent_status="pending"` AND `parent_unblocked_at` older than `V11_REVIEW_SIBLING_AGEOUT_DAYS`. Emits `ev:cancelled` with `reason="review_sibling_ageout"`. `=off` disables age-out; siblings sit pending forever (pre-v11.42). |
| `V11_REVIEW_SIBLING_AGEOUT_DAYS` | 14 | W2-T3. Age cutoff in days. `legacy-cli`-created siblings use 2× this value (default 30 days) as best-effort protection since `v11_session_is_live("legacy-cli")` is structurally false — see spec non-goal for rationale. Tighten (lower) or loosen (higher) freely. |
| `V11_AGEOUT_GUARD_CARVEOUT` | on | W2-T2 (RC5b). `common.sh:L816` GUARD ROLLBACK carve-out: when replay-vs-legacy delta is fully accounted for by ledger `cancelled` events with `reason="review_sibling_ageout"`, do NOT trip the regression-guard. Compares `(replay + reason_ageout_count) vs legacy` instead of raw `replay vs legacy`; against the prior aggregate it adds back only the age-outs new since that aggregate (`max(0, ageout_count - prior .ageout_count)`, S2-R4). The count is the replay's `.ageout_count`. **FOOTGUN**: setting `V11_REVIEW_SIBLING_AGEOUT=on + V11_AGEOUT_GUARD_CARVEOUT=off` reproduces exactly the silent-revert the bundling was designed to prevent. **Load-time protection**: `common.sh` WARNs loudly + auto-forces `CARVEOUT=on` when it detects `AGEOUT=on + CARVEOUT=off`. The reverse combo (AGEOUT=off + CARVEOUT=on) is inert (carve-out has zero ageout events to credit) and safe. |
| `V11_ALIGN_ON_SESSION_END` | dryrun | W2-T3. `hooks/session-end` invocation of `/align-aggregate` skill for automatic phantom-cleanup. `=dryrun` (default) runs the skill in list-phantoms mode — reports what it WOULD cancel but writes nothing. `=apply` opts in to auto-apply cancellations. `=off` skips the invocation entirely. |

## v11.41 (candidate) — Cross-Session Handoff Loop — sprint-01

| Env Var | Default | What it does |
|---------|---------|--------------|
| `V11_HANDOFF_DOC_DRIFT` | on | L1.1 (v11-handoff-cross-session-loop). `scripts/handoff` reads cached `sessions/{project}/.drift-scan-result.json` (from prior `/v11-drift`) and folds a `⚠ DOC-DRIFT` warning into `handoff.md` `_WARNING_BLOCK` when grade ∈ {C, D, F}. `=off` suppresses the warning entirely (cache file untouched). Missing / empty / malformed cache is silently skipped either way. Test: `tests/test_handoff_doc_drift.py`. |
| `V11_LOOP_BASELINE` | on | L1.3b (v11-handoff-cross-session-loop). `scripts/handoff` invokes `scripts/lib/loop_baseline.py` AFTER the QR-1 pending reconcile and QR-2 category re-derivation, BEFORE the staging→final promotion. Writes `sessions/{project}/.loop-baseline.json` atomically (schema v1: `handoff_at`, `git_head`, `spec_md_mtime`, `autonomy_level`, `expected_open_tasks_count`, `handoff_tasks_hash`, `baseline_source` + Sprint 3 slots). Load-bearing for L2.1 boot-delta, L2.3 rehydrate verification, L2.4 loop-ack. `=off` skips the write entirely; the write is non-blocking (timeout 5s + `\|\| echo WARN`), so it can NEVER orphan a handoff. Tests: `tests/test_loop_baseline.py` (unit, 54 tests), `tests/test_loop_baseline_integration.py` (integration, L1.3c). |
| `V11_LOOP_BOOT_DELTA` | on | L2.1 (v11-handoff-cross-session-loop). `hooks/detect-project` reads `.loop-baseline.json`, diffs against current disk (`git_head`, `spec_md_mtime`, `expected_open_tasks_count`), and emits a `⚡ SINCE LAST HANDOFF` banner via `hookSpecificOutput.additionalContext` on stdout — the model actually sees this (stderr from hooks is invisible per the 2026-09-01 dogfood). `=off` skips both diff compute and emit; L2.3 rehydrate verification and L2.2 freshness gate stay live. Also caches the diff field list in `_RV_DELTA_FIELDS` for L2.4 `handoff_ack.baseline_delta_fields` to reuse without re-derivation. Test: `tests/test_boot_delta.py`. |
| `V11_HANDOFF_FRESHNESS_GATE` | on | L2.2 (v11-handoff-cross-session-loop). Same `detect-project` handler: if `handoff.md` mtime exceeds `V11_HANDOFF_MAX_AGE_DAYS` (default 7), prepends `⚠ STALE HANDOFF: … verify state before resuming.` to the L2.1 `additionalContext` block. `=off` disables the check entirely, keeping `V11_HANDOFF_MAX_AGE_DAYS` free as a tightening knob (a 0-day cap would fire on any handoff older than 24h — legitimate tightening, not disable semantics). Test: `tests/test_boot_delta.py::TestFreshnessGate`. |
| `V11_ORPHAN_DETECTOR` | on | L2.5 (v11-handoff-cross-session-loop). `hooks/session-end` scans `$SESSIONS_ROOT/*/.last-spawn-at` files older than `V11_LOOP_ORPHAN_MINUTES` (default 60). For each latch, checks `~/.agent-metrics/loop-events.jsonl` for a matching `handoff_ack` OR `rehydrate_missed` event (same project, ts >= latch mtime). Missing → emits `HANDOFF_ORPHAN` event via `scripts/lib/loop_events.py`, then touches `{latch}.orphan-notified` sibling marker for fire-once (persistent across sessions — the observer that later re-notices should not re-emit). `=off` disables the entire scan. Never blocks session-end (hook always exits 0). Also gated by `V11_LOOP_ORPHAN_MINUTES > 0`. Test: `tests/test_orphan_detector.py`. |
| `V11_LOOP_ORPHAN_MINUTES` | 60 | L2.5 orphan-age threshold (integer minutes). Setting to `0` acts as an alternative disable path for the whole detector. Above 0, tighten (lower) or loosen (higher) as needed. |
| `V11_LOOP_ACK_EVENT` | on | L2.4 (v11-handoff-cross-session-loop). Emits a `handoff_ack` event to `~/.agent-metrics/loop-events.jsonl` when rehydrate verification passes (counts + IDs match, no divergence). Carries `prev_handoff_at` (from baseline), `identity_matched=true`, and `baseline_delta_fields` reused from L2.1's diff — grep receipts of healthy cycles. Independent of `V11_REHYDRATE_VERIFY` so operators can silence receipts without silencing the `rehydrate_missed` failure emission path. Test: `tests/test_rehydrate_verification.py::TestHappyPath`. |
| `V11_REHYDRATE_VERIFY` | on | L2.3b (v11-handoff-cross-session-loop). `hooks/detect-project` compares `sessions/{project}/.loop-baseline.json.expected_open_tasks_count` (recorded at emit by L1.3b) against the live per-session `task-state.json` count. On divergence, discriminates a `failure_mode` (`skill_not_invoked` \| `gate_off` \| `script_error` \| `manual_override` \| `identity_mismatch`) and appends a `rehydrate_missed` event to `~/.agent-metrics/loop-events.jsonl` via `scripts/lib/loop_events.py` (L2.3a). Fire-once via `~/.agent-metrics/sessions/$V11_SESSION_ID/.rehydrate-verify-done` marker (same pattern as `.handoff-surfaced` and `.review-surfaced-*`). Piggybacks the existing `detect-project` hook — no new hook wiring per Sprint 2 constraint. `=off` skips verification entirely (marker not written). Identity-mismatch discrimination requires `sessions/{project}/handoff-tasks.json` to be present for ID-set comparison. Test: `tests/test_rehydrate_verification.py` (L2.3c). |
| `V11_HANDOFF_FORCE_RECONCILE` | on | L1.2 (v11-handoff-cross-session-loop). `scripts/handoff` runs `v11_rebuild_project_aggregate` on the per-session path too, not only the aggregate-fallback path. Extends the existing rebuild at `handoff:517-524` (which only fires when `STATE_SOURCE=aggregate`) with a mirror block at `handoff:527-546` gated on `STATE_SOURCE=per-session` + this lever, `timeout 5`. Fixes the stale-durable-aggregate problem (2026-09-01 dogfood: v11 project aggregate was 11 days stale on this box). `=off` restores per-session-skip behavior. Independent of the aggregate-path rebuild, which fires unconditionally regardless of this lever. Tests: `tests/test_handoff_force_reconcile.py` (4 tests: on/off × per-session/aggregate). Also fixed a pre-existing bug in the same edit: both rebuild subshells now pass `V11_HOME="$V11_HOME"` instead of the hardcoded `"$HERCULES_ROOT/v11"` (which silently no-op'd whenever `HERCULES_ROOT` didn't have v11 co-located — invisible in production, but the class of bug the drift-check block at `handoff:1615/1618` already got right). |

## v11.37 — Alignment Remediation — 2026-08-28

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_REGISTRY_RECONCILE` | on | v11.37 W1-T1 ticket #38-F2: `scripts/reconcile-agent-registry` runs its full add/prune/atomic-write path. `=off` puts the reconciler into pure no-op mode (exits 0 without touching `~/.agent-registry/agents.json`) — used during incident containment or when a stale environment shouldn't get reconciled. Independent of `--dry-run`/`--apply`/`--revert` flags: any of those exit cleanly at 0 with the lever off. |
| `V11_LEDGER_STRICT_ATTRIBUTION` | off | v11.37 W1-T2 ticket #38-F1: write-time normalization gate in `v11_ledger_append` (`hooks/lib/common.sh:2436`). Tri-state — `off` (default, pre-v11.37 behavior — no observability); `advisory` or `on` — for agent-authored events (`created`/`review`/`artifact_warn`) missing `owner`+`metadata.agent`+`recommended_agent`, emit a STDERR WARN and mirror the event to `~/.agent-metrics/unattributed-events.jsonl` for later analysis. **Primary ledger write ALWAYS proceeds** — this is observability, not data-loss. Read-only companion audit: `scripts/audit-ledger-attribution`. |
| `V11_INDEX_BODY_CHECK` | on | v11.37 W2-T1 ticket #42: `scripts/check-index-body-status-consistency` runs. `=off` no-ops the check (exit 0). Wired into `scripts/handoff:1425` drift-check loop + `run-tests --regression`. See `docs/DRIFT_CHECKS.md`. |
| `V11_ROLLBACK_LEVER_CHECK` | on | v11.37 W2-T2 ticket #44: `scripts/check-rollback-lever-drift` runs. `=off` no-ops (exit 0). Same wiring surfaces as `V11_INDEX_BODY_CHECK`. |
| `V11_REGISTRY_CHECK` | on | v11.37 W2-T3 ticket #38-F2 companion check: `scripts/check-registry-drift` runs the 3-way disk↔registry↔ledger reconciliation. `=off` no-ops (exit 0). Same wiring surfaces. A FAIL from this check IS a `--spawn` block (data-honesty class: adversarial-lite-reviewer-shaped regressions must not silently hide). |
| `V11_DRIFT_VERBOSE` | off | v11.37 W2-T4 UX lever for `scripts/handoff` drift-check block. `off` (default) — 1-line summary only (`drift checks: N ran, P PASS, W WARN, F FAIL`); `on` — full per-check WARN/FAIL block on stderr. FAIL blocks always print regardless of verbose. |
| `V11_SKIP_DRIFT_CHECKS` | (unset) | v11.37 W2-T4 unified operator bypass. Setting to `1` (or passing `--skip-drift-checks` to `scripts/handoff`) skips the ENTIRE drift-check family in one lever. Individual per-check env-vars still work at the script level. Recovery path for stuck operators. |

## v11.36 — Proactive Discipline (W2) — 2026-08-28

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_HANDOFF_MTIME_GUARD` | on | Ticket #41 F1 (post-CLOSE follow-up shipped 2026-08-28): `scripts/handoff` refuses to regenerate `handoff.md` when the file is NEWER than the trigger basis (`.session-summary.md`, falling back to `STATE_FILE`). The unattended `session-end` auto-emit path is what this protects — the `/handoff` skill and any manual invocation pass `--force` implicitly. Content-hash fallback: if the summary is still the V11.17 auto-stub (fingerprint match), the guard does not fire and regen proceeds (nothing to protect). `=off` reverts to the pre-F1 always-regenerate behavior. See `improvements/41-auto-handoff-clobbers-hand-written.md` and `tests/test_handoff_mtime_guard.py`. |
| `V11_TASK_PROJECT_AUTODEFAULT` | on | Controls `sync-tasks` Strategy 1.7 (#36-F1): when `metadata.project` is absent and no task/session/ledger-identity strategy resolves it, checks whether the session's CWD is inside `$SESSIONS_ROOT/{project}/` and auto-defaults to that project. `=off` disables Strategy 1.7 entirely (falls through to Strategy 2 / NO PROJECT HOME as before) AND restores the original WARN/ADVISORY text at the two downstream sites (the `TaskCreate` implicit-attribution warning and the `TaskUpdate(completed)` Bug E advisory) instead of the V11.36 INFO-level downgrade. The all-strategies-failed "NO PROJECT HOME" warning is unaffected either way — it stays WARN. |
| `V11_SPAWN_NOTIFY_ON_IDLE` | off | Doc-only, prompt-level lever in `orchestrate.md` §"Idle notification hygiene" (#36-F2 fold-in, W3-T1/T2/T3). Governs ONLY the orchestrator's own default, when messaging a peer session via `SendMessage`, of whether to subscribe for that peer's idle notice — not code-enforced, no hook reads it. `=on` reverts to the pre-sprint default of always subscribing. It has no effect on `Agent()`-tool background spawns: those fire an unconditional harness idle-completion event with no per-call field to gate — do not treat this lever as suppressing that (see the §"Idle notification hygiene" audit finding: 0 `notify_when_idle` occurrences existed in any spawn template prior to this change). |
| `V11_CLASS_INCLUDED_CHECK` | on | `scripts/check-class-included` (W2-T2, wired into `scripts/handoff` and `scripts/run-tests --regression`) no-ops instead of flagging a class/function referenced in source without a matching `#Include`/import line. `=off` disables the check entirely (exit 0 always) — a confirmed missing-include drift (exit 1) will neither block `handoff --spawn` nor soft-block the regression tier. See `docs/DRIFT_CHECKS.md`. |
| `V11_GIT_TASKLIST_CHECK` | on | `scripts/check-git-tasklist-alignment` (W2-T3, wired into `scripts/handoff` and `scripts/run-tests --regression`) no-ops instead of flagging git-modified/untracked files not tied to any completed task's `metadata.artifacts`. `=off` disables the check entirely (exit 0 always). Advisory-only either way — this check never FAILs (exit 2 WARN at most), so it never blocked `--spawn` or the regression tier to begin with. See `docs/DRIFT_CHECKS.md`. |
| `V11_HOTKEY_SYNC_CHECK` | on | `scripts/check-hotkey-sync` (W2-T4, wired into `scripts/handoff` and `scripts/run-tests --regression`) no-ops instead of flagging a hotkey present on one configured surface but missing from another. `=off` disables the check entirely (exit 0 always). Advisory-only either way — this check never FAILs (exit 2 WARN at most). See `docs/DRIFT_CHECKS.md`. |

## v11.35 — Artifact-on-Complete Advisory — 2026-07-29

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_ARTIFACT_ON_COMPLETE` | `warn` | Controls the improvement-16 audit-class completion check in `hooks/sync-tasks`. `warn` (default) = model-visible `additionalContext` advisory + a durable ledger row (`ev:"artifact_warn"`/`ev:"artifact_exempt"`) when an audit-class task (Explore/adversarial-reviewer/adversarial-lite-reviewer/coherence-reviewer, or an Audit/Verify/Inventory/Map/Find/Investigate subject, or `metadata.task_class:"audit"`) completes with no evidence in `files_changed`/`summary`/`review.summary`/`self_review`. `off` = the check does not run at all (no advisory, no ledger row). There is no `block` mode — `sync-tasks` is PostToolUse and always exits 0 (see file header); a 5-lens swarm review found the originally-proposed block mode structurally impossible. |
| `V11_ARTIFACT_STATUS` | on | `=off` disables the `scripts/status` consumer line ("Artifact evidence: N advisory(ies) recorded, M exempt") that reads the ledger rows above. Shipped in the same change as the producer. |

## v11.34 — Session-Aware Write-Gate — 2026-07-20

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_WRITE_GATE` | `block` | Controls the genuine-stall branch of `guard-write-gates` (a session that HAD a task in_progress and let it lapse). `block` (default) = today's `exit 2` behavior, unchanged. `warn` = downgrades the stall block to a stderr advisory (never exits 2). `off` = disables task-state enforcement entirely (both stall and fresh-session paths skip straight through). Does not affect the `total<2` or completed-project exemptions, which are unconditional. |
| `V11_BASH_WRITE_WARN` | on | `=off` disables the `guard-enforcement` advisory that fires when a Bash command performs a source-file write (heredoc `<<`, `>`/`>>` redirect, `tee`, `sed -i`, `dd of=`) in a task-bearing project. The advisory never blocks either way — this knob only silences the stderr warning and skips the synthetic audit row. |
| `V11_SESSION_LIVENESS_MINUTES` | 15 | v11.37 W1-T5 documented (was silent). Tuning knob (integer minutes) — NOT an on/off toggle. Controls the aliveness window used by `v11_session_is_live()` in `hooks/lib/common.sh:3649` for write-gate + active-project ownership decisions + review-queue GC coupling. Higher values keep dead sessions treated as live longer (less stealing); lower values are stricter. Related sites: `hooks/lib/common.sh:4445-4535` (review-queue liveness/GC), `common.sh:3705` (V11_REVIEW_CROSS_PROJECT_CHECK also reads this indirectly). |

## v11.33 — Lossless Sync Fallback — 2026-07-17

| Env Var | Default | What it does |
|---------|---------|-----------------|
| `V11_SYNC_SCRATCH_RECONCILE` | on | `=off` disables the entire (c) lane: no `.needs-reconcile` marker recording on the raced path, no top-of-hook drain in sync-tasks, no session-end drain. Restores pre-v11.33 scratch behavior (raced completion may leave the per-session scratch undercounted until manual repair). The `scripts/handoff` prefer-aggregate guard keys on marker presence, so with recording off it never triggers. |
| `V11_SYNC_NARROW_HOLD` | on | `=off` restores the legacy whole-process FD-201 hold (lock released at hook exit instead of after the last STATE write). Only affects contention frequency, not correctness. |
| `V11_SYNC_TASKS_LOCK_TIMEOUT` | 10 (seconds) | Numeric knob, not on/off — introduced in the v11.32-era BugG remediation, formalized here. Raises/lowers the FD-201 `flock -w` budget before the unserialized fallback fires. Tests set it to 0 to force the fallback deterministically; production default unchanged. |

## v11.32 — Half-Wired Loop Audit — 2026-07-15

No new rollback env vars were introduced this version — the audit closed half-wired *code paths*
(installers, attribution readers, gate re-wiring), not new toggles. One existing lever changes
behavior:

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_AUTO_REHYDRATE` | on | Originally introduced in V11.17 (doc-only for 6 versions — see the V11.17 section below for the original lever). As of v11.32 (H5) it is now **code-enforced** in `scripts/v11-resume-tasks`: setting `=off` disables the actual auto-rehydration-from-`handoff-tasks.json` behavior at the code level, not just the doc-level intent. |

Other v11.32 items — git-hook installer fixes (worktree/symlink `--git-common-dir` resolution),
`agent-scorecard --routing`, `guard-effort` matcher revival (`Task|Agent`), `review-queue-maintenance`
flock + `review-cadence` wiring, `scripts/ledger-verify`, auto-pair `scope:"small"` stamping, and the
`--regression` / `--regression-extended` two-tier split — are CLI-flag-level, prompt-level, or bug
fixes to existing gated code paths. The CHANGELOG entry does not name a dedicated new rollback env
var for any of them.

## v11.31 — Pre-Scope Actuation + Two-Source Token Capture — 2026-07-15

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_SCOPE_WARN` | on | `sync-tasks` stops warning on missing/invalid `metadata.scope` for work tasks (review-sibling/blocker tasks remain exempt either way). |
| `V11_PRESCOPE_SMELL` | on | `sync-tasks` stops warning on multi-deliverable description smells (conjunction / 3+ runbook steps / >600 chars on a non-small task). |
| `V11_PRESCOPE_CONTEXT` | on | Fired pre-scope advisories no longer emit the PostToolUse `hookSpecificOutput.additionalContext` envelope — the orchestrator model stops seeing the advisory inline in the `TaskCreate` tool result (this is the dogfood-verified visibility fix). |
| `V11_PRESCOPE_LEDGER` | on | Fired advisories stop landing as `ev:prescope` durable-ledger rows — both the status-neutral event and the replay-fold counter-inflation guard are disabled. |
| `V11_PRESCOPE_STATUS` | on | `scripts/status` stops printing the `Pre-scope: X% scoped, N advisories open` line. |

The two-source token-capture fix (root cause: `track-agents` probed hypothesized snake_case fields
while real harness payloads are camelCase, e.g. `totalTokens`) reuses the existing `V11_TOKEN_CAPTURE`
lever from V11.29 — no new env var was introduced for it.

## v11.30 / W2-T6 — Version-Stamp Drift Guard

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_STAMP_DRIFT` | on | `scripts/check-stamp-drift` (invoked from `scripts/run-tests` alongside the drift check, and — as of v11.36 W2-T5 — also from `scripts/handoff` at the pre-handoff drift-check site) no-ops instead of comparing version stamps across the agent registry, README, VERSION.md, and CLAUDE.md against a git-derived anchor; a real version-stamp mismatch will not soft-block either regression tier (`--regression` or `--regression-extended`), and will not surface in `handoff` output either. **v11.36 W2-T1 extension**: this same lever ALSO gates the independent per-project version-file consistency phase (`sessions/{project}/.stamp-drift-extra.json`) — `=off` disables both the git-anchor comparison and the per-project phase together; there is no separate lever for the extension. |

## v11.30 / W5-T16 — Cross-Session Verdict Fold-Back

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_REVIEW_LEDGER` | on | `v11_review_queue_mark_done` skips B1 (durable verdict store at `~/.agent-metrics/review-verdicts/{project}/`), B2 (`ev:"review"` ledger event), and B4 (verdict_ref/verdict_sha on the queue done event); `mark-done` reverts to severity-only behavior identical to pre-W5-T16. Independent of `V11_REVIEW_ENFORCEMENT`. |

## V11.29 — Concurrency Lanes, Pre-Scoped Tasks, Token Ledger, Worktree Default

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LANE_LEASE` | on | `hooks/lib/common.sh` lane-lease helpers (`v11_lane_claim/release/force_release/gc/status`) and the `sync-tasks` auto-claim-on-`in_progress`/auto-release-on-`completed` behavior are disabled; no "LANE CONFLICT" advisory, no `~/.agent-metrics/lanes/<project>.jsonl` writes. |
| `V11_PRESCOPE_ADVISORY` | on | `sync-tasks` stops emitting the pre-scoping advisory when a `TaskCreate` sets `metadata.scope=large` or is complex/novel without `metadata.deliverable_of`. |
| `V11_TOKEN_CAPTURE` | on | `dispatch-trace-append` ignores `--tokens/--tool-uses/--duration-ms/--event`, and `track-agents` skips passthrough of harness-reported usage into `usage.jsonl`; scorecard/effectiveness `avg-tokens/spawn` column stays omitted. |
| `V11_WORKTREE_DEFAULT` | on | Editing spawns no longer default to `isolation:"worktree"` (skill rule 20 + orchestrate + context-tiered-mode); docs-level policy toggle only — does not touch `scripts/worktree-sweep` itself. **Zero code consumers** (improvements/11 M4): no script or hook reads it. The harness, not V11, picks the worktree base ref; the V11-side guard is `V11_WORKTREE_BASE_CHECK`. |

## V11.28 — Handoff Steering Prompt

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_HANDOFF_STEER` | on | No steer span is prepended into `$PROMPT`/`handoff.md`, and the sidecar `.handoff-steer.md` (or `--steer` flag) is not consumed — file is left in place rather than archived to `.handoff-steer.md.prev`. |
| `V11_STEER_PREV_GRACE_SECS` | 300 | v11.37 W1-T5 documented (was silent). Used only with `V11_STEER_PERSIST=off` (S2-R3). Tuning knob (integer seconds) — NOT an on/off toggle. Controls the freshness window for V11.28.2 steer re-bake from `.handoff-steer.md.prev`. If a prior handoff in this episode consumed the sidecar to `.prev`, the next handoff within `V11_STEER_PREV_GRACE_SECS` seconds re-bakes from the fresh `.prev` to keep the steer intact. Higher values = longer episode window; lower values = stricter one-shot semantics. Read at `scripts/handoff:1781`. |
| `V11_STEER_PERSIST_MAX_AGE_SECS` | 259200 | Review #20 (S2-R3 follow-up). Tuning knob (integer seconds; `0` = no cap). `scripts/handoff` retires `.handoff-steer.consumed.md` to `.acked` instead of re-injecting it once its mtime is this old (default 72 h), whichever session regenerates. Bounds a kept steer whose successor never Read or regenerated `handoff.md`. Test: `tests/test_handoff_steer.py::TestSteerPersist::test_age_cap_is_tunable_and_zero_disables_it`. |
| `V11_STEER_PERSIST` | on | S2-R3 (F38). `scripts/handoff`: a steer baked from `.handoff-steer.md` or `--steer` is also written, when `handoff.md` is promoted, to `sessions/<project>/.handoff-steer.consumed.md` (line 1 `<!-- v11-steer-consumed session=<id> at=<iso> source=file|flag -->`, then the sanitized, capped steer). The session is the hook-stdin `V11_SESSION_ID` under session-end, else `CLAUDE_CODE_SESSION_ID`, else `V11_SESSION_ID`; empty for a plain terminal run. Every later regeneration with no new sidecar or `--steer` re-injects it (stderr `NOTE: re-injected the consumed steer`). `hooks/detect-project` retires it when a Read of exactly `sessions/<project>/handoff.md` carries a session id other than the header's: it is renamed to `.handoff-steer.consumed.md.acked` with an ack line appended. The consumer's own Reads, Reads without a session id, Reads of other files, and Reads by a headless session (`CLAUDE_CODE_ENTRYPOINT` `sdk-*` — `claude -p`, as review-daemon runs, sets `sdk-cli` — `mcp` or `claude-code-github-action`) keep it (the hook uses builtins only; the rename runs once per steer). Review #20: a regeneration also retires it (`.acked`, ack line `via=regen`) when the run's session (the same rule) and the header's are both set and differ and the run is not headless (the successor regenerated, so it has resumed), and (`via=age`) when the kept copy is older than `V11_STEER_PERSIST_MAX_AGE_SECS`; an empty header or run session leaves the age cap only. A new sidecar or `--steer` replaces it. Observed 2026-09-27: SessionEnd regenerated `handoff.md` more than 300 s after `/handoff` and dropped the S2 kickoff steer. `=off` → today's one-shot: no kept copy, re-bake only from a `.prev` younger than `V11_STEER_PREV_GRACE_SECS`, and detect-project retires nothing. Tests: `tests/test_handoff_steer.py::TestSteerPersist`, `tests/test_session_end_split.py::test_consumed_steer_survives_stop_and_session_end`. |
| `V11_SPAWN_LATCH_SECS` | 120 | v11.37 W1-T5 documented (was silent). Duplicate-spawn idempotency latch window (integer seconds — 0 disables). If two `--spawn` invocations of the same project fire within this window, the second is refused as a duplicate (unless `--spawn-anyway`). Prevents accidental double-Zeus-window launches. Read at `scripts/handoff:2455-2460`. |

## V11.27 — Ledger Integrity (six half-wired loops)

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_RETRO_SANITY_GUARD` | on | `scripts/status` stops printing the "retro flywheel likely broken" warning when the retro counter exceeds 10×`V11_RETRO_THRESHOLD`; the fd-201 flock around the retro read-increment-write in `hooks/session-end` still applies (not gated by this var). |
| `V11_A4_DEADGATE_WARN` | on | `track-autonomy` and `scripts/status` stop warning when autonomy level ≥4 and `high_risk_history` is empty (the always-block landing gate itself is unchanged). |
| `V11_DETECT_RECONCILE` | off | Default off — set `=on` to make `hooks/detect-project` emit the read-only `v11_detect_reconcile` JSON block (zombie/discipline + review-queue + fold-families + retro-counter signals). |
| `V11_RQ_TRACE_UNKNOWN` | on | `v11_review_queue_add` stops adding a `trace` field / WARN when admitting `agent_id=="unknown"` entries (still admits them; only the trace/WARN is disabled). |
| `V11_FOLD_RECONCILE` | off (dry-run default) | `scripts/fold-reconcile --apply --confirm` writes are gated behind this; without it, only `--dry-run` propose-only output is available even with `--apply --confirm` passed. |

## V11.26 — Handoff State Machine Extraction + Test-Honesty Lint

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LINT_TEST_HONESTY` | on | `scripts/lint-test-honesty` gate (hard since v11.46, see `V11_LINT_HONESTY_GATE`) in both `scripts/run-tests --regression` and `--regression-extended` is skipped; P1–P4 pattern checks (stderr-subtraction, disjunctive-decision-assert, bare-`_run()`-negative-only-assert, bash case-without-default) do not run. |

## V11.25.1 — Drift-Sweep Follow-ups + Stale Handoff Summary

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_STALE_SUMMARY_CHECK` | on | `scripts/handoff` treats any existing `.session-summary.md` as canonical forever — no mtime/task-state-newer freshness check, no archive to `.session-summary.md.prev.md`, no stub regeneration. |
| `V11_STALE_SUMMARY_GRACE_SECS` | 86400 | Overrides the staleness grace window (seconds) used by the freshness check above; not an on/off toggle. |
| `V11_SESSION_END_REORDER` | on | `hooks/session-end` reverts to emitting `handoff.md` BEFORE `last-session.json` is written, reintroducing the stale-read-of-prior-session bug the reorder fixed. |

## V11.25.0 — Discipline Mechanization + V11.21 Producer Completion

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_POSTCOMMIT_AUTOCLOSE` | on | `hooks/post-commit-close-tasks` does not auto-close in_progress tasks matching `S{N}-T{M}:` in the HEAD commit subject. |
| `V11_POSTCOMMIT_DRYRUN` | off | Set `=on` to log post-commit auto-close matches without writing status_changed events. |
| `V11_VALIDATION_LINT` | on | `hooks/lib/validation_lint.py` (PreToolUse Bash matcher + commit-msg hook) stops enforcing the `Validation:` tag on commits. |
| `V11_VALIDATION_LINT_STRICT` | off | Default warn-only; set `=on` to hard-block commits missing/malformed `Validation:` tags instead of warning. |
| `V11_VALIDATION_LINT_HEURISTIC` | on | Disables the `(verb ∧ number)` heuristic that WARNs on missing tag without false-positiving chore/docs commits. |
| `V11_AUTO_PAIR_REVIEW` | on | `sync-tasks` `TaskCreate` branch stops auto-synthesizing a paired adversarial-lite-reviewer sibling task for medium/complex/novel or medium/high-risk parents. With it on, an INV-7-exempt parent is never paired (#101, S2-R1): `metadata.skip_review=true`, `metadata.review_of` set, or `metadata.agent` `adversarial-*`. |
| `V11_TASKCREATE_DEDUPE` | `advisory` | v11.37 W1-T5 documented (was silent). **Tri-state**, NOT binary: `off` = dedupe disabled entirely, TaskCreate always creates; `advisory` (default) = detect duplicates, log a WARN, still create; `on` = detect and refuse (`exit 2`). Read at `hooks/sync-tasks:782`. Advisory keeps historical behavior while surfacing false-duplicate patterns; strict `on` protects sensitive projects from accidental re-creation. |

## V11.24 — Session-Bind Drift Fix (Strategy 1.6)

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LEDGER_TASK_HOME` | on | `sync-tasks` Strategy 1.6 (ledger `(session_uuid, task_id)` scan when Strategies 1 and 1.5a both miss) is disabled — `TaskUpdate` without `metadata.project` can silently misroute to a stale session-bound project again. |

## V11.23 — Handoff Cross-Project Scope Leak Fix

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_TASK_ROUTE_BY_METADATA` | on | `v11_rebuild_project_aggregate` reverts to V11.15.5 per-session Bug-H quarantine (whole-session include/exclude based on whether ANY task declares $PROJECT). Per-task filter disabled. |
| `V11_HANDOFF_LIVE_RECONCILE` | on | `hooks/sync-tasks` does NOT stamp `_proj` on TaskCreate / TaskUpdate(in_progress); live-snapshot writer disabled. |
| `V11_HANDOFF_CATEGORY` | on | `scripts/handoff` does not emit HANDOFF_CATEGORY banner (TO_BUILD / PAUSED_EXTERNAL / PAUSED_USER / RESUME); no blocker surfacing at top. |
| `V11_GATE_SUBSTANCE` | on | `scripts/handoff` does not check session-summary stub fingerprints (W3 5/29 — unedited stub detection). |
| `V11_GUARD_STALE_TASK` | on | `hooks/guard-stale-task` exits silently (zombie task advisory disabled). |

**Layer 1 softening (V11.23)**: `scripts/handoff` `open_tasks_by_session` filter at lines ~1141, ~1456 now accepts `metadata.project == $PROJECT` OR `metadata.project == null`. No env var — controlled by code path. Safe because Layer 3 ensures null-metadata tasks only land in $PROJECT.json when their session was legitimately for $PROJECT.

**Architectural fix (Layer 3) applies going forward**: Tasks routed by `metadata.project` (with session-project fallback for null) at every aggregate rebuild. **Pre-V11.23 legacy contamination** (tasks accumulated in wrong aggregates whose source sessions are now orphaned) requires manual cleanup — delete the aggregate file and let it rebuild from live sessions, OR run `scripts/reconcile-aggregates --apply`.

**Gate 14** (handoff scope integrity) and `scripts/reconcile-aggregates` are read-only diagnostics and have no rollback (no-ops when nothing to report).

## V11.21 — Agent Routing & Dual-Layer Review

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_AUTO_PAIR_REVIEW` | on | No paired review tasks created; V11.19 queue path resumes |
| `V11_SELF_REVIEW_REQUIRED` | on | Shape-validation of a *present* self_review payload skipped (malformed-JSON synthetic `lite_self` row no longer emitted); absence tracking is a separate lever, see `V11_SELF_REVIEW_ACTUATE` (W5-T15) |
| `V11_CONTRACT_MODE` | on | Prompt-level lever, not code-enforced — read by the team-orchestrator skill (SKILL.md §"Contract Mode"). `off` restores the V11.29 worktree-by-default rule and the V11.21 per-task review flow, and overrides `V11_REVIEW_MODE` and `metadata.contract`. SC-A (2026-09-30). |
| `V11_REVIEW_MODE` | task | Reserved for SC Part B (`wave` or `task`); no hook reads it yet — SC-B1 adds the read in hooks/sync-tasks, which then skips per-task auto-pairing only when `V11_REVIEW_MODE=wave` AND `metadata.contract=true`. Until then use the Interim recipe (per-task-review.md). |
| `V11_DAAO_ROUTING` | on | Phase 4 defaults to `spec-implementer-v11` when `metadata.agent` unset; explicit `metadata.agent` always honored (prompt-level lever — followed by the orchestrator LLM, not code-enforced) |
| `V11_HANDOFF_REVIEW_FILTER` | on | `handoff-tasks.json` reverts to V11.18 shape (pending_parent siblings kept) |
| `V11_WAVE_CHECK` | on | `scripts/wave-check` exits 0 unconditionally (script-level bypass) |

**Coupling**: when `V11_AUTO_PAIR_REVIEW=on`, sync-tasks suppresses V11.19 enqueue for tasks whose parent has `metadata.review_task_id` set, unless it names a `pair_` shadow this session's `open_tasks` does not hold (a rehydrated task, S2-R1): that one keeps its queue row.

## v11.30 / W5-T15 — Layer A Self-Review Actuation

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_SELF_REVIEW_ACTUATE` | on | Disables both the completion-hint self_review postamble (A1) and the synthetic `missing_self_review` absence row appended to `agent-errors.jsonl` on reviewable completion (A2); stderr nudge (`V11_SELF_REVIEW_NUDGE`) is unaffected |
| `V11_SELF_REVIEW_NUDGE` | on | Silences the stderr missing-self_review nudge only; the A2 absence row (`V11_SELF_REVIEW_ACTUATE`) is unaffected — the two levers are fully independent (W5 prod-fix de-nested the gates) |

## V11.20 — Audit & Improve Subagents

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_CALLER_KIND` | on | `track-autonomy` omits `caller_kind` field from audit events |
| `V11_WAVE_ATTRIBUTE` | on | `wave-review-attribute` exits 0 (no attribution) |
| `V11_SWARM_ATTRIBUTE` | on | `swarm-review-attribute` exits 0 (no attribution) |

## V11.19 — Review Enforcement

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_REVIEW_ENFORCEMENT` | on | Disables the AUTOMATIC review-queue paths: sync-tasks enqueue + sync-tasks-driven mark-done and the pending backstop. The manual `scripts/review-queue mark-done` CLI is NOT gated — deliberate operator action always works |
| `V11_REVIEW_NUDGE` | on | Silence detect-project review nudge |
| `V11_REVIEW_CROSS_PROJECT_CHECK` | on | v11.37 W1-T5 documented (was silent). Gates the cross-project review scope guard in `hooks/lib/common.sh:3705,3920` — when on, well-formed review entries with cross-project paths are rejected (silent per site comment); `=off` restores permissive behavior across project boundaries. Behavior-significant for cross-project review workflows. |

## V11.18 — Handoff Hygiene

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_FOLD_FAMILIES` | on | No token-overlap family folding in handoff |
| `V11_DISCIPLINE_DETECTOR` | on | No discipline check for shipped-but-unclosed tasks |
| `V11_DISCIPLINE_NUDGE` | on | No TaskList nudge for likely-shipped tasks |
| `V11_COMPLETION_HINT` | on | No file-edit → task-completion hint |
| `V11_HANDOFF_ADDENDUM` | on | No `.handoff-addendum.md` prepend |
| `V11_REHYDRATE_FOLD` | on | Families unfolded into raw members during rehydration |
| `V11_DISCIPLINE_WINDOW_HOURS` | 6 | Window for discipline detector audit-log lookback |

## V11.17 — Smooth Handoff

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_STUB_SUMMARY` | on | No auto-written `.session-summary.md` stub |
| `V11_AUTO_HANDOFF` | on | `session-end` does not auto-emit handoff |
| `V11_HANDOFF_NUDGE` | on | No detect-project handoff nudge |
| `V11_COMPACT_HANDOFF_LINE` | on | No "Handoff waiting" line in post-compact |
| `V11_AUTO_REHYDRATE` | on | No auto-rehydration from `handoff-tasks.json` |
| `V11_ACTIVE_PROJECT_OWNER` | on | v11.35.6 #15-F2: No liveness check on Tier-2 global active-project; any session can read another's binding |
| `V11_ATTRIBUTE_BY_PATH` | on | v11.35.6 #15-F3: Reverts to active-project fallback for NON_PROJECTS paths in track-autonomy (restores the self-work leak) |
| `V11_HANDOFF_STRICT` | on | v11.35.6 #30: No provenance warning when counters come from a different session |
| `V11_PROJECT_NAME_GUARD` | on | v11.35.6 #15-F4: No character validation on metadata.project in sync-tasks |

## V11.16 — Durable Ledger

| Env Var | Default | What `=off` Does |
|---------|---------|-----------------|
| `V11_LEDGER_CUTOVER` | on | Aggregate is NOT replayed from ledger; legacy fold path used |
| ~~`V11_CANCELLED_FILTERS_REPLAY`~~ | ~~on~~ | **HISTORICAL — documented for release-notes clarity; NEVER made it into code.** grep confirms 0 reads across `scripts/`+`hooks/` (v11.37 W1-T4 doc-downgrade fix for ticket #43). Improvement #17's cancelled-events-open-view fold is UNGATED — no rollback lever exists. If a user needs to disable #17's behavior at runtime, see ticket #48 (v11.38 candidate) which proposes wiring the lever properly with a paired cutoff timestamp so a toggle doesn't retroactively unfold historical cancelled events across the entire ledger. |
| `V11_RISK_TEXT_MASK` | on | v11.35.4 improvement #25: `=off` restores raw-text risk classification — prose inside commit-message heredocs/quotes trips HIGH patterns again. Masking is consulted only to re-test a raw HIGH hit and bails to raw on any structural doubt. |
| `V11_CUTOVER_ACCEPT_CORRECTION` | **off** | v11.35.2 improvement #24 — ENABLE knob, not a rollback: set it to the EXACT project name (`=HAM`, never `=on` — refused) to let ONE rebuild of THAT project pass BOTH cutover count floors when a correction legitimately shrinks counts (logged `reason:"correction-authorized"`). Project-scoped per adversarial finding #3 so a leaked flag cannot authorize other projects. Per-invocation only. |

## Full Disable Recipe

To revert to V11.16 behavior (pre-review, pre-handoff-hygiene):
```bash
export V11_AUTO_PAIR_REVIEW=off V11_SELF_REVIEW_REQUIRED=off V11_DAAO_ROUTING=off
export V11_REVIEW_ENFORCEMENT=off V11_REVIEW_NUDGE=off
export V11_FOLD_FAMILIES=off V11_DISCIPLINE_DETECTOR=off V11_COMPLETION_HINT=off
export V11_HANDOFF_REVIEW_FILTER=off V11_WAVE_CHECK=off
```
