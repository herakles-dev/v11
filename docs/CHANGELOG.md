# V11 Protocol Changelog

> **This file is the source of truth for V11 version history.** Every version bump adds its
> full entry HERE, newest first — NOT into CLAUDE.md. CLAUDE.md §17 carries only a one-line
> "Current: v11.X" pointer, so the protocol doc stays lean in every subagent's context (every
> non-Explore subagent loads CLAUDE.md). Enforced by `scripts/check-changelog-drift` (soft-block
> in both `scripts/run-tests --regression` and `--regression-extended`): it fails on inline entries in CLAUDE.md §17 OR a Current
> version missing from this file. For rollback env vars, see [ROLLBACK_REFERENCE.md](ROLLBACK_REFERENCE.md).

---

## v11.46 "Stop the Bleeding" (v11-leverage-program S1) — 2026-09-26

**Fix the defects that lose work or misreport it.** Sprint S1 of v11-leverage-program (spec: `sessions/v11-leverage-program/spec.md`,
roadmap §S1, gate G1), plus the S1 window of Lane D (D0, #88). The rows stay out of `sync-tasks`. S1 was the program's first
wired sprint: S0 ran unwired (#98). Targets:
- **#75:** `/handoff` dropped open tasks (M1 baseline: 0/5 and 1/6 live) and nudged the session that wrote it.
- **#76, #82:** the write gate blocked the handoff's own files, and block messages named no way forward.
- **#70:** background waits went unseen. **#72:** there was no cost visibility.
- **#53, #38:** the routing scorecard and the registry-drift check trusted self-filled or unnormalised labels.
- **#55:** CRITICAL findings could never be resolved. S1 delivers the ADR only.
- **S0 sprint-close findings:** the session GC deleted with no backup (R1), `run-tests`' lints checked master from a worktree (R3a), unwired session dirs were invisible (R3b, #98), and `--restore` had a repoint race (R4, #100).

Every row got a paired adversarial-lite review: #30–#34, #37, #38, #41–#43, #47–#50, #54, #55, #58–#61, #69, #70, #73 and #74. S1-T13 got a
full adversarial review (#35). Findings were fixed in fix tasks #36, #39, #40, #44–#46, #52, #53, #56, #62–#64, #71 and #72. The S1-T11
follow-ups b–f (#57, #65–#68) are two blind hand-checks, their comparison and two read-side fixes. The last review round:
- **#69** (S1-T1, ISSUES_FOUND: 1 HIGH, 3 MEDIUM, 2 LOW) was fixed by fix task #71 (merge `3d75638`).
- **#70** (S1-T2, PASS: 1 MEDIUM, 2 LOW) was fixed by fix task #72: `a8df95a` (E1, E3) and the E2 test `28741e7`.
- **#73** (S1-T3, PASS: 1 MEDIUM, 1 LOW) was fixed in `7623a96`.
- **#74** (S1-T4, PASS: 4 LOW) was fixed in `3d75638` (E1, E4), team-orchestrator `d4efa64` (E2) and `~/.claude/skills` `fd2925a` (E3).
- The S1-T15 round-2 fixes (`88d65c3`) got a paired review (#6 of the 10:25 list): PASS, 3 MEDIUM and 3 LOW. Its fixes merged as `c778e57` (see T15).

The conversation resumed twice, at 10:25 and 19:40, and each resume restarted the TaskList at #1 (see Known limits). Task numbers
above are from the first list unless marked. The last round is from the 19:40 list:
- **#3** (S1-T2c, PASS_WITH_CONDITIONS: 1 HIGH, 2 MEDIUM, 2 LOW) was fixed by fix task #11 (merge `7bbb0bf`). One LOW went to ticket #111.
- **#4** (the S1-T15 review-#6 fixes, FAIL: 1 HIGH, 1 MEDIUM, 1 LOW) was fixed by fix task #7 (merge `3911e7e`).
- **#5** (S1-R2, PASS_WITH_CONDITIONS: 1 MEDIUM, 1 LOW) was fixed by fix task #8 (merge `75d50c7`).
- **#6** (S1-T11d/T11f, PASS: 1 MEDIUM, 7 LOW) was fixed by fix task #9 (merge `17cdd04`). The 4 LOWs it left are ticket #112.
- **#10**, the sprint-close adversarial review of `399beb8..7d15f4b`: PASS_WITH_CONDITIONS, 3 HIGH, 7 MEDIUM, 4 LOW. Fix task #12 (merge `8c71664`) fixed the `review-daemon` MEDIUM and the `guard-agent-stall` LOW, and `artifacts/fold-review.sh` now fails loudly. The three HIGHs and four of the MEDIUMs share one root cause. It is caveated under Known limits and leads S2 (#113). This entry settles the review's CHANGELOG, M1, M3 and M7 findings.
- Fix tasks #71 and #72 and the S1-T15 handoff test budgets (`a9df8e0`) got no paired review of their own. The sprint-close review covered them, since its range includes them. The fix tasks from the 19:40 list (#7, #8, #9, #11, #12) got one batched lite review, #15 (`7d15f4b..d07ddd6`): PASS_WITH_CONDITIONS, 0 HIGH, 1 MEDIUM, 3 LOW (ledger seqno 574). Fix task #16 (merge `c010db0`) fixed the MEDIUM (the cutover alias carve-out now adds back only the aliases new since the prior aggregate) and two LOWs (`review-daemon` parks only on the AMBIGUOUS refusal; a unit test pins run-tests' `, N errors` Results line). The third LOW, `scripts/status` and `review-queue-maintenance --stats` counting parked entries as open, is deferred to S2.
- Two verdicts are kept as files, not ledger rows: review #3's (`artifacts/s1-review3-t2c-verdict.json`) and the sprint-close verdict (`artifacts/s1-sprint-close-review.json`). #102 dropped the first, and `mark-done` refuses both parents' reused ids (F33).
- Fix task #13 (merge `15bd991`, test-only), found by this CLOSE's `--regression-extended` phase 2: `tests/integration/harness.py` drove `session-end` with a Stop payload, so the two `TestCrossSessionLegacyPath` tests failed once S1-R1 (review #58) made only SessionEnd retire the scratch. The harness now sends Stop, checks the scratch survives it, then sends SessionEnd and accepts the quarantine. The `LEDGER_READY`-gated `TestCrossSessionReopen` runs an external script with `V11_ROOT` hardcoded and HOME not isolated (F34); it is skipped by default.

Commits `399beb8..c010db0` in v11 (90 commits + 64 merges, 144 files changed, +22,119/−884), plus the orchestrator's CLOSE
commit that carries this write-through and the `--regression-extended` result. `d1afc7b..adcbea3` in the team-orchestrator
skill repo (17 commits), plus the `journal/decisions.md` commit at CLOSE: the ADR-55, G1 and resume-epoch decisions. `e929981`,
`b913dbd`, `fd2925a` and `422163c` in `~/.claude/skills` (the handoff skill).

### Handoff truth (#75 → M1)

**T1: #75a handoff emission from the ledger replay ∪ the live snapshot** (`V11_HANDOFF_SOURCE_CHECK`, `V11_HANDOFF_LIVE_WINDOW_SECS`).
- `scripts/handoff` builds `open_tasks` from the live session's ledger replay, plus any live-snapshot tasks the ledger never saw.
- The live session is the env session when its last ledger event is within the window. Otherwise it is the newest Claude session with a UUID-shaped id; a tool pseudo-session such as `legacy-cli` never wins (`84970b5`).
- Every entry carries `identity {subject_norm, create_seq}`. Ledger entries skip the family fold and the stale-session heuristic.
- `handoff-tasks.json` gains `live_session_uuid`, `open_tasks_source` and `source_check`.
- A shrink breaker mirrors the 2x growth breaker, and an emission of 0 open tasks exits 2 unless `--allow-empty`. Both fire only when a dropped task is not closed in the ledger.
- **M1: met.** 6/6, 5/5 and 6/6 on the three #75 archivestream fixtures (`tests/fixtures/handoff_m1/`), where the pre-S1 emission gives 0/0/1. 8/8 live at the 2026-09-26 handoff. Both real resumes were recovered with it: 5/5 at 10:25 and 2/2 at 19:40 on the fixed replay (see M1 under Metrics for the caveat).
- That live handoff also found F25. The shrink breaker counted 11 hook-minted `pair_` review shadows as dropped and refused the correct 8-task emission. The orchestrator verified 8/8 and promoted `.autoemit-proposed.json` by hand.
- **Fix task #71: the review #69 fixes (F25/F26; merge `3d75638`)** (new lever `V11_HANDOFF_SOURCE_BUDGET_SECS`):
  - **Scope.** The drop audit counts only the live session's prior entries, matched by identity (`subject_norm` + `create_seq`). Another session's still-open task goes to `source_check.dropped_foreign` with a WARN and never trips a guard. An idle live session, a fallback emission or a failed source check counts every prior entry.
  - **Shadows.** `pair_` review shadows and pending_parent siblings never count (`dropped_by_policy`).
  - **Paired promotion.** A refused emission promotes no `handoff.md`, so the pair stays the last accepted one, and `--spawn` exits 2. The shrink floor goes from 5 to 3, because the counted set is now smaller.
  - **Env session authoritative.** `hooks/session-end` passes `V11_SESSION_ID_SOURCE=hook-stdin` (a state channel, not a lever), and `scripts/handoff` takes that session outright. A manual run's env session is also live when a running claude process owns it.
  - **Loud fallback.** A replay that fails or times out prints a WARN and sets `open_tasks_source: "legacy-fallback:<reason>"`, and the `handoff.md` footer names it. The replay, the live-set pass and the drop audit share one budget, `V11_HANDOFF_SOURCE_BUDGET_SECS` (default 12, clamped to 3..14), inside session-end's 20 s kill.
  - **Surfaced refusal.** Both refusals print `handoff: refused — <reason>`, write `.handoff-refused` and add one note line to the kept `handoff.md`. session-end stamps the open-set digest, so a Stop does not retry until the task set changes.
  - **Lever-off byte diff.** A test runs `72ef8e3`'s `scripts/handoff` and the current one with `V11_HANDOFF_SOURCE_CHECK=off` and compares `handoff-tasks.json` byte for byte.
  - **F25 replay.** On the refused 2026-09-26 input, the fixed script accepts the same 8 tasks the live run proposed: 11 dropped by policy, 0 unexplained. The p95 is 6.47 s on a 5,920-event ledger.
  - **S1-T4 review nits.** The summary keeps its title when Blockers fill the budget, and both paths count lost lines the same way. `v11-bootstrap-session` `%q`-quotes the resume command and anchors a relative `V11_HOME` at `$PWD`.

**T2: #75b consumers keyed on identity** (`V11_HANDOFF_IDENTITY_KEYS`). New `scripts/lib/handoff_identity.py`.
- `detect-project`'s rehydrate verification compares subject_norm multisets. A clean rehydrate with fresh task ids is acked, and different tasks that reuse ids are a mismatch.
- `handoff` and `v11-resume-tasks --list` recover a null subject by identity, never through another session's task id.
- Resume payloads carry `metadata.rehydrated_from`. A pre-S1 `handoff-tasks.json` rehydrates byte-identical.
- **Fix task #72: the review #70 fixes** (`a8df95a`, `28741e7`), under the same lever:
  - A rehydrated live task is keyed on its `metadata.rehydrated_from.identity`, so a task renamed before the handoff no longer gives a false `identity_mismatch`.
  - A helper failure, or an unreadable handoff file, records `identity_matched=false` on the ack, with a stderr line. It is never a silent match.
  - E2: a test checks that a pre-S1 file rehydrates byte-identical against a frozen copy of the pre-S1-T2 `v11-resume-tasks` (`tests/fixtures/handoff_identity/`).

**T2c: restart identity, read side (F31)** (`V11_REPLAY_REHYDRATE_ALIAS`, `V11_WAVE_CHECK_EPOCH_BINDING`; merge `76e5a74`). After the
10:25 resume the TaskList renumbered from 1 while the hooks kept session `a059e6ae`. The CLOSE wave-check found two defects.
- **Rehydrate alias.** Old #71 was renamed (seqno 487) before the resume and rehydrated as #1 under its new `subject_norm`, so the ledger minted a new identity and #71 stayed open for good. `v11_replay_ledger` now treats a `created` whose `metadata.rehydrated_from.identity` names another identity already folded as an alias, and folds its events into the original.
  - Only an identity's first event can alias it. A malformed or unknown target is ignored, and chains resolve with a loop guard.
  - It is read-side, so existing ledgers heal with no rewrite. The replay's identity view also emits `created_claims`.
- **Epoch binding.** `wave-check` bound `review_of` through `(session, task_id)` claims alone. Review 69 of old #3 (S1-T1) also covered the new #3 (CLOSE prep), and task-state rows for reused ids matched two identities.
  - A review now binds to the claimant created under the id last before the review's own `created`. A `pair_` shadow also accepts a same-instant parent.
  - A task-state row takes the id's current holder. Undecidable cases keep the claim-only rule.
  - Live: WORK_INCOMPLETE went from `['5','4','71','7','5']` to `['5','4','7']`.
- **Review #3 fixes (19:40 list; fix task #11, merge `7bbb0bf`):**
  - **Terminal-target guard (HIGH).** A target already completed or cancelled at the alias's `created` is never aliased. A stale handoff that rehydrates finished work stays a separate task instead of reopening the original.
  - **Cutover alias carve-out.** Each alias lowered the replay total by 1, so the cutover REGRESSION-GUARD blocked the rebuild twice live (prior 178, ledger 177). The replay now reports `alias_count`, and the guard adds it back and logs `alias_carveout` to `ledger-cutover.jsonl`. Review #15 (fix #16): the guard adds back only `max(0, alias_count − prior alias_count)`, so once an aggregate already holds the fold, a real loss is not masked; the ledger-vs-legacy check keeps the full count, because the legacy fold counts both identities.
  - **Open-claimant preference.** A task-state row goes to the one open claimant whose last id in the session is the row's id. `epoch_owner` only breaks a tie, so a stale open identity's row-only metadata (`skip_review`) no longer leaks into the newer task.
  - **Lever gating.** `V11_WAVE_CHECK_EPOCH_BINDING=off` also drops the `created_claims` claim expansion, so `=off` matches the pre-T2c output.
- The write side is ticket #111: `sync-tasks` should key a rehydrated TaskCreate on `rehydrated_from.identity`, and `GATE_AUTOCLOSE` closes an aliased identity under the target's key.
- The rows: `V11_WAVE_CHECK_EPOCH_BINDING` is in the v11.46 wave-check table of `docs/ROLLBACK_REFERENCE.md`. `V11_REPLAY_REHYDRATE_ALIAS` sits with the other `v11_replay_ledger` levers under "Unreleased — 2026-09-22 triage fixes".

**T3: #75c no self-nudge** (`V11_HANDOFF_SELF_NUDGE_SUPPRESS`). When `handoff-tasks.json`'s `live_session_uuid` is the reading
session, `detect-project` skips the rehydrate nudge and the L2.3 verification, and `post-compact` omits "Handoff waiting". Any doubt
(a pre-S1 file, a missing id) keeps the nudge. Review #73 (`7623a96`): a self match writes `.handoff-surfaced`, so the check runs once
per stamp, and another session's re-stamp mid-session does not nudge the writer. A resume keeps the session id, so T3 also
suppressed the nudge at both of S1's resumes (see Known limits).

**T4: #57 + #81** (`V11_HANDOFF_SUMMARY_LINES`, default 40).
- One helper, `_v11_summary_excerpt`, replaces two silent `head -20` cuts. A long `.session-summary.md` keeps every heading, puts Blockers / Open Questions first, and ends with a marker that names the full summary.
- The rehydrate command, everywhere it is emitted, is the absolute `$V11_HOME/scripts/v11-resume-tasks PROJECT`. This part has no lever.

**T14: handoff-surface docs.**
- `docs/HANDOFF_SMOOTH.md` gains a "S1 behaviour (v11.46)" section.
- The `docs/SCRIPTS.md` rows use `$V11_HOME/scripts/…`.
- The skill's `close.md`/`quickstart.md` (`4e6263c`) and `~/.claude/skills/handoff/SKILL.md` match T1 and T4.
- The CLOSE fixed the remaining relative or literal paths:
  - CLAUDE.md §0/§9 and the skill's `scripts.md` (F27);
  - the team-orchestrator `SKILL.md` DETECT 1e `plan-resume --list` (`d4efa64`);
  - two handoff `SKILL.md` examples (`fd2925a`);
  - all three now use `${V11_HOME:-/path/to/v11}` or `$V11_HOME` (S1-T4 review #74).
- The S1-T14 re-check after fix tasks #71 and #72:
  - `docs/HANDOFF_SMOOTH.md` "S1 behaviour" already matched the #71 breaker (`8a5c962`). This CLOSE adds the review #70 rename keying and `identity_matched=false`, and the review #73 once-per-stamp self check.
  - The handoff skill's Step 3 and Arguments row (`~/.claude/skills` `422163c`) and the CLOSE playbook (team-orchestrator `adcbea3`) said "prior ≥ 5" and "the old file is kept". Both now give the floor of 3 live-session tasks and say that `handoff.md` is kept too and `--spawn` exits 2. The skill also names `.handoff-refused` and the loud fallback.
- Carried, not docs: `scripts/handoff`'s header comments still show `./scripts/handoff` (:3) and say a plain run "is unchanged" (:34), but a plain run can now exit 2 (F27). The handoff skill's other literal `/path/to/v11` command examples (:39, :169, :232, :255, :297 after `422163c`) stay as they are, since review #74 named only the `--spawn-anyway` line and the Related row.

### Gates and messages (#76, #82, #70 → M7)

**T5: #76 write-gate-scoped exemption** (`V11_WRITE_GATE_SCRATCH_EXEMPT`).
- New `v11_is_write_gate_exempt` runs on the block path only. It exempts the harness scratchpad (the shared `V11_SCRATCHPAD_ERE`) and six exact `sessions/<project>/` handoff basenames.
- `v11_is_metadata_file` is unchanged.
- T5 merged first, because T7 and the dogfood depended on it.

**T6: #82 honest blocks** (`V11_BASH_WRITE_WARN`, new value `=legacy`).
- HIGH blocks add a heredoc-data hint or a `$var`-path `rm` hint.
- Write-gate blocks add a "Possible half-applied change" line.
- The F4 advisory also matches interpreter file writes: `python`/`node` `open(…, 'w')`, `write_text`, `writeFile`, `perl -i`.
- Exit codes are unchanged: a 31-case matrix was diffed against master.

**T7: #70 wait contract, hook side** (`V11_BG_WAIT_CONTRACT`; `STALL_WAIT_MAX_MARKERS`/`_MAX_NUDGES`/`_RENUDGE_MINUTES`/`_STALE_HOURS`).
- `guard-agent-stall` scans `~/.agent-metrics/waiting/<project>/*-waiting.json` before its `in_progress==0` exit.
- It nudges through PostToolUse `additionalContext` when:
  - the pid is dead or reused;
  - a `done_marker` appears in the log;
  - the log's last line is terminal and the pid is gone;
  - `expect_by` has passed.
- A marker gets at most 3 nudges, then one STALE line.
- Three review rounds: reviews #31 and #42, fix #45.
- **Sprint-close review fix** (fix task #12, `4fcaed0`, no lever). The WAIT NUDGE, STALE and MALFORMED lines print the marker filename JSON-escaped and capped at 80 characters under the waiting dir. Any local writer chooses that name, so a newline in it could inject a line of hook-trusted text into `additionalContext`. Valid `<agent>-waiting.json` names print unchanged.
- **M7: mechanism verified live** (see Metrics). No agent writes waiting markers yet.

**T8: #70 wait contract, prompt side.** The Spawn Contract clause (`context-tiered-mode.md`) and a `monitor.md` §5f row (skill
`d1afc7b`). Commits `049cbe0`, `bcfae42` and `dfd3ae2` align the text with the hook.

### Cost visibility (#72 → M6)

**T9: `scripts/cost-ledger`.** No lever: it is opt-in by invocation. `V11_MODEL_PRICING` overrides the price table.
- It reports tokens and a $ estimate per task, agent or sprint, with a capture rate.
- Spawns come from dispatch-trace and are joined on exact keys to subagent transcripts. Each transcript belongs to one Agent call, and fork replays are skipped: they had double-counted 1.43M tokens ($1.08).
- Prices come from the new `config/model-pricing.json`.
- The fallback token sources (task-notification, dispatch `tokens`, ledger `artifacts.tokens`) hold the last turn's context size, so they stay unpriced.
- New `scripts/lib/task_notification.py` is the shared `<task-notification>` parser (#69). New `schemas/cost-ledger.schema.json`.
- `--json` states `pricing.basis=api_list_price_equivalent` and `pricing.scope=subagents_only`.
- S1-P2 (the Q6 SubagentStop spike, `artifacts/s1-spike-q6-subagentstop.md`) chose the token sources.

**T10: the cost line** (`V11_COST_STATUS`, `V11_COST_STATUS_TIMEOUT`, `V11_COST_STATUS_FRESH`, `V11_COST_LEDGER`).
- `scripts/status` prints one `Cost:` line from a cached, single-flight `cost-ledger` run, bounded at 3 s.
- The skill's `monitor.md` dashboard and `journal.md` retrospective copy the line (`a1c5e3b`).

### Honest signals (#53 → M3, #38 → M4, #55, #96, #97)

**T11: #53 scorecard read side** (`V11_AS_ROUTING_RAW`, `V11_AS_ROTATED`, `V11_AS_TRANSCRIPTS`, `V11_AS_TRANSCRIPTS_DIR`; `--live-window H`).
- `agent-scorecard --routing` judges each dispatch-trace row against the ledger's own `created.metadata.agent` for the task live at the spawn, not against the row's self-filled recommendation.
- Buckets: agreed, diverged, self_executed, companion, unknown.
- The headline is the decided rate, with coverage and floor..ceiling bounds.
- Excluded: WAIVED verdicts, void and waived corrections, backfill rows, and rows whose project has no ledger.
- The b–f follow-ups:
  - two independent blind 50-row hand-checks, S1-T11b and S1-T11e (n = 100), and their comparison (S1-T11c); see M3 below;
  - completion-only spawns are counted (S1-T11d, `26c1cb2`);
  - liveness is judged before the spawn (`--live-window H`, default 2 h);
  - rotated ledgers are merged;
  - a served-task search finds the task a spawn actually served;
  - a ledger served-task match counts only when unambiguous (S1-T11f, `e6263e7`).
- The waiver writer (`review-queue mark-done`) ledgers `outcome=waived` (`5536697`).
- Live: 198 of 2,145 decided rows diverged (9.2%), coverage 43.5%.
- **Review #6 fixes (19:40 list; fix task #9, merge `17cdd04`):**
  - The transcript served-task path judged a prompt that named several tasks by all their plans together, so one matching plan made the spawn agreed. Each named task is now judged on its own. The row counts only when every task gives the same bucket, and is otherwise unknown with `ambiguous_served_task`. A teammate name that owns exactly one named task picks that task.
  - Task-id capture strips a trailing `.` or `-` (`task #7.` → 7).
  - A completion row counts from its start (ts − duration) for the companion and self-exec windows.
  - Session liveness accepts ledger events up to 5 min after the spawn, the same grace as owner/in_progress.
  - Measured on one frozen copy of `~/.agent-metrics`: the headline stays 9.4% (205/2,191 → 205/2,181), and coverage goes 43.7% → 43.5%.
  - The 4 LOWs left are #112.

**T12: #38 registry-drift read side.** The lever is unchanged: `V11_REGISTRY_CHECK`.
- Ledger labels are normalised.
- A named background spawn is aliased to its created event's agent, joined inside one ledger file and never on a bare task_id.
- An owner that is itself a plausible agent type is never aliased. It WARNs as a type mismatch instead.
- **M4: 232 → 13** at merge (6 real drift, 5 writer gaps, 2 cross-project). The target, <10, is not met. 14 at the CLOSE prep. The user accepted 14 at G1 (see Metrics).

**T13: #55 ADR** (`sessions/v11-leverage-program/adr-55-dispositions.md`). Revision 4.1 was **accepted by the user at G1 on 2026-09-26**:
- dispositions live in a side ledger keyed by `attribution_key`, and the latest row wins;
- only a daemon re-review or the user may close a CRITICAL without a fix;
- the historical CRITICALs are triaged first;
- sibling ingest goes through #102.

The implementation is S3-T5/T6/T7.

**T16: #96 wave-check replays the ledger** (`V11_WAVE_CHECK_COVERAGE`, `V11_WAVE_CHECK_WAIVER_COVERAGE`, `V11_WAVE_CHECK_SKIP_REVIEW_STRICT`; opt-in replay view `V11_REPLAY_EMIT_IDENTITIES`).
- The wave is built from `v11_replay_ledger`'s identity view, keyed by `(subject_norm, create_seq)`, so a closed sprint is visible.
- Exit codes:
  - unreviewed reviewable work exits 2;
  - a CRITICAL from any verdict source (artifacts, summary counts, `ev:"review"`, the verdict file) exits 3;
  - an unreplayable ledger exits 4.
- `pair_` shadows are judged from their parent. Waivers get their own bucket.
- The default replay output is byte-identical.

**S1-P1** re-encoded the 19 S0-CLOSE waivers in the live ledger as `outcome=waived`.

**S1-P3: #97 verdict binding.**
- `review-queue mark-done` resolves the parent by `(session, task_id)` (`ea3cf2a`). A reused id with no session exits 2 and writes nothing. A non-UUID session, or one that holds no task under the id, counts as no session (`1047fc6`).
- `review-daemon` passes the entry's session, which is the parent's (review #61 HIGH, `f012ba0`). The fix landed at 06:19, before the next 03:30 review-cadence cron run.
- New `scripts/lib/review_corrections.py` is the one waived/void correction rule (`48888aa`). The scorecard, the fold and wave-check all use it, and the default fold skips void rows.
- The seqno-311 misfile was corrected live (seqnos 421/422).
- **Refused folds are parked** (sprint-close review, fix task #12, `4fcaed0`; `V11_REVIEW_DAEMON_PARK`, default on).
  - When `mark-done --verdict-file` refuses with the AMBIGUOUS message (exit 2 plus "names more than one task" / "tasks under task_id"; review #15), `review-daemon` parks the queue entry. Any other exit 2, such as a CLI usage error, stays pending. Before, the entry stayed pending, and after a same-id resume each nightly cadence run paid for a new headless review that could never bind.
  - `v11_review_queue_park` appends an `ev:"parked"` copy of the row: the claim cleared, `parked_at`, `park_reason`, `park_rc`, `verdict_kept` (the kept verdict file) and `parked_by`. Drain paths take `ev=="pending"` only. Any other non-zero rc leaves the entry pending, since it may be transient.
  - `review-queue` gains `park` and `unpark`. `dashboard`, `backstop` and `stats` report parked entries apart. `pending --json` is unchanged unless you pass `--include-parked`.
  - **Un-park:** `review-queue unpark PROJECT TASK_ID` makes the entry drainable again, and the next drain re-reviews it. Or fold the kept verdict with `review-queue mark-done PROJECT TASK_ID "" SESSION --verdict-file <verdict_kept>`, since a done event closes a parked entry. A new enqueue of the task also re-pends it. When the id names several tasks inside one session (a resume), neither route binds until #113 gives `mark-done` an identity argument: the fold refuses, and an un-parked entry pays for one more review and parks again. Keep the verdict file until then.
  - `=off` restores the pre-fix behavior: the entry stays pending and is re-drained on every run.

### Test and GC rails (S0 sprint-close findings)

**T15: #95 the extended gate.**
- **Gate 13 honours fixture project dirs** (`ee0fa9b`). `v11-compliance-check` accepts a path, and the 4 slow `test_gate13_skipdirs_wave.py` tests pass. Before the meta-test fix, `test_full_suite_green_and_grown` timed out: its nested suite ran serially and overran the 2,850 s budget.
- **The meta-test** (`88d65c3`). Outside an xdist worker, `test_full_suite_green_and_grown` runs the nested suite at `-n 8`. Inside a worker it skips, with the reason, when the serial estimate is over budget. One real run took 1,381 s for 3,761 tests, well inside the 2,850 s budget. The run was red on two load flakes, and both are fixed below.
- **The pipefail SIGPIPE race** (`8292051`). Under `set -o pipefail`, `echo "$out" | grep -q P` can fail with 141: `grep -q` exits between bash's two writes of a multi-line value. The race was the cause of the v11-retro self-test flake, which is **resolved**: 56/640 failures under stress before, 0/640 after.
  - The audit covered every early-exit reader behind a pipe in the 85 pipefail shell files, plus `hooks/lib/common.sh`: 147 hits, **43 lines fixed in 19 files**, and 104 left with a reason code.
  - The fixes use here-strings, `grep … >/dev/null` for multi-write writers, and `|| true` on display-only `| head`.
  - New `tests/test_pipefail_early_exit.py` is a static check plus a deterministic mechanism test.
- `tests/test_handoff_context.py` tests its own tree, not a hardcoded `/path/to/v11`, with a realistic timeout (`1d94c35`).
- Every subprocess budget under 30 s in `tests/test_handoff_*.py` is now 30 s: 38 call sites in 11 files (`a9df8e0`). Under load, four `test_handoff_resume` tests had timed out, and all four pass alone. `test_handoff_resume` also runs its own tree's `handoff-bak-gc`.
- **Review #6 fixes (10:25 list; merge `c778e57`):**
  - **Here-strings in `common.sh`** (M1, `f7b48fa`). The audit had skipped `hooks/lib/common.sh`, which 31 pipefail scripts source. Its four `printf | grep -q` lines now use here-strings with the same flags. One of them is the dangerous-command match in `v11_check_risk`, which missed 7 of 3,000 multi-line values. `tests/test_pipefail_early_exit.py` now also scans the libs those files source, transitively, and asserts `common.sh` is among them.
  - **verify-gate Results parsing** (M2, `c0ac46c`, F29). The gates decided with `grep '0 failed'`, which also matches "10 failed" (pre-existing since `de0cf00`). Gates 1 and 2 reported all-pass with 10, 20 or 30 failures, and gate0 FAILed every clean run. Each gate now matches `run-tests`' `Results:` line with an anchored regex. An absent failed clause is 0, and no `Results:` line is a named FAIL. New `tests/test_verify_gate_results.py`.
  - **The meta-test runs inside an xdist worker** (M3, `7a1a797`). `run-tests --full`, which the gates call, runs at `-n 8`, so the meta-test always skipped on the gate path. The nested suite now always runs at `-n min(8, cpus)`, with the outer run's xdist env stripped. The serial fallback and its skip are gone, and a missing pytest-xdist fails loudly.
  - **`ledger-archive --before`** matches a whole `YYYY-MM-DD` (LOW, `878eebf`). The date lands in the archive file name, and the old check anchored only the start.
  - **`worktree-sweep` globs** (`3cfdfaf`, found when the meta-test first ran in a worker). An unquoted `for glob in $GENERATED_GLOBS` expanded against a cwd that held `tests/.reports/`, so a generated-only worktree was reported UNCOMMITTED. The globs are now split with `read -ra`.
- **Review #4 fix (19:40 list; fix task #7, merge `3911e7e`).** The review FAILed the Results parsing on one HIGH: the line left out pytest's error count and nothing guarded a zero total, so "2990/3000 passed" with 10 setup errors and "0/0 passed" both passed.
  - `run-tests`' `Results:` line now carries `, N errors`.
  - Each gate sets a failed count only when T > 0, E == 0 and P+F+S == T. A missing, unparseable or short line fails closed, and so does any outcome the line doesn't name (xfail, xpass).
  - The one-failure autonomy-grant allowance is kept and documented.
- None of the T15 changes has a lever.
- **`run-tests --regression-extended` exits 0 on `1d781e7`** (2026-09-27, 37.9 min). Phase 1: 3,875 passed, 17 skipped. Phase 2, the serial slow tier: 22 passed, 8 skipped, including the meta-test's nested full suite and the Gate 13 fixtures (#95). The stamp and changelog lints pass. So S1-T15 is done.
  - Two earlier CLOSE runs were red, and neither was a code failure. On `7d15f4b`, phase 2's meta-test failed one hook-timing test under concurrent agent load; that test passes alone in 2.7–2.9 s against a 5 s budget. Two harness-drift tests also failed there, fixed by #13. On `15bd991`, phase 1 had 6 hook-subprocess timeouts while a fix agent was testing, at a 15-min load of about 17. All 6 pass when run serially, and phase 2 was green.
  - Lesson (retro): run the extended CLOSE gate only when no agents are testing on the host.

**R1: the session GC quarantines** (`V11_SESSION_GC_MODE`, `V11_SESSION_GC_TTL_HOURS` = 168, `V11_SESSION_GC_QUARANTINE_HOURS`).
- Liveness is checked in order: current session, heartbeat, owning process (pid + `procStart`), mtime.
- Expired dirs move to `sessions/.gc-quarantine/<utc-ts>/` and are purged after 7 days.
- The review #58 follow-up (`02933c4`): SessionEnd teardown quarantines the scratch, and a Stop never removes it.
- New `hooks/session-end --gc-run`; `--gc-preview` prints every decision.
- `rotate-metrics --sessions` runs the GC instead of `rm -rf` (`02933c4`).

**R3a: lint-test-honesty is a hard gate** (`V11_LINT_HONESTY_GATE`) in every mode except `--fast`. `run-tests` exports
`V11_HOME=$V11_ROOT` for its lint/check phase, so a worktree run checks the worktree.

**R3b: #98 item 3.** `check-wiring-parity`:
- lists unwired V11 session dirs (`--strict-unwired`, `--unwired-since`);
- writes weekly reports (`--report-dir`, `--keep`);
- manages one `# v11-wiring-parity` cron line (`--install-cron` / `--uninstall-cron`, Sun 04:30). The line is installed live.

**R4: #100 `--restore` hardening.** The restore writes to the path it inspected and refuses a repointed target. An unreadable
backup dir exits 1.

**R2: #94 tests never write the real `~/.agent-metrics/sessions`** (`d4df4c7`; `V11_TEST_HOME_GUARD`).
- `scripts/lib/context_tracker.py` resolves `$METRICS_DIR`, else `$HERCULES_ROOT/.agent-metrics`, else `~/.agent-metrics`. It had hardcoded the last, so `hooks/sync-tasks` wrote `context-estimate.json` into the real dir from any test that isolated only `METRICS_DIR`/`HERCULES_ROOT`.
- `tests/conftest.py` gains an autouse, module-scoped guard. It snapshots the real sessions dir and fails a module that creates or writes a test-shaped entry the module owns. An unowned change only warns, since concurrent runs share the dir. It never deletes anything.
- The two self-review test modules also set `HOME`. They had leaked `v11-myproj.md` into `~/.claude/plans` through plan-sync.
- New `tests/test_real_home_isolation.py`. The debris that already exists is left for manual removal.
- **Review #5 fix (19:40 list; fix task #8, `c136a24`).** The guard banner says that an owned change may come from a concurrent run using the same id, such as another worktree on pre-#94 code or an xdist worker. It suggests a re-run or `V11_TEST_HOME_GUARD=off`. The isolation fixture sets `HOME` before `exec_module` and uses test-shaped session ids, so the guard would catch a regression.

### Lane D: D0 (#88, groundwork for M11)

- **D0-1:** `scripts/lib/roster.py` is the live roster of agents and skills, with a `roster_hash` and a cache (`V11_ROSTER_CACHE`). Live: 102 agents + 4 built-ins, 70 skills + 1 plugin skill.
- **D0-2:** `scripts/dispatch-advise --engine baseline`.
  - Fixed routes come first, each with its provenance. Otherwise it ranks by BM25, plus the META_MAP prior and a scorecard tie-break.
  - It returns the top-3 agents and skills and an `advice_id`.
  - It logs to `~/.agent-metrics/dispatch-advice.jsonl` (`V11_DISPATCH_ADVICE_LOG`, `=off`). `V11_AGENT_SCORECARD=off` drops the tie-break.
  - New `schemas/dispatch-advice.schema.json`.
- **D0-3:** `dispatch-trace-append --advice-id` is additive. With no id, the line is byte-identical.
- **D0-4:** skill wiring (`V11_DISPATCH_ADVISE`, prompt-only): the Phase 3 STEP 3 `--pending` table and the Phase 4 spawn step.
- **D0-5:** `reconcile-agent-registry` field-syncs existing entries from `.md` frontmatter (description, model, tools, triggers, version). The hardcoded 11.37.0 is gone. Applied live to 59 entries; backup `.bak-pre-d0-5`.

**Also shipped.** `scripts/publish` tolerates non-object PORT_REGISTRY entries and registers Next.js sites with `websocket: true`
(`bc67e71`). This was a pre-existing edit from another session; the user approved it riding in S1.

### Metrics (G1)

| Metric | Target | Result |
|---|---|---|
| M1 handoff carries the open tasks | 100% on fixtures + live | **Met.** 6/6, 5/5, 6/6 on the fixtures; 8/8 live on 2026-09-26. The live emission was promoted by hand after the F25 breaker refusal. With fix task #71 the script accepts the same 8 on that input. Both real resumes were recovered with it: 5/5 at 10:25, and 2/2 at 19:40 on the fixed replay. Caveat: M1's command reads `~/.claude/tasks/session-<sid8>` with sid8 = `live_session_uuid`. After a resume that is the frozen first-list store (`session-a059e6ae`, last written 08:15), not the live one. The 2/2 was checked by hand against the live list's store (`session-87a619b2`: #4 and #5 in progress). `handoff-tasks.json` does not name its store (#113). |
| M3 routing override honesty | within ±2 pp of a hand-check | **Fails on legacy data.** Restated at G1; see below. |
| M4 registry-drift WARNs | <10 | **Accepted at G1; the target is not met.** 232 → 13 at merge. 14 WARN and 0 FAIL at this write-through, since G1 registered `secret-jar`, an agent another session had added without registering it (the registry has 103 entries). |
| M6 cost visibility | per task, agent and sprint | **Met for sprint and agent.** Per task holds only within one TaskList. See M6 below. |
| M7 silent waits detected | within 1 TaskList | **Mechanism verified.** It was verified live on this wired project with one dead-pid marker the orchestrator wrote. The nudge came within 1 TaskList, and a marker with a live pid stayed silent. No agent writes waiting markers yet, so detection of real silent waits against the 5+ baseline is unmeasured. |

**M3.** Two independent blind 50-row hand-checks were run (S1-T11b and S1-T11e, n = 100).
- ±2 pp cannot be resolved at this n: one row moves the rate by 11–13 pp.
- Under the helper=agreed rubric, the scorecard (0.165 pooled, after S1-T11f) sits **outside** the blind spawn-keyed 95% interval, 0.040 [0, 0.131].
- Under helper=diverged it sits inside: 0.209 [0.065, 0.364].
- The largest contributor to the gap is the trace writer (#103: trace rows name the wrong task or project). It is not the sole cause; see the G1 decisions.
- Evidence: `artifacts/s1-t11b-blind-handcheck.md`, `s1-t11c-m3-comparison.md`, `s1-t11e-blind2.md`.

**G1 decisions** (the user, 2026-09-26; recorded in the team-orchestrator `journal/decisions.md`):
- **M3 is restated.** It is spawn-keyed. It passes when the scorecard's diverged rate lies inside the 95% bootstrap interval of a spawn-keyed blind hand-check, and helper spawns count as agreed. It is measured on NEW trace rows only, after #103 and #54 land in S3. S1 records **FAIL** on legacy data.
- **The cause of the FAIL.** #103 is the largest contributor, not the sole cause. Of the 12 disagreements, 5 are trace-writer rows, 3 are rubric, 1 was a classifier bug (fixed in S1-T11f) and 3 are other. The in-interval counterfactual moves only rows 4 and 11, and row 4 is a bare task_id bound through the 2 h window: the id-reuse family (#113).
- **M4 is accepted** at 14 WARN / 0 FAIL, after `secret-jar` was registered through `reconcile-agent-registry` (103 registry entries). The writer-gap WARNs ride with #103 (S3), and the alias WARNs with #108.
- **F21 is kept:** the 5-min sibling grace, name-matched review siblings and the 2 h `--live-window`. S3 may tune them.
- **ADR-55** rev 4.1 is accepted (see T13).
- **The resume epoch** (sprint-close review): caveated in S1 (see Known limits). The epoch key leads S2 (#113).
- **spawn-claude-window.** The G1 re-run item found `~/.claude/hooks/__tests__/test_spawn_claude_window.py` obsolete: it imports the module S0-T10 deleted. A smoke test of the live `spawn-claude-window.py` against the current `handoff.md` passed. The rewrite is #110.

**M6.** `scripts/cost-ledger v11-leverage-program --by sprint`, re-run at this write-through (2026-09-26 23:36 CEST). All figures are the **API list-price equivalent, subagents only**. The orchestrator session is not included.
- S1 (`sprint-01-bleeding`): **$516.02** over 64 spawns (62 with tokens), 1,037.2M tokens.
- Program total: $655.54 over 122 spawns. Capture is 116/122 (95.1%), and all 116 are priced from transcripts.
- The other rows are unchanged: S0 (`sprint-00-rails`) $99.23, planning $22.92, planning-r3 $17.37.
- Earlier figures for S1 and the program: $400.26 and $539.78 at the CLOSE prep, and $457.10 and $596.62 at the first write-through (11:37).
- **Per task is caveated.** `--by task`, the default, groups on the bare task id. After a resume one key merges 2–3 tasks under the first one's label. Live: key `7` sums S1-T5, S1-T2c and the review #4 fix (19:40 list), labelled S1-T5. `--by sprint` and `--by agent` do not group on task ids. The fix is in #113.

### Known limits (the resume epoch; S2 leads with #113)

A resumed conversation keeps the hook session id (`a059e6ae` all through S1) but gets a fresh TaskList that renumbers from 1 (stores
`session-87a619b2` at 10:25 and `session-dedc750b` at 19:40). Nothing records that TaskList epoch, so ids 1–14 of the session each name
2–3 tasks. At G1 the user chose to caveat this in S1 and lead S2 with the epoch key (#113). Until then:
- **S1-T3 suppresses the rehydrate nudge after a resume.** The resumed session matches `live_session_uuid`, so `detect-project` (:81) treats it as the writer, and the nudge and L2.3 stayed silent at both resumes. Manual recovery, used twice in S1: `$V11_HOME/scripts/handoff PROJECT`, then `$V11_HOME/scripts/v11-resume-tasks PROJECT` and one TaskCreate per payload. The rehydrated tasks continue their ledger identities.
- **`review-queue mark-done` refuses reused ids after a resume** (S1-P3, F33). It exits 2 and writes nothing when the parent's id names several tasks in the session. Verdicts are kept as files: review #3 of S1-T2c (`artifacts/s1-review3-t2c-verdict.json`) and the sprint-close verdict (`artifacts/s1-sprint-close-review.json`), both under `sessions/v11-leverage-program/`. `review-daemon` parks such entries instead of re-reviewing them.
- **`cost-ledger --by task` merges tasks that share an id** (see M6).
- **M1's command reads the frozen first-list store** after a resume (see the M1 row).
- `dispatch-advise --task-id` matches a bare id across every session's open tasks, so after a resume use `--pending` or pass the task text (F28).

### Tickets filed, findings carried

- **#101** (MEDIUM, S2): `sync-tasks` auto-pair ignores `skip_review`, `review_of` and `adversarial-*` (INV-7 isn't enforced on the producer side). Addenda: each resume minted `pair_` shadows for the rehydrated tasks again, the skip_review CLOSE included (F28, and pair_36/_37 at 19:40).
- **#102** (HIGH, with S3-T6): the ledger's 4 KB line cap drops finding-heavy review verdicts. Worse case, F11: the ADR review's completion has no artifacts and a 0/0/0/0 summary. The S1 rescue is `artifacts/fold-review.sh`. It is not safe after a resume: when the parent's id names several tasks in one session, `mark-done` refuses (F33), and the script now reports the refusal and keeps the verdict file instead of printing an unrelated ledger row.
- **#103** (HIGH, with S3-T2/T3): `track-agents` stamps the wrong task on dispatch-trace rows and fills in its own recommendation. F23 adds a wrong-project row and a false self-executed record.
- **#104** (LOW): `check-rollback-lever-drift` can't see a lever read through an `env("V11_…")` helper in bash-wrapped Python, so `V11_AS_ROUTING_RAW`, `V11_AS_ROTATED` and `V11_AS_TRANSCRIPTS` are bullets, not table rows, in `docs/ROLLBACK_REFERENCE.md`.
- **#105** (MEDIUM): `check-stamp-drift` anchors on the newest version string in any commit subject, not just `release(v11.x)`, so a mid-sprint `docs(v11.N)` subject turns `--regression` red until the release (F14).
- **#106** (LOW): three drift lints default `V11_HOME` to the main tree, so run directly from a worktree they check master (F17). `run-tests` itself was fixed in S1-R3a.
- **#107** (MEDIUM, S2): `sync-tasks` ledger fidelity. A completed event takes the active task's subject (F2), and the `pair_` activation is never ledgered (F5).
- **#108** (LOW): registry hygiene after D0-5. `version` mixes V11 stamps and agent semver, five `file` paths point at nothing, and nine models are `inherit` (F20). The M4 alias WARNs ride here.
- **#109** (MEDIUM): `adversarial-lite-reviewer` has no search tool, so its integration lens can't enumerate callers (F9).
- **#110** (LOW, with S5-T5): `test_spawn_claude_window.py` tests the deleted module, so the live `spawn-claude-window.py` has no unit test (F30).
- **#111** (MEDIUM, S2): the write side of S1-T2c. A rehydrated TaskCreate is keyed on its new subject, not on `rehydrated_from.identity`, and `GATE_AUTOCLOSE` closes an aliased identity under the target's key.
- **#112** (LOW, S3 with the M3 re-measure): the `agent-scorecard --routing` read-side residuals that the review #6 fix left: the one-live-ledgered-session rule, filtered counters, docs and test gaps.
- **#113** (HIGH, leads S2): the resume epoch. A resumed conversation keeps the hook session id but gets a fresh TaskList, and nothing records the epoch. Seven `(session, task_id)` resolvers diverge. It proposes one epoch-aware resolver, and it absorbs the Known limits above.
- **#97** gains an addendum: the review queue is keyed by a bare task_id too (F6, F19).
- **Carried in `artifacts/s1-close-findings.md`:**
  - F12: stall output is plain stdout the model never sees (#87, S2-T3);
  - F13: load-sensitive test timeouts (S3-T1 re-tunes the harness; F15, the v11-retro flake, is resolved);
  - F32: `scripts/wave-review` crashes when an aggregate `task_artifacts` entry holds a count instead of a list, and it reads the aggregate by bare id (#97). It is a LOW ticket candidate, and the S1 sprint-close prompt was written by hand.
- **Carried from the S1-T15 fix review** (#6 of the 10:25 list). Four of its six findings were fixed in `c778e57` (see T15). Two are carried:
  - the pipefail detector's pattern gaps;
  - a here-string can spill to a TMPDIR temp file in the hooks.

**New scripts and flags.**
- Scripts: `scripts/cost-ledger`, `scripts/dispatch-advise`.
- Libraries: `scripts/lib/roster.py`, `review_corrections.py`, `handoff_identity.py`, `task_notification.py`.
- Config: `config/model-pricing.json`.
- Schemas: `schemas/cost-ledger.schema.json`, `schemas/dispatch-advice.schema.json`, and `advice_id` in `dispatch-trace.schema.json`.
- New flags:
  - `handoff --allow-empty`;
  - `check-wiring-parity --strict-unwired`/`--unwired-since`/`--report-dir`/`--keep`/`--install-cron`/`--uninstall-cron`;
  - `hooks/session-end --gc-run`;
  - `agent-scorecard --live-window`;
  - `check-registry-drift --human-owner`/`--project-root`/`--dispatch-trace`;
  - `dispatch-trace-append --advice-id`;
  - a path argument to `v11-compliance-check`;
  - `review-queue park`/`unpark` and `pending --json --include-parked` (fix task #12).
- `rotate-metrics --sessions` now runs the GC.
- `run-tests`' `Results:` line gains `, N errors` (fix task #7).

All are registered in `docs/SCRIPTS.md`. All but the `review-queue` subcommands are also in the skill's `playbooks/scripts.md`, which
has no `review-queue` row. `cost-ledger` and `dispatch-advise` are also in CLAUDE.md §9.

**Net-new levers.**
- Handoff: `V11_HANDOFF_SOURCE_CHECK`, `V11_HANDOFF_LIVE_WINDOW_SECS`, `V11_HANDOFF_SOURCE_BUDGET_SECS` (fix task #71), `V11_HANDOFF_IDENTITY_KEYS`, `V11_HANDOFF_SELF_NUDGE_SUPPRESS`, `V11_HANDOFF_SUMMARY_LINES`.
- Gates and waits: `V11_WRITE_GATE_SCRATCH_EXEMPT`, `V11_BG_WAIT_CONTRACT` (+`STALL_WAIT_*`).
- Cost: `V11_COST_STATUS` (+`_TIMEOUT`/`_FRESH`), `V11_COST_LEDGER`, `V11_MODEL_PRICING`.
- Scorecard: `V11_AS_ROUTING_RAW`, `V11_AS_ROTATED`, `V11_AS_TRANSCRIPTS` (+`_DIR`).
- wave-check: `V11_WAVE_CHECK_COVERAGE`, `V11_WAVE_CHECK_WAIVER_COVERAGE`, `V11_WAVE_CHECK_SKIP_REVIEW_STRICT`, `V11_REPLAY_EMIT_IDENTITIES`.
- Restart identity (S1-T2c): `V11_REPLAY_REHYDRATE_ALIAS`, `V11_WAVE_CHECK_EPOCH_BINDING`.
- Review queue: `V11_REVIEW_DAEMON_PARK` (fix task #12).
- Session GC: `V11_SESSION_GC_MODE`, `V11_SESSION_GC_TTL_HOURS`, `V11_SESSION_GC_QUARANTINE_HOURS`.
- Test gates: `V11_LINT_HONESTY_GATE`, and `V11_TEST_HOME_GUARD` (S1-R2; read only by `tests/conftest.py`).
- Lane D: `V11_ROSTER_CACHE`, `V11_DISPATCH_ADVICE_LOG`, `V11_AGENT_SCORECARD`, and the prompt-only `V11_DISPATCH_ADVISE`.

`V11_BASH_WRITE_WARN` gains `=legacy`. The pre-existing silent lever `V11_STEER_MAX_CHARS` (v11.40) now has its row (F27).

**Tests added** (`399beb8..6b00659`; the later fix merges added cases to existing files, listed with each fix).
- 18 new test files:
  - `test_block_honest_alternative`, `test_check_registry_drift`, `test_cost_ledger`, `test_dispatch_advise`, `test_handoff_identity_keys`
  - `test_handoff_self_nudge`, `test_handoff_source_budget`, `test_handoff_source_check`, `test_handoff_summary_resume`, `test_pipefail_early_exit`
  - `test_real_home_isolation`, `test_review_corrections`, `test_roster`, `test_run_tests_lint_gate`, `test_stall_wait_contract`
  - `test_status_cost_line`, `test_verify_gate_results`, `test_write_gate_scratch_exempt`
- Fixtures:
  - the M1 fixtures are in `tests/fixtures/handoff_m1/archivestream/`;
  - the frozen pre-S1-T2 `v11-resume-tasks` is in `tests/fixtures/handoff_identity/`.
- 38 files were extended: 36 test modules (9 of them only for the S1-T15 handoff test budgets), `tests/conftest.py` (the S1-R2 guard) and `tests/hooks/test-bash-write-warn.sh`.
- In total, 467 test functions were added and 6 removed (rewrites).

**Rollback levers:** see `docs/ROLLBACK_REFERENCE.md` § "v11.46 — Stop the Bleeding". `V11_REPLAY_REHYDRATE_ALIAS` is the one
exception: its row sits with the other `v11_replay_ledger` levers under "Unreleased — 2026-09-22 triage fixes". No lever covers the four
live data changes:
- the S1-P1 waiver rows and the S1-P3 correction rows are append-only ledger rows. Undo one by appending an `outcome=void` correction that names it (`scripts/lib/review_corrections.py`: a voided correction corrects nothing). The apply scripts are `artifacts/s1-p1-apply.sh` and `s1-p3-apply.sh`.
- the D0-5 registry sync is undone by restoring `~/.agent-registry/agents.json.bak-pre-d0-5-20260926T030740Z`.
- the G1 `secret-jar` registration is undone by restoring `~/.agent-registry/agents.json.bak-pre-secret-jar-20260926194935`.

---

## v11.45 "Rails" (v11-leverage-program S0) — 2026-09-26

**Make the system safe to change.** Sprint S0 of v11-leverage-program (spec: `sessions/v11-leverage-program/spec.md`,
roadmap §S0, gate G0). Every later sprint relies on these rails. Four tickets:
- **#90:** `session-end` was wired to `Stop`, so session teardown ran every turn. This was the root cause behind #75's same-session drops, the dead context tracker, retro-counter inflation and steer loss.
- **#86:** the fleet couldn't receive hook changes: 8/98 projects were at template parity, `v11-update` was frozen at v11.11 and its `--all --dry-run` wrote for real.
- **#85:** a sprint-prefixed commit could close tasks in another live session's project.
- **#89:** the CLOSE checks couldn't see the skill, and new scripts never reached the orchestrator.

Every row was adversarially reviewed (review tasks #13–#22), and every finding was fixed in fix tasks #23–#26 before merge.
Commits `346137f..d5d1938` (23 commits).

**T1 — regression lock.** `scripts/run-tests --regression*` takes an exclusive, host-global `flock`
(`$HOME/.cache/v11/regression.lock`, so worktrees with different `V11_ROOT`s still serialize). It covers pytest, the drift lints
and the extended slow tier. A second run waits up to `V11_REGRESSION_LOCK_TIMEOUT`, then exits 75. The lock fd is closed in
children (review fix `6085618`). Lever `V11_REGRESSION_LOCK`.

**T2 — hook-surface spike.** `sessions/v11-leverage-program/recon/spike-hook-surface.md` answers nine hook-surface questions with
citations, plus an orchestrator-verification section with corrections: Q4 `TaskUpdate` is its own tool; SessionEnd on tmux kill is
undocumented. Design rule adopted for T6: correctness must not depend on SessionEnd firing.

**T3 — #85 post-commit resolves the project from the committing repo.** `hooks/post-commit-close-tasks` resolves in this order:
`$V11_PROJECT`, then the repo's `.v11-project` pin (exactly one valid line), then the repo basename. The basename tier fires only
when the repo sits at its project's canonical root (realpath match) and that project's ledger exists. It never reads the host-global
active-project file. The repo root is the main worktree root (`--git-common-dir`), or the submodule's own toplevel inside a
submodule. Anything ambiguous refuses with a warning. `scripts/lib/postcommit_analysis.py` treats `cancelled` as terminal.

**T4 — #86 `v11-update` rebuilt as a template diff.** New `scripts/lib/wiring_diff.py` is the pure diff core, and `scripts/v11-update`
is a thin CLI over it:
- A hook command wired anywhere in the template is **managed** and reconciled to the template's exact `(event, matcher)` wiring. Every other command is **custom** and preserved byte-for-byte.
- The report distinguishes `fields_preserved` (per-hook keys such as `async`/`statusMessage`), `timeout_preserved` (custom timeouts only) and `superseded` (`guard-teammate-timeout` is removed wherever `guard-agent-stall` is wired).
- Writes keep the file's indent and newline, rewrite `hooks` in place, and are atomic and mode/symlink-safe. Errors are per-file: the batch continues and exits 1 at the end.
- `--dry-run` really writes zero bytes (it creates no backup dir either). Changed files are backed up under `V11_UPDATE_BACKUP_ROOT` first.
- `--all` discovers every wired `settings.json` under `V11_UPDATE_SCAN_ROOT`, not just `$SESSIONS_ROOT`. Discovery prunes dated backup and snapshot dirs (`v11.backup.*`, `*.bak`, `.v11-backups`), so a backup copy is never treated as a fleet project.
- `--scan` is deprecated and points at `check-wiring-parity`.

**T5 — #86 wiring truth.**
- `scaffold` builds a new project's `settings.json` from the template via `wiring_diff.py new-project-settings`. The stale 16-hook heredoc and the orphan `templates/project-settings.json` are gone.
- `v11-compliance-check` and `validate-project-setup` read hook counts live from the template.
- `tests/test_hooks_selftest.py` covers `ALL_HOOKS` and is regression-marked.
- New `scripts/check-wiring-parity` is the read-only fleet report, with a matcher-parity column (bare `Task` vs `Task|Agent`).
- `CLAUDE.md` §13 and `docs/ENFORCEMENT.md` correct the "dormant" docs: `guard-teammate-timeout` is superseded, `enforce-subagent` is opt-in/custom, and only `refresh-freshness-tags` is dormant.

**T6 — #90 Stop/SessionEnd split** (`V11_STOP_SPLIT`). `hooks/session-end` dispatches on `hook_event_name`.
- **Stop** takes the cheap path only when the project wires SessionEnd→session-end with a timeout of at least 30 s: the aggregate fold, plus an auto-emit throttled on the open-set digest. Otherwise it keeps the full per-turn path, so unsynced projects never lose teardown.
- **SessionEnd** runs the critical work first, then an exactly-once-per-sitting claim (one session-log row, one retro increment), manifest and scratch removal, then the bounded optional work. The claim is keyed on `session_id` plus a `.sitting` marker, so `--resume` counts again and a duplicate SessionEnd does not.
- A UUID-only GC removes dead-session dirs (`V11_SESSION_GC_HOURS`/`_ALL`/`_DRYRUN`, `--gc-preview`). It never touches `legacy-cli` or the other shared identities.
- `.handoff-autoemit-at` and the digest are stamped only on a successful emit. The #41 hand-edit guard holds on both paths (`skipped: hand-edited`).
- Behaviour change: session-end now runs align-aggregate *after* project resolution, so it uses the session's own project rather than the global active-project file. It still falls back to the global file when no project resolves (fix task #26, `b24bacf`).
- The template's SessionEnd entry carries `"timeout": 60`. The canary (`artifacts/s0-t6-canary.md`) found that the harness kills an untimed SessionEnd hook at ~1.5 s, before the emit, the retro counter and scratch removal.

**T7 — fleet sync (HIGH, user-approved).** `v11-update --all` was applied to 97/97 discovered projects, which are now at template
parity: M10 = 100%, against a baseline of 8/98. This carries the SessionEnd wiring, `guard-agent-stall` and `Task|Agent` fleet-wide.
example-project's custom hooks are preserved. Backups: `~/.v11-backups/v11-update/20260925T223523Z` (96 files) and
`~/.v11-backups/v11-update/20260925T223306Z` (1 file).

**T8 — #89 meta-rails.**
- `check-stamp-drift` also checks the team-orchestrator `SKILL.md` frontmatter and footer (`V11_ORCH_SKILL_MD`). A missing file FAILs unless `V11_ORCH_SKILL_REQUIRED=off`.
- `check-index-body-status-consistency` is scoped to the `**Status:**` line. Its README matching is case-sensitive for the ALL-CAPS tokens, and its warnings name any rejected lowercase words. This clears #73's false WARN.
- `check-class-included` judges every occurrence of an identifier: FAIL dominates (#40 F1).
- The skill's `close.md` lists the CLOSE gates, and `scripts.md` carries the registration rule and the backfill.

**T9 — #89 data rails.** `rotate-metrics` has a per-subdir policy:
- `ledger/<project>.jsonl`/`.seq`/`.lock` are never moved; `ledger/*.bak*`/`*.stale*` older than `LEDGER_BAK_TTL_DAYS` (14) are archived.
- `review-queue/` is report-only.
- `outbox/<project>/*.md` older than `OUTBOX_TTL_DAYS` (30) are archived.
- Top-level rotation is locked, with `V11_ROTATE_SETTLE_SECS` between `mv` and `gzip`.

New `scripts/install-rotate-cadence` installs the weekly cron line (`# v11-rotate-metrics`, Sun 04:15).

**T10 — #89 governance (user-approved).** `~/typesafe` and `~/.claude/skills` were git-init'd locally, with no remote. The skills repo
uses an allowlist `.gitignore` covering the 14 V11-family skills. Secret and large-file scans were clean before the first commit.
New `scripts/backup-surface` backs up, lists and restores the remaining non-git surfaces. The stale `~/.claude/hooks/spawn_claude_window.py`
was backed up, then deleted.

**T11 — ticket-index reconciliation.**
- Closed: #26 (a harness issue), #40-F2, #58 (residuals moved to S5).
- #01's schema v2 is frozen.
- #38 is re-scoped and out of CRITICAL (M4 re-baselined at 232).
- #59 → MEDIUM; #61 item 4 is closed.
- New #91.

**New scripts.** `scripts/backup-surface`, `scripts/check-wiring-parity`, `scripts/install-rotate-cadence`, and `scripts/lib/wiring_diff.py`
(library + `new-project-settings` subcommand). Rebuilt: `scripts/v11-update`. Deleted: `templates/project-settings.json`.
All are registered in `docs/SCRIPTS.md` and the skill's `playbooks/scripts.md`.

**Net-new levers.** `V11_REGRESSION_LOCK` (+`_FILE`/`_TIMEOUT`/`_PROBE`), `V11_STOP_SPLIT`, `V11_SESSION_GC_HOURS`/`_ALL`/`_DRYRUN`,
`V11_ORCH_SKILL_REQUIRED`, `V11_ORCH_SKILL_MD`, `V11_ROTATE_SETTLE_SECS`, `LEDGER_BAK_TTL_DAYS`, `OUTBOX_TTL_DAYS`,
`V11_UPDATE_TEMPLATE`/`_SCAN_ROOT`/`_BACKUP_ROOT`, `V11_SURFACE_BACKUP_ROOT`.

**Tests added.** 13 new test files:
- `test_backup_surface`, `test_check_class_included`, `test_check_index_body_status_consistency`, `test_check_wiring_parity`
- `test_install_rotate_cadence`, `test_postcommit_project_resolution`, `test_rotate_metrics_subdirs`, `test_run_tests_regression_lock`
- `test_scaffold_wiring_parity`, `test_session_end_split`, `test_v11_update`, `test_validate_project_setup_wiring`, `test_wiring_diff`

4 files were extended: `test_check_stamp_drift`, `test_hooks_selftest`, `test_v11_compliance_check_wave`, and `test_scripts_smoke`
(+4 manifest entries). The new fixtures are in `tests/fixtures/wiring/`, including the frozen pre-S0-T4 `v11-update`, which proves the
dry-run bug. In total: **158 new test functions** (173 collected items in the new files), 0 removed.

**Deferred (named, not faked).**
- #91: `v11-compliance-check` Gate 3 reads the `~/sessions/` mirror.
- #92: `v11-update` does not propagate a new template key into a hook a project already has.
- #93: `v11-compliance-check --scan` still scores against a hardcoded 10.
- #94: tests write `context-estimate.json` into the real `~/.agent-metrics/sessions/`, because `scripts/lib/context_tracker.py` ignores `METRICS_DIR`. The UUID-only GC spares the resulting test-named dirs; removing them is manual.
- #89 residuals: prompt-only levers in playbook markdown are still invisible to `check-rollback-lever-drift`. `~/.claude/docs/README.md` still says 96 agents (the live count is 102; this predates S0).
- Pushing v11 is the user's call.

**Rollback levers:** see `docs/ROLLBACK_REFERENCE.md` § "v11.45 — Rails". For the fleet wiring, restore from the per-file
`~/.v11-backups/v11-update/<ts>/` backups, or remove the template's SessionEnd entry and re-run `v11-update --all`.

**Addendum: landed after the release commit `6113602`** (the S0 CLOSE owed this; written at the S1 CLOSE).
- `77e20ab`: **`v11-update --restore STAMP [STAMP ...] [--apply]`** (review #18 E1) is a one-command rollback of an apply.
  - Without `--apply` it lists every file backed up under `$V11_UPDATE_BACKUP_ROOT/STAMP` (backup → target, sha256 differs?) and writes nothing.
  - `--apply` restores each file byte-exact with the backup's mode, atomically and through a symlinked target. It first saves the current file under `<root>/<now>-pre-restore/`, which is itself restorable.
  - Stamps run oldest first. An unknown or invalid stamp refuses the whole call (exit 2); a path escape, a target inside the backup root or a missing target fails that file only (exit 1).
  - `wiring_diff.atomic_write` takes bytes and an explicit mode. A real-data dry-run of the S0-T7 stamps listed 97 files and wrote 0.
  - Test: `tests/test_v11_update_restore.py` (7). Hardened in v11.46 (S1-R4, #100).
- `fd150df`: the two `case` statements S0-T6 added to `hooks/session-end` (the GC verdict and the split-wiring check) get explicit `*)` arms. `--regression-extended`'s lint-test-honesty found them at the S0 CLOSE, after a green `--regression`: from a worktree the lint had scanned master (s0-close F7, fixed in v11.46 S1-R3a).
- `02d6dfe`: filed from the S0 CLOSE:
  - #95 (HIGH): `--regression-extended` is red on 4 Gate 13 slow tests, pre-existing;
  - #96 (MEDIUM): `wave-check` reads only `open_tasks`, so a closed sprint reports no tasks;
  - #97 (LOW): `task_artifacts` is keyed by numeric task id;
  - #98 (HIGH): a session started in a dir without `.claude/settings.json` runs with no V11 hooks. The S0 sprint itself ran unwired.
  - v11.46 shipped #95's Gate 13 fix (S1-T15), #96 (S1-T16), #98 item 3 (S1-R3b), and the review-verdict binding half of the #97 family (S1-P3).
- `72ef8e3`: filed #99 (align-aggregate bypasses the seqno counter; backfilled rows read as live; executor naming) and #100 (`--restore` hardening) from the #27/#28 lite reviews. v11.46 took #99 items 2–3 (S1-P1, S1-T11) and #100 (S1-R4).

---


## v11.44 "Orchestrator Quality" — 2026-09-08

**Make the orchestrator a first-class, scoreable actor and grade the briefs it authors.**
Motivated by the 2026-09-08 loop-effectiveness audit (`sessions/v11-audit-and-improve/artifacts/loop-effectiveness-audit-2026-09-08.md`),
which found the orchestrator falls through every crack: invisible at the runtime layer
(all 13,966 `autonomy-audit` rows `caller_kind=unknown`, **0** with `outcome=="error"`),
junk-bucketed at the review layer (~151 findings scattered across 5 free-form spellings +
`main`), and its task-authoring quality unmeasured. Spec: `sessions/v11-orchestrator-quality/spec.md`
(4-lens swarm-reviewed before build — `artifacts/swarm-review-round1.md`).

**T1 — shared fold-table + helpers.** `hooks/lib/actor-canonical.json` (single source of truth)
loaded by both `v11_canonical_actor` (bash, common.sh) and `scripts/lib/actor_canonical.py`
(Python). Folds the orchestrator family → `orchestrator`; non-family names pass through
UNCHANGED (non-lossy). New `v11_brief_attribution_key` = `SHA256(project|subject_norm|create_seq|brief)`
(canonical identity, not the ephemeral `task_id`). Cross-language identity test.

**T2 — canonicalize the readers.** `agent-scorecard` + `agent-effectiveness` route every
actor comparison through the fold-table (read-side; `V11_ORCH_QUALITY=off` reverts to literal
match). `agent-effectiveness --rank` folds the family into one row, ACCUMULATING counts (single-
contributor agents behave byte-identically). Added `brief` to the `LAYERS` list + both `--layer`
validators. Left `_ORCH_SENTINELS` (token-attribution exclusion) UNCHANGED, with a guard test.

**T3 — G2: revive the runtime-error layer** (dormant FLEET-WIDE, not just for the orchestrator).
`track-autonomy` read a top-level `.error` that current Claude Code payloads never populate; the
real tool result + `is_error` live at `.tool_response`. Now detects it. Gated `V11_RUNTIME_ERROR_CAPTURE`;
cannot false-positive on a success.

**T4/T5 — `scripts/grade-briefs`.** Scores ledger `created` briefs (excluding `source==migration`):
scoped / right-agent / outcome (scored); testable / agent-fit (coarse advisory). `--apply` appends
**additive** `found_by_layer="brief"` findings on the canonical `orchestrator` with
`cause_kind=briefing_defect|briefing_risk`, idempotent via the canonical-identity key, NEVER
touching an executor's finding. Reuses `agent-scorecard --routing --json` for the aggregate override rate.

**T6 — cause_kind on execution findings.** `sync-tasks` stamps `cause_kind="execution_defect"` on
new lite/wave findings (additive, write-time). Together with T5's `briefing_defect`, a dual-fault
task shows a fault on BOTH the executor's and the orchestrator's scorecard — the **intended union**.

**T7 — Brief Quality surface.** `agent-scorecard orchestrator` gains a Brief Quality section +
`--layer brief` (human + `--json brief_quality` block): findings, defect/risk split, top reasons, trend.

**T8 — the consumer (closes the loop).** `check-improve-subagent-triggers` folds orchestrator
candidates (5 spellings → 1 signal + 1 cooldown marker) and emits an `orchestrator-briefing-quality`
suggestion when the briefing-defect rate crosses a threshold (`V11_ORCH_BRIEF_DEFECT_THRESHOLD`
default 0.30, `V11_ORCH_BRIEF_MIN` default 3) — a surfaced TaskCreate to review authoring guidance,
never an auto-edit. Directly answers the audit's Fix #2 ("actuate the consumer").

**Tests:** `tests/test_actor_canonical.py` + `tests/test_orchestrator_quality.py` (canonicalization
cross-lang, rubric, additive-idempotent-union, migration-exclusion, runtime-error capture, consumer
fire+cooldown, all 3 rollback levers).

**Deferred (named, not faked):** orchestrator/subagent runtime split (G3) + per-brief override
attribution — both need a `dispatch-trace` v2 `session_uuid` (its schema is "frozen v1"; it records
no child session id and `task_id` is heavily reused). Auto-amendment of orchestrator instructions
(no `~/.claude/agents/*.md` target — CLAUDE.md / team-orchestrator SKILL.md is a separate, higher-risk change).

**Rollback levers:** `V11_ORCH_QUALITY`, `V11_BRIEF_REVIEW`, `V11_RUNTIME_ERROR_CAPTURE`,
`V11_ORCH_BRIEF_DEFECT_THRESHOLD`, `V11_ORCH_BRIEF_MIN` (see ROLLBACK_REFERENCE.md).

---

## v11.43 "Timing Calibration" — 2026-09-04

Meta-improvement session output. Root-caused the chronic "estimates run too long" complaint against actual dev history: mining `~/.agent-metrics/ledger/*.jsonl` + git (2026-05→09, 27 v11 efforts, ~130 projects) showed a v11 version *spans* a median **19 calendar days** but is only **~4 active-days / ~3.5 active-hours** of work — estimates were anchored to calendar/hand-coding intuition, 4–8× the real effort, with no empirical anchor anywhere in the framework. This version makes the real numbers a re-derivable input that planning *consumes* where estimates are emitted. Three waves, additive, one prompt-level rollback lever. (Version follows the committed v11.42 task-state-integrity work; v11.41/v11.42 CHANGELOG backfill is pre-existing drift, tracked separately.)

**W1 — Data plane: anchor + re-derivation script (2 files + 1 test suite).**

- **`scripts/build-timing`** (new, pure `python3`, mirrors `scripts/audit-ledger-attribution`): reads the durable ledger, matches `created`→`completed` by `(project, create_seq)`, reports same-day task cycle time, active-days (distinct dates), active-hours (Σ gaps clamped 30 min). `--project/--since/--estimate N/--json/--test/--ledger-dir`. **Bug fixed vs the scratch derivation**: cross-session dormancy (rehydrated tasks completed weeks later) inflated raw durations into the 100k-min range — now reported separately as `dormant_*` and NEVER in the median.
- **`docs/BUILD_TIMING.md`** (new): canonical anchor table (task ≈30–60 min · point-release ≈<1h · sprint ≈an evening · MVP ≈a few active-days · flagship = the exception) + evidence + methodology + the "calendar ≠ effort" rule.
- Test: `tests/test_build_timing.py` (11 cases) — same-day median is headline, dormant excluded, active-days/hours math, `--estimate` bands, stable `--json` shape. All green.

**W2 — Consumption: where estimates get emitted (5 surfaces).**

- `playbooks/interview.md` STEP 4c — the plan-summary gate now attaches a wall-clock band ("Est. build ~{active_time} — active work, not calendar"), `V11_TIMING_ANCHOR`-gated.
- `playbooks/task-patterns.md` — per-task active-time anchor (routine ≈30 min → novel ≈half-day) after the metadata block + Defaults-Matrix pointer.
- `SKILL.md` — Behavior Rule #3 under Interview & Planning: estimate in active-time, anchor to `docs/BUILD_TIMING.md`.
- `CLAUDE.md §6` — note distinguishing wall-clock build time (→ BUILD_TIMING.md) from token-effort levels.
- `templates/SCALING_GUIDE.md` — "Timeline" column recalibrated from calendar-weeks ("1–3 weeks") to active-time; footnote on external-gate calendar.

**W3 — Feedback loop (lightweight) + registration.**

- `playbooks/journal.md` — `/v11 retrospective` agent gains `build-timing --json` as an INPUT; retro JSON schema gains a `timing_actual` block (`median_task_min`, `active_hrs`, `active_days`, `estimate_drift_note`); formation-outcome journal row notes estimate-vs-actual. No `v11-retro`/`session-end`/task-schema/hook change (consume-light; per-task `metadata.estimate` capture filed as v11.44 follow-up).
- Registered in `CLAUDE.md §9` + `docs/SCRIPTS.md`; rollback lever in `docs/ROLLBACK_REFERENCE.md`.

**Rollback var.** `V11_TIMING_ANCHOR=off` — suppresses the STEP 4c estimate line, reverting to task-count-only. All other artifacts (script, doc, anchors, retro field) are additive and inert without acting on the estimate.

**Tests-added.** `tests/test_build_timing.py` (11). **Memory.** `feedback_build_timing_calibration.md`.

---

## v11.42 "Task-State Integrity" — 2026-09-02

*(Backfilled 2026-09-08 — this entry postdates the release; the v11.43 header above flags the gap it closes.)* Hardened the task-state / durable-ledger layer against the identity- and pair-drift classes surfaced while draining the v11.40 review queue. Two waves, additive schema only, no reader breakage.

**W1 — Safe additive schema + audit helper** (commit `74239d6`). Task-state integrity fields added additively, with docs and a read-only audit helper to inspect them.

**W2 — Durability + lifecycle wiring.**

- **Pair-ID durability** (`828bc27`, RC3): the review-sibling pair counter is now sourced from the durable ledger and salted with a random suffix, so pair IDs survive rehydrate/replay instead of colliding on a session-local counter.
- **Guard carve-out + skill v1.4 age-out + session-end wiring** (`858557e`, RC2 + RC5b): guard exemption for the integrity path, skill-version age-out at v1.4, and session-end hook wiring for the new state.

No new top-level rollback env vars beyond the wave-local RC toggles. Full task detail: git range `74239d6..858557e`.

---

## v11.40 "Review Residuals" — 2026-08-29

Same-day follow-through on the five deferrals filed at v11.39.1 (commit `b91682d`) after draining the v11-38-consolidation review queue (16 adversarial-lite-reviewer verdicts, 22 findings). Every finding either fixed here, or explicitly re-scoped as a future seed with rationale. Three waves + CLOSE, six tasks. No new HIGH-risk data mutations; no new rollback env vars beyond the one new tunable.

**W1 — Backfill hardening (4 tasks + 5 tests).** Two edge-case code fixes plus two coverage additions to `scripts/backfill-ledger-attribution`.

- **W1-T1 (#4 E4 task_id=0 falsy)**: new `_str_task_id` helper preserves integer 0 across four sites (`build_create_index`, `resolve_attribution`, `attribution_key`, sink row). Prior `str(ev.get("task_id") or "")` collapsed 0 to empty string, silently losing Strategy 2 attribution and producing false-collision attribution_keys. Test: `TestTaskIdZero` (2 cases — Strategy 2 resolution + attribution_key distinctness).
- **W1-T2 (#4 E5 .bak first-apply-wins)**: `process_file` now skips `.bak` write if the file already exists, so `.bak` always holds the TRUE pre-backfill original and `--revert` restores that. Docstring updated. Test: `TestBakFirstApplyWins` (1 case — 2nd apply doesn't overwrite, revert restores original).
- **W1-T3 (#5 E1 flock scenario)**: test spawns child holding `LOCK_EX` via `flock(1)` on ledger `.lock` sidecar; asserts `--apply` returns exit 2 (lock timeout) within `acquire_lock` timeout window. Test-only — the flock discipline was already in place (v11.39.1); this catches regression. `shutil.which("flock")` skip guard for systems without `flock(1)`.
- **W1-T4 (#5 E2 tmp-survivor guard)**: test globs ledger dir for `*.tmp.backfill` after `--apply` across 3 projects; asserts empty. Cheap regression guard for staging→`os.replace` atomicity.

Suite: `test_backfill_ledger_attribution.py` 12 → 17 tests, all green. Files: `scripts/backfill-ledger-attribution`, `tests/test_backfill_ledger_attribution.py`.

**W2 — Doc/handoff sweep (2 tasks + 3 tests).**

- **W2-T1 (#18 README.md prose rot)**: replaced 30-line stale narrative under "Current Version: V11.39" (opening line narrated V11.30 as current, bullets listed V11.30/V11.29/V11.15/V11.14/V11.13/V11.12) with a 3-line recent-line + pointer to `docs/CHANGELOG.md`. Replaced 12-line "Protocol Version History" that stopped at V11.15 with a 6-line pointer. README: 146 → 116 lines. The README's job stopped at "what V11 is"; the CHANGELOG's job is "what changed when". Delegating instead of duplicating means future stamp bumps don't drift prose again. Files: `README.md`.
- **W2-T2 (#1/#34 handoff steer truncation)**: root cause CONFIRMED via Haiku audit (`scripts/handoff:1846` had hard cap `${STEER_TEXT:0:2000}` with no truncation warning; 2334-char steer cut at char 2000 = exact "CL" cutoff match, byte-for-byte). Fix: env-var-tunable via `V11_STEER_MAX_CHARS` (default 2000 backcompat, `=0` disables cap entirely); stderr warn-on-truncate names the cap value, pre-cap length, first 80 chars of the tail lost, and the env var name. Added file-header comment about `.handoff-steer.md` → `.handoff-steer.md.prev` consume-semantics (addresses #34 files_changed metadata mismatch). Tests: 3 new (`length_cap_prints_stderr_warning`, `max_chars_env_var_raises_cap`, `max_chars_zero_disables_cap`); `test_handoff_steer.py` 22 → 25 tests, all green. Files: `scripts/handoff`, `tests/test_handoff_steer.py`.

**W3 — Schema enum expansion (1 task + 14 tests).**

- **W3-T1 (#20 unmeasured_causal_claim)**: `schemas/agent-errors.schema.json` `error_type` enum 12 → 13 values. `unmeasured_causal_claim` was declared as valid output in `~/.claude/agents/adversarial-lite-reviewer.md`'s Lens 4 (causal-claim audit) but was missing from the ledger schema — any Layer B verdict emitting it would have failed schema validation. Preventive close; live ledger emissions = 0 at commit time. Also confirmed `adversarial-reviewer.md` and `coherence-reviewer.md` use "lens" not "type" — no additional enum values needed from those two agents. Tests: 14 new in `test_v11_21_schemas.py` (13 parametrized covering full enum + 1 rejection guard for a typo-shaped non-enum value); all green. Files: `schemas/agent-errors.schema.json`, `tests/test_v11_21_schemas.py`.

**CLOSE.** `docs/CHANGELOG.md` v11.40 "Review Residuals" stanza landed above v11.39. `CLAUDE.md §17` pointer bumped v11.39 → v11.40. `README.md` Current Version bumped. `VERSION.md` v11.40 stanza inserted. `agents/V11_AGENT_REGISTRY.json` `metadata.version` + all 13 `agents[*].version` bumped. `scripts/check-stamp-drift` returns green on all 5 surfaces. `scripts/run-tests --regression` returns green.

**Commit-SHA list** (v11 repo, in order):

- `d4b7593` — `fix(v11.40 W1): backfill hardening — 2 code fixes + 5 test additions`
- `3b0d4e7` — `docs(v11.40 W2-T1): README.md prose write-through (#18)`
- `cb561d5` — `fix(v11.40 W3-T1): agent-errors error_type enum + unmeasured_causal_claim (#20)`
- `1895929` — `fix(v11.40 W2-T2): handoff steer cap → env var + warn-on-truncate (#1/#34)`

**Tests-added.** 22 new tests (5 backfill + 3 handoff-steer + 14 schema-enum), all green. No regressions in existing suites (`test_backfill_ledger_attribution.py` 12 → 17, `test_handoff_steer.py` 22 → 25, `test_v11_21_schemas.py` +14 new).

**Rollback vars.** Net-new this sprint: `V11_STEER_MAX_CHARS` (default 2000 preserves backcompat; `=0` disables cap entirely; else clamps to N chars with stderr warn).

**Follow-ups (v11.41 candidates).** Secondary defect surfaced during W2-T2 audit: `V11_STEER_PREV_GRACE_SECS=300` expiry silently produces a steerless handoff.md when regeneration happens more than 5min after first bake in the same session. Not fixed here (out of W2-T2 scope); file when the pattern surfaces operationally. Also: the 754 unresolvable rows in `~/.agent-metrics/unattributed-events.jsonl` remain a fixed dead-letter — inherent, not a defect. No v11.40 review-queue drain performed on v11.40's own reviewable completions; the queue will grow by ~6 (W1-T1..T4, W2-T1..T2, W3-T1, CLOSE) for future sprints to drain along with v11.38/v11.39's residuals.

---

## v11.39 "Post-Consolidation" — 2026-08-29

Same-day follow-through on the three v11.38-deferred surfaces the user asked to close after v11.38 scope-lock. No new feature scope; every ticket carries pytest coverage or a live-apply verification. Two waves + CLOSE, six tasks.

**W1 — #48 wire (2/2).** `hooks/lib/common.sh:3469` (open-view exclusion filter in `v11_replay_ledger`'s Python fold pass) now gates cancelled-fold behind `V11_CANCELLED_FILTERS_REPLAY` (default `"on"` preserves #17 F1). When `=off`, cancelled events unfold ONLY when `cancelled_at >= V11_CANCELLED_UNFOLD_SINCE_TS` (default `now-1h`) — the paired cutoff prevents the R2 swarm's retroactive-unfold silent failure on stale cancelled events. Gate site chosen over the `3338` fold handler so `rec.status="cancelled"` stays terminal; only the OPEN-VIEW exclusion is gated. Env vars threaded through the shell prefix at `v11_replay_ledger:2971-2972` so they inherit into the `python3 - <<PYEOF` block. Pytest: `TestCancelledUnfoldReplay` (3 cases in `tests/test_ledger_replay.py`) — F3 acceptance (T-2h folded / T-30min unfolded with cutoff=T-1h), explicit-`=on` regression, unparseable-`cancelled_at` safety default. Red-then-green proof: reverting the gate makes F3 fail with `assert '2' in set()` while safety cases still pass. All 10 existing `TestCancelledTaskExclusion` tests remain green (default preserves #17 F1). Files: `hooks/lib/common.sh`, `tests/test_ledger_replay.py`.

**W2 — Historical backfill + doc harmonization (3/3).** New `scripts/backfill-ledger-attribution` (Python3, ~400 LOC): walks `~/.agent-metrics/ledger/*.jsonl` (excluding `archive/`), fills missing attribution on agent-authored rows (`created`/`review`/`artifact_warn`) via two strategies — (1) review rows get `reviewer_agent → owner` promotion (matches v11.38 W3 #49 direction), (2) all agent-authored types look up same-`task_id` create-row attribution via `(project, session_uuid, task_id[, create_seq])` or `(project, subject_norm, create_seq)`. Unresolvable rows → `~/.agent-metrics/unattributed-events.jsonl` (same sink `v11_ledger_append:2506` writes under `V11_LEDGER_STRICT_ATTRIBUTION`) with SHA256 `attribution_key` for downstream dedup. State-transition + system-event rows LEFT ALONE per CLAUDE.md §14.1 (reader inherits at query time; denormalizing would corrupt the taxonomy). Idempotent (only fills empty slots), FD-207-compatible (`fcntl.flock(LOCK_EX)` on `.lock` sidecar), atomic (staging → `os.replace`), `.bak` snapshot per file. Modes: `--dry-run` (default), `--apply`, `--revert` (restores from `.bak`, preserves `.bak.pre-revert.<ts>`). Rollback: `V11_LEDGER_BACKFILL_ATTRIBUTION=off` hard no-op. Pytest: 11 cases in `tests/test_backfill_ledger_attribution.py` — reviewer promotion, create-row lookup, state-transition + system-event NON-modification, idempotency (byte-identical after 2nd apply), --dry-run writes nothing, --revert restores `.bak` with pre-revert snapshot, rollback lever noop, malformed-line preservation. Live `--apply` on 164 ledger files rewrote 353 rows (316 via reviewer promo + 37 via sibling create-row lookup), sunk 754 unresolvable to the dead-letter. Result verified with `scripts/audit-ledger-attribution --by-ev`: **review-event gap 325 → 9 (all-time)**, **190 → 9 (30d)**, closing the v11.37 W1-T2 audit's 209/209 attribution hole for review rows. Agent-authored gap rate: 21.7% → 14.9%. `VERSION.md` intro (5 lines) reworded from stale "no longer maintained past v11.9.0" to accurate "Not a canonical changelog. Since v11.29 this file is bumped intermittently as an artifact of satisfying `scripts/check-stamp-drift`; authoritative per-release log is `docs/CHANGELOG.md`" — the intro now matches the pattern every v11.29+ stanza already apologizes for at its tail. Files: `scripts/backfill-ledger-attribution` (new), `tests/test_backfill_ledger_attribution.py` (new), `VERSION.md`, live-only: 164 `*.jsonl.bak` sidecars under `~/.agent-metrics/ledger/`.

**CLOSE.** Ticket #48 body flipped PROPOSED → SHIPPED with commit SHA. `README.md` Current Version bumped `V11.38` → `V11.39`. This CHANGELOG entry landed. `CLAUDE.md §17` pointer bumped to v11.39. `VERSION.md` heading gained a v11.39 stanza. `scripts/check-stamp-drift` returns green. `scripts/run-tests --regression` returns green.

**Commit-SHA list** (v11 repo):
- `b54bab6` — `fix(v11.39 W1-T1+T2): wire V11_CANCELLED_FILTERS_REPLAY + cutoff (#48)`
- `4852a0b` — `feat(v11.39 W2-T1+T2): backfill-ledger-attribution + live apply (#49 F1)`
- `a3db203` — `docs(v11.39 W2-T3): VERSION.md intro reflects actual bump pattern (#39)`

**Tests-added.** 3 new `TestCancelledUnfoldReplay` cases + 11 new `test_backfill_ledger_attribution.py` cases = 14 new tests, all green. No test-side regressions.

**Rollback vars.** Net-new this sprint: `V11_CANCELLED_FILTERS_REPLAY` (default `on`), `V11_CANCELLED_UNFOLD_SINCE_TS` (default `now-1h` when replay=off), `V11_LEDGER_BACKFILL_ATTRIBUTION` (default `on`; `=off` hard no-op).

**Follow-ups.** The `754` unresolvable rows (createds with no matching attribution + orphan `artifact_warn` events) sit in `~/.agent-metrics/unattributed-events.jsonl` as a fixed dead-letter — inherently unresolvable via the two strategies. Downstream audit needs a `--exclude-dead-letter` flag or migration-source filter if a further honesty pass wants to segment them out; not filed as a v11.40 seed since it's a query-side ergonomic, not a data-plane defect. Review-queue drainage of the 10 v11.38-shipped-work reviews was NOT run this sprint per steer's tight scope — first sprint that closes them will drain 10+n where n = v11.39's own reviewable completions.

---

## v11.38 "Consolidation" — 2026-08-29

Root-clustered fold of every v11.37-deferred ticket + the user-deferred pytest suite. Six tickets (#39/#48/#49/#50/#51/#52) + v11.37 W1-T6 pytest scope. Theme: **close the residuals the v11.37 sprint honestly filed rather than pretending they were shipped.** No new feature scope; hardening + coverage + one contingent wire that user reviewed and skipped. Two of the six tickets (#51/#52) were surfaced by v11.37 post-CLOSE adversarial-lite reviews of the sprint's own shipped work — closing them here completes the review-driven improvement loop.

Spec: `sessions/v11-38-consolidation/spec.md` (Round 1 — no external swarm review; sprint scope was well-known review-driven backlog authored across v11.37 CLOSE-T4 + post-CLOSE remediations, so the standard "swarm before locking" discipline was intentionally skipped in favor of PM-drafted locked-design-calls confirmed at scope-lock).

**W1 — Reconciler + ledger safety hardening (4/4 tasks).** Three review-surfaced code defects + full pytest coverage for the v11.37 W1-T6 deferred scope. `scripts/reconcile-agent-registry:compute_plan()` now resolves the registry `file:` field before treating a name as a prune candidate (#51 fix — closes the latent risk that a nested-only `.md` would be silently pruned by `-maxdepth 1` archive/ exclusion). `hooks/lib/common.sh:v11_ledger_append` strict-mode mirror path now runs under dedicated FD-209 flock + best-effort `jq del(.description,.metadata,.artifacts)` truncation cap when line >4000B (#52 fix — closes concurrent-writer interleaving and Linux O_APPEND torn-line risk on the diagnostic side-file; primary FD-207 critical section unaffected). Three new pytest files with 18 total tests: `test_reconcile_agent_registry.py` (7 tests — dry-run/apply/revert semantics, atomic-mv, LOCK_NB refuse-not-serialize, archive/ policy, nested-file regression guard), `test_ledger_writer_normalization.py` (6 tests — off/advisory/on × agent-authored/state-transition/system-event matrix + 10-concurrent-writer proof + oversized-line truncation), `test_audit_ledger_attribution.py` (5 tests — 3-class taxonomy per CLAUDE.md §14.1 + --by-ev breakout). All 18 pass. Note: v11.37 W1-T6's "backfill" test category not implemented — the sprint scope-reduced W1-T2 to READ-ONLY audit only; historical backfill remains a v11.39 candidate (#49 F1 residual). Files: `scripts/reconcile-agent-registry`, `hooks/lib/common.sh`, `tests/test_reconcile_agent_registry.py` (new), `tests/test_ledger_writer_normalization.py` (new), `tests/test_audit_ledger_attribution.py` (new).

**W2 — Staleness sweep (3/3 tasks, parallelizable across files).** Cross-consumer doc/test sweeps of drift that pre-dated v11.37. `agents/V11_AGENT_REGISTRY.json` `metadata.version` + all 13 `agents[*].version` bumped `"11.35.0"` → `"11.38"`; `README.md` Current Version bumped; `VERSION.md` gained a v11.38 section header — closes #39, `scripts/check-stamp-drift` reports 4/5 OK (last surface = CLAUDE.md §17, bumped by CLOSE-T3). Six test assertions in `tests/test_hook_behaviors.py`, `tests/test_e2e_v11_pipeline.py`, `tests/test_session_scoped_active_project.py` switched from `.strip() == "name"` to `.splitlines()[0] == "name"` to match v11.35.6 W2 F2 owner-stamped 2-line active-project format — all 7 previously-failing tests from v11.37 CLOSE-T4 now GREEN (#50 F1). `schemas/agent-errors.schema.json` `error_type` enum extended additively with `"correctness"` + `"unknown"` (both live-observed via `jq -r '.error_type' ~/.agent-metrics/agent-errors.jsonl | sort -u`) — `test_str_001_live_ledger_validates` PASS (#50 F2). Files: `agents/V11_AGENT_REGISTRY.json`, `README.md`, `VERSION.md`, `tests/test_hook_behaviors.py`, `tests/test_e2e_v11_pipeline.py`, `tests/test_session_scoped_active_project.py`, `schemas/agent-errors.schema.json`.

**W3 — Attribution close-out (2/2 tasks; #48 wire deferred per user scope-lock).** `hooks/lib/common.sh:_v11_review_ledger_event` now populates `owner` (the attribution field checked by `audit-ledger-attribution` per CLAUDE.md §14.1 3-class taxonomy) from the verdict file's `reviewer` field with `"adversarial-lite-reviewer"` fallback — closes the 100% attribution gap surfaced by v11.37 W1-T2 audit (209/209 review events unattributed in last 30d). PM design call locked: `owner` (not `metadata.agent`) matches existing agent-authored `owner` pattern and is the primary strict-mode check site. Red-then-green pytest (`tests/test_review_writer_attribution.py`, 3 tests, all PASS): custom-reviewer flow-through, canonical fallback, resolved vs identity-unresolved branches. New events carry attribution going forward; historical 209/209 gap unchanged per scope constraint (backfill scope-reduced out — v11.39 candidate). `#48` (V11_CANCELLED_FILTERS_REPLAY Option A wire) explicitly reviewed by user at scope-lock and DEFERRED per no-user-need. Design remains ready (~15 LOC + paired cutoff-timestamp lever preventing retroactive-unfold silent failure); pick up whenever a debugging use case surfaces. Files: `hooks/lib/common.sh`, `tests/test_review_writer_attribution.py` (new).

**CLOSE.** Ticket-body ↔ README-index reconcile (CLOSE-T1, commit a8c16f1) flipped 5 tickets to SHIPPED with commit SHAs and marked #48 explicitly DEFERRED. This entry (CLOSE-T2) shipped `v11.38` stanza. `v11/CLAUDE.md §17` pointer bump (CLOSE-T3), `run-tests --regression-extended` post-CLOSE gate (CLOSE-T4, target 2695/2695), and coherence-reviewer 5-lens swarm (CLOSE-T5) follow per the roadmap.

**Commit-SHA list.** All commits landed in the v11 repo (no team-orchestrator repo work this sprint):
- `5a03b35` — `feat(v11.38 W1-T1 + W1-T3a): reconcile-agent-registry — resolve nested file: field before prune (#51)`
- `d04f060` — `feat(v11.38 W1-T2 + W1-T3c): unattributed-events.jsonl mirror — flock + PIPE_BUF cap (#52)`
- `7cba664` — `feat(v11.38 W1-T3b): audit-ledger-attribution pytest coverage — 3-class taxonomy`
- `7d50e1a` — `fix(v11.38 W2-T1): bump 4 stale v11.35.0 stamps to v11.38 (#39)`
- `0455a92` — `fix(v11.38 W2-T2): update 6 stale test assertions for owner-stamped active-project (#50 F1)`
- `4d697d9` — `fix(v11.38 W2-T3): extend agent-errors error_type enum + correctness + unknown (#50 F2)`
- `123b97d` — `fix(v11.38 W3-T1): review-writer populates owner from verdict.reviewer (#49)`
- `a8c16f1` — `docs(v11.38 CLOSE-T1): reconcile ticket-body Status + README rows for shipped scope`

**Tests-added.** 4 new pytest files (18 W1 tests + 3 W3-T1 tests = 21 total), 6 in-place test-assertion fixes, 1 schema enum expansion. All new tests PASS; all previously-known-failing tests from v11.37 CLOSE-T4 now GREEN.

**Rollback vars.** Net-new this sprint: none. All fixes are pure test-side, schema-additive, or additive-safety on existing lever surfaces (mirror path stays gated by pre-existing `V11_LEDGER_STRICT_ATTRIBUTION=off` default; reconciler still gated by `V11_REGISTRY_RECONCILE`).

**Follow-ups (v11.39 seeds).** Ticket #48 (`V11_CANCELLED_FILTERS_REPLAY` Option A wire) remains PROPOSED — user-reviewed + skipped at v11.38 scope-lock, design ready to ship when a debugging use case surfaces. Historical ledger-attribution backfill of the 209 unattributed review events + agent-authored `created` events with `metadata.agent`-missing rows deferred as v11.39 candidate (writer-side gap now closed; backfill is orthogonal cleanup). VERSION.md intro claim ("no longer maintained past v11.9.0") stayed unfixed this sprint — the file has been bumped intermittently since v11.29; harmonizing the intro is orthogonal to #39's stamp bump.

---

## v11.37 "Alignment Remediation" — 2026-08-28

Root-clustered fold of 7 HIGH/CRITICAL tickets (#38 amplified, #42-#47) surfaced by the v11.36 post-CLOSE 6-lens Haiku swarm alignment review. Theme: **remediate the drift first, then ship the checks that catch it — completing the v11.36 W2 `check-*-drift` family and wiring every member into every commit surface.** Spec: `sessions/v11-37-alignment-remediation/spec.md` (Round 2, post-swarm-review — wave order inverted from Round 1's W1→W2 to reconcile-first per swarm C2 finding that Round 1 deadlocked at dogfood time; 20 tasks bundled from 22 per swarm C5).

**W1 — Reconcile the amplified drift (5/6 tasks; T6 pytest suite user-deferred).** `scripts/reconcile-agent-registry` — atomic Python reconciler with `--dry-run` / `--apply` / `--revert` semantics, staging→atomic-mv precedent, `.bak` sidecar. Live-applied 135→96 agents under `-maxdepth 1` scan (archive/ excluded per new policy); registered CRITICAL `adversarial-lite-reviewer` (781 tasks) + 5 v11.36 W2 drift-siblings (`archive-drift-agent`/`claude-md-drift-agent`/`docs-drift-agent`/`prevention-drift-agent`/`tracking-drift-agent`); pruned 54 speculative-project entries with no on-disk `.md`. `V11_REGISTRY_RECONCILE=off` lever. `scripts/audit-ledger-attribution` (READ-ONLY) audits the 3 attribution classes from CLAUDE.md §14.1 (agent-authored / state-transition / system-event); `hooks/lib/common.sh:v11_ledger_append` writer normalization mirrors agent-authored events with empty attribution to `~/.agent-metrics/unattributed-events.jsonl` — primary ledger write always proceeds. `V11_LEDGER_STRICT_ATTRIBUTION=off` default (advisory when on). New CLAUDE.md §14.1 documents the honest 3-class schema (state-transition + system-event events legitimately carry no actor; the true gap is smaller than the raw 6k+ count). Historical backfill deferred to v11.38 candidate #49 (28.2% honest gap in agent-authored events, not 100%). 8 ticket-body Status flips (#13/#15/#27/#32/#34/#35/#36/#37 canonicalized to the schema `check-index-body-status-consistency` will enforce). `V11_CANCELLED_FILTERS_REPLAY` doc downgrade (#43 Option B PM-locked): marked historical in ROLLBACK_REFERENCE.md + improvements/17 + improvements/24 rather than wired live — Option A (wire the lever + paired cutoff-timestamp lever) filed as v11.38 candidate #48. 5 silent levers documented (`V11_STEER_PREV_GRACE_SECS`, `V11_SPAWN_LATCH_SECS`, `V11_SESSION_LIVENESS_MINUTES`, `V11_TASKCREATE_DEDUPE`, `V11_REVIEW_CROSS_PROJECT_CHECK`). Archive/ policy + Index-body canonical schema written into `docs/DRIFT_CHECKS.md`. **W1-T6 pytest suite explicitly deferred by user at scope-lock — recorded in TaskList as pending-deferred, not lost.** Files: `scripts/reconcile-agent-registry` (new), `scripts/audit-ledger-attribution` (new), `hooks/lib/common.sh`, `v11/CLAUDE.md` §14.1 (new), `docs/ROLLBACK_REFERENCE.md`, `docs/DRIFT_CHECKS.md`, `improvements/17-*.md`, `improvements/24-*.md`, `~/.agent-registry/agents.json`, `~/CLAUDE.md`.

**W2 — Ship + wire check-\*-drift family (4/4 tasks; W2-T5 orphan resolution folded into W1-T5).** Three new drift-check siblings extend the v11.36 W2 pattern; naming precedent `V11_<NAME>_CHECK` suffix corrected from Round 1's `_DRIFT_CHECK` stacking. `scripts/check-index-body-status-consistency` — Python, umbrella-token logic, WARN on drift, FAIL on missing ticket-file or README row. Live: 14 WARN / 0 FAIL. `V11_INDEX_BODY_CHECK=off`. `scripts/check-rollback-lever-drift` — greps `${V11_[A-Z0-9_]+:-` and `os.environ.get('V11_[A-Z0-9_]+'` across `scripts/`+`hooks/`, filters test-seams + internal-state channels via EXCLUSIONS array, cross-references `docs/ROLLBACK_REFERENCE.md`. WARN silent lever; FAIL doc-lie. Live: 0 FAIL / 77 WARN. `V11_ROLLBACK_LEVER_CHECK=off`. Fixup commit c8d66be dropped an over-eager self-exclusion that missed the check's own `V11_ROLLBACK_LEVER_CHECK` env read. `scripts/check-registry-drift` — 3-way join (disk/registry/ledger), `-maxdepth 1` disk scan, FAIL when disk `.md` missing from registry, WARN on ledger-active-not-on-disk + registered-not-on-disk. Live: 0 FAIL / 183 WARN (ledger-orphan noise expected pre-backfill). `V11_REGISTRY_CHECK=off`. `scripts/handoff:1443` loop expanded from 4→8 members (adds `check-changelog-drift` rewire + 3 new siblings). New `--skip-drift-checks` bypass flag. New 1-line summary UX: `drift checks: N ran, K PASS, M WARN, F FAIL — see stderr for detail`. Per-check verbose block gated by `V11_DRIFT_VERBOSE=on` (default off). `scripts/run-tests --regression` gains 3 new blocks alongside precedent. `docs/DRIFT_CHECKS.md` updated with new siblings + archive/ policy + on-demand section (documenting `check-improve-subagent-triggers` as F2b resolution — on-demand-only, not wired — per #46-F2 orphan decision). Files: `scripts/check-index-body-status-consistency` (new), `scripts/check-rollback-lever-drift` (new), `scripts/check-registry-drift` (new), `scripts/handoff` (loop expansion + `--skip-drift-checks`), `scripts/run-tests` (3 new regression blocks), `docs/DRIFT_CHECKS.md`, `docs/ROLLBACK_REFERENCE.md`.

**W3 — SKILL.md maintenance (3/3 tasks; team-orchestrator repo commits marked TO-repo).** SKILL.md single-commit fix per swarm C5 bundle: `error-recovery.md` added to Reference Playbooks table (16→17 rows matching Playbook load triggers table), frontmatter `version: "11.34.4"` → `"11.37"`, body footer's hardcoded `**Version:** 11.34.4 "Session-Aware Write-Gate"` replaced with pointer to `v11/CLAUDE.md §17` (source of truth — reduces future 4-surface stamp drift, #39 v11.38 deferred). `scripts/v11-compliance-check` gate 3 threshold rewritten from hardcoded `-ge 13` to dynamic count from canonical `$V11_HOME/.claude/settings.json` (current: 23 refs). Router-script mappings text-only: `/v11 validate PROJECT` → explicitly names `validate-project-setup`, `/v11 tracker [PROJECT]` → explicitly names `tracker-status`, `/v11 diagnose` → marked orchestrator-side (no script backing; enumerates sessions, walks each with tracker-status + v11-compliance-check --scan). Files: `~/.claude/skills/team-orchestrator/SKILL.md` (2 commits), `scripts/v11-compliance-check`.

**CLOSE.** Ticket-body ↔ README-index reconcile (CLOSE-T1) flipped 6 tickets (#42-#47) PROPOSED→SHIPPED with commit SHAs from both repos; #38 already updated at W1-T1+W1-T2 land. This entry (CLOSE-T2) shipped `v11.37` stanza. `v11/CLAUDE.md §17` pointer bump (CLOSE-T3), `run-tests --regression-extended` post-CLOSE gate (CLOSE-T4), and 6-lens alignment review re-run as regression proof (CLOSE-T5) follow per the roadmap's explicit CLOSE chain. Handoff task (CLOSE-T6) landed as commit `a3d28f6` at the v11.36 post-CLOSE window — mtime-guard from #41 F1 protects hand-narrated handoff.md from `session-end` auto-emit clobber.

**Commit-SHA list.**
- `a3d28f6` — `fix(v11.36 post-CLOSE #41 F1): mtime-guard on scripts/handoff — preserve hand-authored handoff.md from session-end auto-emit`
- `2c20c5a` — `docs: v11-proactive-discipline post-CLOSE 6-lens alignment review — file 6 tickets (#42–#47) + amplify #38 (CRITICAL)`
- `f99bc4d` — `feat(v11.37 W1): alignment remediation W1-T1..T5 — reconciler + attribution + doc sweep`
- `a81ae98` — `docs(v11.37): file #49 review-writer 100% attribution gap + index #48/#49`
- `be32fe7` — `feat(v11.37 W2): ship + wire 3 new check-*-drift siblings — family expansion complete`
- `c8d66be` — `fix(v11.37 W2-T2): drop check-rollback-lever-drift self-exclusion (own V11_ROLLBACK_LEVER_CHECK read was missed)`
- `be21df2` — `feat(v11.37 W3-T2): v11-compliance-check gate 3 dynamic threshold`
- `c0104d4` — `docs(v11.37 CLOSE-T1): reconcile ticket-body Status + README rows for shipped scope`
- `d4c611f` (team-orchestrator repo) — `feat(v11.37 W3-T1): SKILL.md — 17-row Reference Playbooks table + version pointer`
- `5759e47` (team-orchestrator repo) — `feat(v11.37 W3-T3): SKILL.md router-script mappings for /v11 validate|tracker|diagnose`

**Tests-added.** 0 new pytest files this sprint (W1-T6 user-deferred; the 3 new W2 drift-check scripts registered as regression-tier soft-block checks in `scripts/run-tests --regression`, matching precedent from v11.36 W2's own drift-check siblings — none gained pytest suites at ship time).

**Rollback vars** (new this sprint; full detail in `docs/ROLLBACK_REFERENCE.md` § v11.37): `V11_REGISTRY_RECONCILE` (default on; `=off` no-ops the reconciler write path — `--revert` still consumes `.bak`), `V11_LEDGER_STRICT_ATTRIBUTION` (default off = advisory WARN + primary ledger write always proceeds; `=on` mirrors agent-authored events with empty attribution to `unattributed-events.jsonl`; `=advisory` intermediate), `V11_INDEX_BODY_CHECK`, `V11_ROLLBACK_LEVER_CHECK`, `V11_REGISTRY_CHECK` (each default on; `=off` no-ops that drift-check both in `scripts/handoff` loop and `scripts/run-tests --regression`), `V11_DRIFT_VERBOSE` (default off = 1-line summary; `=on` restores per-check WARN/FAIL block).

**Follow-ups (v11.38 seeds).** Ticket #39 (pre-existing v11.35.0 stamp drift across 4 surfaces — deferred as multi-root-sprint risk), #48 (V11_CANCELLED_FILTERS_REPLAY Option A wire + paired cutoff-timestamp lever, contingent on user need), #49 (review-writer 100% attribution gap; audit surfaced 209/209 review events unattributed in last 30d — orthogonal writer-side bug from the schema-honest 28.2% agent-authored gap), historical ledger-attribution backfill (28.2% honest gap in agent-authored `created` events at 18% + `review` events at 100%), reify alignment-review as `scripts/run-alignment-review PROJECT` (folded into #49 v11.38 candidate).



Root-cause-clustered fold of 6 open ticket surfaces (#05, #32, #34, #35, #36, #37) plus fold-ins (#02, #15-F3) into 3 waves: docs reachability, proactive drift catch, noise hygiene. Spec: `sessions/v11-proactive-discipline/spec.md` (Round 2, post-swarm-review — 9 material findings fixed from a first draft that reinvented shipped infrastructure and pointed at the wrong skill path).

**W1 — Reachable docs.** SKILL.md at the authoritative `~/.claude/skills/team-orchestrator/` path (NOT `v11/.claude/skills/` — Round 1's mistake) got an extraction audit (`playbooks/EXTRACTION_AUDIT.md`) that found only ~28 net extractable lines against a ≤450-line target — short of the originally-hoped ≤400/≤350, but the real reachability win is the new `## Playbook load triggers` table replacing vague "load on demand" prose at two SKILL.md sites, paired with a `## Load trigger` H2 header landed on all 17 playbook files. Roster-count drift (#32) fixed at its 4 stale "97 agents" hits in root `~/CLAUDE.md`; `~/scripts/validate-claude-md.sh` gained a `check_agent_count` step comparing the claim against `jq '.metadata.total_agents' ~/.agent-registry/agents.json`. New `v11/scripts/agent-utilization.sh` prints a used/0x table per agent from `~/.agent-metrics/`, feeding #32's follow-on demotion-queue idea. Files: `~/.claude/skills/team-orchestrator/{SKILL.md,playbooks/*.md}` (17 files, own local git repo), `~/CLAUDE.md`, `~/scripts/validate-claude-md.sh`, `v11/scripts/agent-utilization.sh` (new).

**W2 — Proactive drift catch.** Four sibling `check-*-drift` scripts extend the shipped `check-stamp-drift`/`check-changelog-drift` pattern per the spec's prior-art register — no omnibus reinvented. `check-stamp-drift` itself extended (+155 lines) with a per-project `.stamp-drift-extra.json` phase (#35 case 1, version drift across N files — reuses the existing `V11_STAMP_DRIFT` lever, no new one). New `check-class-included` (#35 case 2, a referenced class/import with no matching `#Include`/import line — its FAIL is the only one of the four that can block a spawn). New `check-git-tasklist-alignment` (#35 case 3, git-modified files not tied to a completed task's `metadata.artifacts` — WARN-only by design, never FAILs). New `check-hotkey-sync` (#35 case 4, a hotkey present on one configured surface but missing from another — WARN-only). All four wired into `scripts/handoff`'s existing `handoff-discipline-check` call site (not a new call site) and registered into `scripts/run-tests --regression` (+62 lines) alongside the pre-existing stamp/changelog checks. New canonical index `docs/DRIFT_CHECKS.md`. Separately, `hooks/sync-tasks` (#36-F1) gained **Strategy 1.7** — CWD-inside-`$SESSIONS_ROOT/{project}/` project resolution, running after every task/session/ledger-identity strategy and before the ambient active-project-file fallback — and downgraded the two successful-fallback WARN sites to INFO (the genuine all-strategies-failed WARN is untouched). #15-F3 was scope-checked for fold-in (W2-T12) and explicitly DEFERRED: it's a different mechanism (gating/authorization attribution cutting across `common.sh`/`track-autonomy`/`guard-write-gates`, not `sync-tasks`) with its own unresolved design question — carried to a future sprint, ticket body updated with the deferral rationale. Files: `scripts/check-stamp-drift`, `scripts/check-class-included` (new), `scripts/check-git-tasklist-alignment` (new), `scripts/check-hotkey-sync` (new), `scripts/handoff`, `scripts/run-tests`, `hooks/sync-tasks`, `docs/DRIFT_CHECKS.md` (new), `docs/ROLLBACK_REFERENCE.md`, `v11/CLAUDE.md` §4, `improvements/15-session-scoped-project-resolution.md`.

**W3 — Noise hygiene.** `~/.claude/skills/team-orchestrator/playbooks/orchestrate.md` spawn-template audit (+55 lines) found zero pre-existing `notify_when_idle: true` occurrences in any template (nothing to strip); added a new `## Idle notification hygiene` section citing #29's outbox contract (SHIPPED v11.35.6) as the reason bounded query-return spawns don't need idle notification, plus a real `V11_SPAWN_NOTIFY_ON_IDLE=on|off` lever (default off = quiet) gating the orchestrator's own `SendMessage(notify_when_idle=...)` default — replacing Round 1's `V11_PEER_IDLE_SUPPRESS`, a doc-only marker that gated nothing. Note: this lever has no effect on `Agent()`-tool background-spawn idle-completion events, which the harness fires unconditionally with no per-call gate to suppress. `v11/CLAUDE.md` §7 gained the active-work discriminator sub-bullet (in_progress task + recent Edit/Write on `metadata.files_touched`/`artifacts` + a TaskUpdate within the last ~20 calls ⇒ confirmed-spurious reminder, skip silently, never create make-work tasks to satisfy it). New memory `feedback_reminder_active_work_noise.md` (W3-T5) codifies the same rule for future sessions. #02's `V11_SPAWN_CHECK` hook fold-in (W3-T6) was scope-checked and DEFERRED (needs actual spawn-time enforcement code, out of scope this sprint) — its doc-only tool-surface checklist was already shipped pre-sprint, so W3-T6 added a cross-reference pointer in `orchestrate.md` instead of duplicating it. Files: `~/.claude/skills/team-orchestrator/playbooks/orchestrate.md`, `v11/CLAUDE.md` §7, `~/.claude/projects/-home-hercules-v11/memory/feedback_reminder_active_work_noise.md` (new), `improvements/02-agent-type-tool-matching.md`.

**CLOSE.** Ticket-body ↔ README-index reconcile (CLOSE-T1) marked #05/#32/#34/#35/#36/#37 SHIPPED v11.36 and fixed 6 stale `Status: open/PROPOSED` bodies (#07/#28/#29/#30/#31/#33) against an already-SHIPPED index; filed follow-up ticket #38 (registry-vs-ledger roster gap) mid-review. This entry (CLOSE-T2) bumps `v11/CLAUDE.md` §17's pointer below. Feedback-rule-obviation proof (CLOSE-T3) and full regression (CLOSE-T4) follow per the roadmap's explicit CLOSE blockedBy chain (T1→T2→T3→T4→T5→T6).

**Commit-SHA list.** Two commits carry the sprint's work:
- `d7dccef` — `docs: §4 metadata.project auto-default note + §7 active-work discriminator (v11.36 W2-T11+W3-T4)` — first-pass CLAUDE.md edits
- `ef5628d` — `feat(v11.36): proactive-discipline sprint — drift-check family + reachable docs + noise hygiene` — the consolidating commit (this CHANGELOG entry itself is part of ef5628d; the paragraph originally noted "uncommitted" state was authored in-race with the consolidating commit and superseded by it)
- `3f6cc82` (team-orchestrator skill repo) — `feat(v11.36 W1+W3): SKILL.md extraction + playbook load-triggers table + orchestrate.md hygiene`

CLOSE-T5 adversarial-reviewer's meta-observation: the initial "uncommitted" claim is a textbook example of the drift class this sprint aims to catch — a doc line written before its own commit landed. Corrected in-place at CLOSE-T5 remediation. No check currently verifies a CHANGELOG's own git-state claims against actual git state at read time; filed as an observation in `sessions/v11-proactive-discipline/retro-notes.md` for a future check-*-drift sibling.

**Tests-added.** 0 new pytest files this sprint (best-effort count via `git diff --stat -- tests/`, which shows only the auto-generated `.last-run-metrics.json`). W2's four drift-check scripts are registered as regression-tier soft-block checks directly in `scripts/run-tests`, matching the pre-existing `check-stamp-drift`/`check-changelog-drift` sibling pattern (also not independently unit-tested) rather than gaining their own pytest suites.

Rollback vars (all new this sprint; full detail in `docs/ROLLBACK_REFERENCE.md` § v11.36): `V11_TASK_PROJECT_AUTODEFAULT` (default on — Strategy 1.7 + WARN→INFO downgrade; `=off` restores pre-v11.36 `sync-tasks` behavior), `V11_SPAWN_NOTIFY_ON_IDLE` (default off — quiet spawns; `=on` reverts to the pre-sprint noisy idle-subscription default), `V11_CLASS_INCLUDED_CHECK`, `V11_GIT_TASKLIST_CHECK`, `V11_HOTKEY_SYNC_CHECK` (each default on, `=off` no-ops that check, all three advisory-WARN-only except `check-class-included`'s FAIL path). `V11_STAMP_DRIFT` (pre-existing v11.32-era lever) now ALSO gates the new per-project `.stamp-drift-extra.json` phase — no separate lever was introduced for the extension. **Known residual**: `check-stamp-drift` still reports DRIFT (exit 1) after this entry's own CLAUDE.md §17 bump, because 3 further surfaces — `agents/V11_AGENT_REGISTRY.json` (`metadata.version` + `agents[*].version`), `README.md` (Current Version), and `VERSION.md` (newest section heading) — are stuck at stale `11.35.0`, a pre-existing gap that predates this sprint (never bumped across the v11.35.1–v11.35.6 patch line) and sits outside CLOSE-T2's file scope. Filing as a follow-up is recommended; `CLOSE-T4`'s `run-tests --regression-extended` will soft-block on this until it's fixed.

Follow-ups: ticket #38 (registry-vs-ledger reconcile, filed during W1-Rev), the pre-existing `agents/V11_AGENT_REGISTRY.json`/`README.md`/`VERSION.md` stamp-drift residual noted above, and the wire-check-changelog-drift-into-handoff v11.37 candidate noted in `docs/DRIFT_CHECKS.md` remain open for a future sprint.

### v11.36 post-CLOSE follow-up — ticket #41 F1 (mtime-guard on `scripts/handoff`) — 2026-08-28

Ticket #41 was authored during CLOSE-T6 when the orchestrator's hand-narrated `handoff.md` was silently clobbered by the `session-end` auto-emit path — the exact drift class this sprint targets, surfacing inside the sprint's own deliverable. F1 ships the ~15-LOC guard the ticket recommends. `scripts/handoff` now refuses to regenerate `handoff.md` when its mtime is newer than the trigger basis (`.session-summary.md`, falling back to `STATE_FILE`) and a new `--force` flag is absent. The unattended `session-end` auto-emit path (`hooks/session-end:281-285`) omits `--force` and is therefore protected; the `/handoff` skill (`~/.claude/skills/handoff/SKILL.md` Step 3 + Step 6) passes `--force` implicitly because the user is in the loop. Content-hash fallback: if `.session-summary.md` still carries the V11.17 stub fingerprint, the guard does not fire (nothing worth preserving). New test suite `tests/test_handoff_mtime_guard.py` (6 tests, all pass — skip / --force / rollback lever / absent-file / stub-summary fallback / summary-newer-than-handoff regen). Rollback: `V11_HANDOFF_MTIME_GUARD=off`. Files: `scripts/handoff` (guard + `--force` + `--help`), `tests/test_handoff_mtime_guard.py` (new), `docs/ROLLBACK_REFERENCE.md`, `~/.claude/skills/handoff/SKILL.md`, `improvements/41-auto-handoff-clobbers-hand-written.md`, `improvements/README.md`.

## v11.35.6 — Wave-Based Improvement Session — 2026-08-20

Root-cause-clustered wave remediation of improvements #26-33 + residuals from shipped tickets #02/#15/#17/#24. Nine open tickets collapsed into 5 root causes (RC1-RC5), executed across 5 waves (W0-W4) in a single session.

**W0 — Triage + documentation.** 8 new tickets (26-33) filed with full Problem/Evidence/Proposed/Risk/Rollback/Acceptance structure. README index corrected: #03→SHIPPED (scout-verified), #17-F2→SUBSUMED (v11.27 ADR fold). #05 evidence addendum: independently re-confirmed in a 14-agent session — orchestrator skill now 472 lines core + 17 playbooks/4,328 lines, ~20% load-bearing. Serial test measurement for stale timeout budget (#11/W4-2).

**W1 — Spawn-contract prose (team-orchestrator skill repo).** 6 mis-typed agent spawns fixed across `playbooks/swarm-review.md` (5 agents: `adversarial-reviewer`/`Explore` → `general-purpose` — these agents Write JSON output files, which requires the Write tool) and `playbooks/journal.md` (1 retro agent: `Explore` → `general-purpose`). Root cause of #04's dead flywheel: Write-disabled agents ordered to produce files. New: outbox contract (`~/.agent-metrics/outbox/$PROJECT/{agent}.md`) in `playbooks/orchestrate.md` (protocol step 5 + Rule 10); tool-surface matrix §4d; idle-event triage table in `playbooks/monitor.md` §5f (replaces suppression with 4-row diagnosis); `read_at`+`files_read` freshness fields in all 4 pinpoint schema copies in `playbooks/context-tiered-mode.md`; dual-delivery reword (disk=durable, message=fast path); freshness carve-out from DO-NOT-re-search clauses; pre-spawn checklist (tool-surface + outbox delivery). Closes: **#02** (partial — 6 spawns + matrix; V11_SPAWN_CHECK hook deferred to W4), **#28**, **#29**, **#31**.

**W2 — Ledger integrity + project binding.** **15-F2** owner-stamped active-project binding: global file carries owning session UUID on line 2; Tier-2 reader checks `v11_session_is_live` on the owner — if a different live session owns the file, returns empty instead of adopting the foreign binding; `v11-bootstrap-session` fixed to `head -n 1` (T12); `V11_ACTIVE_PROJECT_OWNER=off` rollback. **17-F3** production-shape regression guard: `test_cancelled_without_subject_norm_still_excluded` — creates cancelled events WITHOUT `subject_norm` (the actual production shape that broke #17's fix), validates exclusion via `sess_task_index` identity fallback (#24 lesson: test production shapes, not helper shapes). **15-F4** project-name character allowlist: `sync-tasks` rejects `metadata.project` values with disallowed characters (`^[a-zA-Z0-9._-]{1,128}$`); same validation in `scripts/scaffold`; `V11_PROJECT_NAME_GUARD=on` rollback. **15-F5** `audit-query --stats` null-project counter: surfaces null/empty-project entries as `(null/empty project: N / TOTAL)`.

**W3 — Handoff honesty.** Provenance-gated counter display (#30): `scripts/handoff` compares `V11_SESSION_ID` vs `SOURCE_SESSION_UUID` — when they differ (counters from a prior session), emits a warning in the handoff prompt instead of presenting stale numbers as current. `V11_HANDOFF_STRICT=off` rollback. Args-aware mandates (#33): `SKILL.md` Steps 3.5 and 5 reworded from "MANDATORY ask" to "MUST HAVE an answer, not MUST ASK the question" — 3 resolution paths (explicit arg, inferred from context, ask). Closes: **#30**, **#33**.

**W4 — Worktree + spawn verification.** Stale-ref advisory (#27): `guard-worktree-isolation` records `HEAD` at spawn time (`head_at_spawn` in registry), compares against current HEAD at reconciliation, emits advisory when they differ. W4-1 (v11-spawn-check hook) deferred — depends on W1 corpus settling. Closes: **#27**.

**W5 — Handoff safety.** EXIT trap installed before steer consume catches orphaned `.tmp.PID` files on abort (323 observed half-handoff orphans). `.bak` retention capped at 5 newest per project (was unbounded — 2,616 files observed). `v11-drift-scan` glob pattern fixed to match `*.tmp.*` and `*.bak.*` (the actual file patterns) in addition to `*.tmp`/`*.bak`. Steer-restore contract preserved (improvements/23 test green). **Staging pattern**: handoff.md now writes to `$HANDOFF_FILE.staging.$$` instead of directly to `$HANDOFF_FILE`; the staging file is promoted to final only after handoff-tasks.json emit + pending reconcile both succeed — aborts during emit no longer leave handoff.md shipped without its companion task file, killing the half-handoff class. Schema v2 deferred. Closes: **#01** (partial — staging pattern shipped, schema v2 remaining).

Rollback vars: `V11_HANDOFF_STRICT`, `V11_PROJECT_NAME_GUARD`, `V11_ACTIVE_PROJECT_OWNER`, `V11_ATTRIBUTE_BY_PATH` (all added to `docs/ROLLBACK_REFERENCE.md`). Commits: ea2ed75, 822969a, 107e74c, aebac27, 8d343e2, 4c6a153, 4aaac9f, b26e08e, 72b39fc, 1cbd9de, 9bf738c, 8e2bc78.

## v11.35.5 — Context Audit — 2026-08-18

Context-economy pass from a multi-agent audit session. Boot token budget reduced ~65k→~41k by relocating verbose hook tables and ear-gate contract detail out of CLAUDE.md into docs/ (still loadable on demand). **guard-fat-read** advisory hook: warns on heavy Reads (images >100KB, text >50KB) to route payload to a subagent sidecar so it dies with the sidecar's context, not the orchestrator's. `V11_FAT_READ_ADVISORY=off` rollback. Adversarial-lite-reviewer frontmatter `description` fields capped to routing-relevant content (trim ceremony, keep triggers). Commits: a44ac9c, 8d87b78, 13af0bd, 288f15b, e08b1cf.

## v11.35 — Improvements Triage Line — 2026-08-02 → 2026-08-06

Consolidated entry for the 2026-08 improvements-triage sessions (this entry was written 2026-08-06, retroactively covering the 2026-08-02 ships that landed without a changelog entry — the "Current" pointer had silently stayed at v11.34).

**v11.35 (2026-08-02):** improvement **#16** artifact-on-complete advisory + status consumer (ebdb84c, pinned 729ec80) · **#17** `cancelled` ledger events get a terminal-status fold branch + open-view exclusion, rollback `V11_CANCELLED_FILTERS_REPLAY=off` (a54550c) · **#18 + #12/M1** `open_tasks` flat view re-keyed from `dict[task_id]` to a list of self-describing records, fixing cross-session task_id collisions (efc42ad) · **#12/H1** worktree-isolation silent no-op safety net — `guard-worktree-isolation` hook (3c175bb) · **#12/H2+M2** scoped reviewer/executor self-report tool (8bb1272).

**v11.35.1 (2026-08-02):** session-scoped context tracker + improvements/15 F1 second bypass writer (137c0fb).

**v11.35.2 (2026-08-06) — improvement #24: #17's fix verified broken in production, root-caused, re-fixed.** HAM field report proved the shipped cancelled-event exclusion never held against real data. Root cause was three stacked gaps, none in #17's fold branch itself: (1) **writer gap** — no sanctioned cancel emitter exists; all production `cancelled` events were hand-appended without `subject_norm`, and the fold keys by `idk() = (project, subject_norm, create_seq)`, so they landed on a phantom record; (2) **reader gap** — the `review` branch had an unresolved-identity fallback (E1), normal status events had none; (3) **test gap** — the test helper requires `subject_norm`, making the production shape untestable by construction (tests green, production broken). A 4th gap surfaced mid-fix: the corrected replay legitimately shrank HAM's total 367→366 (phantom removed) and the cutover REGRESSION-GUARD blocked it as an apparent regression. Shipped: **F1** `sess_task_index` `(session_uuid, task_id) → idk-key` fallback in `v11_replay_ledger` (fires only when `subject_norm` is absent; heals historical data on every replay for any identity with ≥1 well-formed precedent event — precedent-less identities keep legacy phantom behavior) · **F2** `V11_CUTOVER_ACCEPT_CORRECTION=on` explicit per-invocation logged guard escape (`reason:"correction-authorized"`, default off) · **F3** `scripts/task-cancel` sanctioned writer (resolves identity from the `created` event, appends via `v11_ledger_append`) · **F4** `TestIdentityFallbackSubjectNormless` 4 production-shaped tests, suite 52/52. Acceptance verified live on HAM (open_tasks/active_task_ids/active_task clean, zero hand-patching). Platform sweep: HAM was the only ledger with identity-less status events; 37 active drifted aggregates rebuilt (29 cutover clean, 8 correctly held on legacy by the guard). Full narrative: `improvements/24-cancelled-replay-fix-verified-broken-in-production.md`.

**v11.35.3 (2026-08-06) — backlog clearance (#20-23) + #24 adversarial remediation.** Same-day adversarial review of the v11.35.2 fix returned 5 findings (1 reproduced-HIGH): the fallback index was last-write-wins, so same-session task_id reuse (production-real: HAM `bd617d7c`) could land an ambiguous cancel on the WRONG task → sticky `_IDK_AMBIGUOUS` sentinel, refuse-on-ambiguity (fail-closed to phantom), closest-preceding semantics before the second claimant; `V11_CUTOVER_ACCEPT_CORRECTION` re-scoped from `=on` to `=<project-name>` (a leaked blanket flag can never authorize a different project; deliberately bypasses BOTH count floors for the named project only); identity-bearing reconciles now populate the index; the active_task reverse walk shares the resolve helper; one pre-existing residual documented (within-session `open_tasks_by_session` t_id collision — display-only, truth unaffected). Fold suite 54/54. **#23 (HIGH)**: `scripts/handoff` — 4 scalable `--argjson` → `--slurpfile` (the E2BIG exit-126 class on large aggregates) + EXIT trap restoring the consumed steer sidecar on nonzero exit; live-verified on example-project's real 115-task aggregate with fold ENABLED (exit 0, manifest 115→108); `tests/test_handoff_argmax.py`, 203/203 handoff tests. **#20**: path-context risk downgrade — `rm -rf` strictly inside the session scratchpad drops HIGH→LOW (absolute literal paths only, whole-command reject on any metachar, fail-closed in every direction, worktree class deferred), `V11_RISK_PATH_CONTEXT=off`, `tests/test_risk_path_context.py` 8/8. **#21**: Live-Ops Express Lane in the team-orchestrator skill (safety-critical DETECT reads only; backstop/dashboard/retro defer to CLOSE as compliance; one mission task `metadata.scope:"mission"`; `V11_LIVE_OPS_LANE` prompt lever). **#22**: `playbooks/monitor.md` §External process monitoring (two-plane monitors, terminal-state filter coverage, serving-side-first stall protocol, teardown discipline). Skill-repo commit a0ca655; v11 commits 60208df + 51bda47.

**v11.35.4 (2026-08-06) — improvement #25: structure-aware risk classification.** The gate that blocked v11.35.3's own commit (its message DESCRIBED the recursive-delete pattern) now masks inert text payloads before re-testing a would-be-HIGH hit: executor token present → no masking; heredoc bodies stripped by line-anchored terminator; quoted spans only when provably well-paired; every doubt bails to raw. Zero cost unless the raw string already matched HIGH. Pre-existing executor-quoted blind spot (`bash -c 'rm ...'` was always low) pinned by test, not changed. Rollback `V11_RISK_TEXT_MASK=off`; `tests/test_risk_text_mask.py` 10/10. Incident appendix: the first draft used an inline ERE with parens in a char class, which the `[[ ]]` tokenizer rejects — every hook sources common.sh, so ALL tools bricked for ~10 min; recovered via the user-run `!` bash-passthrough (now documented as the sanctioned brick-recovery path). Inline-ERE-in-variable rule encoded at the crash site.


## v11.34 — Session-Aware Write-Gate — 2026-07-20

Closes `improvements/13-write-gate-session-aware.md` (field report, session `comedic-study` + 4-agent recon swarm) and absorbs `improvements/12-spawn-contract-gaps.md` §H2. Root cause: `guard-write-gates` blocked the first honest edit of a fresh session in a task-bearing project — a session that never touched the task system reads identically to a genuine stall, so the gate punished the standard "spawn/handoff into a project that already has tasks from another session" path. The blocked actor structurally could not satisfy the gate (its remedy is session-scoped; the gate's signal is project-scoped), so it routed around it — via Bash-heredoc (this field report) or by editing the task-state JSON to pass and reverting it (the improvement-12 incident). Both escape hatches were ungated and audit-invisible.

**F1 — Fresh-vs-stall discriminator**: `guard-write-gates` now distinguishes a session that has never engaged the task system (no per-session task-state file) from a genuine stall (a session that HAD a task in_progress and let all its tasks lapse). Fresh sessions — and sessions that have *finished* all their own work — are **allowed through** with a once-per-session stderr advisory naming the open-task count (from the project aggregate) and the remedy. Only a session carrying its own unfinished work (`pending + in_progress ≥ 1`) still `exit 2` under the default. This also subsumes improvement-12 §H2: a subagent's session likewise carries no per-session task-state, so it now reads as fresh (advisory) instead of unsatisfiable (block) — the tampering incentive it created is closed at the root, not patched at the symptom.

**F3 — `V11_WRITE_GATE` knob**: `block` (default, unchanged stall behavior) | `warn` (downgrades the stall block to advisory, never exits 2) | `off` (disables task-state enforcement entirely). The `total<2` and completed-project exemptions are unconditional either way.

**F4 — Observable Bash-write bypass**: `guard-enforcement` now emits a non-blocking stderr warning when a Bash command performs a source-file write (heredoc `<<`, `>`/`>>` redirect, `tee`, `sed -i`, `dd of=`) in a task-bearing project, plus a best-effort synthetic audit row for attribution. This closes a previously-silent, undocumented bypass of the Write/Edit audit trail (verify-syntax, attribution) — the escape hatch the field-report incident actually used. Gated by `V11_BASH_WRITE_WARN` (default on); disabling only silences the warning, it was never a block.

**Doc coherence (F5)**: `docs/ENFORCEMENT.md`, `CLAUDE.md` §13, `docs/PROTOCOL_FUNDAMENTALS.md`, `docs/AGENT_TEAMS.md` (deleted a dead V11.11-era ownership-block claim), `docs/ROLLBACK_REFERENCE.md`, and the `improvements/` index corrected to describe the shipped fresh-vs-stall behavior instead of the old flat "advisory" or "blocks ownership" mislabels.

Commits: 6c32e29 (F1+F2+F3), 7afd3fa (merge), 914ccd4 (F4), 814280b (merge), 030ba87 (spec). Rollback: `V11_WRITE_GATE=warn|off`, `V11_BASH_WRITE_WARN=off`.

**v11.34.1 — same-day post-ship review remediation.** Three adversarial reviewers (hook correctness, consumer-surface coherence, orchestrator workflow integration) audited the merge. Fixed: **Q2** (finished-wave false block — the discriminator keyed on "ever touched a task" so a session that *completed* all its own tasks re-hit the stall block whenever sibling sessions had pending work; now keys on the session's own open work `pending+in_progress≥1` via `v11_session_has_open_work`), **Q4** (fresh advisory throttled to once-per-session), **Q3** (open-task count read from the aggregate, not `handoff-tasks.json`; remedy leads with "create+start a task", `/v11` made conditional), **Q5** (F4 narrowed — dropped the command-substitution heredoc match that false-warned on `git commit -m "$(cat <<EOF)"` / `gh pr create`, and exempted `v11_is_metadata_file` targets + atomic `.tmp` writes). Commits bd1c1d5, ccaab60; verify fixtures 9/9 + 14/14, regression 17/17. **Known limitation (deferred → improvement 14):** *multi-session aggregate masking/misattribution* is pre-existing and unfixed — because `guard-write-gates` and `track-autonomy` read the project aggregate, a sibling session's `in_progress` masks the gate for every other session AND mis-stamps their edits onto the sibling's `task_id`/`agent_id` (counted against an innocent agent by `agent-scorecard`). Needs a session-scoped gate+attribution signal. "v11.34 shipped" ≠ "multi-session attribution is trustworthy."

**v11.34.2 — session-scoped write-gate + attribution (improvement 14).** Resolves the T4 limitation above. `guard-write-gates` now reads THIS session's own `.in_progress` for the block decision instead of the project aggregate (`guard-write-gates:136` → `v11_session_state_path`), so a sibling session's active task no longer masks a genuine stall for everyone else. `track-autonomy` now attributes an edit to the session's OWN active task/agent (`track-autonomy:207` → session file), falling back to `null` — a sibling's `task_id`/`agent_id` is never borrowed, so `agent-scorecard` stops blaming the wrong agent. Single-session behavior is unchanged (aggregate ≡ session when there's one session); the only new blocking is a session neglecting *its own* created-but-unstarted tasks (satisfiable). Downstream (`agent-scorecard` keys on `agent_id`, `audit-query` treats `task_id` as an honest denominator) verified compatible with null attribution. Commits 48f6436 (F1), 107388a (F2), 6b81f1e (spec); verify fixtures 12/12 + 3/3, regression 17/17. No stamp sweep (patch keeps anchor 11.34).

## v11.33 — Lossless Sync Fallback + Test-Isolation Hardening — 2026-07-17

Closes the sync-tasks silent lost-update gap (found via adversarial audit session v11-active-project-drift; BugG root-cause). On >`V11_SYNC_TASKS_LOCK_TIMEOUT` (default 10s) FD-201 contention, sync-tasks proceeded unserialized and a concurrent same-session completion write could be silently dropped from the per-session scratch (reproduced: 4 racers → completed=3, one task stuck in_progress). The durable ledger was never lossy (own FD-207 lock); only the scratch — which `scripts/handoff` reads — drifted. **Fix (design (c)+(d)-lite, adversarially reviewed, 4 findings remediated)**: (d)-lite narrows the FD-201 hold to end at the last STATE write (release before the aggregate rebuild; `V11_SYNC_NARROW_HOLD=off`); (c) raced writers append a marker line (subject capped 500ch, O_APPEND-atomic) + artifacts to per-task atomic sidecars, drained exactly-once by the next locked call AND by session-end (backstop for a race on the session's last TaskUpdate) via `v11_apply_reconcile_markers`; replays the V11.21 sibling `pending_parent→pending` flip and `task_artifacts`; STR advisory counter is a documented accepted loss (`V11_SYNC_SCRATCH_RECONCILE=off`); `scripts/handoff` prefers the ledger-derived aggregate when a `.needs-reconcile` marker is present. Commits: dbda947 (fix), 535ba83 (test-isolation sweep: 26-module HOME-leak fix + conftest real-plans-dir leak detector + xdist timeout hardening), e3994cd (track-autonomy rotation keep-count byte-derived — was rotating on every hook call, 13,876 micro-archives). Tests: +17 incl. genuinely-concurrent race tests with deterministic readiness barriers (holder-acquired + all-racers-in-fallback confirmed before release; no sleep-tuning). Full suite green.

## v11.32 — Half-Wired Loop Audit — 2026-07-15

Closes improvements/11 (5-lane audit, 3-agent interference review, waves risk-ordered by activation risk). **H1**: git-event hooks layer (v11.25) activated for the FIRST time anywhere — installer names corrected in docs (W0-1), scaffold git-inits + auto-installs both hooks with compliance Gate 15 (W2-5), canary install caught 2 latent BASH_SOURCE symlink bugs (W2-4b) and review-drain caught a third (installers now resolve `--git-common-dir` so worktree installs land where git reads hooks). Existing-project backfill stays user-triggered. **H2**: routing fields get their first reader — `agent-scorecard --routing` override-rate rollup (79.3% divergence surfaced; completion-row double-count fixed in drain). **H3**: guard-effort revived (`Task|Agent` matcher — dead since the Agent rename) + tab-collapse field misalignment fixed with per-field jq reads (W3-3). **H4**: review-queue-maintenance gains flock across read-backup-rewrite (W2-1) and is wired into the review-cadence wrapper after the daemon (W2-2) — queue GC finally scheduled. **H5**: `V11_AUTO_REHYDRATE` code-enforced in `scripts/v11-resume-tasks` (was doc-only 6×). **M1**: `scripts/ledger-verify` cold-path verdict-hash verification (36/36 OK live; never in the replay fold). **M2**: auto-pair review siblings stamped `scope:"small"` — criterion #3 pair_N pollution closed (re-measured live post-boot: PASS). **M3**: two-tier regression — `--regression` = deterministic fast core (17 tests, <30s), `--regression-extended` = full suite (`-m "not benchmark"`, ~2,500 tests); first-ever full run surfaced 24 pre-existing slow-tier failures (all outside the default tier) → W4-1 triage. **M4/M5/L1/L2**: prompt-level levers labeled honestly, ledger-archive + review-queue-maintenance in SCRIPTS.md, unattributed-findings count in `scripts/status`, backfill tool header note.

## v11.31 — Pre-Scope Actuation + Two-Source Token Capture — 2026-07-15

Closes the dead v11.29 pre-scope loop end-to-end. Spec: `improvements/10-prescope-actuation.md` (21 tasks, session v11-prescope-alignment).

**Honest detection (S1-A1/A2)**: sync-tasks warns on missing/invalid `metadata.scope` on work tasks (review-sibling/blocker exempt; `V11_SCOPE_WARN=off`) and on multi-deliverable description smells — conjunction / 3+ runbook steps / >600 chars non-small (`V11_PRESCOPE_SMELL=off`). Kills the self-labeling dependency: before this, only 13% of tasks carried scope and the v11.29 advisory had never fired in production.

**Visible signal (S1-B1/B2)**: fired advisories emit a PostToolUse `hookSpecificOutput.additionalContext` envelope — the orchestrator model now SEES them in the TaskCreate tool result (`V11_PRESCOPE_CONTEXT=off`; dogfood-verified live in the shipping session). Each firing also lands as a status-neutral `ev:prescope` durable-ledger row with reason code, plus a replay fold branch preventing counter inflation (`V11_PRESCOPE_LEDGER=off`).

**Dispatch consumption (S1-C1/C2/C3)**: new read-only `scripts/prescope-check PROJECT [TASK_ID]` (exit 11 = split-before-spawn, replicates the S1-A1 exemption asymmetry), wired into orchestrate.md Phase 4 dispatch filter + task-patterns.md; `scripts/status` gains `Pre-scope: X% scoped, N advisories open` (`V11_PRESCOPE_STATUS=off`).

**Two-source token capture (S1-D1..D7)**: root cause of the inert v11.29 token ledger — track-agents probed hypothesized snake_case fields; real harness payloads are camelCase (`totalTokens`). Fixed with camelCase-first probing. Async spawns expose no usage at hook time, so the orchestrator records `artifacts.tokens` from completion-notification usage at the closing TaskUpdate (orchestrate.md §4e Rule 9); agent-scorecard merges both sources deduped by (project, task_id) with source-labeled capture rates, and `scripts/token-baseline` snapshots before/after (pre-rollout baseline: 0.22% capture, median 140k).

**Playbook alignment (S1-E1/E2)**: 4 playbook↔tooling mismatches fixed (prescope wording, agent-recommend precedence over spec.md roster, token-economy carve-out xref, TaskList carve-out); all 121 task-template example rows now carry owner/scope/complexity.

Tests: +6 advisory, +6 context/ledger, +14 scope/smell, +23 prescope-check, +11 scorecard tokens, +8 token capture; test_ledger_wiring fixtures updated for the ev:prescope era (found by a supplementary agent run — the file sits outside the run-tests manifest, gap noted). Known deferred: scope-adoption ≥90% measurement (criterion #3) next session; run-tests manifest backfill.

## v11.30 — Review-Loop Structural: Layer A Actuation + Verdict Fold-Back — 2026-07-11

W5 of `improvements/07-v1129-alignment.md` (specs: `improvements/08`, `improvements/09`) + production-readiness swarm fixes.

**Layer A actuation (W5-T15)**: self_review absence is now actuated, not just nudged — completion-hint suggests the self_review postamble; sync-tasks appends a synthetic `missing_self_review` `lite_self` row (LOW) on reviewable completion without one, symmetric with the malformed-payload guard. Rollback: `V11_SELF_REVIEW_ACTUATE=off` (independent of `V11_SELF_REVIEW_NUDGE` — gates de-nested in prod-fix). KEY FIND: the V11.22 reviewable gate had never fired (post-fold STATE read + tab-collapse in TSV join) — both latent bugs fixed; Layer A "compliance near-zero" was largely instrumentation that couldn't see.

**Cross-session verdict fold-back (W5-T16)**: drained review verdicts land in the durable ledger as `ev:"review"` events (status-neutral, counters-free replay) with full verdict JSON in `~/.agent-metrics/review-verdicts/{project}/` (sha-addressed, `verdict_ref`/`verdict_sha` on the queue done event). New CLI: `review-queue mark-done PROJECT TASK_ID [SEV] [SESSION] [--verdict-file FILE]`. Identity recovery for prior-session/wiped tasks via ledger scan; `identity_unresolved` flag beats dropping. Rollback: `V11_REVIEW_LEDGER=off`. Validated in production the same session by a live mid-session TaskList wipe: all 5 verdicts folded with zero loss.

**v11-coherence skill (W5-T17)**: L6 ledger gate keys on V11 markers (spec.md/.task-state.json) not dir mtime (kills 46 false LEDGER_MISSING); dual-lens reliability note (single-scanner clean bills are not clean bills).

**Production-readiness swarm (5 lenses) found + fixed**: case-sensitive severity derivation in `--verdict-file` (lowercase "critical" recorded as NONE — INV-3 poison); `V11_SELF_REVIEW_ACTUATE` nested inside NUDGE gate; phantom `ev:review` records inflating counters via realign; verdict-store same-second filename collisions; `check-stamp-drift` anchor polluted by merge-commit subjects (`--no-merges`); replay keying collision for identity-unresolved reviews; silent CLI exit on dangling `--verdict-file`.

Known deferred: fold-back data is write-only in the replay aggregate (nothing projects `last_review_*` into dashboards yet) — follow-up noted in `improvements/09`.

## v11.29 — Concurrency Lanes, Pre-Scoped Tasks, Token Ledger, Worktree Default — 2026-07-10

Closes the 4 gaps from the 2026-07-10 operator review + user notes. Spec: `sessions/v11-improvements/spec.md`.

**Lane lease** (concurrent-session task-execution guard, mirrors review-queue ownership):
- `v11_lane_claim/release/force_release/gc/status` in `hooks/lib/common.sh` — store `~/.agent-metrics/lanes/<project>.jsonl`, flock fd 209, append-only, steal only from not-live holders. Rollback: `V11_LANE_LEASE=off`.
- sync-tasks auto-claims on `TaskUpdate(in_progress)` with "LANE CONFLICT" stderr advisory (never blocks), releases on `completed`.
- `scripts/lanes` CLI (status/gc/release [--force]) + Phase 4 dispatch-filter clause + dashboard "Lanes:" line (orchestrator skill).

**Pre-scoped tasks**: decomposition moved from spawn time to TaskCreate (skill rule 21 rewritten; task-patterns §Pre-scoping discipline); sync-tasks advisory fires on `metadata.scope=large` or complex/novel without `metadata.deliverable_of`. Rollback: `V11_PRESCOPE_ADVISORY=off`.

**Token ledger**: `dispatch-trace-append --tokens/--tool-uses/--duration-ms/--event completion`; track-agents defensive usage passthrough to usage.jsonl (never fabricates); avg-tokens/spawn column in agent-effectiveness + agent-scorecard (omit-when-absent). Rollback: `V11_TOKEN_CAPTURE=off`. Lean-agent spike: `spec-implementer-v11-lean` (~68% token cut/spawn, contract-parity checked; rollout pending user decision).

**Worktree default**: editing spawns default to `isolation:"worktree"` (skill rule 20 + orchestrate + context-tiered-mode); guard rails first — `scripts/worktree-sweep` (dry-run/--apply sweep + `verify` exit-code contract 0=CLEAN_MERGED/10=UNCOMMITTED/11=UNMERGED/12=GENERATED_ONLY/2=UNKNOWN), CLOSE-checklist sweep step, gotcha docs (silent-edit-loss, Task-tool cwd quirks, main-tree diff checks). Rollback: `V11_WORKTREE_DEFAULT=off` (docs-level policy).

**Bug fixes** (scout-found, pre-existing): session liveness misjudged sessions writing only to subdirs (`.heartbeat` touch in sync-tasks); review-queue GC default now derived as 2× liveness window (was silently divergent 15/30); 4 worktrees leaked since 2026-07-01 cleaned; untracked-dirs porcelain bug in sweep classification; lint-test-honesty P1 in lane test.

Tests: ~90 new across 8 suites; full regression 20/20 + drift + honesty-lint green. Dual live validation: real token traces captured for this sprint's own spawns; lane machinery exercised by the concurrent sessions that built it.

## Backfilled from CLAUDE.md §17 (v11.24–v11.28) — 2026-07-01

## v11.28 — Handoff Steering Prompt

Closes the longest-standing handoff gap: the orchestrator could never put a single word into the *first message* of a spawned session — the continuation prompt was 100% derived from disk state (task-state / session-summary / plan-context) and immutable once assembled, with no `--steer`/`--message`/positional/env override anywhere. Worse, `--spawn` doesn't even reuse that bash `$PROMPT`; `spawn-claude-window.py::build_bootstrap_prompt` re-reads `handoff.md` and synthesizes its own terser <1500-char bootstrap, so there are **two independent prompt-builders**. **Fix routes through the one shared artifact both read — `handoff.md`.** Two input paths: sidecar file `sessions/<project>/.handoff-steer.md` (primary — the orchestrator Writes it losslessly, no shell-quoting of multi-line text) and `--steer "TEXT"` flag (convenience); **file wins** if both, stderr warns. The steer lands in `handoff.md` between `<!-- v11-steer-start -->`/`<!-- v11-steer-end -->` markers (OUTSIDE the Quick Resume code fence so steer content can't break fence extraction), is prepended into bash `$PROMPT` (so stdout/`--copy`/`--file` manual-paste carries it too), and is extracted + placed by the python bootstrap immediately after `/v11\n\n` — `/v11` stays the leading slash-command token so auto-rehydrate still fires; the steer is the first instruction, ahead of the mechanical state pointer. **Consume-and-clear**: the sidecar is baked into `handoff.md`, archived to `.handoff-steer.md.prev`, then removed — one-shot steering never leaks into a LATER handoff (same discipline as the V11.25.1 stale-summary archive). **Safety** (the spawned window runs `--dangerously-skip-permissions`, so steer is trust-elevated): both layers strip ANSI/control bytes incl. bracketed-paste terminators (`\x1b[201~`) and neutralize the literal steer markers; capped at 2000 chars; `--json` mode exits before steer logic (safe no-op, preserves the file). **Dual-layer reviewed** (V11.21): Layer-B adversarial pass returned PASS with 1 MED + 2 LOW — E1 a crafted steer containing the literal end-marker could forge a span boundary and inject a fake `## Quick Resume`/field lines the bootstrap parser reads → strip marker literals + anchor structural-section search past the steer-end marker; E2 a steer with a fake `- Progress:` line shadowed bootstrap stats (steer lives inside the fenced `$PROMPT`) → parse fields from `rfind("## Current State")` (the REAL heading is always the LAST occurrence since steer is prepended; first-occurrence `find` was defeated by steer containing the heading); E3 a test off-by-one. All fixed + pinned with 2 new regression tests. Rollback: `V11_HANDOFF_STEER=off` (also skips file consumption). Files: `scripts/handoff`, `.claude/hooks/spawn-claude-window.py` (live host file — `~/.claude` is unversioned), `.claude/skills/handoff/SKILL.md` (live), `tests/test_handoff_steer.py` (14 tests). 14/14 steer + 78/78 handoff-cluster green, honesty-lint clean.

## v11.27 — Ledger Integrity (six half-wired loops)

Closes six half-wired control loops in the tracking substrate — where an artifact/sensor was generated, incremented, or read but the matching consume/reset/validate/write half was never built. Spec at `sessions/v11-ledger-integrity/spec.md` (impl-grade spec `pm/v11-ledger-integrity-spec.md`); recon = two waves (13 agents) + 3 adversarial lenses. **Core principle: mechanize acknowledgment, not actuation** — surface/read halves are mechanized (safe); every mutate half stays gated, propose-only, or default-off. Live confirmation at sprint start: sofly `.retro-counter == 791` (>15× the >50 flywheel-broken threshold). **(T2) Retro flywheel flock + sanity guard** — `hooks/session-end` wraps the retro read-increment-write in an fd-201 flock (200=task-state, 202=aggregate; 201 collision-free) so concurrent CLOSEs can't lose a write; `scripts/status` prints `⚠ retro flywheel likely broken` when counter>10×`V11_RETRO_THRESHOLD`. No auto-reset. Rollback `V11_RETRO_SANITY_GUARD=off`. **(T3) A4 dead-gate legibility** — `v11_check_risk` (`common.sh:1056`) auto-approves A4 high-risk only on a `high_risk_history` match, but nothing ever appends to it (`any([])==false → return 2`): a silent always-block. `track-autonomy` + `scripts/status` now warn when level≥4 and history empty. Zero behavior change. **A characterization test pins the current empty→block `return 2`** (via `v11_check_risk`, not `v11_check_autonomy` which delegates high-risk) as the deliberate landing gate for any future writer. Rollback `V11_A4_DEADGATE_WARN=off`. **(T1) S1 DETECT reconcile surface** — `hooks/detect-project` emits one read-only `v11_detect_reconcile` JSON block (zombie/discipline + review-queue + fold-families + retro-counter) consolidating four unsurfaced signals; new `v11_fold_manifest_read`/`v11_retro_counter_read` wrappers with `[ -f ]` guards. **Strictly non-mutating** — reads the existing discipline log rather than invoking the writer (adversarial-review M1 fix). Hook count stays 17 (no new hook). Opt-in `V11_DETECT_RECONCILE` (default off). **(T5) Enqueue unknown-attribution trace** — `v11_review_queue_add` admits `agent_id=="unknown"` (a legit orchestrator/bg-agent fallback), adds a `trace` field, emits a WARN — never rejects; Rules A/B unchanged. Rollback `V11_RQ_TRACE_UNKNOWN=off`. **(T6) Propose-only fold-reconcile** — new `scripts/lib/family_fold.py::propose_merge()` + `scripts/fold-reconcile` CLI: `--dry-run` default proposes a merge only when family_size>1 ∧ identical `subject_norm` ∧ identical sprint (absent-sprint families skipped — adversarial-review L1); `--apply --confirm` appends append-only `reconcile scope=identity` ledger events (SKIPPED+WARN on append failure, not silent inflation — M2). Never runs in hooks/DETECT. Rollback `--dry-run` default + `V11_FOLD_RECONCILE=off`. **(T4) CUT to a design spike** (`sessions/v11-ledger-integrity/T4-spike.md`) — an A4 history writer is not safely feasible as scoped (MATCHED_PATTERN duplication, no pre→post hook signal, unreliable `caller_kind`); spike reframes the fix as "detect blocked-then-executed" instead of "detect human." **Dual-layer reviewed** (V11.21): Layer-B adversarial pass found 2 MED + 1 LOW, all fixed and re-verified. Tests: +830 lines across 9 files (T2 6, T3 9, T1 SC1/SC2, T5 SC7, T6 7×SC8); `--regression` 20/20 + honesty-lint clean; affected classes green serially. All five levers default to the safe state.

## v11.26 — Handoff State Machine Extraction + Test-Honesty Lint

Stops the V11.25.x handoff-bug whack-a-mole loop (10 fixes in 5 weeks) by naming and enforcing the invariants. Spec at `sessions/v11-handoff-invariants/spec.md`. The V11.25.2 retro and backfill review independently flagged "silent state-machine failures in auto-emit hooks — source attribution must be baked in" as the recurring pattern; V11.26 bakes it in. **(1) Handoff confidence state machine extracted to typed Python** (`scripts/lib/handoff_state.py`, 250 lines, stdlib only): four enums (`SessionSummarySource`, `StateSource`, `LedgerSource`, `HandoffDecision`), two exceptions (`ProtocolViolation`, `UnhandledHandoffState`), `resolve_decision()` pure function + `main()` CLI. Bash now subprocesses the module via JSON IPC at scripts/handoff:1407-1456 (replacing the V11.25.2 inline case block). `_CONF_DECISION="UNKNOWN"` is statically unreachable — Python raises `UnhandledHandoffState` instead. Invariants enforced at runtime: I1 decision always in declared enum, I2 raw inputs raise ProtocolViolation, I3 unhandled tuples raise UnhandledHandoffState, I4 AUTHORITATIVE implies empty downgrade_reasons, I5 non-canonical summary sources always contribute `session_summary_not_from_disk`. Graceful degradation on subprocess failure (loud stderr + skip artifact + handoff.md still builds). **(2) Hypothesis property tests** (`tests/test_handoff_state_invariants.py`, 26 tests, 200 examples each, `derandomize=True` for CI stability): I1–I9 + C1 (CLI subprocess output parity vs direct Python) + C2 (exit codes 0/1/2). All 5 `SessionSummarySource` enum values exhaustively parametrized. **(3) Test-honesty lint** (`scripts/lint-test-honesty`, AST + regex hybrid, <2s on the suite, wired into `scripts/run-tests --regression` as a soft-block): four patterns — P1 stderr-subtraction (V11.25.2 5d3492d), P2 disjunctive-decision-assert (5d3492d), P3 bare `_run()` followed by negative-only asserts (5d3492d), P4 bash case-without-`*)`-default (the V11.25.x root pattern). Initial run flagged 19 violations; AST refinement of P3 narrowed to 5 real issues. Two were T7-E4 hits my V11.25.2 sprint missed (`test_handoff_hygiene.py:161,478` — `_run()` followed by `assert not …`). Three were P4 in `scripts/handoff` (autonomy-name lookup, decision warning case, handoff-category banner) — all gained explicit `*)` defaults. Final state: 0 lint violations. Rollback: `V11_LINT_TEST_HONESTY=off`. **(4) 5-state dogfood matrix** (`tests/integration/test_handoff_5state_dogfood.py`, 9/9 PASS): end-to-end tests for each `SessionSummarySource` state (`missing`, `written`, `stale-replaced`, `stale-unarchived`, `synthesized`) running real `scripts/handoff` against fixtures, parsing `.handoff-confidence.json`, asserting decision + downgrade_reasons. Surfaced **V11.26.1 finding F-STALE-REPLACED-IS-STUB** (LOW): the stub regen elif branch at `scripts/handoff:660` writes the fresh stub but never sets `SESSION_SUMMARY_IS_STUB=1`, so `stale-replaced` resolves to `AUTHORITATIVE` instead of `AUTHORITATIVE-WITH-CAVEATS` — a stale-replaced stub masquerades as a human-written summary in the confidence artifact. Test asserts the current bug behavior with fail-loudly maintainer instructions so the V11.26.1 fix has a built-in landing gate. Tests: 26/26 (`test_handoff_state_invariants`) + 9/9 (`test_handoff_5state_dogfood`) + 38/38 V11.25.x regression (`test_handoff_stale_summary` + `test_handoff_hygiene`) = 73/73 PASS. Falsifiable durability bet (spec success criterion #6): the next handoff-edge-case bug must surface as a Python exception in CI or a lint failure, NOT a silent incorrect downgrade in production. If V11.27 ships another silent-fall-through patch in untyped bash, this sprint failed its goal.

## v11.25.2 — V11.18 Backfill Review Findings

Three surgical fixes carved from the V11.18 sprint adversarial-lite review backfill (9 historical tasks reviewed in parallel, 2026-06-19; report at `sessions/v11-handoff-hygiene/reviews/backfill-2026-06-19.md`). All three are the same "could-have-shipped-V11.25.1's-bug" pattern — silent state-machine failure precursors in code paths adjacent to the stale-summary work. **(1) `scripts/handoff` `_CONF_DECISION` extended for non-canonical summary sources** (T6-E1 MED HIGH-conf): the case statement only handled `STATE_SOURCE ∈ {per-session, aggregate}` and silently fell to `_CONF_DECISION="UNKNOWN"` whenever `SESSION_SUMMARY_SOURCE` landed on `stale-replaced` (archive succeeded but stub regen <30 chars) or `synthesized` (inline fallback at L960). New `_SS_NONCANONICAL` signal drives `PER-SESSION-NO-DISK-SUMMARY` (per-session branch) and `AUTHORITATIVE-WITH-CAVEATS` (aggregate branch with ledger). `.handoff-confidence.json` gains `session_summary_source` field + `session_summary_not_from_disk` downgrade_reason. Companion T6-E2 LOW: warn-only stale path (`NO_STUB_FLAG` or `V11_STUB_SUMMARY=off`) now sets `SESSION_SUMMARY_SOURCE="stale-unarchived"` instead of leaving `missing` — the file-exists branch was then promoting to `written` and masking the known-stale state. **(2) `hooks/completion-hint` METRICS_DIR guard** (T4-E2 MED HIGH-conf): the hook runs under `set -u +e` and references `$METRICS_DIR` at L63 with no guard. If `common.sh` ever fails to export it (minimal env, lazy init, source partial-failure), `set -u` would error fatally with no observable signal — indistinguishable from "no active task". Added `[ -z "${METRICS_DIR:-}" ] && exit 0` immediately after `source common.sh`. Companion T4-E1 LOW: in `V11_COMPLETION_HINT_DEBUG=1` mode, the L91 exit when `_FILE_TOKS` is empty now emits a stderr line explaining "no tokens >=4 chars from basename" so operators can distinguish silent skips. **(3) `tests/integration/test_handoff_hygiene.py` test-honesty cluster** (T7-E1 HIGH + T7-E2/E3/E4 MED): the V11.18 sprint shipped four false-green test patterns identical in shape to the cluster V11.25.1 just fixed in `test_handoff_stale_summary.py` (commit b135c71). T7-E1: L297 `second.stderr.replace(first.stderr, "")` subtraction trick — split into two direct `not in` assertions. T7-E2: L483 `test_authoritative_when_clean` accepted 3 disjunctive decision values (`{AUTHORITATIVE, PER-SESSION, LEGACY-AGGREGATE}`); fixture seeds only the aggregate, no V11_SESSION_ID, so the resolver MUST deterministically pick `AUTHORITATIVE` — assertion tightened. T7-E3: L205 `_run([str(DISC_SCRIPT), "p1"], env)` lacked `bash` prefix used everywhere else. T7-E4: 3 negative T2 tests at L224/L235/L249 called `_run(...)` without capturing rc; silent crashes passed vacuously. All gain `rc = _run(...)` + `assert rc.returncode == 0, rc.stderr`. Tests: 27/27 (`tests/integration/test_handoff_hygiene.py`) + 11/11 (`tests/test_handoff_stale_summary.py` regression) + 95/95 across handoff-hygiene + stale-summary + family-fold + handoff-corruption sweep. No rollback env-vars needed — all three fixes are pure additive correctness; no new toggle surface. Convergent signal with V11.25.2 backfill retro (`retros/2026-06-19.json`): both reviews independently flagged "silent state-machine failures in auto-emit hooks — source attribution must be baked in" as the recurring pattern.

## v11.25.1 — Drift-Sweep Follow-ups + Stale Handoff Summary

Closes the V11.25.0 F1 drift sweep follow-up list (3 LOW items, sweep score 2/10) plus a separately-discovered handoff staleness bug. **(1) DC1 coherence anchor regex `-iE`** (`v11-coherence` skill DC1 anchor): mixed-case `v11.X.Y` tokens now match alongside `V11.X.Y`. **(2) Three undocumented hooks added to §13** in this file: `require-producer-script` (Pre Bash), `completion-hint` (Post Write/Edit), `guard-stale-task` (Post TaskList) — row count 14→17; wiring re-verified against `settings.json` before write. **(3) Strategy 1.6 stderr marker** (`hooks/sync-tasks:201`): silent V11.24 rare-path resolution now emits `[v11.24-strategy-1.6]` marker carrying resolved project + task_id + session_uuid so the ledger-task-home fix is observable. 5/5 Strategy 1.6 tests pass (commits dc6db17 + d0ee144). **(4) Stale `.session-summary.md` detection + session-end ordering** (commit c8b6234): live failure 2026-06-19 — v11-sharpening's auto-generated handoff embedded a 60-day-old April session summary into a fresh Zeus spawn. Two cooperating root causes: (a) `scripts/handoff` treated any existing `.session-summary.md` as canonical with no freshness check (once written, authoritative forever); (b) `hooks/session-end` auto-emitted `handoff.md` BEFORE writing `last-session.json`, so the auto-emit read the prior session's enrichment fields. Fixes: `scripts/handoff` now archives stale summary to `.session-summary.md.prev.md` (recoverable) and regenerates a fresh stub when summary mtime exceeds `V11_STALE_SUMMARY_GRACE_SECS` (default 86400s) OR `task-state.json` is >1h newer; `hooks/session-end` extracts the auto-emit into `_v11_auto_emit_handoff` function and invokes it AFTER `last-session.json` is written. Dogfood live: v11-sharpening's 1431h-old April summary archived, fresh stub written, visible stderr WARN. Rollback: `V11_STALE_SUMMARY_CHECK=off`, `V11_STALE_SUMMARY_GRACE_SECS=N`, `V11_SESSION_END_REORDER=off`. Tests: +8 (`tests/test_handoff_stale_summary.py`). Cross-project ledger contamination in v11-sharpening's `recent_completed` surfaced as a side observation — pre-V11.24 historical drift, separate scrub.

## v11.25.0 — Discipline Mechanization + V11.21 Producer Completion

Three-strand discipline closure plus hygiene burst. **(1) Post-commit task-close hook** (`hooks/post-commit-close-tasks`) fires on git post-commit, matches `^S\d+(-prep)?-T[A-Za-z0-9]+:` in HEAD subject, appends idempotent `status_changed` events with `caller_kind="hook"`, `commit_sha`, `matched_pattern`, `hook_version` audit fields. Multi-task subjects (`S55-T2,T3:` / `S55-T2 + T3:`) close all referenced tasks. The reference project's canary chain-installed via `scripts/install-postcommit-hook` (Strand H added symlink-detection + md5-verified chain-wrapper to avoid write-through clobbering tracked source like that project's S50-T4 advisor). Catch-22 with linter resolved: HYPOTHESIZED commits with `Pairs: T<id>` exclude those task IDs from auto-close, keeping unmeasured-claim work-tasks open across iterations. **(2) Validation tag linter** (`hooks/lib/validation_lint.py` + dual-surface PreToolUse Bash matcher + commit-msg hook) enforces Lens 4's `Validation: HYPOTHESIZED|DRY-RUN|MEASURED-LIVE-PARTIAL|LIVE` tag. HYPOTHESIZED requires an open paired-task ID resolved via the durable ledger. `(verb ∧ number)` heuristic WARNs on missing tag without false-positiving chore/docs commits. Lens 4's "until linter ships" get-out-of-jail clause cleared in `agents/adversarial-lite-reviewer.md`. **(3) V11.21 auto-pair producer completion** — the marquee dual-layer review feature was *theatrical*: `hooks/sync-tasks` read `metadata.review_of`/`review_task_id` but no code path created the pair. Adoption measured at 0-1.5% across sampled projects. Now `sync-tasks` TaskCreate branch auto-synthesizes a sibling review task when (a) `V11_AUTO_PAIR_REVIEW != off`, (b) parent `complexity ∈ {medium, complex, novel}` OR `risk ∈ {medium, high}`, (c) parent has no existing `review_task_id`. Sibling enters with `pair_<n>` namespace (counter-based `_v11_pair_seq` reservation; no collision with Claude Code native int IDs), `metadata.review_of=parent_id`, `parent_status=pending_parent`. Existing activation code at line 848+ transitions `pending_parent → pending` on parent completion. Dogfood verified live (`pair_1` synthesized for complex task in an internal environment). Discovered + fixed `. as $root` jq operator-precedence trap during impl. **Hygiene burst**: `sessions/v11-sharpening/spec.md` rewritten to V11.24 reality (80→88L, V11.8 original archived), `handoff.md` 83→48L (drops manual rehydration block — V11.17 owns it), `MEMORY.md` 223→179L (27 over-length entries trimmed to ≤200-char hooks, V11.11-reform archived, partial-load resolved), 2 stale `__autonomy-grant-selftest-*` dirs cleared. F1 drift sweep score 2/10 (data plane solid; 3 LOW/MED follow-ups carved to V11.25.1: DC1 coherence anchor regex case-insensitivity, 3 undocumented hooks need §13 rows, Strategy 1.6 stderr marker). Rollback: `V11_POSTCOMMIT_AUTOCLOSE=off`, `V11_POSTCOMMIT_DRYRUN=on`, `V11_VALIDATION_LINT=off`, `V11_VALIDATION_LINT_STRICT=off` (default warn-only), `V11_VALIDATION_LINT_HEURISTIC=off`, `V11_AUTO_PAIR_REVIEW=off`. Tests: +107 hook tests (post-commit 37 + validation-lint 70 post-polish) + 10 auto-pair + 7 install-helper = +124 net.

## v11.24 — Session-Bind Drift Fix (Strategy 1.6)

Closes the misroute class surfaced live during the engine.example.com wiring-finish session on 2026-06-05: detect-project (V11.18+) binds each Claude Code session to the first project it sees and suppresses cross-project drift — a safety feature. But when a session was bound to project A (e.g. inherited from a stale `active-project` file) and the user issued `TaskCreate(metadata.project=B)`, the create events landed in B's ledger via Strategy 1 (explicit metadata) — but subsequent `TaskUpdate(completed)` calls without an explicit `metadata.project` fell through the old Strategy 1.5's `.project` fallthrough and resolved to A, silently misrouting every completion event + its artifacts + counters_delta. Fix: split Strategy 1.5 into 1.5a (`.open_tasks[id].metadata.project` only — no fallthrough) and 1.5c (the deferred `.project` fallback), and insert new **Strategy 1.6 ledger-task-home**: when 1.5a misses, scan `~/.agent-metrics/ledger/*.jsonl` for a `created` event matching `(session_uuid, task_id)` — a unique pair within a Claude Code session — and resolve PROJECT to that event's `.project`. Strategy 1.6 also captures `subject_norm` + `create_seq` from the same match so the downstream identity-resolution ladder doesn't fall through to LEDGER-IDENTITY-MISS (TaskUpdate payloads don't carry a subject, so Step 3's subject-based fallback can't fire). Rollback: `V11_LEDGER_TASK_HOME=off`. Cost: one grep + jq per ledger file (~100-200 files; early-out on grep miss). Only fires when Strategies 1 and 1.5a both miss — never on hot path.



## v11.23.0 — Handoff Cross-Project Scope Leak Fix (2026-06-01)

Fully fixes the handoff cross-project scope leak (bug report `reports/bug-handoff-cross-project-scope-leak-20260601.md`, severity HIGH, blast radius every multi-project user). Smoking gun: `handoff-tasks.json` for `atlas-terminal` contained 19 open tasks, only 4 legitimately for that project (21%). The other 15 belonged to portfolio, eigen-opus, and music-corpus projects whose contributing Claude sessions had `active-project=atlas-terminal`.

This release lands a **three-layer fix** absorbing all uncommitted handoff-hygiene strands from the past week (5/29 `handoff-accuracy` W1/W2/W3 + 6/01 AM `guard-stale-task` from the swarm-studio audit + 6/01 PM Layer 1 jq filter):

**Layer 1 — handoff aggregate filter (softened V11.23):** `scripts/handoff` jq blocks at lines ~1141 and ~1456 filter `open_tasks_by_session` by `metadata.project`. Today's first pass dropped null-metadata tasks too aggressively; V11.23 softens to accept (`metadata.project == $PROJECT` OR null), safe because Layer 3 ensures null-metadata tasks only land in $PROJECT.json when their session legitimately was for $PROJECT.

**Layer 2 — `_proj` per-task stamp at TaskCreate/Update (W1, originally 5/29):** `hooks/sync-tasks` stamps each task with a hook-resolved project on `TaskCreate` and `TaskUpdate(in_progress)` events, gated on `V11_HANDOFF_LIVE_RECONCILE=on`. Stamps ONLY when source is authoritative (metadata or task-own-record); skips when ambient-project-fallback. Plus W1 live-snapshot writer + W2 Zeus spawn fixes + W3 gate substance check + HANDOFF_CATEGORY banner (TO_BUILD / PAUSED_EXTERNAL / PAUSED_USER / RESUME).

**Layer 3 — per-task aggregate routing (NEW V11.23):** `hooks/lib/common.sh::v11_rebuild_project_aggregate` replaces the per-session V11.15.5 Bug-H quarantine with finer-grained per-task routing. Each task `t` from session `s` belongs to aggregate $P iff:
- `t.metadata.project == $P` (explicit, cross-session safe), OR
- `t.metadata.project` is null/missing AND `s.project == $P` (legacy fallback).

Applied uniformly to `open_tasks_by_session`, `recent_completed`, `blocked_tasks`, `active_task_ids`, `recommended_agents`, `task_artifacts`. Open counters (pending/in_progress/blocked) recomputed from filtered set; `completed` only contributed by sessions where `session.project == $project` (avoids cross-project over-count; under-counts slightly for cross-project sessions — accepted residual). `aggregated_from` filtered to sessions that actually contributed ≥1 task (mirrors Bug-H outcome at per-task granularity). Single session now contributes to **multiple** project aggregates correctly.

**`scripts/reconcile-aggregates`** — NEW one-shot maintenance script. Walks `$TASK_STATE_DIR/*.json`, classifies each task as clean/unstamped/mismatch. `--dry-run` reports JSON; `--apply` triggers `v11_rebuild_project_aggregate` for affected projects. Re-runnable, idempotent.

**Gate 14 — Handoff scope integrity (NEW):** in `scripts/v11-compliance-check`. Reads `sessions/$PROJECT/handoff-tasks.json` if present; verifies every emitted task's `metadata.project` is $PROJECT (or null/legacy-OK). WARNs on foreign-project mismatch.

**W4 cleanup (today, from 5/29 W3 adversarial review):** E1 `BLOCKED=0` guard on TO_BUILD HANDOFF_CATEGORY branch; E2 softened PAUSED_USER banner copy; E4 +2 regression tests.

**`hooks/guard-stale-task` (from swarm-studio audit §H9):** new PostToolUse:TaskList advisory hook. Detects zombie pattern (in_progress task with recent file-edit audit activity but no completion event). 60-min cooldown, max 3 alerts. Rollback: `V11_GUARD_STALE_TASK=off`.

**Empirical validation:**
- `scripts/reconcile-aggregates --project atlas-terminal --verbose`: 16 clean, 23 unstamped, 0 mismatch — the 23 null-project tasks now get routed AWAY on rebuild.
- 12 lying tasks (real portfolio tasks with explicit `metadata.project=atlas-terminal`) are not auto-detectable — bug report acknowledges this requires manual reconciliation.

**Five rollback levers (each independent):**
- `V11_TASK_ROUTE_BY_METADATA=off` — Layer 3 reverts to V11.15.5 per-session quarantine.
- `V11_HANDOFF_LIVE_RECONCILE=off` — Layer 2 stamp + snapshot writer disabled.
- `V11_HANDOFF_CATEGORY=off` — category banner + blocker surfacing disabled.
- `V11_GATE_SUBSTANCE=off` — gate substance check (unedited stub detection) disabled.
- `V11_GUARD_STALE_TASK=off` — zombie-task advisory hook disabled.

**Test additions:** `tests/test_v11_23_layer3_routing.py` (12 tests); `tests/test_handoff_context.py` (+2 W4 regression); `tests/test_zeus_spawn_fixes.py` (W2). **Modified:** `tests/test_sync_tasks_per_session.py::test_misstamped_session_excluded_from_aggregate` updated to V11.23 substantive contract; dropped now-irrelevant "Bug H quarantine" stderr assertion.

**Lineage:** Closes bug-H residual from V11.15.5 → V11.16 (durable ledger) → V11.17 (smooth handoff) → V11.18 (handoff hygiene) → V11.19 (review enforcement) → V11.21 (dual-layer review). This release is the LAYER below those: the underlying aggregate data plane is now per-task-routed, removing the structural source of cross-project contamination.

---

## v11.21.0 — Agent Routing & Dual-Layer Review (2026-05-23)

V11.20 made every layer's errors attributable but left two structural breaks open: (1) only 5 of 113 agents saw real use (97% of attributed errors landed on `spec-implementer-v11`; the 43 spec `## Agents` tables were theater because TaskCreate never read them), and (2) V11.19's deferred review queue failed in dogfood — 22 completions sat un-drained until backfill. V11.21 closes both by baking dual-layer review into the task lifecycle and routing every Phase 4 spawn through DAAO.

**Layer A — self-review** (executor's hand): the implementing agent emits `{severity, errors[]}` JSON in its own `TaskUpdate(completed)` payload at `metadata.artifacts.self_review`. Cheap (~500 tokens in-context), forces articulation at completion, attributes to the executor directly. **Layer B — adversarial-lite** (independent hand): the orchestrator skill pairs a sibling review task at Phase 4 TaskCreate (`metadata.review_of=parent_id`, `metadata.parent_status=pending_parent`, `metadata.agent=adversarial-lite-reviewer`). On parent completion, `sync-tasks` flips the sibling `pending_parent → pending`. The reviewer reads parent's `files_changed + metadata.artifacts + metadata.artifacts.self_review` and writes its verdict to ITS OWN `metadata.artifacts.review` — never to the parent. V11.20 attribution traverses `metadata.review_of` to find the originating agent. Layer A is made falsifiable by the **calibration miss counter** (INV-3): when self=NONE/LOW but adversarial=HIGH/CRITICAL on the same parent, `scripts/agent-scorecard` and `scripts/agent-effectiveness` log a `self_review_miss` and emit a calibration advisory at >50% miss rate (≥4 paired data points noise floor). Without that counter Layer A would degrade to ceremony; with it the layer is observable.

**Three rollback levers, each independent + one documented coupling:** `V11_AUTO_PAIR_REVIEW=off` (no paired review tasks; V11.19 queue path remains functional), `V11_SELF_REVIEW_REQUIRED=off` (self_review absence not tracked; agents may still emit), `V11_DAAO_ROUTING=off` (Phase 4 reverts to `spec-implementer-v11` for tasks WITHOUT `metadata.agent`; explicit `metadata.agent` is ALWAYS honored). **Coupling:** when `V11_AUTO_PAIR_REVIEW=on`, sync-tasks suppresses V11.19 enqueue for tasks whose parent has `metadata.review_task_id` set (O(1) lookup via the forward link the orchestrator sets at pair time — no TaskList scan). Per-task mutual exclusion, not per-project.

### Components

- **(T1) Schema migrations, additive only** — `agent-errors.schema.json` `found_by_layer` enum gains `lite_self` + `lite_adversarial` (legacy `lite` retained, aliased at read time); `task-metadata.schema.json` `artifacts` $def gains `self_review` (object: severity enum + errors array), `review_id` (≤64 char pointer), `review_task_id` (parent forward link); task-metadata gains optional `review_of`, `parent_status`, `skip_review`, `synthetic_completion`. All 37 existing V11.20 ledger entries validate against the extended schemas unchanged (STR-001). `executor_kind` added as orthogonal optional field (`self|adversarial`) — distinct from `caller_kind`.
- **(T2) `scripts/agent-recommend`** — NEW CLI. Reads `~/.agent-registry/agents.json`; `--with-scorecard` consults `agent-scorecard`. Flags: `--meta {web-app|backend-svc|cli-tool|library|integration|pipeline|realtime|agent-system|infra|data-ml}`, `--complexity {routine|medium|complex|novel}`, `--domain <str>`, `--json`. Documented JSON envelope: `{version:"1", recommendations:[{agent_id, model, category, scorecard_success_rate, scorecard_trend, reason}], fallback_used:bool, query_meta:{...}}`.
- **(T3) `scripts/wave-check PROJECT WAVE`** — INV-12 enforcement. Exits 0 when (a) all wave work tasks completed AND (b) all paired adversarial reviews completed with severity ≤ HIGH. Non-zero with structured reason: `WORK_INCOMPLETE | REVIEW_INCOMPLETE | CRITICAL_BLOCKING`.
- **(T4) `scripts/dispatch-trace-append`** + `~/.agent-metrics/dispatch-trace.jsonl` — one line per Phase 4 spawn. FD-209 flock, mkdir-p guard, 4096-byte line cap.
- **(T5-T9) Playbook rewrites** — implementation-detail invariants moved out of spec.md into playbooks: `orchestrate.md` carries DAAO routing table + pair-at-TaskCreate; `per-task-review.md` absorbs 13 invariants; `task-patterns.md` binds spec.md `## Agents` → `metadata.agent`; `interview.md` surfaces Cynefin + agent-recommend; `close.md` adds §6e per-session scorecard split by layer.
- **(T10) Self-review postamble on 8 high-usage agents** (`spec-implementer-v11`, `backend-architect`, `frontend-specialist`, `database-engineer`, `security-engineer`, `testing-engineer`, `performance-optimizer`, `ai-integration-specialist`). Remaining ~100 agents: V11.22 phased rollout.
- **(T11) `adversarial-lite-reviewer.md` v11.21.0** — required `parent_task_id` input, dual-mode contract (code-review when `files_changed` present, content-review when `files_changed=[]` + non-empty `metadata.artifacts`).
- **(T12) `hooks/sync-tasks` V11.21 branch** — `pending_parent → pending` sibling status transition on parent completion; `self_review` schema validate warn-not-fail; `metadata.synthetic_completion=true` skips ALL ledgers; O(1) V11.19 enqueue suppression.
- **(T13) Orchestrator skill Phase 4 sequence** — 3-call atomic pair-at-TaskCreate, dispatch filter excludes `parent_status==pending_parent`, startup recovery scan synthesizes missing siblings, DAAO routing via `agent-recommend`, dispatch-trace logging, wave-check gate.
- **(T14) `scripts/status`** — V11.21 grouping with plain-language summary line.
- **(T15) `scripts/handoff` review-sibling filter + `scripts/v11-resume-tasks` orphan rehydration** — pending_parent siblings dropped from `handoff-tasks.json`; orphan reviews tagged `is_review_sibling=true`.
- **(T16) `scripts/agent-scorecard` `self_review_calibration` block** — INV-3 falsifiability mechanism. Miss = self ∈ {NONE,LOW} AND adversarial ∈ {HIGH,CRITICAL}. Calibration advisory at >50% miss rate with ≥4 paired data points.
- **(T17) +56 integration tests** covering STR-001 through STR-008. Suite total: 1735 → 1791 collected.
- **(T18) Cutover** — three env var defaults already ON in code.

### Deferred to V11.22

1. Default `review_budget_per_sprint` cap (calibrates from V11.21 dogfood data)
2. Self-review postamble on remaining ~100 agents
3. Domain formations (political-pipeline, etc.)
4. Per-task multi-reviewer

### Cutover Transition Policy

Pre-cutover work tasks (completed BEFORE V11.21 shipped) are NOT retroactively paired. They flow through the V11.19 queue path which remains functional alongside V11.21.

### Dogfood Evidence

V11.21 was built using V11.21 protocol. Every reviewable sprint-02+ task carries `metadata.review_task_id` to a paired adversarial-lite-reviewer sibling.

---

## v11.20.0 — Audit & Improve Subagents (2026-05-23)

V11.19 closed the per-task adversarial-lite loop (Layer 2 attribution); V11.20 wires the remaining two review layers (wave + swarm) into the same per-agent ledger AND adds an orchestrator/subagent split to every audit event.

### Components

- **(T1) Schema extensions** — `agent-errors.jsonl` gains `found_by_layer`, `caller_kind`, `task_id_inferred`, `attribution_key`. Two NEW idempotency ledgers: `attribution-keys.jsonl` and `unattributed-findings.jsonl`.
- **(T2) Three helpers** in `hooks/lib/common.sh`: `v11_caller_kind`, `v11_compute_attribution_key`, `v11_resolve_file_to_task`.
- **(T3) `hooks/track-autonomy`** writes `caller_kind` on every audit event.
- **(T4) `hooks/sync-tasks`** stamps `found_by_layer="lite"`, `attribution_key`, optional `caller_kind`.
- **(T5) `scripts/wave-review-attribute`** — NEW. Reads wave verdict JSON, resolves file→task, attributes to executing agents.
- **(T6) `scripts/swarm-review-attribute`** — NEW. Sibling of T5 for swarm reviews.
- **(T7) `scripts/wave-review --attribute`** sub-mode.
- **(T8) `scripts/agent-scorecard`** — NEW. Single-agent deep dive across all 4 layers with caller-kind split.
- **(T9) `scripts/agent-effectiveness`** extended with `--layer` + `--caller-kind` filters.
- **(T10-T11) `scripts/backfill-wave-findings` + `scripts/backfill-swarm-findings`** — fleet-wide historical attribution.

**Cross-path determinism** (load-bearing invariant): bash `v11_compute_attribution_key` and Python `hashlib.sha256` produce BIT-IDENTICAL keys. This is the idempotency contract for cross-layer dedup.

**Caller-kind detection caveat**: V11_SUBAGENT and V11_PARENT_SESSION_ID env vars are NEW conventions. Until the Claude Code Agent-tool launcher injects them, most events fall through to "unknown".

### Dogfood Evidence

Reviewer caught 10 real bugs across T1-T5. All fixed inline. 100+ V11.20-touched tests passing.

---

## v11.19.0 — Review Enforcement (2026-05-22)

V11.15 wired the per-task adversarial-lite review loop; V11.19 makes it actually fire. Root cause of silence: completed-without-review was byte-identical to completed-with-review — sync-tasks silently no-op'd.

### Components

- **(T1) Per-project review queue** at `~/.agent-metrics/review-queue/$PROJECT.jsonl` — append-only JSONL with `pending`/`done` events.
- **(T2) `scripts/review-queue`** CLI: `pending`, `stats`, `list`, `mark-done`, `all-pending`.
- **(T3-T4) `sync-tasks` enqueue/mark-done** on `TaskUpdate(completed)` transitions.
- **(T5) `detect-project` nudge** on first Read per session per project.
- **(T6) `scripts/handoff` confidence integration** — pending reviews downgrade AUTHORITATIVE label.
- **(T7) `scripts/backfill-reviews`** — one-shot scan for historical completions missing reviews.
- **(T8) `scripts/drain-review-queue`** — orchestrator dispatch helper.
- **(T9) `scripts/agent-effectiveness` cleanup** — filters zero-task agents.
- **(T10-T11) Orchestrator skill + tests** — 38 tests, all passing.

### Dogfood Evidence

22 historical tasks backfilled, 3 adversarial-lite reviews drained against the V11.19 code itself.

---

## v11.18.0 — Handoff Hygiene (2026-05-22)

V11.17 closed the UX gap; V11.18 closes the four integrity gaps that V11.17 assumed were upstream-clean but in dogfood (claude-trader-pro) were not.

### Fixes

- **(T1) Token-overlap family fold** — Jaccard ≥ 0.25 OR overlap ≥ 0.45 clusters near-duplicate task subjects.
- **(T2) Discipline detector** — flags in_progress tasks with recent file-edit audit activity.
- **(T3) One-shot TaskList nudge** — surfaces likely-shipped tasks.
- **(T4) Write/Edit completion-hint hook** — suggests task completion when edited file matches task subject.
- **(T5) Addendum slot** — `.handoff-addendum.md` prepended above auto-generated handoff.
- **(T6) AUTHORITATIVE label downgrade** — requires ledger_source=ledger AND zero stale-in_progress AND zero folded families.
- **(T9) Family-aware rehydration** — one TaskCreate per family with `metadata.family_size`.

Tests: 42 unit + 23 integration; zero regressions.

---

## v11.17.0 — Smooth Handoff (2026-05-20)

The V11.16 durable ledger fixed every structural handoff bug; V11.17 closes the UX gap on top of it. Five additive levers:

1. `scripts/handoff` auto-writes a structured `.session-summary.md` stub when missing (quality floor 30 bytes)
2. `session-end` hook auto-emits `handoff.md` + `handoff-tasks.json` (mtime <60s guard)
3. `detect-project` surfaces "[V11] N open task(s) in handoff" on first Read per session
4. `post-compact` adds "Handoff waiting" line when applicable
5. `/v11` Phase 1 step 1a.5 auto-rehydrates TaskList from `handoff-tasks.json` when empty

Full contract: [docs/HANDOFF_SMOOTH.md](HANDOFF_SMOOTH.md).

---

*Prior versions (v11.16 and earlier) documented in session archives and git history.*
