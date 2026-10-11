#!/bin/bash
# V11 Hook Library — shared constants and functions sourced by all hooks.

# Constants
HERCULES_ROOT="${HERCULES_ROOT:-$HOME}"
V11_HOME="${V11_HOME:-$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." 2>/dev/null && pwd || echo "$HERCULES_ROOT/v11")}"
SESSIONS_ROOT="${SESSIONS_ROOT:-$HERCULES_ROOT/sessions}"
METRICS_DIR="$HERCULES_ROOT/.agent-metrics"
TASK_STATE_DIR="$METRICS_DIR/task-state"
REGISTRY_FILE="$METRICS_DIR/project-paths.json"
ACTIVE_PROJECT_FILE="$METRICS_DIR/active-project"

# v11_read_active_project — safe read of the active-project signal file.
# Returns a sanitized project name on stdout, or empty string if:
#   - file doesn't exist
#   - file is empty
#   - content fails whitelist regex (path traversal, shell metacharacters, length > 64)
# Never returns more than one line. Always exit 0 (empty stdout = "no active project").
# SEC-C-02: hardens 8+ hooks/scripts that cat'd ACTIVE_PROJECT_FILE directly
# and concatenated the result into filesystem paths (e.g. sessions/$PROJECT/.autonomy-state).
#
# P4 (2026-05-14): two-tier read for session-scoped isolation.
#   Tier 1: $METRICS_DIR/sessions/$V11_SESSION_ID/active-project (preferred when session_id present)
#   Tier 2: $ACTIVE_PROJECT_FILE (legacy global, CLI scripts and fallback)
# One project-name rule (improvements/59): a leading letter or digit, then
# letters/digits/._- , 64 chars max. Rejects "." and ".." (which collapse
# $SESSIONS_ROOT/$PROJECT onto the sessions root), dot-dirs (.gemini, .forge)
# and shell debris captured from raw command text (example-project;  $P;  *).
# The EREs live in variables: an inline ERE in [[ =~ ]] in this file once
# bricked every hook (v11.35.3). Rollback: V11_PROJECT_SLUG_GUARD=off.
V11_PROJECT_SLUG_ERE='^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
V11_PROJECT_SLUG_ERE_LEGACY='^[a-zA-Z0-9._-]{1,64}$'
v11_valid_project_slug() {
    if [ "${V11_PROJECT_SLUG_GUARD:-on}" = "off" ]; then
        [[ "$1" =~ $V11_PROJECT_SLUG_ERE_LEGACY ]]
    else
        [[ "$1" =~ $V11_PROJECT_SLUG_ERE ]]
    fi
}

# One session-id rule (S2-R5): a leading letter or digit, then letters/digits/
# ._- , 64 chars max, so $METRICS_DIR/sessions/<id> is always a child of
# sessions/. The old '^[a-zA-Z0-9._-]{1,64}$' let "." and ".." through
# (sessions/.. is the metrics dir itself, which SessionEnd's scratch retirement
# would delete under V11_SESSION_GC_MODE=remove) and dot-names (.gc-quarantine).
# Builtins only. v11_parse_input drops an id that fails it (V11_SESSION_ID=""),
# so an invalid id reads as no id downstream. No lever: revert the commit.
V11_SESSION_ID_ERE='^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
v11_valid_session_id() {
    [[ "$1" =~ $V11_SESSION_ID_ERE ]]
}

v11_read_active_project() {
    local raw candidate

    # Tier 1: session-scoped (only if V11_SESSION_ID available and well-formed)
    if v11_valid_session_id "${V11_SESSION_ID:-}"; then
        candidate="$METRICS_DIR/sessions/$V11_SESSION_ID/active-project"
        if [ -f "$candidate" ] && [ -s "$candidate" ]; then
            raw=$(head -n 1 "$candidate" 2>/dev/null | tr -d '[:space:]')
            if v11_valid_project_slug "$raw"; then
                printf '%s' "$raw"
                return 0
            fi
            # Invalid content in session-scoped file — fall through to global
            echo "v11_read_active_project: rejected invalid content in $candidate" >&2
        fi
    fi

    # Tier 2: global fallback (legacy, scripts without session_id)
    # 15-F2: check owner liveness — if a different live session owns the global
    # file, its project binding is theirs, not ours. Return empty (no project)
    # unless V11_ACTIVE_PROJECT_OWNER=off disables the check.
    [ -f "$ACTIVE_PROJECT_FILE" ] || return 0
    [ -s "$ACTIVE_PROJECT_FILE" ] || return 0
    raw=$(head -n 1 "$ACTIVE_PROJECT_FILE" 2>/dev/null | tr -d '[:space:]')
    if ! v11_valid_project_slug "$raw"; then
        echo "v11_read_active_project: rejected invalid content in $ACTIVE_PROJECT_FILE" >&2
        return 0
    fi

    if [ "${V11_ACTIVE_PROJECT_OWNER:-on}" = "on" ] && [ -n "${V11_SESSION_ID:-}" ]; then
        local owner
        owner=$(sed -n '2p' "$ACTIVE_PROJECT_FILE" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$owner" ] && [ "$owner" != "${V11_SESSION_ID:-}" ] \
           && v11_session_is_live "$owner" 2>/dev/null; then
            echo "v11_read_active_project: global file owned by live session ${owner:0:8}, skipping Tier-2" >&2
            return 0
        fi
    fi

    printf '%s' "$raw"
}

# v11_write_active_project — atomic dual-write to global + session-scoped paths.
# Args: $1 = sanitized project name (must match the whitelist regex)
# Side effect: writes to $ACTIVE_PROJECT_FILE always, plus session-scoped file if V11_SESSION_ID set.
# P4 (2026-05-14): per-session scoping to prevent cross-session active-project contamination.
# 15-F2 (v11.35.6): global file carries owner session UUID on line 2 for liveness gating.
v11_write_active_project() {
    local project="$1"
    [ -z "$project" ] && return 1

    # Validate before write — refuse to write attacker-controlled content into either path
    if ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_write_active_project: rejected invalid project name" >&2
        return 1
    fi

    # Always update global (legacy compat for CLI tools without V11_SESSION_ID)
    # Format: line 1 = project name, line 2 = owning session UUID (or empty)
    mkdir -p "$(dirname "$ACTIVE_PROJECT_FILE")"
    local owner="${V11_SESSION_ID:-}"
    v11_valid_session_id "$owner" || owner=""
    printf '%s\n%s\n' "$project" "$owner" > "$ACTIVE_PROJECT_FILE"

    # Additionally update session-scoped file when V11_SESSION_ID is well-formed
    if [ -n "$owner" ]; then
        local scoped_dir="$METRICS_DIR/sessions/$owner"
        mkdir -p "$scoped_dir" 2>/dev/null
        printf '%s\n' "$project" > "$scoped_dir/active-project"
    fi
}

# --- V11.13: Per-session task state ---
# sync-tasks writes per-session, then rebuilds the project aggregate.
# Source of truth: $METRICS_DIR/sessions/$V11_SESSION_ID/task-state.json (one Claude session owns one file)
# Derived view:    $TASK_STATE_DIR/$PROJECT.json + sessions/$PROJECT/.task-state.json (aggregate of all sessions)
#
# Before V11.13, sync-tasks keyed by project: concurrent sessions on the same
# project destructively merged each other's counters (each TaskCreate did
# .total += 1; reconciliation recounted from one session's TaskList and trimmed
# the other session's IDs as "zombies"). Per-session ownership eliminates the
# merge step entirely; aggregate becomes a read-time fold.

# v11_session_uuid — sanitized current session UUID, or "legacy-cli" fallback.
# Used by sync-tasks to stamp session_uuid into per-session state and to
# annotate aggregate fields with attribution.
# Adversarial-review fix (HIGH-2, 2026-05-14): require leading alphanumeric so
# "..", ".", "..hidden" can't resolve to parent / hidden directories. Length 1-64.
# W1-T5 fix (2026-07-10): V11_SESSION_ID is only populated when a hook parses
# it out of the PostToolUse/PreToolUse JSON on stdin (v11_parse_input) --
# scripts invoked directly via the Bash tool (no hook JSON on stdin) never see
# it, so they fell back to "legacy-cli" even though the SAME session's hooks
# had already stamped review-queue/task-state entries with the real uuid.
# Claude Code exports CLAUDE_CODE_SESSION_ID into every Bash tool subprocess
# (confirmed live via `env`), so fall back to it before "legacy-cli" -- this
# makes a plain `scripts/drain-review-queue --safe` resolve the SAME identity
# a hook in the same session would have used, so self-authored/self-claimed
# queue entries are recognized as owned by the current session instead of
# misclassified as a concurrent one.
v11_session_uuid() {
    local sid="${V11_SESSION_ID:-}"
    if [ -z "$sid" ]; then
        sid="${CLAUDE_CODE_SESSION_ID:-}"
    fi
    if v11_valid_session_id "$sid"; then
        printf '%s' "$sid"
    else
        printf '%s' "legacy-cli"
    fi
}

# v11_session_state_path — absolute path to the current session's task-state file.
# When V11_SESSION_ID is unset/malformed (CLI scripts, no Claude session), returns
# a stable path under sessions/legacy-cli/ so callers behave consistently.
v11_session_state_path() {
    printf '%s' "$METRICS_DIR/sessions/$(v11_session_uuid)/task-state.json"
}

# v11_session_has_open_work — true (0) if the CURRENT session's OWN per-session
# task-state file exists AND shows unresolved work of its own:
# (.pending // 0) + (.in_progress // 0) >= 1. False (1) for:
#   - no per-session file (FRESH session that never created/updated a task), or
#   - file exists but pending==0 AND in_progress==0 (session completed every
#     task it owns — a FINISHED wave, even while sibling sessions still have
#     pending work in the project aggregate).
# Pure query — reads only, no writes, no side effects.
#
# V11.34.1 (Q2 fix): superseded v11_session_touched_tasks, whose discriminator
# was "total>=1" — coarse enough that a session which had FINISHED all its own
# tasks (completed==total, pending==0, in_progress==0) still read as "touched"
# and hit the stall BLOCK below whenever the PROJECT aggregate wasn't globally
# complete (siblings still had pending work). That wrongly blocked a finished
# background agent from writing cleanup/artifacts/self-review. Keying on the
# session's own open work instead of "ever touched" fixes the false block
# while preserving the intended behavior for a session that created a task and
# never started it (own pending>=1 — still blocks, and is satisfiable since
# the session owns that task) and for a genuine stall (in_progress lapsed back
# to 0 without completing — still blocks).
v11_session_has_open_work() {
    local state_file pending in_progress
    state_file="$(v11_session_state_path)"
    [ -f "$state_file" ] || return 1
    pending=$(jq -r '.pending // 0' "$state_file" 2>/dev/null)
    in_progress=$(jq -r '.in_progress // 0' "$state_file" 2>/dev/null)
    case "$pending" in ''|*[!0-9]*) pending=0 ;; esac
    case "$in_progress" in ''|*[!0-9]*) in_progress=0 ;; esac
    [ $((pending + in_progress)) -ge 1 ]
}

# v11_rebuild_project_aggregate PROJECT
# Walks all $METRICS_DIR/sessions/*/task-state.json where .project == PROJECT.
# Builds the derived aggregate at $TASK_STATE_DIR/$PROJECT.json and mirrors to
# $SESSIONS_ROOT/$PROJECT/.task-state.json. Backward-compat schema:
#   - .active_task_ids: union of all sessions' IDs, deduped, as strings (legacy shape)
#   - .active_task_ids_by_session: {uuid: [...]} added for diagnostics (new)
#   - .recent_completed[]: entries gain optional .session_uuid (additive, non-breaking)
#   - .aggregated_from: ["uuid", ...] (new)
#   - .aggregate_built_at: ISO ts (new)
# Counters (.total, .completed, .pending, .in_progress, .blocked) are SUMS across sessions.
# Atomic write under flock; aggregate preserved on jq failure.
v11_rebuild_project_aggregate() {
    local project="$1"
    [ -z "$project" ] && return 1
    if ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_rebuild_project_aggregate: rejected invalid project name" >&2
        return 1
    fi

    local sessions_dir="$METRICS_DIR/sessions"
    local aggregate_file="$TASK_STATE_DIR/${project}.json"
    local mirror_file="$SESSIONS_ROOT/$project/.task-state.json"
    local now
    now=$(date -Iseconds)

    mkdir -p "$TASK_STATE_DIR" 2>/dev/null

    # Belt-and-braces snapshot (archive-aware aggregate fix): capture the
    # CURRENTLY-DISPLAYED total/completed before anything below overwrites
    # aggregate_file, so the cutover guard further down can floor against
    # what a consumer saw a moment ago — independent of whichever source
    # (legacy fold or a prior ledger cutover) produced it. Never regress a
    # visible count, full stop.
    # _prior_alias_count / _prior_ageout_count: a prior cutover's aggregate is
    # the folded replay, so its total already nets out the aliases and age-out
    # cancellations it reports (review #15, S2-R4).
    # One jq for all four (review #20): this runs on every Task* call. Invalid
    # JSON prints nothing, so all four stay 0; a non-number field reads as 0.
    local _prior_total=0 _prior_completed=0 _prior_alias_count=0 _prior_ageout_count=0
    if [ -s "$aggregate_file" ]; then
        IFS=$'\t' read -r _prior_total _prior_completed _prior_alias_count _prior_ageout_count \
            < <(jq -r '[.total, .completed, .alias_count, .ageout_count] | map(numbers // 0) | @tsv' \
                    "$aggregate_file" 2>/dev/null) || true
        case "$_prior_total" in ''|*[!0-9]*) _prior_total=0 ;; esac
        case "$_prior_completed" in ''|*[!0-9]*) _prior_completed=0 ;; esac
        case "$_prior_alias_count" in ''|*[!0-9]*) _prior_alias_count=0 ;; esac
        case "$_prior_ageout_count" in ''|*[!0-9]*) _prior_ageout_count=0 ;; esac
    fi

    # Collect matching session files
    # V11.23 Layer 3 (V11_TASK_ROUTE_BY_METADATA=on, default on):
    # Include a session if it contributes ANY task to $project — either by its
    # session-level stamp matching, OR by any per-task metadata.project / recent
    # completed task with metadata.project == $project. Per-task filtering inside
    # the jq merge then rejects the foreign tasks. This replaces the per-session
    # Bug-H quarantine (V11.15.5) with a per-task filter that is finer-grained
    # and handles the smoking-gun cc0bbe64 case (session.project=A but tasks
    # legitimately target other projects).
    #
    # Legacy path (V11_TASK_ROUTE_BY_METADATA=off): keep the V11.15.5 Bug-H
    # quarantine for emergency rollback.
    local matching=()
    if [ -d "$sessions_dir" ]; then
        local f p
        for f in "$sessions_dir"/*/task-state.json; do
            [ -f "$f" ] || continue
            [ -s "$f" ] || continue
            jq empty "$f" 2>/dev/null || continue

            if [ "${V11_TASK_ROUTE_BY_METADATA:-on}" = "off" ]; then
                # Legacy V11.15.5 path: per-session stamp + Bug-H quarantine.
                p=$(jq -r '.project // empty' "$f" 2>/dev/null)
                [ "$p" = "$project" ] || continue
                ownership=$(jq -r --arg P "$project" '
                    [ (.open_tasks // {}) | to_entries[] | .value.metadata.project? ]
                    | map(select(. != null and . != ""))
                    | if length == 0 then "trust"
                      elif (index($P) != null) then "include"
                      else "exclude" end
                ' "$f" 2>/dev/null || echo trust)
                if [ "$ownership" = "exclude" ]; then
                    echo "v11_rebuild_project_aggregate: Bug H quarantine — skipping mis-stamped session $(basename "$(dirname "$f")") (.project=$project but its tasks declare another project)" >&2
                    continue
                fi
                matching+=("$f")
            else
                # V11.23 Layer 3: include session if it has ANY $project signal.
                # Per-task filtering inside the merge will reject foreign tasks.
                relevant=$(jq -r --arg P "$project" '
                    (((.project // "") == $P)
                        or ([(.open_tasks // {}) | to_entries[] | .value.metadata.project? // empty] | index($P) != null)
                        or ([(.recent_completed // []) | .[] | .metadata.project? // empty] | index($P) != null)
                        or ([(.blocked_tasks // []) | .[] | .metadata.project? // empty] | index($P) != null)
                    ) | tostring
                ' "$f" 2>/dev/null || echo "false")
                [ "$relevant" = "true" ] || continue
                matching+=("$f")
            fi
        done
    fi

    local aggregate
    if [ ${#matching[@]} -eq 0 ]; then
        # No session files found for this project.
        if [ -f "$aggregate_file" ] && jq empty "$aggregate_file" 2>/dev/null; then
            # Frozen-aggregate guard (2026-07-21): an empty scan with an existing
            # aggregate used to refresh .aggregate_built_at (and blank
            # .aggregated_from) while leaving every counter untouched — stale
            # data wearing a fresh timestamp, which downstream consumers
            # (guard-write-gates in_progress check) then trusted. Preserve the
            # prior aggregate byte-identical instead and warn, so staleness
            # stays detectable by its own timestamp. Diagnosis:
            # sessions/cta-tracker/artifacts/sync-tasks-freeze-diagnosis.json
            echo "v11_rebuild_project_aggregate: session-file scan EMPTY for '$project' but an aggregate exists — preserving prior aggregate unchanged (counters may be stale)" >&2
            # v11.42 W1-T2 (RC5a): additive audit log so no-ledger dormant projects
            # become discoverable to align-aggregate/audit tooling (per recon #5
            # Option D). stderr-only signal was previously invisible to programmatic
            # readers. Best-effort — never fails the rebuild. Rollback: V11_LEDGER_AUDIT_NOLEDGER=off.
            if [ "${V11_LEDGER_AUDIT_NOLEDGER:-on}" != "off" ]; then
                local _empty_scan_log="$METRICS_DIR/ledger-cutover.jsonl"
                local _empty_scan_ledger="$METRICS_DIR/ledger/${project}.jsonl"
                local _has_ledger="false"
                [ -f "$_empty_scan_ledger" ] && _has_ledger="true"
                printf '{"ts":"%s","project":"%s","decision":"empty-scan-preserve","has_ledger":%s}\n' \
                    "$now" "$project" "$_has_ledger" >> "$_empty_scan_log" 2>/dev/null || true
            fi
            aggregate=$(cat "$aggregate_file")
        else
            aggregate=$(jq -n --arg project "$project" --arg now "$now" '{
                project: $project,
                total: 0, completed: 0, pending: 0, in_progress: 0, blocked: 0,
                phase: "discovery",
                active_task: null,
                active_task_ids: [],
                active_task_ids_by_session: {},
                recent_completed: [],
                blocked_tasks: [],
                recommended_agents: {},
                task_artifacts: {},
                aggregated_from: [],
                last_updated: $now,
                aggregate_built_at: $now
            }')
        fi
    else
        # Merge across all session files via jq -s (slurp into array)
        # V11.23 Layer 3: gated on V11_TASK_ROUTE_BY_METADATA.
        # When ON (default): apply per-task filter to open_tasks, recent_completed,
        # blocked_tasks, active_task_ids, recommended_agents, task_artifacts —
        # then merge from the filtered per-session structures. Open counters are
        # recomputed from the filtered open_tasks. Completed counter is summed
        # ONLY from sessions where session.project == $project (avoids
        # cross-project over-count; under-counts slightly for sessions whose
        # session.project drifted, accepted residual: open-task accuracy is the
        # user-visible bug).
        # When OFF: legacy V11.15.5 behavior (per-session-level Bug-H quarantine,
        # counters summed across all matching sessions including foreign-tasks).
        local _v11_23_route="${V11_TASK_ROUTE_BY_METADATA:-on}"
        local _route_flag="false"
        [ "$_v11_23_route" != "off" ] && _route_flag="true"
        aggregate=$(jq -s \
            --arg project "$project" \
            --arg now "$now" \
            --argjson route "$_route_flag" '
            # V11.23 Layer 3 helper: per-task ownership filter.
            # A task t belongs to $project iff:
            #   (a) explicit: t.metadata.project == $project, OR
            #   (b) legacy fallback: t.metadata.project is null/missing AND
            #       the containing session.project == $project.
            # When $route == false, this filter is a passthrough (legacy behavior).
            def _v23_task_belongs($p; $sess_proj):
                if $route == false then true
                else
                    ((.metadata.project // null) == $p)
                    or ((.metadata.project // null) == null and $sess_proj == $p)
                end;
            # Step 1: per-session pre-process — filter each session to ONLY the
            # tasks belonging to $project (under $route).
            map(
                . as $s
                | ($s.project // null) as $sess_proj
                | (
                    ($s.open_tasks // {}) | with_entries(
                        select(.value | _v23_task_belongs($project; $sess_proj))
                    )
                  ) as $filt_open
                | (
                    ($s.recent_completed // []) | map(
                        select(. | _v23_task_belongs($project; $sess_proj))
                    )
                  ) as $filt_rcomp
                | (
                    ($s.blocked_tasks // []) | map(
                        select(. | _v23_task_belongs($project; $sess_proj))
                    )
                  ) as $filt_blocked
                | (
                    # Scope-id set: all task ids contributing to $project from this session.
                    [ ($filt_open | keys[]) ]
                    + [ ($filt_rcomp[]  | .id // empty) ]
                    + [ ($filt_blocked[] | .id // empty) ]
                    | map(tostring)
                    | unique
                  ) as $scope_ids
                | $s + (
                    if $route == true then
                        {
                            open_tasks:      $filt_open,
                            recent_completed: $filt_rcomp,
                            blocked_tasks:   $filt_blocked,
                            # active_task_ids: filter to scope unless session has no
                            # open_tasks at all + session.project matches (TaskList-only
                            # reconciliation produces a trimmed active_task_ids list
                            # without populating open_tasks; trust it as-is).
                            active_task_ids: (
                                if (($s.open_tasks // {}) | length) == 0 and $sess_proj == $project
                                then (($s.active_task_ids // []) | map(tostring))
                                else
                                    ($s.active_task_ids // [])
                                    | map(tostring)
                                    | map(select(. as $id | $scope_ids | index($id) != null))
                                end
                            ),
                            recommended_agents: (
                                if (($s.open_tasks // {}) | length) == 0 and $sess_proj == $project
                                then ($s.recommended_agents // {})
                                else
                                    ($s.recommended_agents // {})
                                    | with_entries(select(.key as $k | $scope_ids | index($k) != null))
                                end
                            ),
                            task_artifacts: (
                                if (($s.open_tasks // {}) | length) == 0 and $sess_proj == $project
                                then ($s.task_artifacts // {})
                                else
                                    ($s.task_artifacts // {})
                                    | with_entries(select(.key as $k | $scope_ids | index($k) != null))
                                end
                            ),
                            # Recompute open counters from filtered open_tasks.
                            # FALLBACK: when the session has NO open_tasks at all
                            # (e.g. TaskList-only counter reconciliation, where
                            # sync-tasks parsed [pending]/[completed] from tool_output
                            # but no TaskCreate events fired to populate open_tasks),
                            # AND session.project == $project, trust the scalar
                            # counter. Safe because empty open_tasks rules out
                            # cross-project tasks. Once any TaskCreate fires the
                            # filtered-count path takes over (open_tasks non-empty).
                            _v23_pending: (
                                if (($s.open_tasks // {}) | length) == 0 and $sess_proj == $project
                                then ($s.pending // 0)
                                else ([$filt_open | to_entries[] | select(.value.status == "pending")] | length)
                                end
                            ),
                            _v23_in_progress: (
                                if (($s.open_tasks // {}) | length) == 0 and $sess_proj == $project
                                then ($s.in_progress // 0)
                                else ([$filt_open | to_entries[] | select(.value.status == "in_progress")] | length)
                                end
                            ),
                            _v23_blocked: (
                                if (($s.open_tasks // {}) | length) == 0 and $sess_proj == $project
                                then ($s.blocked // 0)
                                else ([$filt_open | to_entries[] | select(.value.status == "blocked")] | length)
                                end
                            ),
                            # Completed: only contribute if session.project == $project
                            # (conservative — under-counts slightly for cross-project sessions,
                            # but avoids over-counting; user-visible bug is OPEN-task accuracy).
                            _v23_completed: (if $sess_proj == $project then ($s.completed // 0) else 0 end)
                        }
                    else {} end
                  )
            )
            |
            # Step 2: merge across (filtered) sessions
            {
                project: $project,
                total: (
                    if $route == true then
                        ((map(._v23_pending // 0)     | add)
                         + (map(._v23_in_progress // 0) | add)
                         + (map(._v23_blocked // 0)   | add)
                         + (map(._v23_completed // 0) | add))
                    else (map(.total // 0) | add) end
                ),
                completed: (
                    if $route == true then (map(._v23_completed // 0) | add)
                    else (map(.completed // 0) | add) end
                ),
                pending: (
                    if $route == true then (map(._v23_pending // 0) | add)
                    else (map(.pending // 0) | add) end
                ),
                in_progress: (
                    if $route == true then (map(._v23_in_progress // 0) | add)
                    else (map(.in_progress // 0) | add) end
                ),
                blocked: (
                    if $route == true then (map(._v23_blocked // 0) | add)
                    else (map(.blocked // 0) | add) end
                ),
                phase: (
                    (sort_by(.last_updated // "1970-01-01") | last | .phase) // "discovery"
                ),
                # V11.14.4: derive .active_task from the canonical open_tasks subject
                # at the active_task_id of the latest session that HAS an active task.
                # Prefer sessions with non-empty active_task_ids so a ghost session
                # (recreated empty after session-end rm-rf) does not mask a real
                # in-progress task in a sibling session. Falls back to the latest
                # session denormalized .active_task when no session has active IDs.
                # (Comments use no apostrophes — bash single-quote context.)
                active_task: (
                    (map(select(((.active_task_ids // []) | length) > 0))
                     | sort_by(.last_updated // "1970-01-01") | last) as $active_sess
                    | if $active_sess != null then
                          (($active_sess.active_task_ids // []) | .[0] // "") as $aid
                          | if $aid != "" then
                              (($active_sess.open_tasks // {})[$aid].subject)
                              // $active_sess.active_task // null
                            else
                              $active_sess.active_task // null
                            end
                      else
                          (sort_by(.last_updated // "1970-01-01") | last | .active_task) // null
                      end
                ),
                active_agent_id: (
                    (sort_by(.last_updated // "1970-01-01") | last | .active_agent_id) // null
                ),
                active_task_sprint: (
                    (sort_by(.last_updated // "1970-01-01") | last | .active_task_sprint) // null
                ),
                active_task_gate: (
                    (sort_by(.last_updated // "1970-01-01") | last | .active_task_gate) // null
                ),
                active_task_ids: (
                    map(.active_task_ids // []) | add
                    | map(tostring) | map(select(. != "" and . != "null"))
                    | unique
                ),
                active_task_ids_by_session: (
                    reduce .[] as $s ({};
                        if (($s.session_uuid // "") != "") then
                            .[$s.session_uuid] = ($s.active_task_ids // [])
                        else . end
                    )
                ),
                recent_completed: (
                    map(
                        (.session_uuid // "unknown") as $u |
                        (.recent_completed // []) | map(. + {session_uuid: (.session_uuid // $u)})
                    ) | add | sort_by(.at // "") | reverse | .[0:10]
                ),
                blocked_tasks: (
                    map(
                        (.session_uuid // "unknown") as $u |
                        (.blocked_tasks // []) | map(. + {session_uuid: (.session_uuid // $u)})
                    ) | add | sort_by(.at // "") | reverse | .[0:5]
                ),
                recommended_agents: (
                    map(.recommended_agents // {}) | add
                ),
                task_artifacts: (
                    map(.task_artifacts // {}) | add
                ),
                # V11.13: per-session open_tasks preserved as nested map for handoff/rehydration.
                # Keyed by session_uuid so cross-session task-id collisions remain distinct.
                # V11.23: open_tasks here is already per-task-filtered (Step 1 above when
                # $route==true). Skip sessions whose filtered open_tasks is empty so the
                # aggregate stays clean (no zero-task sessions cluttering rehydration).
                open_tasks_by_session: (
                    reduce .[] as $s ({};
                        if (($s.session_uuid // "") != "") and ($s.open_tasks // null) != null
                           and (($s.open_tasks | length) > 0) then
                            .[$s.session_uuid] = ($s.open_tasks // {})
                        else . end
                    )
                ),
                finding_tasks: (
                    map(.finding_tasks // {}) | add
                ),
                # V11.15 Bug C: carry review_summary forward. Per-session
                # sync-tasks accumulates it; the aggregate must SUM the counters
                # and recompute avg_difficulty as a tasks_reviewed-weighted mean
                # (a plain average of per-session means would be wrong). Null
                # when no session has any review_summary (matches findings_summary).
                review_summary: (
                    [ .[] | .review_summary // empty ] as $rs
                    | if ($rs | length) == 0 then null
                      else
                        ($rs | map(.tasks_reviewed // 0) | add) as $tr
                        | {
                            tasks_reviewed: $tr,
                            total_errors: ($rs | map(.total_errors // 0) | add),
                            by_severity: {
                                critical: ($rs | map(.by_severity.critical // 0) | add),
                                high:     ($rs | map(.by_severity.high // 0)     | add),
                                medium:   ($rs | map(.by_severity.medium // 0)   | add),
                                low:      ($rs | map(.by_severity.low // 0)      | add)
                            },
                            auto_fixed: ($rs | map(.auto_fixed // 0) | add),
                            escalated:  ($rs | map(.escalated // 0)  | add),
                            avg_difficulty: (
                                if $tr == 0 then null
                                else (($rs | map((.avg_difficulty // 0) * (.tasks_reviewed // 0)) | add) / $tr)
                                end
                            )
                          }
                      end
                ),
                dark_code_advisories: {
                    str_missing_count:        (map(.dark_code_advisories.str_missing_count // 0)        | add),
                    str_missing_complex:      (map(.dark_code_advisories.str_missing_complex // 0)      | add),
                    str_missing_novel:        (map(.dark_code_advisories.str_missing_novel // 0)        | add),
                    completions_without_str:  (map(.dark_code_advisories.completions_without_str // 0)  | add),
                    last_advisory_at: (
                        map(.dark_code_advisories.last_advisory_at // "")
                        | map(select(. != "" and . != null))
                        | if length == 0 then null else max end
                    )
                },
                # V11.23: when route-on, restrict aggregated_from to sessions that
                # actually contributed at least one task to this project (any of
                # open_tasks / recent_completed / blocked_tasks non-empty after the
                # per-session filter). Mirrors the V11.15.5 Bug-H quarantine
                # outcome (excluded session not listed) but at the per-task level.
                aggregated_from: (
                    if $route == true then
                        [.[] | select(
                            (((.open_tasks // {})       | length) > 0)
                            or (((.recent_completed // []) | length) > 0)
                            or (((.blocked_tasks // [])  | length) > 0)
                        ) | (.session_uuid // "unknown")] | unique
                    else
                        map(.session_uuid // "unknown") | unique
                    end
                ),
                last_updated:    (map(.last_updated // $now) | max),
                # #87: fold the per-session progress clock the same way as
                # last_updated (max across contributing sessions). A session
                # scratch written before #87 has no last_progress_at, so it
                # falls back to that session own last_updated field instead of
                # dragging the aggregate max down to null.
                last_progress_at: (map(.last_progress_at // .last_updated // $now) | max),
                aggregate_built_at: $now
            }
            | .findings_summary = (
                if (.finding_tasks | length) == 0 then null
                else {
                    critical: ([.finding_tasks | to_entries[] | select(.value == "critical")] | length),
                    high:     ([.finding_tasks | to_entries[] | select(.value == "high")]     | length),
                    medium:   ([.finding_tasks | to_entries[] | select(.value == "medium")]   | length),
                    low:      ([.finding_tasks | to_entries[] | select(.value == "low")]      | length),
                    total_raw: (.finding_tasks | length)
                }
                end
            )
        ' "${matching[@]}")
    fi

    # Atomic write to aggregate. Adversarial-review fix (HIGH-1, 2026-05-14):
    # flock timeout previously did `exit 0` (silent discard). Under two concurrent
    # sessions both rebuilding, one silently lost its write and the mirror diverged.
    # Now: log timeout to stderr and exit non-zero so the rebuild is visibly stale.
    local rebuild_rc=0
    (
        flock -w 5 202 || { echo "v11_rebuild_project_aggregate: aggregate flock timeout for $project ($aggregate_file)" >&2; exit 1; }
        local tmp="$aggregate_file.tmp.$$"
        printf '%s' "$aggregate" | jq '.' > "$tmp" 2>/dev/null
        if [ -s "$tmp" ] && jq empty "$tmp" 2>/dev/null; then
            mv "$tmp" "$aggregate_file"
        else
            rm -f "$tmp"
            echo "v11_rebuild_project_aggregate: jq produced invalid aggregate for $project; existing file preserved" >&2
            exit 1
        fi
    ) 202>"$aggregate_file.lock" || rebuild_rc=$?

    # Mirror to session dir
    local session_dir="$SESSIONS_ROOT/$project"
    if [ -d "$session_dir" ] || mkdir -p "$session_dir" 2>/dev/null; then
        if [ -s "$aggregate_file" ] && jq empty "$aggregate_file" 2>/dev/null; then
            (
                flock -w 5 203 || { echo "v11_rebuild_project_aggregate: mirror flock timeout for $project" >&2; exit 1; }
                cp "$aggregate_file" "$mirror_file" 2>/dev/null
            ) 203>"$mirror_file.lock" || rebuild_rc=$?
        fi
    fi

    # --- V11.16 Cutover: ledger replay becomes authoritative (auto-rollback guard) ---
    # ADR §7, sprint-2 #4. The legacy session-fold written above is now the GUARD
    # REFERENCE + the fallback, no longer the source of truth. User-approved
    # approach (2026-05-18): "Cutover with auto-rollback guard".
    #
    #   ledger exists + replay >= legacy (total AND completed not lower)
    #       -> CUTOVER: replay overwrites the aggregate; the lossy ephemeral
    #          session-fold is retired for this project. Gate-1 proved replay
    #          is equal-or-superset of (and strictly more correct than) legacy.
    #   ledger exists but replay is BEHIND legacy (fewer total/completed)
    #       -> GUARD ROLLBACK: keep legacy, log LOUDLY. A behind ledger means
    #          this project is not yet backfilled (migration #6 catches up).
    #          Never serve a regressed count to a consumer.
    #   no ledger
    #       -> keep legacy + emit a loud SOURCE warning (durability not yet
    #          guaranteed for this project until its ledger is seeded).
    #
    # Escape hatch: V11_LEDGER_CUTOVER=off forces pure-legacy (no replay, no
    # overwrite) — the documented rollback lever (cf. V11_FLYWHEEL_META_CLUSTER).
    # When cutover succeeds the aggregate IS the replay, so the shadow diff
    # (replay-vs-replay) is information-free and is skipped — net latency for a
    # healthy project is one replay, same as the sprint-1 shadow path.
    local _cutover_done=0
    local _ledger_file="$METRICS_DIR/ledger/${project}.jsonl"
    local _cutover_log="$METRICS_DIR/ledger-cutover.jsonl"
    # V11.16 legacy-pinned lever (migrate-ledger --pin PROJECT):
    # If $METRICS_DIR/ledger/.legacy-pinned/<project> exists, force legacy path for
    # this project regardless of whether a ledger exists.  Emergency rollback without
    # a code deploy.  Log LEGACY-PINNED to stderr and the cutover JSONL log.
    local _legacy_pinned_file="$METRICS_DIR/ledger/.legacy-pinned/${project}"
    if [ "${V11_LEDGER_CUTOVER:-on}" != "off" ] && [ -f "$_legacy_pinned_file" ]; then
        echo "v11_rebuild_project_aggregate: LEGACY-PINNED for '$project' — cutover skipped (pin file: $_legacy_pinned_file). Remove with: migrate-ledger --unpin '$project'" >&2
        printf '{"ts":"%s","project":"%s","decision":"legacy-pinned"}\n' \
            "$now" "$project" >> "$_cutover_log" 2>/dev/null || true
        # Honest provenance: the legacy fold above may have PRESERVED a prior
        # cutover's content (the V11.15.6 no-live-sessions "refresh existing
        # aggregate" path keeps every field, incl. .ledger_source="ledger").
        # An emergency-pinned project must NOT keep advertising ledger
        # provenance — strip the marker so consumers (handoff banner, /v11
        # status) treat it as legacy. Data itself is intentionally left as-is
        # (freezing the last legacy/known state is the pin contract; for a
        # no-session project legacy has nothing better to offer — no worse
        # than pre-V11.16). Atomic, best-effort, never fails the rebuild.
        if [ -s "$aggregate_file" ] && jq -e 'has("ledger_source")' "$aggregate_file" >/dev/null 2>&1; then
            (
                flock -w 5 202 || exit 1
                local _ptmp="$aggregate_file.tmp.$$"
                jq 'del(.ledger_source)' "$aggregate_file" > "$_ptmp" 2>/dev/null
                if [ -s "$_ptmp" ] && jq empty "$_ptmp" 2>/dev/null; then
                    mv "$_ptmp" "$aggregate_file"
                else
                    rm -f "$_ptmp"; exit 1
                fi
            ) 202>"$aggregate_file.lock" && {
                if [ -d "$session_dir" ] && [ -s "$aggregate_file" ]; then
                    ( flock -w 5 203 || exit 1
                      cp "$aggregate_file" "$mirror_file" 2>/dev/null
                    ) 203>"$mirror_file.lock" || true
                fi
            }
        fi
        # fall through to shadow diff (diagnostic only, harmless)
    elif [ "${V11_LEDGER_CUTOVER:-on}" != "off" ] && [ -f "$_ledger_file" ] \
       && [ -s "$aggregate_file" ] && jq empty "$aggregate_file" 2>/dev/null; then
        local _replay
        # Env vars are prefixed on `timeout` (the external command that execs
        # bash) so they are inherited by the WHOLE child script — not just the
        # `source` builtin. A `VAR=val source f && func` prefix would apply
        # only to `source`, leaving METRICS_DIR empty in v11_replay_ledger
        # (latent in the sprint-1 shadow path; load-bearing here). Project is
        # passed positionally ("$1") to avoid any quoting/injection.
        _replay=$(
            HERCULES_ROOT="$(dirname "${METRICS_DIR}")" \
            METRICS_DIR="${METRICS_DIR}" \
            V11_HOME="${V11_HOME}" \
            timeout 15 bash -c \
                'source "$V11_HOME/hooks/lib/common.sh" 2>/dev/null && v11_replay_ledger "$1"' \
                _ "${project}" \
                2>/dev/null
        ) || _replay=""
        if [ -n "$_replay" ] && printf '%s' "$_replay" | jq empty 2>/dev/null; then
            local _lt _lc _rt _rc
            _lt=$(jq -r '.total // 0'     "$aggregate_file" 2>/dev/null || echo 0)
            _lc=$(jq -r '.completed // 0' "$aggregate_file" 2>/dev/null || echo 0)
            _rt=$(printf '%s' "$_replay" | jq -r '.total // 0'     2>/dev/null || echo 0)
            _rc=$(printf '%s' "$_replay" | jq -r '.completed // 0' 2>/dev/null || echo 0)
            # CUTOVER DECISION = STRICT COUNT-GUARD ONLY (V11.16 final, after
            # the full --all fleet verification, 2026-05-18).
            #
            # History of this decision (kept so it is never re-litigated):
            # marker-trust (bypass the guard for migrated projects) was tried
            # because the 6-project canary showed migration de-poisoning
            # inflated aggregates (claude-ahk 0/2 -> coherent 2/1). But the
            # full 96-project fleet check proved the de-poison case and a
            # genuine bounded-window history-loss case are STRUCTURALLY
            # INDISTINGUISHABLE from the scalars alone: both are simply
            # "ledger < legacy". Any margin heuristic that trusts the marker
            # on a small drop also silently collapses real history on coherent
            # projects (container-control-api 6/6 -> 1/1 lost 5 real
            # completions; v11-handoff-durability 24/4 -> 23/4). Therefore the
            # ONLY history-safe rule is: cutover NEVER reduces a visible count.
            #
            # The .migrated marker does NOT bypass the guard. Its value is:
            # (1) the ledger is seeded + acceptance-verified -> durability is
            # live for ALL new work on EVERY migrated project immediately;
            # (2) audit record; (3) the legacy-pin counterpart. Cutover timing
            # is purely the count-guard: a project flips to the ledger the
            # moment normal use makes the ledger replay reach/exceed legacy
            # on BOTH total and completed (the user's "recoup when I use it"
            # self-heal). De-poison of an inflated legacy aggregate happens
            # then too — when the ledger legitimately overtakes it — never by
            # discarding a count we cannot prove was poisoned. legacy-pin
            # above still overrides everything; V11_LEDGER_CUTOVER=off too.
            # Belt-and-braces (archive-aware aggregate fix): also floor against
            # the aggregate's own PRIOR total/completed (captured at function
            # entry, before the legacy fold above overwrote aggregate_file).
            # This catches the case where the legacy re-fold ITSELF already
            # regressed vs. what was previously displayed (e.g. a prior ledger
            # cutover had a higher count than a freshly-recomputed legacy
            # fold would produce) — never write a smaller total/completed
            # than a consumer already saw, on either axis.
            # improvements/24: an operator-authorized CORRECTION can
            # legitimately DECREASE replay counts (e.g. the identity-fallback
            # fix removes phantom records that inflated total, or folds stray
            # completed events onto real records). Raw counts cannot tell a
            # correction from a regression, so the guard stays fail-closed by
            # default. The escape hatch is PROJECT-SCOPED (adversarial
            # finding #3, 2026-08-06): V11_CUTOVER_ACCEPT_CORRECTION must
            # equal THIS project's name — a leftover exported flag can never
            # authorize a correction on a different project (the exact
            # trust-the-operator-marker failure mode that once cost
            # container-control-api 5 real completions). It deliberately
            # bypasses BOTH count floors (prior-aggregate AND ledger-vs-
            # legacy): a correction of an inflated aggregate is precisely the
            # case where the honest replay is below both. Set it for ONE
            # rebuild of ONE project; never export it persistently.
            local _accept_correction=0
            case "${V11_CUTOVER_ACCEPT_CORRECTION:-off}" in
                off|"") : ;;
                on)
                    echo "v11_rebuild_project_aggregate: V11_CUTOVER_ACCEPT_CORRECTION=on is not accepted — set it to the exact project name (e.g. =$project) so the authorization cannot leak onto other projects. Guard remains active." >&2
                    ;;
                "$project") _accept_correction=1 ;;
                *) : ;;  # names a different project — guard stays active here
            esac
            # v11.42 W2-T2 (RC5b): FOOTGUN PROTECTION. The unsafe lever combo
            # V11_REVIEW_SIBLING_AGEOUT=on + V11_AGEOUT_GUARD_CARVEOUT=off would
            # reproduce exactly the silent-revert the bundling was designed to
            # prevent (age-out shrinks replay → REGRESSION-GUARD trips → pins to
            # stale zombie-inflated legacy). Detect + auto-force CARVEOUT=on with
            # loud WARN. The reverse combo (AGEOUT=off + CARVEOUT=on) is inert
            # and safe (nothing to credit → carve-out is a no-op).
            if [ "${V11_REVIEW_SIBLING_AGEOUT:-on}" != "off" ] && [ "${V11_AGEOUT_GUARD_CARVEOUT:-on}" = "off" ]; then
                echo "v11_rebuild_project_aggregate: FOOTGUN for '$project' — V11_REVIEW_SIBLING_AGEOUT=on + V11_AGEOUT_GUARD_CARVEOUT=off silently reverts age-out via regression-guard. Auto-forcing V11_AGEOUT_GUARD_CARVEOUT=on for this rebuild. Set both =off (or both =on) intentionally to avoid this warning." >&2
                export V11_AGEOUT_GUARD_CARVEOUT=on
            fi
            # v11.42 W2-T2 (RC5b): cancel-driven-shrink carve-out. Count ledger
            # events with reason="review_sibling_ageout" (written by Wave 2 T3's
            # skill v1.4 age-out sweep) and add that count to replay's total for
            # comparison — a shrink fully accounted for by age-out is NOT a
            # regression. Prior events without this reason (pre-Wave-2 manual
            # cancellations) are NOT counted, so this never retroactively
            # bypasses the guard for other correction paths.
            # S2-R4: the count is the replay's .ageout_count (parsed events, so
            # a non-compact `"reason": "..."` line counts too; a grep missed
            # it). Against the PRIOR, add back only age-outs the prior did not
            # already reflect (max(0, ageout_count - prior ageout_count)): the
            # whole-ledger count re-added on every rebuild let a real loss of
            # up to that many tasks pass the guard once an aggregate carried
            # them (review #15's alias pattern). The legacy session-fold never
            # sees a ledger-only cancellation, so the ledger-vs-legacy check
            # below still adds the full ageout_count.
            local _ageout_count=0 _ageout_carveout=0
            if [ "${V11_AGEOUT_GUARD_CARVEOUT:-on}" != "off" ]; then
                _ageout_count=$(printf '%s' "$_replay" | jq -r '.ageout_count // 0' 2>/dev/null || echo 0)
                case "$_ageout_count" in ''|*[!0-9]*) _ageout_count=0 ;; esac
                _ageout_carveout=$((_ageout_count - _prior_ageout_count))
                [ "$_ageout_carveout" -lt 0 ] && _ageout_carveout=0
            fi
            # review #3 (S1-T2c): rehydrate-alias carve-out. v11_replay_ledger
            # folds each rehydrate alias into its original identity, so total
            # drops by one against a prior that counted both identities (live:
            # v11-leverage-program prior 178 vs ledger 177, blocked). The
            # replay reports how many it folded (.alias_count); add it back,
            # like the age-out carve-out. V11_REPLAY_REHYDRATE_ALIAS=off folds
            # none, so this is 0.
            # review #15: against the PRIOR, add back only aliases the prior did
            # not already fold (max(0, alias_count - prior alias_count)); an
            # unconditional add-back let a real loss of up to alias_count tasks
            # pass the guard on every rebuild after the first cutover. The
            # legacy session-fold always counts both identities, so the
            # ledger-vs-legacy check below still adds the full alias_count.
            local _alias_count _alias_carveout
            _alias_count=$(printf '%s' "$_replay" | jq -r '.alias_count // 0' 2>/dev/null || echo 0)
            case "$_alias_count" in ''|*[!0-9]*) _alias_count=0 ;; esac
            _alias_carveout=$((_alias_count - _prior_alias_count))
            [ "$_alias_carveout" -lt 0 ] && _alias_carveout=0
            # cancelled events don't affect .completed; _rc_adj unchanged.
            local _rc_adj="$_rc"
            local _rt_adj_legacy=$((_rt + _ageout_count + _alias_count))
            local _rt_adj=$((_rt + _ageout_carveout + _alias_carveout))
            if [ "$_accept_correction" != "1" ] && { [ "$_rt_adj" -lt "$_prior_total" ] 2>/dev/null || [ "$_rc_adj" -lt "$_prior_completed" ] 2>/dev/null; }; then
                echo "v11_rebuild_project_aggregate: REGRESSION-GUARD for '$project' — ledger replay (total=$_rt completed=$_rc; +ageout_carveout=$_ageout_carveout +alias_carveout=$_alias_carveout → adjusted total=$_rt_adj) would regress below the currently-displayed aggregate (total=$_prior_total completed=$_prior_completed); cutover skipped, prior aggregate preserved." >&2
                printf '{"ts":"%s","project":"%s","decision":"regression-guard-blocked","prior_total":%s,"prior_completed":%s,"ledger_total":%s,"ledger_completed":%s,"ageout_carveout":%s,"alias_carveout":%s}\n' \
                    "$now" "$project" "$_prior_total" "$_prior_completed" "$_rt" "$_rc" "$_ageout_carveout" "$_alias_carveout" >> "$_cutover_log" 2>/dev/null || true
            elif [ "$_accept_correction" = "1" ] || { [ "$_rt_adj_legacy" -ge "$_lt" ] 2>/dev/null && [ "$_rc_adj" -ge "$_lc" ] 2>/dev/null; }; then
                # CUTOVER: ledger is equal-or-superset of legacy on total AND
                # completed — replay is authoritative and never regresses.
                # #87: v11_replay_ledger itself never computes last_progress_at
                # (left out of its ADR-governed determinism contract on purpose,
                # see WALLCLOCK above). Without this, a cutover project would
                # silently lose the progress clock to the // last_updated
                # fallback on every rebuild, since cutover overwrites the
                # legacy-fold aggregate (which DOES carry it) with $_replay
                # (which does not). Derive it here, max ts across every
                # status-changing ledger event (created/in_progress/completed/
                # blocked/cancelled), and merge it in. --rawfile + a per-line
                # try/catch reads $_ledger_file inside the SAME jq process that
                # already writes $_ctmp below (0 new forks: M2 gate, tests/
                # test_sync_tasks_fork_budget.py) and skips a malformed line
                # instead of aborting the whole parse, matching v11_replay_
                # ledger own per-line tolerance (a plain --slurpfile does not:
                # one bad line would fail the entire jq call). Never fails the
                # cutover: no matching event leaves $lpa null and the merge is
                # skipped.
                (
                    flock -w 5 202 || { echo "v11_rebuild_project_aggregate: cutover flock timeout for $project" >&2; exit 1; }
                    local _ctmp="$aggregate_file.tmp.$$"
                    printf '%s' "$_replay" | jq --rawfile ledger_raw "$_ledger_file" '
                        (
                            [$ledger_raw | split("\n")[] | select(. != "")
                                | (try fromjson catch null) | select(. != null)
                                | select((.ev // "") as $e
                                    | ["created","in_progress","completed","blocked","cancelled"] | index($e))
                                | (.ts // empty)]
                            | if length == 0 then null else max end
                        ) as $lpa
                        | if $lpa != null then .last_progress_at = $lpa else . end
                    ' > "$_ctmp" 2>/dev/null
                    if [ -s "$_ctmp" ] && jq empty "$_ctmp" 2>/dev/null; then
                        mv "$_ctmp" "$aggregate_file"
                    else
                        rm -f "$_ctmp"
                        echo "v11_rebuild_project_aggregate: cutover replay produced invalid JSON for $project; legacy aggregate preserved" >&2
                        exit 1
                    fi
                ) 202>"$aggregate_file.lock" && {
                    _cutover_done=1
                    if [ -d "$session_dir" ] && [ -s "$aggregate_file" ]; then
                        (
                            flock -w 5 203 || { echo "v11_rebuild_project_aggregate: cutover mirror flock timeout for $project" >&2; exit 1; }
                            cp "$aggregate_file" "$mirror_file" 2>/dev/null
                        ) 203>"$mirror_file.lock" || true
                    fi
                    local _cutover_reason="guard-pass"
                    [ "$_accept_correction" = "1" ] && _cutover_reason="correction-authorized"
                    [ "$_ageout_carveout" -gt 0 ] 2>/dev/null && [ "$_cutover_reason" = "guard-pass" ] && _cutover_reason="ageout-carveout-material"
                    printf '{"ts":"%s","project":"%s","decision":"cutover","reason":"%s","prior_total":%s,"prior_completed":%s,"legacy_total":%s,"legacy_completed":%s,"ledger_total":%s,"ledger_completed":%s,"ageout_carveout":%s,"alias_carveout":%s}\n' \
                        "$now" "$project" "$_cutover_reason" "$_prior_total" "$_prior_completed" "$_lt" "$_lc" "$_rt" "$_rc" "$_ageout_carveout" "$_alias_carveout" >> "$_cutover_log" 2>/dev/null || true
                }
            else
                # LEDGER BEHIND LEGACY -> keep legacy (NEVER regress a visible
                # count). Expected & benign for a freshly-migrated mature
                # project: its ledger is seeded + acceptance-verified (new work
                # is durable from now on) but its de-poisoned baseline is
                # below the legacy scalar (bounded recent_completed window,
                # ADR §5 MED-2). The project keeps its real count on legacy and
                # AUTO-PROMOTES to the ledger the moment normal use makes the
                # ledger replay reach/exceed legacy — the user-confirmed
                # "recoup when I use it" self-heal. No history is ever shown
                # collapsed; no manual step. (deferred, not an error.)
                echo "v11_rebuild_project_aggregate: LEDGER-DEFERRED for '$project' — ledger replay behind legacy (ledger total=$_rt completed=$_rc < legacy total=$_lt completed=$_lc). Keeping legacy (real count preserved); ledger is durable for new work and auto-promotes once it catches up." >&2
                printf '{"ts":"%s","project":"%s","decision":"ledger-deferred","legacy_total":%s,"legacy_completed":%s,"ledger_total":%s,"ledger_completed":%s}\n' \
                    "$now" "$project" "$_lt" "$_lc" "$_rt" "$_rc" >> "$_cutover_log" 2>/dev/null || true
            fi
        fi
    elif [ "${V11_LEDGER_CUTOVER:-on}" != "off" ] && [ ! -f "$_ledger_file" ]; then
        echo "v11_rebuild_project_aggregate: SOURCE=legacy (no ledger for '$project') — aggregate is the lossy session-fold; handoff durability NOT guaranteed for this project until its ledger is seeded (sprint-2 #6 migration)." >&2
    fi

    # --- Shadow reconciliation diff (ADR §6, Sprint 1 shadow phase) ---
    # Now DIAGNOSTIC ONLY. Post-cutover the aggregate IS the replay, so the
    # diff would compare identical inputs and is skipped. For guard-rollback /
    # no-ledger projects it still classifies legacy-vs-replay divergence.
    # PURELY OBSERVABILITY — zero behavior change, never alters rebuild_rc.
    if [ "$_cutover_done" -eq 0 ]; then
        v11_shadow_reconciliation_diff "$project" "$aggregate_file" || true
    fi

    return $rebuild_rc
}

# v11_shadow_reconciliation_diff PROJECT AGGREGATE_FILE
#   Shadow reconciliation instrument (ADR §6, Sprint 1).
#   Reads the live aggregate already written to AGGREGATE_FILE,
#   independently replays the project ledger via v11_replay_ledger, and
#   logs any structural divergence (field-level: which field, aggregate value,
#   replay value) to $METRICS_DIR/ledger-shadow-divergence.jsonl.
#
#   ALWAYS returns 0.  The real rebuild path must never be affected by this
#   function — it is wrapped in "|| true" at every call site, and all
#   internal failure paths are similarly guarded.  The shadow computation is
#   synchronous but time-bounded (timeout 10): v11_replay_ledger is ~100ms
#   for any realistic ledger, so this adds negligible latency to the rebuild.
#
#   Wall-clock fields (aggregate_built_at, last_updated, last_progress_at)
#   are excluded from the comparison — same exclusion the determinism tests
#   use (§3.2 / test _WALLCLOCK_FIELDS). last_progress_at (#87) is a hook-only
#   stall-clock aid, not reconstructed by v11_replay_ledger, so leaving it
#   unexcluded would flag every project with a status-changed task as
#   diverged on every rebuild.
#
#   Divergence log schema per line:
#   {
#     "ts": "<ISO-8601>",
#     "project": "<project>",
#     "field": "<key>",
#     "aggregate_value": <live>,
#     "replay_value": <replay>,
#     "source": "shadow-diff"
#   }
v11_shadow_reconciliation_diff() {
    local project="$1"
    local aggregate_file="$2"

    # SEC-C-02: validate project name
    [ -z "$project" ] && return 0
    if ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        return 0
    fi

    # Only run if the ledger file exists — no ledger = nothing to diff
    local ledger_file="${METRICS_DIR}/ledger/${project}.jsonl"
    [ -f "$ledger_file" ] || return 0

    # Only run if the aggregate file is present and non-empty
    [ -f "$aggregate_file" ] && [ -s "$aggregate_file" ] || return 0

    # Read the live aggregate (must be valid JSON)
    local live_aggregate
    live_aggregate=$(jq -c '.' "$aggregate_file" 2>/dev/null) || return 0
    [ -n "$live_aggregate" ] || return 0

    # Run ledger replay (time-bounded to 10s; ~100ms in practice).
    # v11_replay_ledger is already defined in this sourced common.sh — call it
    # directly (no subprocess needed) via a subshell to isolate its env/stdout.
    local replay_output
    # Env prefix on `timeout` (the child process), not on `source` — same
    # correctness fix as the cutover path: a `VAR=val source f && func` prefix
    # applies only to the builtin, leaving METRICS_DIR empty in the replay.
    replay_output=$(
        HERCULES_ROOT="$(dirname "${METRICS_DIR}")" \
        METRICS_DIR="${METRICS_DIR}" \
        V11_HOME="${V11_HOME}" \
        timeout 10 bash -c \
            'source "$V11_HOME/hooks/lib/common.sh" 2>/dev/null && v11_replay_ledger "$1"' \
            _ "${project}" \
            2>/dev/null
    ) || return 0   # replay error or timeout = skip (side-effect-never-fails)
    [ -n "$replay_output" ] || return 0

    # Delegate the structural diff + JSONL append to Python.
    # Wall-clock exclusions: aggregate_built_at, last_updated, last_progress_at (ADR §6, test _WALLCLOCK_FIELDS; #87).
    local divergence_file="${METRICS_DIR}/ledger-shadow-divergence.jsonl"
    local now
    now=$(date -Iseconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%S+00:00")

    V11_SHADOW_PROJECT="$project" \
    V11_SHADOW_LIVE="$live_aggregate" \
    V11_SHADOW_REPLAY="$replay_output" \
    V11_SHADOW_DIVERGENCE_FILE="$divergence_file" \
    V11_SHADOW_NOW="$now" \
    python3 - <<'SHADOW_PYEOF' 2>/dev/null || true
import os, sys, json, datetime, pathlib

project       = os.environ.get("V11_SHADOW_PROJECT", "")
live_json     = os.environ.get("V11_SHADOW_LIVE", "")
replay_json   = os.environ.get("V11_SHADOW_REPLAY", "")
divfile       = os.environ.get("V11_SHADOW_DIVERGENCE_FILE", "")
now           = os.environ.get("V11_SHADOW_NOW") or datetime.datetime.now().isoformat()

# Wall-clock fields excluded from the comparison (same set as test _WALLCLOCK_FIELDS).
WALLCLOCK = frozenset({"aggregate_built_at", "last_updated", "last_progress_at"})

try:
    live   = json.loads(live_json)
    replay = json.loads(replay_json)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

if not isinstance(live, dict) or not isinstance(replay, dict):
    sys.exit(0)

all_keys = (set(live.keys()) | set(replay.keys())) - WALLCLOCK

divergences = []
for key in sorted(all_keys):
    lv = live.get(key)
    rv = replay.get(key)
    if lv != rv:
        divergences.append({
            "ts":               now,
            "project":          project,
            "field":            key,
            "aggregate_value":  lv,
            "replay_value":     rv,
            "source":           "shadow-diff",
        })

if not divergences or not divfile:
    sys.exit(0)

pathlib.Path(divfile).parent.mkdir(parents=True, exist_ok=True)
lines = "\n".join(json.dumps(d, separators=(",", ":")) for d in divergences) + "\n"
try:
    with open(divfile, "a", encoding="utf-8") as fh:
        fh.write(lines)
except OSError:
    pass   # side-effect-never-fails
SHADOW_PYEOF

    return 0
}

# Infrastructure dirs excluded from project detection
NON_PROJECTS="v11 v10 v9 v8 v7 v6_Ultra sessions scripts system-apps-config portfolio-platform \
.claude .agent-metrics .agent-registry .secrets .archive .cache .local .npm .nvm .config \
.ssh snap node_modules deploy.sh"

# Parse hook stdin JSON once into global vars.
# S2-T4: single jq pass (was 7-9 separate jq forks: tool_name, file_path,
# command, session_id, tool_response, tool_output fallback, tool_response
# string-unwrap, error, cwd — TaskGet alone forked ~25 of these). Fields are
# emitted as a NUL-delimited raw-string stream (jq -j, explicit "\u0000"
# separators) and read back with one `read -r -d ''` per field.
# Deliberately NOT @tsv: @tsv escapes embedded tabs/newlines/CR *within* a
# field's own text (task descriptions, multi-line tool output) into literal
# two-char "\t"/"\n"/"\r" sequences on the way out, and plain `read` cannot
# losslessly un-escape those back into real control characters on the way in.
# NUL cannot appear in a JSON text payload, so it needs no escaping and is
# unambiguous as a field terminator — ordinary field values pass through
# byte-for-byte.
v11_parse_input() {
  V11_RAW_INPUT="$(cat)"
  # Defensive defaults: if V11_RAW_INPUT is empty/invalid JSON, the jq call
  # below produces no output and every `read` hits EOF without touching its
  # variable. Pre-seed empty strings so behavior matches the old per-field
  # jq calls (an errored call left its var unset/empty either way) even
  # under `set -u`.
  V11_TOOL_NAME="" V11_FILE_PATH="" V11_COMMAND="" V11_SESSION_ID=""
  V11_ERROR="" V11_CWD="" V11_TOOL_OUTPUT=""
  {
    IFS= read -r -d '' V11_TOOL_NAME
    IFS= read -r -d '' V11_FILE_PATH
    IFS= read -r -d '' V11_COMMAND
    IFS= read -r -d '' V11_SESSION_ID
    IFS= read -r -d '' V11_ERROR
    IFS= read -r -d '' V11_CWD
    IFS= read -r -d '' V11_TOOL_OUTPUT
  } < <(printf '%s' "$V11_RAW_INPUT" | jq -j '
    def strize: if type == "string" then . else tojson end;
    (.tool_name // ""), "\u0000",
    ((.tool_input.file_path // .tool_input.path) // ""), "\u0000",
    (.tool_input.command // ""), "\u0000",
    (.session_id // ""), "\u0000",
    (.error // ""), "\u0000",
    ((.cwd // .working_directory) // ""), "\u0000",
    (
      # V11_TOOL_OUTPUT: Claude Code emits the tool result at .tool_response
      # (object). Pre-V11.13 tests synthesise .tool_output (raw text). Prefer
      # the object, as compact JSON text, so downstream jq path queries work;
      # fall back to legacy .tool_output text when .tool_response is
      # absent/null/false. Both consumers (jq path queries AND grep over
      # embedded text) keep working because compact JSON still contains the
      # literal words/IDs they search for.
      #
      # S81-W0-2 (U-new-1): dsh-hooks-claude-code flattens .tool_response into
      # a JSON-encoded STRING before delivering the hook payload. Downstream
      # jq paths like .task.id / .taskId then error with "Cannot index string
      # with X". Unwrap once here so every consumer sees the object shape.
      #
      # GATE (v11-test-debt): only the .tool_response path can be a
      # JSON-encoded string wrapper. The legacy .tool_output fallback is
      # already RAW TEXT and must NOT be re-parsed as JSON — a value like
      # "1. Fix bug [completed]\n2…" read as a JSON stream greedily emits the
      # leading number 1, silently truncating the entire TaskList text to "1"
      # (breaking counter + active_task_ids reconciliation). Only the
      # .tool_response branch below ever calls fromjson.
      #
      # review-#14 HIGH fix: the .tool_response branch always applies tojson
      # to its result (never strize) so a bare non-JSON string ("hello")
      # round-trips as valid quoted JSON ("hello"), matching the pre-S2-T4
      # jq -c dot-tool_response-or-empty behavior byte-for-byte. strize is
      # reserved for the legacy .tool_output fallback below, where the
      # value is raw text and must stay unquoted.
      (.tool_response // null) as $tr
      | if ($tr != null and $tr != false) then
          ($tr | if type == "string" then (fromjson? // .) else . end | tojson)
        else
          (.tool_output // "" | strize)
        end
    ), "\u0000"
  ')
  v11_valid_session_id "$V11_SESSION_ID" || V11_SESSION_ID=""  # S2-R5: "..", ".x", "a/b" = no id

  # V9_ aliases removed in V11.7 — no hooks reference them (verified 2026-03-28)
}

# Classify risk: prints "high", "medium", or "low".
# v11_matches_high_risk_pattern TEXT — the high-risk pattern chain, factored
# out of v11_risk_level so it can run against both the raw command and the
# improvements/25 masked view.
# rm with recursive flag: only matches actual flag TOKENS (-[a-zA-Z]+ bounded by whitespace),
# not "-r" substrings embedded in path components like "references/v11-quick-ref.md".
# Bug 2026-06-01: previous regex used .* and matched any -r in the command string.
v11_matches_high_risk_pattern() {
  local cmd="$1"
  [[ "$cmd" =~ (^|[[:space:]])rm([[:space:]]+-[a-zA-Z]+)*[[:space:]]+(-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)([[:space:]]|$) ]] \
  || [[ "$cmd" =~ DROP[[:space:]]+(DATABASE|TABLE)|TRUNCATE|DELETE[[:space:]]+FROM ]] \
  || [[ "$cmd" =~ docker[[:space:]]+system[[:space:]]+prune[[:space:]]+-a ]] \
  || [[ "$cmd" =~ docker[[:space:]]+volume[[:space:]]+rm ]] \
  || [[ "$cmd" =~ git[[:space:]]+push[[:space:]]+--force|git[[:space:]]+push[[:space:]]+-f ]] \
  || [[ "$cmd" =~ git[[:space:]]+reset[[:space:]]+--hard|git[[:space:]]+clean[[:space:]]+-f ]] \
  || [[ "$cmd" =~ shutdown|reboot|mkfs|dd[[:space:]]+if= ]] \
  || [[ "$cmd" =~ chown[[:space:]]+-R|chmod[[:space:]]+-R[[:space:]]+777 ]] \
  || [[ "$cmd" =~ \>[[:space:]]*/dev/sda ]]
}

# v11_risk_classification_text — improvements/25: the classifier matches
# command TEXT, not command STRUCTURE, so prose inside commit-message
# heredocs/quotes trips HIGH patterns (live incident 2026-08-06: the
# v11.35.3 commit was blocked because its own message DESCRIBED the
# recursive-delete pattern). This emits $V11_COMMAND with inert text
# payloads masked, for risk classification ONLY — every consumer of the
# actual command keeps the raw string.
#
# Fail-closed at every branch — any doubt returns the string unmasked:
#   1. Any shell-EXECUTOR token present (sh/bash/eval/ssh/xargs/python/
#      docker/...) -> no masking: a quoted "rm -rf" handed to an executor
#      is a real delete, not prose.
#   2. Heredoc BODIES are stripped by line-anchored terminator match (exact
#      for arbitrary content). An unclosed heredoc aborts to raw (never
#      over-mask past a bad terminator).
#   3. Single-quoted spans -> MASKED placeholder (valid shell guarantees
#      pairing; a placeholder, not deletion, so masking can never join
#      adjacent tokens into a new dangerous string). Odd quote count -> stop.
#   4. Double-quoted spans only when provably well-paired: any \" or $'
#      in the remaining text -> stop (mispairing could swallow a REAL
#      command between two strings -> false negative; we refuse).
# Rollback: V11_RISK_TEXT_MASK=off restores raw-text classification exactly.
v11_risk_classification_text() {
  local cmd="$V11_COMMAND"
  if [ "${V11_RISK_TEXT_MASK:-on}" = "off" ]; then printf '%s' "$cmd"; return; fi

  # (1) executor tokens — word-bounded; broad list on purpose (less masking
  # = fail-closed). git is deliberately NOT here.
  local _exec_re='(^|[[:space:]]|[;&|(`])(sh|bash|zsh|dash|ksh|csh|fish|eval|exec|source|ssh|scp|sudo|su|doas|xargs|find|env|nohup|setsid|timeout|watch|script|expect|chroot|nsenter|systemd-run|at|batch|screen|tmux|parallel|python[0-9.]*|perl|ruby|node|deno|bun|php|lua|awk|gawk|mawk|osascript|docker|podman|nerdctl|kubectl|crictl|make)([[:space:]]|$|[;&|)`])'
  if [[ "$cmd" =~ $_exec_re ]]; then printf '%s' "$cmd"; return; fi
  # ". file" source alias — regex MUST live in a variable: an inline ERE with
  # parens inside a char class breaks the [[ ]] tokenizer (this exact line,
  # written inline, bricked every hook on 2026-08-06 — recovery required the
  # user-run `!` escape hatch; see improvements/25 §incident).
  local _src_alias_re='(^|[[:space:]]|[;&|(])\.[[:space:]]'
  if [[ "$cmd" =~ $_src_alias_re ]]; then printf '%s' "$cmd"; return; fi

  # (2) heredoc bodies
  local masked
  masked=$(printf '%s\n' "$cmd" | awk '
    BEGIN { n = 0; i = 0 }
    {
      if (i < n) {
        line = $0
        sub(/^\t+/, "", line)            # <<- permits leading tabs
        if (line == terms[i]) { i++ }
        next                              # body + terminator masked
      }
      scan = $0
      while (match(scan, /<<-?[ \t]*[^ \t<]+/)) {
        m = substr(scan, RSTART, RLENGTH)
        sub(/^<<-?[ \t]*/, "", m)
        gsub(/["'"'"']/, "", m)
        terms[n++] = m
        scan = substr(scan, RSTART + RLENGTH)
      }
      print
    }
    END { if (i < n) exit 3 }            # unclosed heredoc -> abort to raw
  ' 2>/dev/null) || { printf '%s' "$cmd"; return; }

  # (3) single-quoted spans
  local _sq_count
  _sq_count=$(printf '%s' "$masked" | tr -cd "'" | wc -c)
  if [ $(( _sq_count % 2 )) -ne 0 ]; then printf '%s' "$masked"; return; fi
  masked=$(printf '%s' "$masked" | sed "s/'[^']*'/MASKED/g")

  # (4) double-quoted spans — refuse on \" or $' (mispairing hazard)
  if grep -qF '\"' <<<"$masked" || grep -qF "\$'" <<<"$masked"; then
    printf '%s' "$masked"; return
  fi
  local _dq_count
  _dq_count=$(printf '%s' "$masked" | tr -cd '"' | wc -c)
  if [ $(( _dq_count % 2 )) -ne 0 ]; then printf '%s' "$masked"; return; fi
  masked=$(printf '%s' "$masked" | sed 's/"[^"]*"/MASKED/g')

  printf '%s' "$masked"
}

v11_risk_level() {
  local tool="$V11_TOOL_NAME" cmd="$V11_COMMAND"
  # High-risk: destructive system/data/git operations
  if v11_matches_high_risk_pattern "$cmd"; then
    # improvements/25: the raw hit may live in inert text (commit-message
    # heredoc, quoted prose). Re-test the masked view; only IT decides.
    # Masking bails back to raw on any structural doubt, so a real
    # destructive command can never be hidden by this path.
    local _masked
    _masked="$(v11_risk_classification_text)"
    if [ "$_masked" = "$cmd" ] || v11_matches_high_risk_pattern "$_masked"; then
      echo "high"; return
    fi
    cmd="$_masked"   # prose-only hit: fall through to medium/low on the masked view
  fi
  # Medium-risk: file writes, or bash with stateful commands
  if [[ "$tool" == "Write" || "$tool" == "Edit" ]]; then
    echo "medium"; return
  fi
  if [[ "$tool" == "Bash" ]] \
  && [[ "$cmd" =~ (^|[[:space:]])(rm|git|docker|npm|pip)[[:space:]] ]]; then
    echo "medium"; return
  fi
  echo "low"
}

# Detect project name from file path, CWD, or active-project file.
# Sets V11_PROJECT and V11_DETECTION_METHOD.
# Tries in order: explicit path → CWD → active-project file.
v11_detect_project() {
  local filepath="${1:-$V11_FILE_PATH}"
  V11_PROJECT="" V11_DETECTION_METHOD=""

  # Try path-based detection first
  _v11_detect_project_from_path "$filepath"

  # Fallback 1: CWD (for Bash commands with no file_path)
  if [ -z "$V11_PROJECT" ] && [ -n "$V11_CWD" ]; then
    _v11_detect_project_from_path "$V11_CWD"
    [ -n "$V11_PROJECT" ] && V11_DETECTION_METHOD="cwd"
  fi

  # Fallback 2: active-project file (set by detect-project hook on Read)
  # Uses v11_read_active_project for defense against path-traversal payloads
  if [ -z "$V11_PROJECT" ]; then
    local active
    active="$(v11_read_active_project)"
    if [ -n "$active" ]; then
      V11_PROJECT="$active" V11_DETECTION_METHOD="active-project"
    fi
  fi

  # V9_ aliases removed in V11.7
}

# Internal: extract project name from a path string (regex, plus one -d stat
# for Convention 3).
# improvements/59: every capture must pass v11_valid_project_slug. Callers feed
# this raw, UNEVALUATED command text (track-autonomy, guard-enforcement,
# v11_check_risk/autonomy), so a capture can be `example-project;`, `$P;` or `*`.
# BASH_REMATCH is copied first: the slug check runs its own [[ =~ ]].
_v11_detect_project_from_path() {
  local filepath="$1" candidate
  [ -z "$filepath" ] && return
  # Convention 1: sessions/{name}/
  if [[ "$filepath" =~ ^$SESSIONS_ROOT/([^/]+) ]]; then
    candidate="${BASH_REMATCH[1]}"
    v11_valid_project_slug "$candidate" || return
    V11_PROJECT="$candidate" V11_DETECTION_METHOD="sessions"; return
  fi
  # Convention 2: portfolio-platform/apps/{name}/
  if [[ "$filepath" =~ ^$HERCULES_ROOT/portfolio-platform/apps/([^/]+) ]]; then
    candidate="${BASH_REMATCH[1]}"
    v11_valid_project_slug "$candidate" || return
    V11_PROJECT="$candidate" V11_DETECTION_METHOD="portfolio-app"; return
  fi
  # Convention 3: $HERCULES_ROOT/{name}/ (excluding infra dirs). Must be an
  # existing directory: a top-level FILE ($HERCULES_ROOT/CLAUDE.md) is not a project.
  if [[ "$filepath" =~ ^$HERCULES_ROOT/([^/]+) ]]; then
    candidate="${BASH_REMATCH[1]}"
    for np in $NON_PROJECTS; do
      [[ "$candidate" == "$np" ]] && return
    done
    v11_valid_project_slug "$candidate" || return
    [ "${V11_PROJECT_SLUG_GUARD:-on}" = "off" ] || [ -d "$HERCULES_ROOT/$candidate" ] || return
    V11_PROJECT="$candidate" V11_DETECTION_METHOD="hercules-root"
  fi
}

# Attribution-only project detection: like _v11_detect_project_from_path but
# resolves NON_PROJECTS dirs to their directory name (method="non-project").
# Use for audit rows where correct attribution matters even for framework files.
# 15-F3 (v11.35.6): closes the self-work attribution leak.
_v11_detect_project_for_attribution() {
  local filepath="$1"
  [ -z "$filepath" ] && return
  _v11_detect_project_from_path "$filepath"
  [ -n "$V11_PROJECT" ] && return
  # Path-based detection returned empty — check if it's a NON_PROJECTS dir
  if [[ "$filepath" =~ ^$HERCULES_ROOT/([^/]+) ]]; then
    local candidate="${BASH_REMATCH[1]}"
    for np in $NON_PROJECTS; do
      if [[ "$candidate" == "$np" ]]; then
        V11_PROJECT="$candidate" V11_DETECTION_METHOD="non-project"
        return
      fi
    done
  fi
}

# Check if path is a metadata/infra file hooks should skip.
# Returns 0 (skip) or 1 (process).
v11_is_metadata_file() {
  local filepath="${1:-$V11_FILE_PATH}" base="${1:-$V11_FILE_PATH}"
  base="${base##*/}"
  # Infrastructure paths
  [[ "$filepath" == */v11/hooks/* || "$filepath" == */v9/hooks/* || "$filepath" == */.agent-metrics/* || "$filepath" == */.claude/* ]] && return 0
  # Known metadata filenames
  case "$base" in
    state.md|spec.md|gates.md|.task-state.json|.autonomy-state|.plan-mode-state) return 0 ;;
    .gitignore|CLAUDE.md) return 0 ;;
  esac
  # Env and backup files
  [[ "$base" == .env || "$base" == .env.* ]] && return 0
  [[ "$base" == *.json.backup* || "$base" == *.md.backup* ]] && return 0
  return 1
}

# Check risk level and apply autonomy grants for enforcement.
# Returns 0 if allowed, 2 if blocked.
# Used by guard-enforcement hook.
# Coerce a raw autonomy level value to a plain integer 0-5.
#
# templates/autonomy-state.schema.json declares .level as an integer, but live
# state files drifted to the display form ("A3") — 6 of 179 as of v11.34.3.
# Every consumer did `jq -r '.level // 0'` then bare arithmetic, so a string
# level silently failed EVERY comparison:
#   - v11_check_risk: `[ "A3" -ge 4 ] 2>/dev/null` errored, making the A4/A5
#     high-risk auto-approval branch UNREACHABLE — autonomy was never consulted
#     for exactly the commands that most need it.
#   - v11_check_autonomy: the same test at the A3/A2/A1 gates leaked raw
#     "integer expression expected" to hook stderr and denied A3+ medium
#     auto-approval.
# Coercing at read time fixes every consumer at once and stays correct if a
# future writer re-emits the display form.
#
# Fails closed in EVERY direction: missing, empty, malformed, non-numeric,
# negative, or out-of-range input all yield 0 (least autonomy). Out-of-range
# high values deliberately do NOT clamp to 5 — a corrupted state file reading
# `"level": 9` must not be handed maximum autonomy. This matches the schema
# validator (v11_validate_state_file), which already rejects <0 or >5 outright.
v11_normalize_autonomy_level() {
  local raw="${1:-0}"
  raw="${raw#[Aa]}"        # strip display prefix ("A3" -> "3")
  raw="${raw%%.*}"         # tolerate float form ("3.0" -> "3")
  case "$raw" in
    ''|*[!0-9]*) printf '0'; return 0 ;;
  esac
  # Force base-10: a leading zero would otherwise be read as octal and "08"
  # would abort the comparison ("value too great for base").
  raw=$((10#$raw))
  [ "$raw" -gt 5 ] && raw=0     # invalid, not "maximally autonomous"
  printf '%s' "$raw"
}

# Read an autonomy level from a state file as a plain integer 0-5.
# Wraps v11_normalize_autonomy_level; returns 0 for a missing/unreadable file.
v11_autonomy_level() {
  local file="$1"
  if [ -z "$file" ] || [ ! -f "$file" ] || [ ! -s "$file" ]; then
    printf '0'; return 0
  fi
  v11_normalize_autonomy_level "$(jq -r '.level // 0' "$file" 2>/dev/null)"
}

# Improvement #20 (2026-08-06) path-context helper: does every path argument
# of a flagged `rm -rf`-class command resolve to a literal absolute path
# strictly inside the harness session scratchpad root? Fail-closed by
# construction:
#   - Any character anywhere in the command that could mean shell expansion,
#     quoting, or path traversal (.. $ ` * ? ~ ' " \ or a literal newline)
#     aborts the WHOLE command from consideration, not just the offending
#     token -- this helper does not attempt real shell parsing of compound
#     commands, so ambiguity anywhere in the command must not leak into a
#     path we never actually inspected.
#   - Zero path arguments (flags only) stays HIGH -- v1 does not treat a
#     flagless `rm -rf` as "nothing to downgrade, therefore safe".
#   - Only the FIRST "rm" word found in the command is treated as the
#     flagged invocation; a compound command with an earlier unrelated rm
#     (e.g. `docker rm x && rm -rf <scratchpad>/y`) conservatively stays
#     HIGH because that earlier segment's args won't match the scratchpad
#     regex. Known v1 limitation; safe direction (under-downgrades, never
#     over-downgrades).
#   - Relative paths and `cd`-then-relative-target compounds stay HIGH (no
#     cd-tracking in v1 -- see improvements/20-risk-gate-path-context.md,
#     which explicitly accepts this as the conservative fallback). Session
#     worktree paths are also NOT handled here -- the ticket proposes
#     reusing the v11.34 write-gate's session-attribution machinery for
#     that, but it's DEFERRED; this function only ever matches scratchpad
#     paths.
# Sets V11_RISK_PATH_CONTEXT_RESOLVED to the space-joined resolved paths on
# success. Returns 0 (downgrade OK) or 1 (stay HIGH).
# The harness session scratchpad, shared with v11_is_write_gate_exempt
# (improvements/76). EREs live in variables (v11.35.3).
V11_SCRATCHPAD_ERE='^/tmp/claude-[0-9]+/[^/]*/[^/]*/scratchpad/.+$'
v11_rm_is_scratchpad_only_delete() {
  local cmd="$1"
  V11_RISK_PATH_CONTEXT_RESOLVED=""
  [ -z "$cmd" ] && return 1

  # Reject on any of these appearing ANYWHERE in the command -- see comment
  # above for why a whole-command reject (not per-token) is the safe choice.
  [[ "$cmd" == *..* ]] && return 1
  [[ "$cmd" == *'$'* ]] && return 1
  [[ "$cmd" == *'`'* ]] && return 1
  [[ "$cmd" == *'*'* ]] && return 1
  [[ "$cmd" == *'?'* ]] && return 1
  [[ "$cmd" == *'~'* ]] && return 1
  [[ "$cmd" == *"'"* ]] && return 1
  [[ "$cmd" == *'"'* ]] && return 1
  [[ "$cmd" == *'\'* ]] && return 1
  case "$cmd" in *$'\n'*) return 1 ;; esac

  # Isolate the flagged rm's own arguments: from the first "rm" word up to
  # the next shell control operator (&&, ||, ;, |) or end of string.
  local segment
  if [[ "$cmd" =~ (^|[[:space:]])rm[[:space:]]+([^\&\|\;]*) ]]; then
    segment="${BASH_REMATCH[2]}"
  else
    return 1
  fi

  # Word-split without pathname expansion (safe: glob-meaningful chars were
  # already rejected above; `read -ra` never globs regardless).
  local -a tokens
  read -ra tokens <<< "$segment"

  local -a paths=()
  local tok
  for tok in "${tokens[@]}"; do
    [[ "$tok" == -* ]] && continue   # flag token, not a path
    paths+=("$tok")
  done

  # No path args -> nothing resolvable to downgrade, stay HIGH.
  [ "${#paths[@]}" -eq 0 ] && return 1

  local p
  for p in "${paths[@]}"; do
    [[ "$p" =~ $V11_SCRATCHPAD_ERE ]] || return 1
  done

  V11_RISK_PATH_CONTEXT_RESOLVED="${paths[*]}"
  return 0
}

# improvements/76: may guard-write-gates let this Write/Edit through with no
# task in_progress? True (0) for the harness scratchpad, and for the /handoff
# skill's own files directly under $SESSIONS_ROOT/<project>/ (exact basenames:
# a nested dir or handoff.md.bak stays gated). Scoped to the write gate only:
# v11_is_metadata_file is also the early exit in detect-project, verify-syntax
# and guard-enforcement, and widening it would stop a handoff.md read binding
# the project and skip JSON validation of a hand-written handoff-tasks.json.
# The path is canonicalized first (realpath -m resolves relative paths, `..`
# and symlinks), so sessions/x/../../src/foo.py never matches; any resolution
# failure gates. Rollback: V11_WRITE_GATE_SCRATCH_EXEMPT=off.
v11_is_write_gate_exempt() {
  local path="$1" resolved root rest project base
  [ "${V11_WRITE_GATE_SCRATCH_EXEMPT:-on}" = "off" ] && return 1
  [ -z "$path" ] && return 1
  resolved=$(realpath -m -- "$path" 2>/dev/null) || return 1
  [ -n "$resolved" ] || return 1

  [[ "$resolved" =~ $V11_SCRATCHPAD_ERE ]] && return 0

  root=$(realpath -m -- "$SESSIONS_ROOT" 2>/dev/null) || return 1
  [ -n "$root" ] || return 1
  case "$resolved" in
    "$root"/*/*) ;;
    *) return 1 ;;
  esac
  rest="${resolved#"$root"/}"
  project="${rest%%/*}"
  base="${rest#*/}"
  case "$base" in
    */*) return 1 ;;
    *) ;;
  esac
  v11_valid_project_slug "$project" || return 1
  case "$base" in
    .session-summary.md|.handoff-steer.md|.handoff-addendum.md|handoff.md|handoff-tasks.json|peers.json) return 0 ;;
    *) return 1 ;;
  esac
}

v11_check_risk() {
  local RISK="$(v11_risk_level)"

  # Low risk always allowed
  [ "$RISK" != "high" ] && return 0

  # High-risk pattern identification
  local MATCHED_PATTERN="" RISK_DESCRIPTION=""

  # Requires bash 4.0+ (Linux default; macOS ships 3.2 — use brew bash)
  declare -A PATTERNS=(
    ["rm -rf"]="Recursive force delete"
    ["rm -fr"]="Recursive force delete"
    ["rm -Rf"]="Recursive force delete"
    ["rm -fR"]="Recursive force delete"
    ["rm -R"]="Recursive delete"
    ["rm -r"]="Recursive delete"
    ["rm --recursive"]="Recursive delete"
    ["DROP DATABASE"]="Database deletion"
    ["DROP TABLE"]="Table deletion"
    ["TRUNCATE"]="Table truncation"
    ["DELETE FROM"]="Data deletion"
    ["docker system prune -a"]="Delete all Docker images"
    ["docker volume rm"]="Docker volume deletion"
    ["git push --force"]="Force push to remote"
    ["git push -f"]="Force push to remote"
    ["git reset --hard"]="Hard reset (loses commits)"
    ["git clean -f"]="Force clean untracked files"
    ["shutdown"]="System shutdown/reboot"
    ["reboot"]="System shutdown/reboot"
    ["mkfs"]="Format filesystem"
    ["dd if="]="Direct disk write"
    ["chown -R"]="Recursive ownership change"
    ["chmod -R 777"]="Dangerous permission change"
  )

  for PATTERN in "${!PATTERNS[@]}"; do
    if grep -qiF "$PATTERN" <<<"$V11_COMMAND"; then
      MATCHED_PATTERN="$PATTERN"
      RISK_DESCRIPTION="${PATTERNS[$PATTERN]}"
      break
    fi
  done

  if [ -z "$MATCHED_PATTERN" ]; then
    MATCHED_PATTERN="(unrecognized high-risk pattern)"
    RISK_DESCRIPTION="Destructive operation detected by risk classifier"
  fi

  # Improvement #20 (2026-08-06): path-context downgrade for scratchpad-scoped
  # recursive-force deletes. `rm -rf <path>` inside the harness-designated
  # session scratchpad is not the same risk as `rm -rf` on project/production
  # data, but pattern-only classification treats them identically -- training
  # operators to route around the guard on the deletes that ARE dangerous.
  # See improvements/20-risk-gate-path-context.md. Rollback:
  # V11_RISK_PATH_CONTEXT=off restores pattern-only classification exactly.
  if [ "$RISK_DESCRIPTION" = "Recursive force delete" ] \
     && [ "${V11_RISK_PATH_CONTEXT:-on}" != "off" ] \
     && v11_rm_is_scratchpad_only_delete "$V11_COMMAND"; then
    echo "guard-enforcement: risk downgraded HIGH→LOW (scratchpad-scoped recursive delete): $V11_RISK_PATH_CONTEXT_RESOLVED" >&2
    return 0
  fi

  # Check A4 auto-approval (project-local autonomy state)
  local AUTONOMY_FILE=""
  v11_detect_project "$V11_FILE_PATH"
  # Fallback: extract path from command if project still unknown
  if [ -z "$V11_PROJECT" ] && [ -n "$V11_COMMAND" ]; then
    local CMD_PATH
    CMD_PATH=$(printf '%s' "$V11_COMMAND" | grep -oE "$HERCULES_ROOT/[^ ]+" | head -1)
    [ -n "$CMD_PATH" ] && v11_detect_project "$CMD_PATH"
  fi
  if [ -n "$V11_PROJECT" ] && [ -f "$SESSIONS_ROOT/$V11_PROJECT/.autonomy-state" ]; then
    AUTONOMY_FILE="$SESSIONS_ROOT/$V11_PROJECT/.autonomy-state"
  elif [ -n "$V11_PROJECT" ] && [ -f "$HERCULES_ROOT/$V11_PROJECT/.autonomy-state" ]; then
    AUTONOMY_FILE="$HERCULES_ROOT/$V11_PROJECT/.autonomy-state"
  fi

  if [ -n "$AUTONOMY_FILE" ] && [ -f "$AUTONOMY_FILE" ]; then
    local LEVEL="$(v11_autonomy_level "$AUTONOMY_FILE")"

    if [ "$LEVEL" -ge 4 ]; then
      # Exact pattern match
      if jq -e --arg p "$MATCHED_PATTERN" \
          '.high_risk_history // [] | any(. == $p)' \
          "$AUTONOMY_FILE" >/dev/null 2>&1; then
        echo "[$(date -Iseconds)] HIGH RISK AUTO-APPROVED (A4): $MATCHED_PATTERN — $V11_COMMAND" \
            >> "$METRICS_DIR/autonomy-changes.log"
        return 0
      fi

      # Prefix match
      local CMD_PREFIX="$(printf '%s' "$V11_COMMAND" | awk '{print $1" "$2" "$3}')"
      if jq -e --arg p "$CMD_PREFIX" \
          '.high_risk_history // [] | any(startswith($p))' \
          "$AUTONOMY_FILE" >/dev/null 2>&1; then
        echo "[$(date -Iseconds)] HIGH RISK AUTO-APPROVED (A4 prefix): $CMD_PREFIX — $V11_COMMAND" \
            >> "$METRICS_DIR/autonomy-changes.log"
        return 0
      fi
    fi
  fi

  # Block with message.
  # V11.34.3: the level goes through v11_autonomy_level so a display-form
  # ("A3") state file renders as A3 rather than the old double-prefixed "AA3",
  # and BLOCK_REASON names why auto-approval did not apply — a granted A5 with
  # an empty high_risk_history previously read as though the grant was ignored.
  local CURRENT_LEVEL="?" BLOCK_REASON=""
  if [ -n "$AUTONOMY_FILE" ] && [ -f "$AUTONOMY_FILE" ]; then
    local CUR_LEVEL HIST_LEN
    CUR_LEVEL="$(v11_autonomy_level "$AUTONOMY_FILE")"
    CURRENT_LEVEL="$CUR_LEVEL"
    HIST_LEN="$(jq -r '.high_risk_history // [] | length' "$AUTONOMY_FILE" 2>/dev/null)"
    case "$HIST_LEN" in ''|*[!0-9]*) HIST_LEN=0 ;; esac
    if [ "$CUR_LEVEL" -lt 4 ]; then
      BLOCK_REASON="level is below A4 — high-risk auto-approval requires A4+"
    elif [ "$HIST_LEN" -eq 0 ]; then
      BLOCK_REASON="A$CUR_LEVEL is sufficient, but high_risk_history is empty — no high-risk pattern has been approved for this project yet"
    else
      BLOCK_REASON="A$CUR_LEVEL is sufficient, but this pattern is not in high_risk_history ($HIST_LEN entr$([ "$HIST_LEN" -eq 1 ] && printf 'y' || printf 'ies'))"
    fi
  else
    BLOCK_REASON="no .autonomy-state resolved for this project — defaults to A0 (manual)"
  fi

  # Write to stderr so Claude Code surfaces the reason to the user.
  # Bug 2026-06-01: previously cat to stdout; harness reported "No stderr output".
  cat >&2 <<EOF
HIGH RISK OPERATION BLOCKED

Risk Level: HIGH
Operation: $RISK_DESCRIPTION
Pattern: $MATCHED_PATTERN
Command: $V11_COMMAND

Current Autonomy Level: A$CURRENT_LEVEL
Not auto-approved: $BLOCK_REASON
Note: A4+ with a matching high_risk_history entry can auto-approve.

This operation can cause data loss or system damage.
To proceed, get explicit user approval.
EOF

  return 2
}

# Check autonomy grants for medium-risk operations.
# Returns 0 if auto-approved, 1 if needs user approval.
# Used by guard-enforcement hook.
v11_check_autonomy() {
  local RISK=$(v11_risk_level)

  # Low risk always allowed
  [ "$RISK" == "low" ] && return 0

  # High risk handled by v11_check_risk
  [ "$RISK" == "high" ] && return 0

  # Medium risk - check autonomy level
  local AUTONOMY_STATE=""

  # Detect project for project-specific autonomy
  v11_detect_project "$V11_FILE_PATH"
  if [ -z "$V11_PROJECT" ] && [ -n "$V11_COMMAND" ]; then
    local CMD_PATH=$(printf '%s' "$V11_COMMAND" | grep -oE "$HERCULES_ROOT/[^ ]+" | head -1)
    [ -n "$CMD_PATH" ] && v11_detect_project "$CMD_PATH"
  fi

  # Load autonomy state (project-specific only, no global fallback)
  # HS-009 (Wave 3c): jq empty validation — a 0-byte or malformed state file would
  # otherwise set empty AUTONOMY_STATE which falls through to LEVEL=0 silently.
  # Consistent with sync-tasks:81 and track-autonomy:84 patterns.
  if [ -n "$V11_PROJECT" ] && [ -f "$SESSIONS_ROOT/$V11_PROJECT/.autonomy-state" ] && \
     [ -s "$SESSIONS_ROOT/$V11_PROJECT/.autonomy-state" ] && \
     jq empty "$SESSIONS_ROOT/$V11_PROJECT/.autonomy-state" 2>/dev/null; then
    AUTONOMY_STATE=$(cat "$SESSIONS_ROOT/$V11_PROJECT/.autonomy-state" 2>/dev/null)
  fi

  # No project detected OR no state file → default to A0 (manual mode)
  # This is safe: guard-risk will handle blocking if needed
  [ -z "$AUTONOMY_STATE" ] && return 1

  # V11.34.3: normalize at read. This also subsumes the old empty/"null"
  # guard, whose `[ -z ] || [ == null ] && LEVEL=0` chaining relied on
  # ||/&& precedence rather than stating the intent.
  local LEVEL
  LEVEL="$(v11_normalize_autonomy_level "$(printf '%s' "$AUTONOMY_STATE" | jq -r '.level // 0' 2>/dev/null)")"

  # A3+: all medium auto-approved
  if [ "$LEVEL" -ge 3 ]; then
    echo "Autonomy A3: all medium-risk auto-approved"
    return 0
  fi

  # A2: check grants for file pattern match
  if [ "$LEVEL" -ge 2 ] && [ -n "$V11_FILE_PATH" ]; then
    while IFS= read -r grant; do
      [ -z "$grant" ] || [ "$grant" == "null" ] && continue
      local PATTERN=$(printf '%s' "$grant" | jq -r '.pattern // empty')
      local GTYPE=$(printf '%s' "$grant" | jq -r '.type // "glob"')
      [ -z "$PATTERN" ] && continue

      case "$GTYPE" in
        glob)
          # shellcheck disable=SC2053
          if [[ "$V11_FILE_PATH" == $PATTERN ]]; then
            echo "Autonomy A2: grant matched $PATTERN"
            return 0
          fi
          ;;
        regex)
          # HS-002 (Wave 3a): ReDoS + flag-injection defense.
          # PATTERN comes from .autonomy-state which is writable by any teammate in
          # the project. Unvalidated patterns in grep -qE allow (a) catastrophic
          # backtracking like (a+)+ → CPU exhaustion, (b) a pattern starting with
          # "-" being interpreted as a grep flag. Mitigations:
          #   - length cap 100 (long patterns are almost always adversarial)
          #   - reject common catastrophic-backtracking shapes
          #   - add -- to stop option parsing
          if [ ${#PATTERN} -gt 100 ]; then
            echo "Autonomy: regex grant rejected (pattern > 100 chars)" >&2
            continue
          fi
          # Detect nested quantifiers like (x+)+, (x*)*, (x+)*, (x*)+ — classic ReDoS
          if grep -qE '\([^)]*[+*][^)]*\)[+*]' <<<"$PATTERN"; then
            echo "Autonomy: regex grant rejected (nested quantifier / ReDoS shape)" >&2
            continue
          fi
          if grep -qE -- "$PATTERN" <<<"$V11_FILE_PATH" 2>/dev/null; then
            echo "Autonomy A2: grant matched regex $PATTERN"
            return 0
          fi
          ;;
        prefix)
          if [[ "$V11_FILE_PATH" == "$PATTERN"* ]]; then
            echo "Autonomy A2: grant matched prefix $PATTERN"
            return 0
          fi
          ;;
      esac
    done < <(printf '%s' "$AUTONOMY_STATE" | jq -c '.grants // [] | .[]' 2>/dev/null)
  fi

  # A1: check approved_categories
  if [ "$LEVEL" -ge 1 ]; then
    local CATEGORY=""
    if [ -n "$V11_FILE_PATH" ]; then
      local EXT="${V11_FILE_PATH##*.}"
      case "$EXT" in
        ts|tsx|js|jsx) CATEGORY="typescript" ;;
        py)            CATEGORY="python" ;;
        sh|bash)       CATEGORY="shell" ;;
        md)            CATEGORY="markdown" ;;
        json|yaml|yml) CATEGORY="config" ;;
      esac
    elif [ -n "$V11_COMMAND" ]; then
      case "$V11_COMMAND" in
        git\ *)                    CATEGORY="git" ;;
        docker\ *)                 CATEGORY="docker" ;;
        npm\ *|yarn\ *|pnpm\ *)   CATEGORY="npm" ;;
      esac
    fi

    if [ -n "$CATEGORY" ]; then
      local MATCH=$(printf '%s' "$AUTONOMY_STATE" | jq -e \
          --arg c "$CATEGORY" '.approved_categories // [] | any(. == $c)' 2>/dev/null)
      if [ "$MATCH" == "true" ]; then
        echo "Autonomy A1: category '$CATEGORY' pre-approved"
        return 0
      fi
    fi
  fi

  # No matching grant - needs approval
  return 1
}

# Check file ownership in Agent Teams context.
# Validates that current agent can write this file based on .formation-registry.json.
# Returns 0 if allowed, 1 if blocked (conflict).
# Used by guard-write-gates hook.
v11_check_file_ownership() {
  local file_path="$1"
  local current_agent_id="${V11_AGENT_ID:-unknown}"

  # Find formation registry — search project session dir, not CWD
  local registry=""
  v11_detect_project "$file_path"
  if [ -n "$V11_PROJECT" ]; then
    if [ -f "$SESSIONS_ROOT/$V11_PROJECT/.formation-registry.json" ]; then
      registry="$SESSIONS_ROOT/$V11_PROJECT/.formation-registry.json"
    elif [ -f "$HERCULES_ROOT/$V11_PROJECT/.formation-registry.json" ]; then
      registry="$HERCULES_ROOT/$V11_PROJECT/.formation-registry.json"
    fi
  fi

  # Early exit if no registry (not in Agent Team)
  [ -z "$registry" ] && return 0

  # Validate JSON structure
  if ! jq empty "$registry" >/dev/null 2>&1; then
    echo "WARNING: Invalid $registry, skipping ownership check" >&2
    return 0
  fi

  # Extract all teammates
  local teammates
  teammates=$(jq -r '.teammates | keys[]' "$registry" 2>/dev/null)

  # Check each teammate's ownership
  while IFS= read -r role; do
    [ -z "$role" ] && continue

    local owner_id
    owner_id=$(jq -r ".teammates[\"$role\"].agent_id" "$registry" 2>/dev/null)

    # Check exact file match
    if jq -e --arg fp "$file_path" ".teammates[\"$role\"].ownership.files | map(. == \$fp) | any" \
       "$registry" >/dev/null 2>&1; then
      if [ "$owner_id" != "$current_agent_id" ]; then
        cat >&2 <<EOF
FILE OWNERSHIP CONFLICT: $file_path
  Owner: $role (agent_id: $owner_id)
  Attempted write by: agent_id: $current_agent_id

Coordinate via task or update .formation-registry.json ownership.
EOF
        return 1
      fi
      return 0
    fi

    # Check directory match (file path starts with owned directory)
    if jq -e --arg fp "$file_path" ".teammates[\"$role\"].ownership.directories | map(. as \$dir | (\$fp | startswith(\$dir))) | any" \
       "$registry" >/dev/null 2>&1; then
      if [ "$owner_id" != "$current_agent_id" ]; then
        cat >&2 <<EOF
FILE OWNERSHIP CONFLICT: $file_path
  Owner: $role (agent_id: $owner_id)
  Attempted write by: agent_id: $current_agent_id

Coordinate via task or update .formation-registry.json ownership.
EOF
        return 1
      fi
      return 0
    fi

    # Check glob patterns (basic implementation using bash patterns)
    local patterns
    patterns=$(jq -r ".teammates[\"$role\"].ownership.patterns[]" "$registry" 2>/dev/null)
    while IFS= read -r pattern; do
      [ -z "$pattern" ] && continue
      # Enable globstar for ** matching
      shopt -s globstar extglob
      # shellcheck disable=SC2053
      if [[ "$file_path" == $pattern ]]; then
        if [ "$owner_id" != "$current_agent_id" ]; then
          cat >&2 <<EOF
FILE OWNERSHIP CONFLICT: $file_path
  Owner: $role (agent_id: $owner_id)
  Pattern matched: $pattern
  Attempted write by: agent_id: $current_agent_id

Coordinate via task or update .formation-registry.json ownership.
EOF
          return 1
        fi
        return 0
      fi
    done <<< "$patterns"
  done <<< "$teammates"

  # File not owned by anyone (new file) - allow with info
  echo "INFO: File $file_path is not assigned to any teammate (new file allowed)" >&2
  return 0
}

# --- V11: Artifact Handoff Functions ---

# Inject upstream artifacts from completed blocking tasks into context.
# Reads task_artifacts from project state file for tasks in blockedBy list.
# Usage: v11_inject_upstream_artifacts PROJECT BLOCKED_BY_IDS...
# Output: JSON array of upstream artifacts on stdout.
v11_inject_upstream_artifacts() {
  local project="$1"
  shift
  local blocked_by_ids=("$@")

  local state_file="$TASK_STATE_DIR/${project}.json"
  [ ! -f "$state_file" ] && echo "[]" && return 0

  local result="[]"
  for task_id in "${blocked_by_ids[@]}"; do
    local arts
    arts=$(jq -r --arg id "$task_id" '.task_artifacts[$id] // empty' "$state_file" 2>/dev/null)
    if [ -n "$arts" ] && [ "$arts" != "null" ]; then
      # Load external artifact_refs content if referenced
      local expanded_arts="$arts"
      local ref_count
      ref_count=$(printf '%s' "$arts" | jq '.artifact_refs | length' 2>/dev/null)
      if [ "${ref_count:-0}" -gt 0 ]; then
        # For each artifact_ref, read file contents if <=2KB (inline); mark larger ones available-only
        while IFS= read -r ref; do
          [ -z "$ref" ] || [ "$ref" == "null" ] && continue
          local ref_path
          ref_path=$(printf '%s' "$ref" | jq -r '.path // empty')
          [ -z "$ref_path" ] && continue
          local full_path="$HERCULES_ROOT/$ref_path"
          if [ -f "$full_path" ]; then
            local size
            size=$(wc -c < "$full_path" 2>/dev/null || echo 9999)
            if [ "${size:-9999}" -le 2048 ]; then
              local content
              content=$(cat "$full_path" 2>/dev/null || true)
              expanded_arts=$(printf '%s' "$expanded_arts" | jq \
                --arg p "$ref_path" --arg c "$content" '
                .artifact_refs = [.artifact_refs[] |
                  if .path == $p then . + {"content": $c, "content_available": true}
                  else .
                  end]
              ' 2>/dev/null)
            else
              expanded_arts=$(printf '%s' "$expanded_arts" | jq \
                --arg p "$ref_path" '
                .artifact_refs = [.artifact_refs[] |
                  if .path == $p then . + {"content_available": true}
                  else .
                  end]
              ' 2>/dev/null)
            fi
          fi
        done < <(printf '%s' "$arts" | jq -c '.artifact_refs // [] | .[]' 2>/dev/null)
      fi

      result=$(printf '%s' "$result" | jq \
        --arg id "$task_id" \
        --argjson arts "${expanded_arts:-$arts}" '
        . + [{"task_id": $id, "artifacts": $arts}]
      ')
    fi
  done

  printf '%s' "$result"
}

# Store a large artifact externally and return an artifact_ref object.
# Artifacts >2KB use external storage per V11 convention.
# Usage: v11_store_artifact_ref PROJECT TASK_ID NAME CONTENT [SUMMARY]
# Output: JSON artifact_ref object on stdout.
v11_store_artifact_ref() {
  local project="$1" task_id="$2" name="$3" content="$4" summary="${5:-}"

  local artifact_dir="$SESSIONS_ROOT/$project/artifacts/$task_id"
  mkdir -p "$artifact_dir"

  local artifact_path="$artifact_dir/$name"
  printf '%s' "$content" > "$artifact_path"

  local size_bytes
  size_bytes=$(wc -c < "$artifact_path")

  local rel_path="sessions/$project/artifacts/$task_id/$name"

  jq -n \
    --arg name "$name" \
    --arg path "$rel_path" \
    --arg summary "${summary:-$name}" \
    --argjson size "$size_bytes" \
    '{"name": $name, "path": $path, "summary": $summary, "size_bytes": $size}'
}

# Read an artifact from external storage by its ref.
# Usage: v11_read_artifact_ref ARTIFACT_REF_JSON
# Output: File contents on stdout.
v11_read_artifact_ref() {
  local ref_json="$1"

  local rel_path
  rel_path=$(printf '%s' "$ref_json" | jq -r '.path // empty')
  [ -z "$rel_path" ] && return 1

  local full_path="$HERCULES_ROOT/$rel_path"
  [ ! -f "$full_path" ] && return 1

  cat "$full_path"
}

# Ensure artifact directory exists for a project/task.
# Usage: v11_ensure_artifact_dir PROJECT TASK_ID
# Output: Path to artifact directory on stdout.
v11_ensure_artifact_dir() {
  local project="$1" task_id="$2"
  local dir="$SESSIONS_ROOT/$project/artifacts/$task_id"
  mkdir -p "$dir"
  printf '%s' "$dir"
}

# --- V11.15: Per-Task Review Config ---

# Resolve the per-task review config for a project, applying schema defaults
# for any missing key. Reads sessions/{project}/.review-config.json if present.
# Output: a complete normalized JSON object on stdout (always all keys).
# Usage: v11_resolve_review_config PROJECT
v11_resolve_review_config() {
  local project="$1"
  local defaults='{"enabled":true,"scope":"all","sample_rate":1,"min_difficulty_to_review":1,"severity_autofix":["LOW","MEDIUM","HIGH"],"severity_escalate":["CRITICAL"]}'
  local cfg_file="$SESSIONS_ROOT/$project/.review-config.json"

  if [ -n "$project" ] && [ -f "$cfg_file" ] && [ -s "$cfg_file" ]; then
    local user_cfg
    user_cfg="$(jq -c '.' "$cfg_file" 2>/dev/null)" || user_cfg=""
    if [ -n "$user_cfg" ]; then
      # User keys override defaults; missing keys fall back to defaults.
      printf '%s\n' "$defaults" | jq -c --argjson u "$user_cfg" '. + $u' 2>/dev/null && return 0
    fi
  fi
  printf '%s\n' "$defaults"
}

# Decide whether a task should be reviewed, given the resolved config and the
# task's risk/complexity. Echoes "yes" or "no". scope=sampled uses task_index.
# Usage: v11_should_review_task CONFIG_JSON RISK COMPLEXITY [TASK_INDEX]
v11_should_review_task() {
  local cfg="$1" risk="$2" complexity="$3" task_index="${4:-0}"
  local enabled scope sample_rate
  # NOTE: jq '.enabled // true' is WRONG — `false // true` is `true` in jq
  # (false is treated as empty by //). Use has() to distinguish absent vs false.
  enabled="$(printf '%s' "$cfg" | jq -r 'if has("enabled") then .enabled else true end')"
  [ "$enabled" != "true" ] && { printf 'no'; return 0; }
  scope="$(printf '%s' "$cfg" | jq -r '.scope // "all"')"
  case "$scope" in
    all) printf 'yes' ;;
    risk-gated)
      if [ "$risk" = "medium" ] || [ "$risk" = "high" ] || \
         [ "$complexity" = "complex" ] || [ "$complexity" = "novel" ]; then
        printf 'yes'
      else
        printf 'no'
      fi ;;
    sampled)
      if [ "$complexity" = "complex" ] || [ "$complexity" = "novel" ]; then
        printf 'yes'
      else
        sample_rate="$(printf '%s' "$cfg" | jq -r '.sample_rate // 1')"
        if [ "$sample_rate" -le 1 ] 2>/dev/null || \
           [ $(( task_index % sample_rate )) -eq 0 ] 2>/dev/null; then
          printf 'yes'
        else
          printf 'no'
        fi
      fi ;;
    *) printf 'yes' ;;
  esac
}

# --- V11: Schema Validation Functions ---

# HS-006 (Wave 3c): derive from V11_HOME (already resolved at top of file) instead of
# fragile 3× dirname chain that breaks if common.sh ever moves. V11_HOME is the
# canonical v11 root; schemas always live at $V11_HOME/schemas.
V11_SCHEMA_DIR="${V11_SCHEMA_DIR:-$V11_HOME/schemas}"

# Validate JSON data against a JSON Schema.
# Uses ajv-cli if available, falls back to jq structural checks.
# Returns 0 if valid, 1 if invalid (with errors on stderr).
# Usage: v11_validate_json JSON_STRING SCHEMA_NAME
#   JSON_STRING: The JSON to validate (string, not file path)
#   SCHEMA_NAME: Schema filename in schemas/ (e.g., "task-metadata.schema.json")
v11_validate_json() {
  local json_data="$1" schema_name="$2"
  local schema_file="$V11_SCHEMA_DIR/$schema_name"

  # Schema file must exist
  if [ ! -f "$schema_file" ]; then
    echo "WARN: Schema not found: $schema_file" >&2
    return 0  # Missing schema = pass (advisory mode)
  fi

  # Try ajv-cli first (full JSON Schema validation)
  if command -v ajv >/dev/null 2>&1; then
    local tmpfile
    tmpfile=$(mktemp /tmp/v11-validate-XXXXXX.json)
    printf '%s' "$json_data" > "$tmpfile"
    local result
    result=$(ajv validate -s "$schema_file" -d "$tmpfile" 2>&1)
    local rc=$?
    rm -f "$tmpfile"
    if [ $rc -ne 0 ]; then
      echo "SCHEMA VALIDATION FAILED ($schema_name):" >&2
      echo "$result" >&2
    fi
    return $rc
  fi

  # Fallback: jq structural validation (checks required fields and enums)
  v11_validate_json_jq "$json_data" "$schema_name"
}

# Lightweight jq-based validation fallback.
# Checks: valid JSON, required fields, enum constraints.
# Does NOT validate: conditional schemas (allOf/if-then), patterns, refs.
v11_validate_json_jq() {
  local json_data="$1" schema_name="$2"
  local errors=""

  # Must be valid JSON
  if ! printf '%s' "$json_data" | jq empty 2>/dev/null; then
    echo "SCHEMA VALIDATION FAILED: Invalid JSON" >&2
    return 1
  fi

  case "$schema_name" in
    task-metadata.schema.json)
      # Required: project, sprint, risk
      local project sprint risk
      project=$(printf '%s' "$json_data" | jq -r '.project // empty')
      sprint=$(printf '%s' "$json_data" | jq -r '.sprint // empty')
      risk=$(printf '%s' "$json_data" | jq -r '.risk // empty')

      [ -z "$project" ] && errors="${errors}Missing required field: project\n"
      [ -z "$sprint" ] && errors="${errors}Missing required field: sprint\n"
      [ -z "$risk" ] && errors="${errors}Missing required field: risk\n"

      # Enum: risk
      if [ -n "$risk" ] && [[ ! "$risk" =~ ^(low|medium|high)$ ]]; then
        errors="${errors}Invalid risk value: '$risk' (must be low|medium|high)\n"
      fi

      # Enum: complexity (if present)
      local complexity
      complexity=$(printf '%s' "$json_data" | jq -r '.complexity // empty')
      if [ -n "$complexity" ] && [[ ! "$complexity" =~ ^(novel|complex|medium|routine)$ ]]; then
        errors="${errors}Invalid complexity: '$complexity' (must be novel|complex|medium|routine)\n"
      fi

      # Enum: scope (if present)
      local scope
      scope=$(printf '%s' "$json_data" | jq -r '.scope // empty')
      if [ -n "$scope" ] && [[ ! "$scope" =~ ^(small|medium|large)$ ]]; then
        errors="${errors}Invalid scope: '$scope' (must be small|medium|large)\n"
      fi

      # Contradiction: routine + medium/high risk
      if [ "$complexity" = "routine" ] && [[ "$risk" =~ ^(medium|high)$ ]]; then
        errors="${errors}Contradiction: routine complexity + $risk risk (recategorize)\n"
      fi

      # High risk requires complexity + scope
      if [ "$risk" = "high" ]; then
        [ -z "$complexity" ] && errors="${errors}High risk requires complexity field\n"
        [ -z "$scope" ] && errors="${errors}High risk requires scope field\n"
      fi
      ;;

    formation-registry.schema.json)
      local formation project teammates
      formation=$(printf '%s' "$json_data" | jq -r '.formation // empty')
      project=$(printf '%s' "$json_data" | jq -r '.project // empty')
      teammates=$(printf '%s' "$json_data" | jq -r '.teammates // empty')

      [ -z "$formation" ] && errors="${errors}Missing required field: formation\n"
      [ -z "$project" ] && errors="${errors}Missing required field: project\n"
      [ "$teammates" = "" ] || [ "$teammates" = "null" ] && errors="${errors}Missing required field: teammates\n"

      # Teammate count: 1-5
      local count
      count=$(printf '%s' "$json_data" | jq '.teammates | length' 2>/dev/null)
      if [ "${count:-0}" -gt 5 ]; then
        errors="${errors}Too many teammates: $count (max 5)\n"
      fi
      ;;

    autonomy-state.schema.json)
      local level
      level=$(printf '%s' "$json_data" | jq -r '.level // empty')
      [ -z "$level" ] && errors="${errors}Missing required field: level\n"
      if [ -n "$level" ]; then
        case "$level" in
          # Non-digit (incl. display form "A3" and floats like "3.0") is
          # malformed input, not a range violation — flag it explicitly
          # instead of letting bare arithmetic error out and get swallowed.
          *[!0-9]*) errors="${errors}Invalid level: $level (must be 0-5)\n" ;;
          *)
            if [ "$level" -lt 0 ] || [ "$level" -gt 5 ]; then
              errors="${errors}Invalid level: $level (must be 0-5)\n"
            fi
            ;;
        esac
      fi
      ;;

    *)
      # Unknown schema — just validate JSON syntax
      ;;
  esac

  if [ -n "$errors" ]; then
    echo "SCHEMA VALIDATION FAILED ($schema_name):" >&2
    printf '%b' "$errors" >&2
    return 1
  fi
  return 0
}

# --- V11: Tool Policy Cascade Functions ---

# Tool group definitions (inline for performance — no file I/O)
V11_GROUP_READ="Read Grep Glob"
V11_GROUP_WRITE="Write Edit"
V11_GROUP_EXEC="Bash"
V11_GROUP_TASK="TaskCreate TaskUpdate TaskList TaskGet"
V11_GROUP_TEAM="SendMessage TeamCreate"
V11_GROUP_SEARCH="WebSearch WebFetch"
V11_GROUP_FS="Read Write Edit Grep Glob"
V11_GROUP_ALL_READ="Read Grep Glob WebSearch WebFetch"
V11_GROUP_TEST="Bash"
V11_GROUP_DEPLOY="Bash"

# Expand a group name to tool list. Returns space-separated tool names.
# Usage: v11_expand_group "group:read"
v11_expand_group() {
  case "$1" in
    group:read)     echo "$V11_GROUP_READ" ;;
    group:write)    echo "$V11_GROUP_WRITE" ;;
    group:exec)     echo "$V11_GROUP_EXEC" ;;
    group:task)     echo "$V11_GROUP_TASK" ;;
    group:team)     echo "$V11_GROUP_TEAM" ;;
    group:search)   echo "$V11_GROUP_SEARCH" ;;
    group:fs)       echo "$V11_GROUP_FS" ;;
    group:all-read) echo "$V11_GROUP_ALL_READ" ;;
    group:test)     echo "$V11_GROUP_TEST" ;;
    group:deploy)   echo "$V11_GROUP_DEPLOY" ;;
    *)              echo "$1" ;;  # Not a group, return as-is (individual tool)
  esac
}

# Expand a profile name to its included tool list.
# Usage: v11_expand_profile "coding"
v11_expand_profile() {
  case "$1" in
    full)     echo "$V11_GROUP_READ $V11_GROUP_WRITE $V11_GROUP_EXEC $V11_GROUP_TASK $V11_GROUP_TEAM $V11_GROUP_SEARCH" ;;
    coding)   echo "$V11_GROUP_FS $V11_GROUP_EXEC $V11_GROUP_TASK" ;;
    testing)  echo "$V11_GROUP_READ $V11_GROUP_TEST $V11_GROUP_TASK" ;;
    readonly) echo "$V11_GROUP_READ $V11_GROUP_TASK" ;;
    minimal)  echo "$V11_GROUP_TASK" ;;
    *)        echo "" ;;  # Unknown profile
  esac
}

# Check if a tool is in a space-separated list.
# Usage: v11_tool_in_list "Read" "$tool_list"
v11_tool_in_list() {
  local tool="$1" list="$2"
  case " $list " in
    *" $tool "*) return 0 ;;
    *) return 1 ;;
  esac
}

# Resolve tool policy for current agent/role/formation.
# Uses deny-wins semantics: if any layer denies, tool is denied.
#
# Reads .formation-registry.json in current directory (or session dir).
# Requires V11_AGENT_ID to be set.
#
# Usage: v11_resolve_tool_policy TOOL_NAME [REGISTRY_PATH]
# Returns: 0=allowed, 1=denied (with reason on stdout)
# Sets: V11_POLICY_REASON (human-readable explanation)
v11_resolve_tool_policy() {
  local tool_name="$1"
  local registry_path="${2:-.formation-registry.json}"
  V11_POLICY_REASON=""

  # No registry = no policy enforcement
  if [ ! -f "$registry_path" ]; then
    V11_POLICY_REASON="No formation registry — all tools allowed"
    return 0
  fi

  # No agent ID = can't check policy
  if [ -z "${V11_AGENT_ID:-}" ]; then
    V11_POLICY_REASON="No agent ID — policy not enforced"
    return 0
  fi

  local registry
  registry=$(cat "$registry_path" 2>/dev/null)
  [ -z "$registry" ] && return 0

  # Find current agent's role
  local current_role=""
  current_role=$(printf '%s' "$registry" | jq -r --arg aid "$V11_AGENT_ID" '
    .teammates // {} | to_entries[]
    | select(.value.agent_id == $aid)
    | .key
  ' 2>/dev/null)

  [ -z "$current_role" ] && {
    V11_POLICY_REASON="Agent $V11_AGENT_ID not in registry — default allow"
    return 0
  }

  # Layer 1: Formation defaults
  local default_profile default_deny default_allow
  default_profile=$(printf '%s' "$registry" | jq -r '.tool_policies.defaults.profile // empty' 2>/dev/null)
  default_deny=$(printf '%s' "$registry" | jq -r '.tool_policies.defaults.deny // [] | .[]' 2>/dev/null | tr '\n' ' ')
  default_allow=$(printf '%s' "$registry" | jq -r '.tool_policies.defaults.allow // [] | .[]' 2>/dev/null | tr '\n' ' ')

  # Layer 2: Role overrides (from tool_policies.per_role)
  local role_profile role_deny role_allow
  role_profile=$(printf '%s' "$registry" | jq -r --arg role "$current_role" '.tool_policies.per_role[$role].profile // empty' 2>/dev/null)
  role_deny=$(printf '%s' "$registry" | jq -r --arg role "$current_role" '.tool_policies.per_role[$role].deny // [] | .[]' 2>/dev/null | tr '\n' ' ')
  role_allow=$(printf '%s' "$registry" | jq -r --arg role "$current_role" '.tool_policies.per_role[$role].allow // [] | .[]' 2>/dev/null | tr '\n' ' ')

  # Layer 3: Teammate-level overrides (from teammates.ROLE.tool_policies)
  local teammate_profile teammate_deny teammate_allow
  teammate_profile=$(printf '%s' "$registry" | jq -r --arg role "$current_role" '.teammates[$role].tool_policies.profile // empty' 2>/dev/null)
  teammate_deny=$(printf '%s' "$registry" | jq -r --arg role "$current_role" '.teammates[$role].tool_policies.deny // [] | .[]' 2>/dev/null | tr '\n' ' ')
  teammate_allow=$(printf '%s' "$registry" | jq -r --arg role "$current_role" '.teammates[$role].tool_policies.allow // [] | .[]' 2>/dev/null | tr '\n' ' ')

  # Effective profile: teammate > role > formation default (most specific wins)
  local effective_profile="${teammate_profile:-${role_profile:-$default_profile}}"
  [ -z "$effective_profile" ] && effective_profile="full"

  # Expand profile to allowed tools
  local allowed_tools
  allowed_tools=$(v11_expand_profile "$effective_profile")

  # Add explicit allows from all layers
  for allow_entry in $default_allow $role_allow $teammate_allow; do
    local expanded
    expanded=$(v11_expand_group "$allow_entry")
    allowed_tools="$allowed_tools $expanded"
  done

  # Check if tool is in allowed set
  if ! v11_tool_in_list "$tool_name" "$allowed_tools"; then
    V11_POLICY_REASON="Tool '$tool_name' not in profile '$effective_profile' for role '$current_role'"
    echo "$V11_POLICY_REASON"
    return 1
  fi

  # Deny-wins: check all deny lists from all layers (expand groups)
  local all_denied=""
  for deny_entry in $default_deny $role_deny $teammate_deny; do
    local expanded
    expanded=$(v11_expand_group "$deny_entry")
    all_denied="$all_denied $expanded"
  done

  if v11_tool_in_list "$tool_name" "$all_denied"; then
    V11_POLICY_REASON="Tool '$tool_name' denied for role '$current_role' (deny-wins cascade)"
    echo "$V11_POLICY_REASON"
    return 1
  fi

  V11_POLICY_REASON="Allowed: profile=$effective_profile, role=$current_role"
  return 0
}

# --- V11.16: Durable Append-Only Ledger (ADR-LEDGER §1–§4) ---
#
# Ledger directory layout (ADR §1.1):
#   $METRICS_DIR/ledger/<project>.jsonl        — event log (append-only, never deleted)
#   $METRICS_DIR/ledger/<project>.jsonl.lock   — dedicated flock target (FD 207)
#   $METRICS_DIR/ledger/<project>.seq          — counter state {__seqno__, subjects:{}}
#   $METRICS_DIR/ledger/.migrated/<project>    — migration marker
#
# v11_ledger_path PROJECT TYPE
#   TYPE: jsonl | lock | seq | migrated
#   Returns the absolute path for that ledger artifact on stdout.
#   Validates PROJECT against SEC-C-02 whitelist; returns 1 + logs on failure.
v11_ledger_path() {
    local project="$1" type="$2"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_ledger_path: invalid project name '$project' (SEC-C-02 whitelist)" >&2
        return 1
    fi
    local ledger_dir="${METRICS_DIR}/ledger"
    case "$type" in
        jsonl)    printf '%s' "${ledger_dir}/${project}.jsonl" ;;
        lock)     printf '%s' "${ledger_dir}/${project}.jsonl.lock" ;;
        seq)      printf '%s' "${ledger_dir}/${project}.seq" ;;
        migrated) printf '%s' "${ledger_dir}/.migrated/${project}" ;;
        *)
            echo "v11_ledger_path: unknown type '$type' (must be jsonl|lock|seq|migrated)" >&2
            return 1
            ;;
    esac
}

# v11_normalize_subject SUBJECT
#   Canonical subject normalization per ADR §2.1.
#   The single canonical implementation is the embedded Python helper below;
#   this bash function CALLS that Python — it NEVER re-implements the algorithm.
#   Bash≡Python parity is guaranteed by construction (same code path, not two
#   independent implementations). Output is the normalized string on stdout.
#   Falls back to "__empty__" on any failure (side-effect-never-fails).
#
# CANONICAL PYTHON HELPER path:
#   $V11_HOME/scripts/lib/normalize_subject.py
#   Implemented once; common.sh calls it; replay/migration import it directly.
v11_normalize_subject() {
    local subject="$1"
    python3 "${V11_HOME}/scripts/lib/normalize_subject.py" "$subject" 2>/dev/null || printf '%s' "__empty__"
}

# v11_reapply_terminal_fold  ID STATUS SUBJECT SID NOW [REVIEW_TASK_ID] [ARTIFACTS_JSON]
#   (STATE on stdin → stdout)
#   v11.33 (scratch reconcile): idempotently re-apply a terminal (completed|blocked)
#   transition to a per-session scratch that LOST the update under the FD-201
#   "proceeding unserialized" fallback in hooks/sync-tasks. The durable ledger
#   already captured the event (FD-207, independent lock); this repairs only the
#   derived per-session scratch that scripts/handoff reads.
#
#   PRESENCE-GATED on .open_tasks[$id]: applies the fold ONLY when the task is
#   still open (i.e. the original terminal write was clobbered). Once the task is
#   absent it is a no-op — so N independent reconcilers converge exactly-once and
#   re-draining is safe. This is sound because the clobber is at the whole-STATE
#   level (last atomic write wins): a lost completion loses ALL of its co-located
#   mutations together, so the same presence gate correctly governs the counter
#   fold, the V11.21 sibling flip, AND the task_artifacts persistence below.
#
#   For ev=completed this REPLAYS three effects of the canonical completed branch
#   in hooks/sync-tasks, COPIED VERBATIM (counter math is not re-derived):
#     * counter fold + recent_completed + _terminal_idk tombstone (~sync-tasks:1275-1306)
#     * V11.21 sibling pending_parent→pending transition when REVIEW_TASK_ID is
#       given (~sync-tasks:1352-1359) — a lost transition permanently blocks the
#       paired review task, so it MUST be replayed (E2a).
#     * task_artifacts[$id]=ARTIFACTS_JSON when ARTIFACTS_JSON is an object
#       (~sync-tasks:1366-1370) — review evidence must survive (E2b).
#   str_violated is hard-set to 0: the STR-violation advisory counter bump
#   (dark_code_advisories.completions_without_str, ~sync-tasks:1318-1321) is an
#   ADVISORY-ONLY telemetry counter surfaced by v11-compliance-check Gate 12; a
#   rare under-count of it on the unserialized-fallback path is an ACCEPTED LOSS
#   (E2c) and is deliberately NOT replayed here.
#   If the counter math / sibling / artifacts logic changes there, change it here
#   too — tests/test_sync_tasks_scratch_reconcile.py guards the equivalence.
#
#   Emits the (possibly unchanged) STATE on stdout; on any jq failure emits the
#   input STATE verbatim (never empties the scratch). Never fails the caller.
#   REVIEW_TASK_ID defaults to "" (no sibling flip); ARTIFACTS_JSON defaults to
#   "null" (no artifacts persistence) — 5-arg callers keep the pre-E2 behavior.
v11_reapply_terminal_fold() {
    local id="$1" status="$2" subject="$3" sid="$4" now="$5"
    local rid="${6:-}" arts="${7:-null}" prior="${8:-}"
    # Defensive: an empty ARTIFACTS_JSON would make --argjson fail; coerce to null.
    [ -n "$arts" ] || arts="null"
    printf '%s' "$arts" | jq empty 2>/dev/null || arts="null"
    local state; state="$(cat)"
    case "$status" in
        completed)
            # F36: counter fold mirrors the canonical TaskUpdate(completed) branch
            # in hooks/sync-tasks — drop only the bucket the task was actually in.
            # $prior empty (older marker lines predate this field, or the caller
            # never resolved it) falls back to the original unconditional
            # in_progress decrement, preserving exact pre-fix behavior.
            printf '%s' "$state" | jq \
                --arg id "$id" --arg subject "$subject" --arg sid "$sid" --arg now "$now" \
                --arg rid "$rid" --argjson arts "$arts" --arg prior "$prior" '
                if ($id != "" and (.open_tasks[$id] != null)) then
                    (if $prior == "in_progress" or $prior == "" then .in_progress = ([.in_progress - 1, 0] | max) | .completed += 1
                     elif $prior == "pending" then .pending = ([.pending - 1, 0] | max) | .completed += 1
                     elif $prior == "blocked" then .blocked = ([.blocked - 1, 0] | max) | .completed += 1
                     elif $prior == "completed" then .
                     else .completed += 1
                     end)
                    | .recent_completed = ([{id: $id, subject: $subject, at: $now, session_uuid: $sid}] + (.recent_completed // []))[:10]
                    | .active_task = null
                    | .active_task_ids = ((.active_task_ids // []) | map(select(. != $id)))
                    | .active_agent_id = null
                    | .last_updated = $now
                    | .last_progress_at = $now  # #87: a recovered status change is real progress
                    | if (.open_tasks[$id]._idk) != null then
                        ._terminal_idk = (._terminal_idk // {})
                        | ._terminal_idk[$id] = (
                            .open_tasks[$id]._idk
                            + {terminal_status: "completed", tombstoned_at: $now}
                            + (if .open_tasks[$id].subject != null then {subject: .open_tasks[$id].subject} else {} end)
                            + (if .open_tasks[$id]._tl_epoch != null then {_tl_epoch: .open_tasks[$id]._tl_epoch} else {} end)
                          )
                      else . end
                    # E2a — V11.21 sibling pending_parent→pending (verbatim, gated on $rid)
                    | (if ($rid != "" and (.open_tasks[$rid].metadata.parent_status // "") == "pending_parent")
                       then
                            .open_tasks[$rid].metadata.parent_status = "pending"
                            | .open_tasks[$rid].metadata.parent_unblocked_at = (.last_updated // $now)
                       else . end)
                    # E2b — task_artifacts persistence (verbatim, gated on object)
                    | (if ($arts | type) == "object"
                       then .task_artifacts = ((.task_artifacts // {}) + {($id): $arts})
                       else . end)
                    | .open_tasks = ((.open_tasks // {}) | del(.[$id]))
                else . end
            ' 2>/dev/null || printf '%s' "$state"
            ;;
        blocked)
            printf '%s' "$state" | jq \
                --arg id "$id" --arg subject "$subject" --arg sid "$sid" --arg now "$now" \
                --arg prior "$prior" '
                if ($id != "" and (.open_tasks[$id] != null)) then
                    (if $prior == "in_progress" or $prior == "" then .in_progress = ([.in_progress - 1, 0] | max) | .blocked += 1
                     elif $prior == "pending" then .pending = ([.pending - 1, 0] | max) | .blocked += 1
                     elif $prior == "completed" then .completed = ([.completed - 1, 0] | max) | .blocked += 1
                     elif $prior == "blocked" then .
                     else .blocked += 1
                     end)
                    | .active_task = null
                    | .active_task_ids = ((.active_task_ids // []) | map(select(. != $id)))
                    | .active_agent_id = null
                    | .blocked_tasks = ([{id: $id, subject: $subject, reason: "unspecified", at: $now, session_uuid: $sid}] + (.blocked_tasks // []))[:5]
                    | .last_updated = $now
                    | .last_progress_at = $now  # #87: a recovered status change is real progress
                    | if (.open_tasks[$id]._idk) != null then
                        ._terminal_idk = (._terminal_idk // {})
                        | ._terminal_idk[$id] = (
                            .open_tasks[$id]._idk
                            + {terminal_status: "blocked", tombstoned_at: $now}
                            + (if .open_tasks[$id].subject != null then {subject: .open_tasks[$id].subject} else {} end)
                            + (if .open_tasks[$id]._tl_epoch != null then {_tl_epoch: .open_tasks[$id]._tl_epoch} else {} end)
                          )
                      else . end
                    | .open_tasks = ((.open_tasks // {}) | del(.[$id]))
                else . end
            ' 2>/dev/null || printf '%s' "$state"
            ;;
        *)
            printf '%s' "$state"
            ;;
    esac
}

# v11_apply_reconcile_markers  MARKER_FILE SID NOW   (STATE on stdin → stdout)
#   v11.33: fold EVERY recorded lost terminal transition in MARKER_FILE back into
#   the piped STATE via v11_reapply_terminal_fold. Each marker line is a small JSON
#   object {task_id,status,subject,review_task_id?}; per-task artifacts (which can
#   exceed PIPE_BUF and so are NOT inlined) live in a whole-file sidecar
#   "MARKER_FILE.artifacts.<task_id>.json". PURE: does NOT lock, write, or delete —
#   the caller owns the scratch's lock / persist / marker-cleanup lifecycle
#   (sync-tasks drains in-memory under its held FD-201; session-end drains on disk
#   under its own lock). Emits STATE on stdout (unchanged if MARKER_FILE is
#   absent/empty). Never fails the caller.
v11_apply_reconcile_markers() {
    local marker="$1" sid="$2" now="$3"
    local state; state="$(cat)"
    [ -n "$marker" ] && [ -s "$marker" ] || { printf '%s' "$state"; return 0; }
    local line tid st subj rtid pst arts_file arts new
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        tid=$(printf '%s' "$line" | jq -r '.task_id // ""' 2>/dev/null)
        [ -n "$tid" ] && [ "$tid" != "null" ] || continue
        st=$(printf '%s' "$line" | jq -r '.status // ""' 2>/dev/null)
        subj=$(printf '%s' "$line" | jq -r '.subject // "unknown"' 2>/dev/null)
        rtid=$(printf '%s' "$line" | jq -r '.review_task_id // ""' 2>/dev/null)
        [ "$rtid" = "null" ] && rtid=""
        # F36: the recorded prior status (absent on marker lines written before
        # this field existed — v11_reapply_terminal_fold treats "" as "in_progress",
        # the original unconditional-decrement behavior).
        pst=$(printf '%s' "$line" | jq -r '.prior_status // ""' 2>/dev/null)
        arts="null"
        # Only look for a sidecar under a filesystem-safe task id (no traversal).
        case "$tid" in
            *[!A-Za-z0-9._-]*) : ;;
            *)
                arts_file="${marker}.artifacts.${tid}.json"
                if [ -f "$arts_file" ] && [ -s "$arts_file" ] && jq empty "$arts_file" 2>/dev/null; then
                    arts="$(cat "$arts_file")"
                fi
                ;;
        esac
        new=$(printf '%s' "$state" | v11_reapply_terminal_fold "$tid" "$st" "$subj" "$sid" "$now" "$rtid" "$arts" "$pst")
        if [ -n "$new" ] && printf '%s' "$new" | jq empty 2>/dev/null; then
            state="$new"
        fi
    done < "$marker"
    printf '%s' "$state"
}

# --- S2-T0b-2 (#113): TaskList epochs, write side ---
# A task id is local to one Claude Code TaskList, and a resumed conversation
# can get a new TaskList that numbers from 1 again under the same hook session.
# hooks/sync-tasks opens an epoch at the first TaskCreate of a session (`fresh`)
# and when a TaskCreate shows the TaskList changed (`reuse`): the id is already
# in the current epoch (with a different tool_use_id), or the claude process
# changed (the sitting) and the id is not above the epoch's max id (review #19
# C1). Each event sync-tasks appends carries the epoch as `tl_epoch` (an int,
# only ever matched); the opening create also carries `tl_open`.
#
# The record $METRICS_DIR/tasklist-epochs/<session> is append-only (C3): every
# TaskCreate appends one snapshot line, and readers take the LAST complete line:
#   v1 <tl_epoch> <fresh|reuse|seed> <pid:starttime|-> <last tool_use_id|->
#      <,id:tu8,id:tu8,...,> <max id|-> <,sitting,...,> <,id,...,> <-|from:,id,...,>
# tu8 is the last 8 characters of the create's tool_use_id, so a re-fired
# PostToolUse for any create of the epoch is recognised (C2). The last three
# fields (review #26; a line without them is read as sittings {its sitting},
# nothing pending, no carry):
#   sittings  the claude processes that created in this epoch (at most 8, oldest
#             first). C1 opens only for a sitting not in it, so two processes
#             sharing one session id (a tmux teammate, a nested
#             `claude -p --resume`) never open an epoch by interleaving.
#   pending   the ids created by the newest sitting since it joined (empty while
#             only the opener created). After a resume, a parallel batch of the
#             new TaskList can deliver an id above the old max first: it joins
#             the old epoch. When an id reuse then opens an epoch in that same
#             sitting, those ids belong to the new TaskList and are CARRIED.
#   carry     the ids carried into this epoch and the epoch they were created in
#             (`from`). Their ledger lines are already written with `from`, and
#             since `from`'s id set never held them before, (session, from, id)
#             still names each one task: they keep `from` as their stamp.
#             v11_tl_epoch_read SESSION TASK_ID sets _V11_TL_EPOCH to `from` for
#             a carried TASK_ID, so C7, Strategy 1.6, C8 and every event of that
#             task agree with its create, and readers need no rewrite.
#             task_epoch.epoch_for_task is the Python side.
# tl_epoch 0 is a `seed` line, written by scripts/task-epoch-seed for a session
# that was live at rollout, and by the first create after an empty or garbled
# last line (which reads as unknown: nothing opens, nothing is stamped, C3; the
# seed line lets tracking resume). A seed epoch's events stay unstamped until the
# next epoch opens. A torn tail (a writer killed mid-line) is skipped, and the
# next writer starts its line on a new one. Only sync-tasks writes, under FD-201;
# past ~64 KB the writer rewrites the record to its last line (tmp + rename).
# scripts/rotate-metrics removes records 30 days after the last write.
# scripts/lib/task_epoch.py read_epoch_record is the Python reader.
# Everything here is bash builtins: no forks on the TaskCreate/TaskUpdate/TaskList
# path (design §7). The helpers set globals and must never be called as $(...).
# Rollback: V11_TASKLIST_EPOCH=off (no record, no stamps: v11.46 line shapes).
_V11_TLR_LINE_ERE='^v1 (0|[1-9][0-9]{0,15}) (fresh|reuse|seed) ([0-9]{1,10}:[0-9]{1,20}|-) ([A-Za-z0-9_-]{1,128}|-) (,([A-Za-z0-9_-]{1,32}:[A-Za-z0-9_-]{1,8},)*) ([0-9]{1,12}|-)( (,([0-9]{1,10}:[0-9]{1,20},){0,8}) (,([A-Za-z0-9_-]{1,32},)*) (-|(0|[1-9][0-9]{0,15}):(,([A-Za-z0-9_-]{1,32},)*)))?$'
_V11_TLR_ID_ERE='^[A-Za-z0-9_-]{1,32}$'
_V11_TLR_NUM_ERE='^[0-9]{1,12}$'
_V11_TLR_PID_ERE='^[0-9]{1,10}$'
_V11_TLR_TICKS_ERE='^[0-9]{1,20}$'
_V11_TLR_EPOCH_ERE='^[1-9][0-9]{9,15}$'

# v11_sitting — V11_SITTING="<CLAUDE_PID>:<starttime>" (field 22 of
#   /proc/<pid>/stat), or "" when CLAUDE_PID is unset or unreadable. A new
#   claude process (a resume) is a new sitting even with the same session id.
v11_sitting() {
    V11_SITTING=""
    local pid="${CLAUDE_PID:-}" stat rest
    local -a f
    [[ $pid =~ $_V11_TLR_PID_ERE ]] || return 0
    [ -r "/proc/$pid/stat" ] || return 0
    IFS= read -r stat 2>/dev/null < "/proc/$pid/stat" || [ -n "$stat" ] || return 0
    rest="${stat##*) }"
    read -r -a f <<< "$rest"
    [[ ${f[19]:-} =~ $_V11_TLR_TICKS_ERE ]] || return 0
    V11_SITTING="$pid:${f[19]}"
}

# v11_tl_epoch_read SESSION [TASK_ID] — read the session's epoch record. Sets
#   _V11_TLR_STATE  off (lever off / no real session) | none (no record) |
#                   unknown (empty or garbled) | ok
#   _V11_TL_EPOCH   the epoch to stamp: its tl_epoch, "" when none/unknown/seed.
#                   For a TASK_ID the epoch carried (review #26), the epoch
#                   that task was created in ("" when that was a seed epoch).
#   _V11_TLR_EPOCH _V11_TLR_REASON _V11_TLR_SITTING _V11_TLR_TUID _V11_TLR_IDS
#   _V11_TLR_MAX _V11_TLR_SITS _V11_TLR_PEND
#                   the last line's fields; _V11_TLR_CFROM/_V11_TLR_CARRY its
#                   carry ("" and "," when none); _V11_TLR_BYTES the record's
#                   size; _V11_TLR_TORN=1 when a torn tail follows the line.
v11_tl_epoch_read() {
    local sid="$1" tid="${2:-}" f line n IFS=
    local -a lines
    _V11_TL_EPOCH=""; _V11_TLR_STATE="off"; _V11_TLR_EPOCH=""; _V11_TLR_REASON=""
    _V11_TLR_SITTING=""; _V11_TLR_TUID=""; _V11_TLR_IDS=""; _V11_TLR_MAX=""; _V11_TLR_TORN=0
    _V11_TLR_SITS=","; _V11_TLR_PEND=","; _V11_TLR_CFROM=""; _V11_TLR_CARRY=","; _V11_TLR_BYTES=0
    [ "${V11_TASKLIST_EPOCH:-on}" != "off" ] || return 0
    v11_valid_session_id "$sid" && [ "$sid" != "legacy-cli" ] || return 0
    _V11_TLR_STATE="none"
    f="$METRICS_DIR/tasklist-epochs/$sid"
    [ -e "$f" ] || return 0
    _V11_TLR_STATE="unknown"
    # mapfile keeps each line's newline, so the last element lacks one only
    # when it is a torn tail. (It reads a 580 KB record in ~2.5 ms; a
    # ${var##*$'\n'} over the whole file took seconds.)
    mapfile lines 2>/dev/null < "$f"
    n=${#lines[@]}
    [ "$n" -gt 0 ] || return 0
    line="${lines[*]}"; _V11_TLR_BYTES=${#line}
    line="${lines[n-1]}"
    if [[ $line != *$'\n' ]]; then
        _V11_TLR_TORN=1
        [ "$n" -gt 1 ] || return 0
        line="${lines[n-2]}"
    fi
    line="${line%$'\n'}"
    [[ $line =~ $_V11_TLR_LINE_ERE ]] || return 0
    _V11_TLR_STATE="ok"
    _V11_TLR_EPOCH="${BASH_REMATCH[1]}"; _V11_TLR_REASON="${BASH_REMATCH[2]}"
    _V11_TLR_SITTING="${BASH_REMATCH[3]}"; _V11_TLR_TUID="${BASH_REMATCH[4]}"
    _V11_TLR_IDS="${BASH_REMATCH[5]}"; _V11_TLR_MAX="${BASH_REMATCH[7]}"
    if [ -n "${BASH_REMATCH[8]}" ]; then
        _V11_TLR_SITS="${BASH_REMATCH[9]}"; _V11_TLR_PEND="${BASH_REMATCH[11]}"
        if [ "${BASH_REMATCH[13]}" != "-" ]; then
            _V11_TLR_CFROM="${BASH_REMATCH[14]}"; _V11_TLR_CARRY="${BASH_REMATCH[15]}"
        fi
    elif [ "$_V11_TLR_SITTING" != "-" ]; then
        _V11_TLR_SITS=",$_V11_TLR_SITTING,"
    fi
    [ "$_V11_TLR_EPOCH" != "0" ] && _V11_TL_EPOCH="$_V11_TLR_EPOCH"
    if [ -n "$tid" ] && [ -n "$_V11_TLR_CFROM" ] && [[ $_V11_TLR_CARRY == *",$tid,"* ]]; then
        _V11_TL_EPOCH=""; [ "$_V11_TLR_CFROM" != "0" ] && _V11_TL_EPOCH="$_V11_TLR_CFROM"
    fi
    return 0
}

# v11_tl_epoch_on_create SESSION TASK_ID TOOL_USE_ID [RACED]
#   A TaskCreate returned TASK_ID: decide whether it opens an epoch, append the
#   record line and set _V11_TL_EPOCH (the epoch to stamp) and _V11_TL_OPEN
#   (fresh|reuse when this create opened it, else ""). Re-reads the record, so
#   call it under FD-201. RACED=1 (FD-201 timed out): nothing is written, and a
#   create that would open an epoch is left unstamped rather than stamped with
#   the epoch it leaves. On an unknown record it appends an epoch-0 seed line
#   holding this id (review #26): nothing opens or is stamped, and the next
#   create is judged against a readable line again.
v11_tl_epoch_on_create() {
    local sid="$1" tid="$2" tuid="$3" raced="${4:-0}"
    local tu8="-" open="" reuse=0 sit epoch reason ids max sits pend carry="-" nl="" dir f line rest x
    _V11_TL_OPEN=""
    v11_tl_epoch_read "$sid"
    [ "$_V11_TLR_STATE" = "off" ] && return 0
    [[ $tid =~ $_V11_TLR_ID_ERE ]] || return 0
    tuid="${tuid//[!A-Za-z0-9_-]/}"; tuid="${tuid:0:128}"
    if [ ${#tuid} -gt 8 ]; then tu8="${tuid: -8}"; elif [ -n "$tuid" ]; then tu8="$tuid"; fi
    v11_sitting
    sit="${V11_SITTING:--}"
    if [ "$_V11_TLR_STATE" = "none" ]; then
        open="fresh"
    elif [ "$_V11_TLR_STATE" = "ok" ]; then
        # C2: a re-fired PostToolUse for a create this epoch already recorded.
        if [ "$tu8" != "-" ] && [[ $_V11_TLR_IDS == *",$tid:$tu8,"* ]]; then
            return 0
        fi
        if [[ $_V11_TLR_IDS == *",$tid:"* ]]; then
            open="reuse"; reuse=1
        elif [ "$sit" != "-" ] && [ "$_V11_TLR_SITS" != "," ] && [[ $_V11_TLR_SITS != *",$sit,"* ]] \
             && [[ $tid =~ $_V11_TLR_NUM_ERE ]] && [[ $_V11_TLR_MAX =~ $_V11_TLR_NUM_ERE ]] \
             && (( 10#$tid <= 10#$_V11_TLR_MAX )); then
            # C1: a new claude process whose TaskList numbers from 1 again. Only
            # for a sitting this epoch has not seen (review #26): processes that
            # share the session id interleave their creates without opening one.
            open="reuse"
        fi
    fi
    if [ "$raced" = "1" ]; then
        [ -n "$open" ] && _V11_TL_EPOCH=""
        return 0
    fi
    max="-"; [[ $tid =~ $_V11_TLR_NUM_ERE ]] && max="$((10#$tid))"
    if [ -n "$open" ]; then
        epoch="${EPOCHREALTIME//[!0-9]/}"
        [[ $epoch =~ $_V11_TLR_EPOCH_ERE ]] || { _V11_TL_EPOCH=""; return 0; }
        reason="$open"; ids=",$tid:$tu8,"; sits=","; pend=","
        [ "$sit" != "-" ] && sits=",$sit,"
        # review #26: an id reuse by the sitting that joined the old epoch last,
        # after it created ids there: those ids are this new TaskList's (a
        # parallel batch delivered them first), so they are carried. A reuse of
        # an id that sitting created itself carries nothing.
        if [ "$reuse" = "1" ] && [ "$sit" != "-" ] && [ "$_V11_TLR_PEND" != "," ] \
           && [[ $_V11_TLR_SITS == *",$sit," ]] && [[ $_V11_TLR_PEND != *",$tid,"* ]]; then
            carry="$_V11_TLR_EPOCH:$_V11_TLR_PEND"
            rest="${_V11_TLR_PEND#,}"
            while [ -n "$rest" ]; do
                x="${rest%%,*}"; rest="${rest#*,}"
                line="${_V11_TLR_IDS#*,$x:}"
                ids="$ids$x:${line%%,*},"
                if [[ $x =~ $_V11_TLR_NUM_ERE ]] && { [ "$max" = "-" ] || (( 10#$x > 10#$max )); }; then
                    max="$((10#$x))"
                fi
            done
        fi
    elif [ "$_V11_TLR_STATE" = "unknown" ]; then
        epoch=0; reason="seed"; ids=",$tid:$tu8,"; sits=","; pend=","
        [ "$sit" != "-" ] && sits=",$sit,"
    else
        epoch="$_V11_TLR_EPOCH"; reason="$_V11_TLR_REASON"; ids="$_V11_TLR_IDS$tid:$tu8,"
        if [[ $_V11_TLR_MAX =~ $_V11_TLR_NUM_ERE ]] && { [ "$max" = "-" ] || (( 10#$_V11_TLR_MAX > 10#$max )); }; then
            max="$_V11_TLR_MAX"
        fi
        sits="$_V11_TLR_SITS"; pend="$_V11_TLR_PEND"
        [ -n "$_V11_TLR_CFROM" ] && carry="$_V11_TLR_CFROM:$_V11_TLR_CARRY"
        if [ "$sit" = "-" ]; then
            sit="$_V11_TLR_SITTING"
        elif [[ $sits != *",$sit,"* ]]; then
            # a sitting joins (at most 8 are kept): its ids are pending until it
            # reuses an id (a carry) or another sitting joins. The first known
            # sitting counts as the opener, whose ids never are.
            pend=","; [ "$sits" != "," ] && pend=",$tid,"
            sits="$sits$sit,"
            x="${sits//[!,]/}"
            (( ${#x} > 9 )) && sits=",${sits#,*,}"
        elif [ -n "${sits#,*,}" ] && [[ $sits == *",$sit," ]]; then
            pend="$pend$tid,"
        fi
    fi
    dir="$METRICS_DIR/tasklist-epochs"; f="$dir/$sid"
    [ -d "$dir" ] || mkdir -p "$dir" 2>/dev/null
    [ "$_V11_TLR_TORN" = "1" ] && nl=$'\n'
    line="v1 $epoch $reason $sit ${tuid:--} $ids $max $sits $pend $carry"
    if ! printf '%s%s\n' "$nl" "$line" 2>/dev/null >> "$f"; then
        [ -n "$open" ] && _V11_TL_EPOCH=""
        return 0
    fi
    # review #26: only the last line is ever read, so past ~64 KB the record is
    # rewritten to it (tmp + rename: a reader outside FD-201 sees the old file
    # or the new one). The rename is the one fork on this path, once per ~64 KB.
    if (( _V11_TLR_BYTES + ${#line} >= 65536 )); then
        { printf '%s\n' "$line" > "$dir/.$sid.compact" && mv -f -- "$dir/.$sid.compact" "$f"; } 2>/dev/null \
            || rm -f -- "$dir/.$sid.compact" 2>/dev/null
    fi
    _V11_TLR_STATE="ok"; _V11_TLR_EPOCH="$epoch"; _V11_TLR_REASON="$reason"; _V11_TLR_SITTING="$sit"
    _V11_TLR_TUID="${tuid:--}"; _V11_TLR_IDS="$ids"; _V11_TLR_MAX="$max"; _V11_TLR_TORN=0
    _V11_TLR_SITS="$sits"; _V11_TLR_PEND="$pend"; _V11_TLR_CFROM=""; _V11_TLR_CARRY=","
    [ "$carry" != "-" ] && { _V11_TLR_CFROM="${carry%%:*}"; _V11_TLR_CARRY="${carry#*:}"; }
    _V11_TL_EPOCH=""; [ "$epoch" != "0" ] && _V11_TL_EPOCH="$epoch"
    _V11_TL_OPEN="$open"
    return 0
}

# v11_tl_entry_current ENTRY_TL_EPOCH — C7: may a per-session STATE entry
#   (open_tasks[id], recent_completed/blocked_tasks, _terminal_idk[id]) stamped
#   with ENTRY_TL_EPOCH ("" = unstamped) stand for the task this call names?
#   Yes with no current epoch, for the current epoch (a carried task's: the
#   epoch it was created in, see v11_tl_epoch_read), and for any entry when the
#   current epoch opened `fresh`: no reuse was seen, so the TaskList before it
#   continues, including one whose record was lost while STATE survived (review
#   #26). Otherwise the entry names an older TaskList's task.
v11_tl_entry_current() {
    [ -z "${_V11_TL_EPOCH:-}" ] && return 0
    [ "$1" = "$_V11_TL_EPOCH" ] && return 0
    [ "${_V11_TLR_REASON:-}" = "fresh" ] && return 0
    return 1
}

# v11_handoff_self_sitting SESSION LIVE_SITTING LIVE_TL_EPOCH — S2-T0b-4 (the
#   S1-T3 condition, design §5). The caller has already matched SESSION to the
#   handoff-tasks.json live_session_uuid; LIVE_SITTING and LIVE_TL_EPOCH are
#   that file's live_sitting and live_tl_epoch (scripts/handoff stamps them).
#   True when this claude process wrote the file and the session's TaskList is
#   still the one it described:
#     - LIVE_SITTING equals v11_sitting's value. A resume is a new claude
#       process, so it is nudged and L2.3 runs. A file without live_sitting
#       (S1 format, or V11_TASKLIST_EPOCH=off at the writer) never matches:
#       fail toward nudging.
#     - when the file names an epoch and the epoch record is readable, the
#       record's epoch (0 = seed) is still that one. An id reuse within the
#       sitting (a #26 wipe) opens a new epoch, so it is nudged.
#   V11_HANDOFF_SELF_NUDGE_SUPPRESS=session: the session match alone (S1).
#   Builtins only; sets V11_SITTING and the _V11_TLR_* globals, so it must
#   never be called as $(...).
v11_handoff_self_sitting() {
    [ "${V11_HANDOFF_SELF_NUDGE_SUPPRESS:-on}" = "session" ] && return 0
    [ -n "$2" ] || return 1
    v11_sitting
    [ -n "$V11_SITTING" ] && [ "$2" = "$V11_SITTING" ] || return 1
    [ -n "$3" ] || return 0
    v11_tl_epoch_read "$1"
    [ "$_V11_TLR_STATE" = "ok" ] || return 0
    [ "$3" = "$_V11_TLR_EPOCH" ]
}

# S2-T0b-2 (#111, review #19 C5/C6): the identity-status predicates
# v11_ledger_append's continuation pass uses, kept apart so the jq/Python parity
# test (tests/test_ledger_rehydrate_identity.py) runs the same code.
#   v11_last_map($status_only): ledger rows -> {key: {ev, seqno}}, each
#     identity's last event; its last STATUS event (created, in_progress,
#     blocked, completed, cancelled) when $status_only (C5: review, prescope and
#     field_update rows never decide). scripts/lib/task_epoch.py last_status()
#     is the Python reference.
#   v11_alias_pairs: the alias sidecar object -> [{a, t, an, tn}].
#   v11_folded($last; $al; $k): the latest of $k's last event and its aliases'
#     (alias-folded, like TaskIndex.last_status), or null.
#   v11_closed($f): that event is completed or cancelled.
_V11_JQ_IDSTATUS_DEFS='
def v11_st_evs: ["created", "in_progress", "blocked", "completed", "cancelled"];
def v11_key($sn; $cs): $sn + "\u0000" + ($cs | tostring);
def v11_last_map($status_only):
    [ .[] | select(type == "object" and (.subject_norm | type) == "string" and .subject_norm != ""
                   and (.create_seq | type) == "number" and .create_seq >= 0)
          | if $status_only then select(.ev as $e | any(v11_st_evs[]; . == $e)) else . end ]
    | sort_by(.seqno // 0)
    | reduce .[] as $r ({}; .[v11_key($r.subject_norm; $r.create_seq)] = {ev: $r.ev, seqno: ($r.seqno // 0)});
def v11_alias_pairs:
    (.aliases // []) | map(select(type == "object" and (.alias | type) == "object"
            and (.target | type) == "object"
            and (.alias.subject_norm | type) == "string" and (.target.subject_norm | type) == "string"
            and (.alias.create_seq | type) == "number" and (.target.create_seq | type) == "number")
        | {a: v11_key(.alias.subject_norm; .alias.create_seq),
           t: v11_key(.target.subject_norm; .target.create_seq),
           an: .alias.subject_norm, tn: .target.subject_norm});
def v11_folded($last; $al; $k):
    [$last[$k]] + [$al[] | select(.t == $k) | $last[.a]] | map(select(. != null)) | max_by(.seqno);
def v11_closed($f): $f != null and ($f.ev == "completed" or $f.ev == "cancelled");
'

# S2-T5 (#58a): v11_ledger_append trim.
#
# Historically this call site cost ~42 forks / ~12 jq (04ea283 measurement,
# recon/S2-baseline.md): most of it was 7-8 separate `$(printf X | jq Y)`
# pipeline forks for validation/extraction, plus the continuation pass
# (below) re-slurping the WHOLE project ledger via `jq -rs` on every single
# `created` event to answer "is this subject_norm's identity still open".
# That is correct but O(ledger): example-project's ledger alone is 1.68 MB.
#
# The T0b-2 review (#111/#19 C5/C6) comment on the old continuation pass
# said the trim should keep the contract with "a per-identity last-STATUS
# map maintained under FD-207 ... plus this sidecar: the target's and each
# candidate's alias-folded status are then map lookups" instead of the
# jq -rs slurp. That is what this does:
#
#   - `.seq` gains two additive fields: `status` (a map keyed by
#     v11_key(subject_norm, create_seq) -> {ev, seqno, origins}, "origins"
#     being every (session_uuid, task_id) that ever wrote a `created` row
#     for that identity — needed to answer the review #26 "did the handoff-
#     named session+id actually create this" mismatch check without a
#     ledger scan) and `status_version` (0 until bootstrapped, 1 once the
#     map covers the whole ledger).
#   - Every append that resolves a status-type event (v11_st_evs: created,
#     in_progress, blocked, completed, cancelled) upserts its own key into
#     `status` as part of the SAME jq call that already rewrites `.seq`
#     (`_V11_JQ_LA_WRITE` below) — no extra fork. review/prescope/
#     field_update never touch it (C5).
#   - A `created` event's continuation decision reads that map directly
#     (`_V11_JQ_LA_CONT_FAST`, O(#identities-in-this-subject-family), not
#     O(ledger)) whenever `status_version == 1`.
#   - The FIRST `created` call a project ever makes after this ships (or
#     any call that needs a continuation decision before the map has ever
#     been built) still pays one `jq -rs` full-ledger slurp
#     (`_V11_JQ_LA_CONT_COLD`, structurally the same decision the old
#     `_V11_JQ_CONTINUATION` made) — but that SAME call also builds the
#     complete map from the rows it already slurped and hands it to
#     `_V11_JQ_LA_WRITE`, which persists it and sets `status_version = 1`.
#     Every later call is the fast, O(1)-ish path. This makes the warm-up
#     self-paying (it costs exactly what today's call already costs, once,
#     per project) rather than a separate migration step.
#   - `test_ledger_rehydrate_identity.py`'s `_write_ledger()` fixture writes
#     a bare `{"__seqno__":.., "subjects":{...}}` `.seq` (no `status`/
#     `status_version`) to simulate a ledger that predates this change —
#     exactly the case the cold path exists for.
#
# `_V11_JQ_IDSTATUS_DEFS` above (v11_key/v11_last_map/v11_alias_pairs/
# v11_folded/v11_closed) is untouched: tests/test_ledger_rehydrate_identity.py
# ::test_last_status_parity_with_task_epoch sources common.sh and calls it
# directly by name, so its signatures and behavior are a hard contract.
# `v11_folded`/`v11_closed`/`v11_key`/`v11_alias_pairs` are pure functions
# of their arguments and are reused as-is by the fast path (it just passes
# the persisted `status` map in place of a freshly-computed `v11_last_map`
# result — identical shape, `{ev, seqno}` — plus each entry's `origins`).

# _V11_JQ_LA_HEADER: envelope validation + version check + ev/subject_norm/
# task_id/rehydrate_target extraction, ALL in one jq call (was 3: the
# has()-chain validate, the .v read, and the ev_type/subject_norm/
# rehydrate_target extract). Output is "\u001f"-joined so the caller splits
# it with plain bash substring ops (0 forks) exactly as the old single
# extraction did. "MALFORMED" / "BADVER\u001f<v>" are sentinels the caller
# checks first. `task_id` (review fix, S2 T2/T3/R2 batch MEDIUM #2) rides
# along for the pair_activate dedupe check below — 0 extra forks for every
# other event type, which is the overwhelming majority of calls.
_V11_JQ_LA_HEADER='
if (type != "object") then "MALFORMED"
elif ((["v","ev","ts","project","subject_norm","task_id","session_uuid"] - keys) | length) > 0 then "MALFORMED"
elif (.v != 1) then "BADVER\u001f\(.v // 0)"
else
  [(.ev | tostring), (.subject_norm | tostring), (.task_id | tostring),
   (.rehydrate_target
    | if type == "object" and (.subject_norm | type) == "string" and .subject_norm != ""
         and (.subject_norm | test("[[:cntrl:]]") | not)
         and (.create_seq | type) == "number" and .create_seq >= 0
         and .create_seq == (.create_seq | floor) and .create_seq < 1000000000
      then .subject_norm, (.create_seq | tostring),
           (.session | if type == "string" and test("^[A-Za-z0-9._-]{1,128}$") then . else "" end),
           (.id | if type == "number" then tostring else . end
                | if type == "string" and test("^[A-Za-z0-9._-]{1,64}$") then . else "" end)
      else "", "", "", "" end)]
  | join("\u001f")
end
'

# _V11_JQ_LA_SEQLOAD: read+validate+default .seq AND bump __seqno__, in one
# call (was: `jq empty` existence probe + `cat` + a separate structure-
# validate jq — 4 forks/2 jq). A missing/unreadable/invalid file falls back
# to the bash-side default below via the empty-output check (jq's own parse
# error means the filter never runs, so this handles "doesn't exist" and
# "not JSON" the same way `[ -f ] && [ -s ] && jq empty` used to). `status`/
# `status_version` are additive (absent on a pre-S2-T5 `.seq`) and default
# to `{}`/0 the same way `subjects` already defaulted. NUL-delimited output
# (seq_json, status_version) via process substitution + `read -r -d ""`
# (the codebase's existing multi-field pattern, e.g. the TaskCreate
# metadata pass) — NOT `$(...)`, which would silently truncate at the first
# embedded NUL.
_V11_JQ_LA_SEQLOAD='
(if type == "object" and (.["__seqno__"] | type) == "number" and (.subjects | type) == "object" then {
    "__seqno__": (.["__seqno__"] + 1),
    subjects: .subjects,
    status: (if (.status | type) == "object" then .status else {} end),
    status_version: (if (.status_version | type) == "number" then .status_version else 0 end)
 } else {"__seqno__": 1, subjects: {}, status: {}, status_version: 0} end) as $sq
| ($sq | tostring), "\u0000", ($sq.status_version | tostring), "\u0000"
'

# _V11_JQ_LA_CONT_FAST: the warm-path continuation decision. Same contract
# as the old `_V11_JQ_CONTINUATION` (below-cold) — a rehydrate_target
# continues while its alias-folded last STATUS event is non-terminal AND a
# `created` row naming rehydrate_target's session+id exists for it or a
# sidecar alias of it (C5/C6, review #26 mismatch check); otherwise a plain
# create_seq for `$norm` continues if it has one still open — but it reads
# the persisted `status` map (O(#identities sharing this subject/alias
# family)) instead of re-slurping the ledger (O(#events ever)). `origins`
# (this identity's own `created` rows' (session_uuid, task_id) pairs, folded
# across aliases the same way status is) stands in for the old mismatch
# check's ledger scan for `.ev == "created" and .session_uuid == $tss and
# .task_id == $tsi`.
_V11_JQ_LA_CONT_FAST="$_V11_JQ_IDSTATUS_DEFS"'
. as $sq
| ($sq.status // {}) as $S
| (if $rh then ($al | if type == "array" then (.[0] // {}) else {} end
              | if type == "object" then v11_alias_pairs else [] end)
   else [] end) as $AL
| def entries($k): [$S[$k]] + [$AL[] | select(.t == $k) | $S[.a]] | map(select(. != null));
  def origins_of($k): [entries($k)[] | (.origins // [])[]];
  (if $rh and $tsn != "" then
      v11_key($tsn; ($tcs | tonumber)) as $tk
      | v11_folded($S; $AL; $tk) as $f
      | if $f == null then {refused: "unknown"}
        elif ($tss == "" or $tsi == ""
              or ([origins_of($tk)[] | select(.s == $tss and .t == $tsi)] | length) == 0)
        then {refused: "mismatch"}
        elif v11_closed($f) then {refused: "terminal"}
        else {seq: ($tcs | tonumber), norm: $tsn} end
   else {} end) as $t
| (if $t.seq != null then $t
   elif $cont_on and $norm != "" and $norm != "__empty__" then
       (($sq.subjects[$norm] // 0) | floor) as $maxseq
       | ([range(1; $maxseq + 1)]
          | map(select(v11_closed(v11_folded($S; $AL; v11_key($norm; .))) | not))
          | max) as $s
       | if $s == null then {} else {seq: $s, norm: $norm} end
   else {} end) as $c
| ($c.seq // "" | tostring), "\u0000", ($c.norm // ""), "\u0000", ($t.refused // ""), "\u0000"
'

# _V11_JQ_LA_CONT_COLD: the cold/bootstrap path — structurally the same
# slurp-based decision the old `_V11_JQ_CONTINUATION` made (kept verbatim;
# only `. as $all` up front and the bootstrap-map build at the end are new),
# used while `status_version != 1` for this project OR the map has gone
# stale (`v11_ledger_append`'s `_status_sync_file` check, below) since it
# was last built. It ALSO builds the complete origins-aware status map from
# the rows it already slurped (`v11_last_map(true)` + `v11_origins_map`, one
# extra reduce over data already in memory — no extra fork), so this is a
# one-time cost per warm-up (or per staleness event): `_V11_JQ_LA_WRITE`
# persists the map and flips `status_version`, and every later `created`
# call — until something touches the ledger outside this function — takes
# the fast path above.
#
# Staleness: the map is maintained ONLY by v11_ledger_append. A writer that
# appends or rewrites this project's ledger directly — confirmed:
# ~/.claude/skills/align-aggregate/align_aggregate.py's write_cancellations()
# (direct `cancelled` events), scripts/ledger-archive's filtered rewrite,
# scripts/backfill-ledger-attribution's tmp+os.replace rewrite — leaves the
# map holding a status the ledger no longer agrees with. All three are
# patched to delete `_status_sync_file` after writing, which is belt-and-
# suspenders: the general guard (`[[ jsonl -nt _status_sync_file ]]`, a
# stat()-only builtin test) already catches ANY writer, known or not, since
# writing a file always moves its mtime forward. scripts/migrate-ledger and
# scripts/task-cancel already go through v11_ledger_append (no bypass);
# scripts/rotate-metrics explicitly never touches `*.jsonl`/`*.seq`;
# scripts/task-epoch-seed only writes `tasklist-epochs/<sid>` records and
# the `.aliases.json` sidecar, never the ledger itself.
_V11_JQ_LA_CONT_COLD="$_V11_JQ_IDSTATUS_DEFS"'
def v11_origins_map:
    [ .[] | select(type == "object" and .ev == "created"
                   and (.subject_norm | type) == "string" and .subject_norm != ""
                   and (.create_seq | type) == "number" and .create_seq >= 0) ]
    | sort_by(.seqno // 0)
    | reduce .[] as $r ({}; .[v11_key($r.subject_norm; $r.create_seq)] =
        ((.[v11_key($r.subject_norm; $r.create_seq)] // []) +
         [{s: ($r.session_uuid // "" | tostring), t: ($r.task_id // "" | tostring)}]));
. as $all
| (if $rh then ($al | if type == "array" then (.[0] // {}) else {} end
              | if type == "object" then v11_alias_pairs else [] end)
 else [] end) as $al
| ([$norm] + (if $tsn != "" then [$tsn] else [] end)) as $n0
| ($n0 + [$al[] | select(.tn as $x | any($n0[]; . == $x)) | .an]) as $norms
| ($all | [.[] | select(type == "object" and (.subject_norm as $s | any($norms[]; . == $s)))]) as $rows
| ($rows | v11_last_map($rh)) as $last
| (if $rh and $tsn != "" then
       v11_folded($last; $al; v11_key($tsn; ($tcs | tonumber))) as $f
       | v11_key($tsn; ($tcs | tonumber)) as $tk
       | if $f == null then {refused: "unknown"}
         elif ($tss == "" or $tsi == ""
               or ([$rows[] | select(.ev == "created" and .session_uuid == $tss
                                     and ((.task_id // "") | tostring) == $tsi
                                     and (.create_seq | type) == "number")
                            | v11_key(.subject_norm; .create_seq)
                            | select(. == $tk or (. as $k | any($al[]; .a == $k and .t == $tk)))]
                   | length) == 0) then {refused: "mismatch"}
         elif v11_closed($f) then {refused: "terminal"}
         else {seq: ($tcs | tonumber), norm: $tsn} end
   else {} end) as $t
| (if $t.seq != null then $t
   elif $cont_on and $norm != "" and $norm != "__empty__" then
       ([$rows[] | select(.subject_norm == $norm and (.create_seq | type) == "number"
                          and .create_seq >= 0) | .create_seq]
        | unique | map(select(v11_closed(v11_folded($last; $al; v11_key($norm; .))) | not)) | max) as $s
       | if $s == null then {} else {seq: $s, norm: $norm} end
   else {} end) as $c
| ($all | v11_last_map(true)) as $bmap_status
| ($all | v11_origins_map) as $bmap_origins
| (reduce ($bmap_status | keys[]) as $k ({}; .[$k] = ($bmap_status[$k] + {origins: ($bmap_origins[$k] // [])})))
  as $bootstrap_map
| ($c.seq // "" | tostring), "\u0000", ($c.norm // ""), "\u0000", ($t.refused // ""), "\u0000",
  ($bootstrap_map | tostring), "\u0000"
'

# _V11_JQ_LA_WRITE: the write. Given the caller's resolved continuation
# decision (cont_seq/cont_norm/refused — empty when none applies) and an
# optional freshly-bootstrapped map, this single call:
#   - mints a fresh create_seq (bumping `subjects[orig_norm]`) when this is
#     a `created` event with no continuation, or uses the caller-provided
#     create_seq for a non-`created` event (or the identity_unresolved:true
#     sentinel -1, or signals "SKIP" — LEDGER-IDENTITY-MISS — when neither
#     is available, mirroring the old bash-side branch exactly);
#   - merges in `$bootstrap_map` (setting `status_version = 1`) when the
#     cold path ran this call;
#   - upserts `status[key]` for status-type events only (C5), appending
#     this row's (session_uuid, task_id) to `origins` on a `created` row;
#   - builds the complete ledger line (seqno/create_seq injection,
#     `continues`, `subject_norm` override, `rehydrate_target_refused`,
#     `tl_epoch` — byte-for-byte the same fields the old inline jq built).
# Output: "OK\0<seq_json>\0<line>\0<resolved_create_seq>\0" or "SKIP\0".
# The PIPE_BUF (4096-byte) truncation cap and the embedded-newline check
# stay bash-side (below) so the identity fields this jq call has ALREADY
# committed to `status_version`/`subjects` can never be reverted by a
# too-late truncation decision.
_V11_JQ_LA_WRITE='
def v11_key($sn; $cs): $sn + "\u0000" + ($cs | tostring);
def v11_st_evs: ["created", "in_progress", "blocked", "completed", "cancelled"];
. as $sq
| ($event.subject_norm // "" | tostring) as $orig_norm
| ($cont_seq != "") as $continues
| (if $ev_type == "created" then
     (if $continues then ($cont_seq | tonumber) else (($sq.subjects[$orig_norm] // 0) + 1) end)
   elif ($event.create_seq | type) == "number" then $event.create_seq
   elif ($event.identity_unresolved // false) then -1
   else null
   end) as $resolved_seq
| if $resolved_seq == null then "SKIP", "\u0000"
  else
    (if $continues then $cont_norm else $orig_norm end) as $winning_norm
    | ($sq
       | (if $bootstrap_map != null then (.status = $bootstrap_map | .status_version = 1) else . end)
       | .subjects = (if $ev_type == "created" and ($continues | not)
                      then (.subjects + {($orig_norm): $resolved_seq}) else .subjects end)
       | (if (v11_st_evs | any(. == $ev_type)) then
            .status[v11_key($winning_norm; $resolved_seq)] = {
              ev: $ev_type, seqno: .["__seqno__"],
              origins: (((.status[v11_key($winning_norm; $resolved_seq)].origins) // [])
                        + (if $ev_type == "created" then
                             [{s: ($event.session_uuid // "" | tostring),
                               t: ($event.task_id // "" | tostring)}]
                           else [] end))
            }
          else . end)
      ) as $sq2
    | ($event
       | del(.rehydrate_target)
       + {seqno: $sq2["__seqno__"], create_seq: $resolved_seq}
       + (if $continues then {continues: true} else {} end)
       + (if $continues and $winning_norm != $orig_norm then {subject_norm: $winning_norm} else {} end)
       + (if $refused != "" then {rehydrate_target_refused: $refused} else {} end)
       + (if $tle != null and .tl_epoch == null and .ev != "review" then {tl_epoch: $tle} else {} end)
       | with_entries(select(.value != null))
      ) as $line
    | "OK", "\u0000", ($sq2 | tostring), "\u0000", ($line | tostring), "\u0000",
      ($resolved_seq | tostring), "\u0000"
  end
'

# v11_ledger_append PROJECT EVENT_JSON
#   Append one event line to the project ledger.
#   Implements ADR §2.3 FD-207 single-flock read-bump-write-then-append algorithm.
#   The caller passes a JSON object that already contains all semantic fields
#   EXCEPT seqno and create_seq — this function assigns those from the .seq file
#   under FD-207 and appends the completed line.
#
#   REQUIRED fields in EVENT_JSON (ADR §1.2):
#     v          (int)    — must be 1
#     ev         (string) — event type
#     ts         (string) — ISO-8601 wall time
#     project    (string) — project name (already resolved by caller)
#     subject_norm (string) — normalized subject
#     task_id    (string) — session-local task id
#     session_uuid (string)
#   For ev=="created": create_seq is assigned fresh from subjects[subject_norm].
#   For ev!="created": create_seq must be passed in EVENT_JSON (from _idk).
#
#   HIGH-A invariant: if the .seq atomic write fails, log and return WITHOUT
#   appending. No line is written, no duplicate seqno is possible.
#
#   Side-effect-never-fails: all failure paths return 0 (|| true semantics).
#   Caller MUST use:  v11_ledger_append "$PROJECT" "$event_json" || true
#   OR embed in a block that ignores the return value.
#
#   FD discipline (ADR §4.1, §4.2):
#     FD 207 → <project>.jsonl.lock (NEVER FD 201/202/203).
#     FD 207 is a leaf acquisition: while held it touches only .seq (read+write)
#     and the .jsonl file (O_APPEND write). It never calls anything that takes
#     FD 201/202/203 — no deadlock possible even when nested inside the FD-201
#     per-session STATE lock that sync-tasks holds for its entire run.
#
#   S2-T5: ~7-8 forks / 3-4 jq per call (down from ~42/12) — see the
#   _V11_JQ_LA_* comments above. `.seq` on disk is now written compact (was
#   pretty-printed via a second `jq '.'` pass this trim folds away); nothing
#   reads it expecting a particular byte layout (grep confirmed — only
#   __seqno__/subjects are read elsewhere, e.g. scripts/ledger-archive,
#   and both survive through unrelated-key-preserving `.foo = x` updates).
v11_ledger_append() {
    local project="$1"
    local event_json="$2"

    # SEC-C-02: validate project name before any filesystem path construction.
    # Builtin regex (0 forks, was `printf | grep -qE` — 2 forks): the ERE
    # lives in the existing shared variable (never inline in `[[ =~ ]]` —
    # v11.35.3 bricked every hook that way), same pattern this file already
    # ships at :3820 and the exact charset `printf | grep` enforced here.
    if [ -z "$project" ] || ! [[ "$project" =~ $V11_PROJECT_SLUG_ERE_LEGACY ]]; then
        echo "v11_ledger_append: invalid project name '$project' — skipping (SEC-C-02)" >&2
        return 0
    fi

    if [ -z "$event_json" ]; then
        echo "v11_ledger_append: malformed event_json (missing required envelope fields) — skipping" >&2
        return 0
    fi

    # One jq call: envelope validate + version check + ev_type/subject_norm/
    # rehydrate_target extract (was 3 calls — see _V11_JQ_LA_HEADER above).
    local _hdr
    _hdr=$(jq -r "$_V11_JQ_LA_HEADER" <<<"$event_json" 2>/dev/null)
    case "$_hdr" in
        ''|MALFORMED)
            echo "v11_ledger_append: malformed event_json (missing required envelope fields) — skipping" >&2
            return 0
            ;;
        BADVER*)
            echo "v11_ledger_append: unknown ledger version '${_hdr#BADVER$'\x1f'}' — skipping" >&2
            return 0
            ;;
    esac
    # review fix (S2 T2/T3/R2 batch, MEDIUM #2): _ev_task_id rides along in
    # the SAME _V11_JQ_LA_HEADER call above (0 new forks) so the
    # pair_activate dedupe check below has the task_id without a second jq.
    local ev_type subject_norm _ev_task_id="" _rt_sn="" _rt_cs="" _rt_ss="" _rt_id=""
    ev_type="${_hdr%%$'\x1f'*}"; _hdr="${_hdr#*$'\x1f'}"
    subject_norm="${_hdr%%$'\x1f'*}"; _hdr="${_hdr#*$'\x1f'}"
    _ev_task_id="${_hdr%%$'\x1f'*}"; _hdr="${_hdr#*$'\x1f'}"
    _rt_sn="${_hdr%%$'\x1f'*}"; _hdr="${_hdr#*$'\x1f'}"
    _rt_cs="${_hdr%%$'\x1f'*}"; _hdr="${_hdr#*$'\x1f'}"
    _rt_ss="${_hdr%%$'\x1f'*}"; _rt_id="${_hdr#*$'\x1f'}"

    local ledger_dir="${METRICS_DIR}/ledger"
    local jsonl_file="${ledger_dir}/${project}.jsonl"
    local lock_file="${ledger_dir}/${project}.jsonl.lock"
    local seq_file="${ledger_dir}/${project}.seq"
    # Staleness marker for the `status` map (review finding: the map is only
    # kept in sync BY v11_ledger_append — an out-of-band writer that appends
    # or rewrites this project's .jsonl directly (confirmed: align-aggregate's
    # write_cancellations(), ledger-archive's filtered rewrite,
    # backfill-ledger-attribution's tmp+os.replace rewrite) leaves the map
    # holding a status the live ledger no longer agrees with — e.g. an
    # externally-cancelled identity still reading "open", so the next
    # `created` on that subject would wrongly CONTINUE it instead of minting
    # fresh. See _status_sync_file's use in Step 2 and after the append below.
    # fix review #16 (S2-T5 MEDIUM): the marker's CONTENT, not just its
    # existence/mtime, is now part of the contract — see the "PENDING" write
    # ahead of the .seq write in Step 4 below (crash-safety for the window
    # between that write and the jsonl append).
    local _status_sync_file="${ledger_dir}/${project}.status-sync"

    mkdir -p "$ledger_dir" 2>/dev/null || {
        echo "v11_ledger_append: failed to create ledger dir '$ledger_dir' — skipping" >&2
        return 0
    }

    # Rollback: V11_REHYDRATE_IDENTITY_WRITE=off keys every create on its own
    # subject, and continuation decides "open" on the last event of any kind
    # with no alias awareness (v11.46).
    local _rh_on=true
    [ "${V11_REHYDRATE_IDENTITY_WRITE:-on}" = "off" ] && _rh_on=false
    [ "$_rh_on" = true ] || { _rt_sn=""; _rt_cs=""; }
    [ -n "$_rt_sn" ] && [ -n "$_rt_cs" ] || { _rt_sn=""; _rt_cs=""; }

    # v11.37 W1-T2 (ticket #38 amplification): attribution-normalization gate.
    # Off by default (V11_LEDGER_STRICT_ATTRIBUTION=off) — unchanged behavior
    # and unchanged fork cost (0) on the default path; only herestring'd in
    # place of `printf | jq` (saves 1 fork each when an operator opts in).
    # Agent-authored events (created / review / artifact_warn) should
    # carry an actor field (owner || metadata.agent || recommended_agent). State
    # transitions (in_progress / completed / cancelled / field_update) inherit
    # attribution from the create row of the same task_id; system events
    # (prescope / reconcile) are inherently no-actor.
    # Lever tri-state:
    #   off (default)  — no observability, no side-file (pre-v11.37 behavior)
    #   advisory       — STDERR WARN + side-file mirror
    #   on             — same as advisory (kept as separate token for future
    #                    "hard refuse" semantics if the operator ever needs it)
    local _v11_lsa="${V11_LEDGER_STRICT_ATTRIBUTION:-off}"
    if [ "$_v11_lsa" != "off" ]; then
        case "$ev_type" in
            created|review|artifact_warn)
                local _owner _agent _rec
                _owner=$(jq -r '.owner // ""' <<<"$event_json" 2>/dev/null)
                _agent=$(jq -r '.metadata.agent // ""' <<<"$event_json" 2>/dev/null)
                _rec=$(jq -r '.recommended_agent // ""' <<<"$event_json" 2>/dev/null)
                if [ -z "$_owner" ] && [ -z "$_agent" ] && [ -z "$_rec" ]; then
                    echo "v11_ledger_append: attribution missing on '$ev_type' event (project=$project task_id=$(jq -r '.task_id // "?"' <<<"$event_json"))" >&2
                    local _unattr_file="${METRICS_DIR}/unattributed-events.jsonl"
                    local _unattr_lock="${METRICS_DIR}/.unattributed-events.lock"
                    mkdir -p "$METRICS_DIR" 2>/dev/null || true
                    # v11.38 W1-T2 (#52 fix): dedicated flock (FD 209, 2s timeout)
                    # + best-effort truncation cap at 4000B. Primary FD-207
                    # critical section is unaffected. All best-effort; never
                    # fail the caller.
                    (
                        exec 209>"$_unattr_lock"
                        flock -w 2 209 || {
                            echo "v11_ledger_append: mirror flock timeout — dropping this unattributed event to STDERR only" >&2
                            exit 0
                        }
                        local _line
                        _line="$event_json"
                        if [ "${#_line}" -gt 4000 ]; then
                            local _reduced
                            _reduced=$(jq -c 'del(.description,.metadata,.artifacts)' <<<"$_line" 2>/dev/null)
                            if [ -n "$_reduced" ] && [ "${#_reduced}" -le 4000 ]; then
                                _line="$_reduced"
                            fi
                        fi
                        printf '%s\n' "$_line" >> "$_unattr_file" 2>/dev/null || true
                    ) 2>/dev/null || true
                fi
                ;;
        esac
    fi

    # --- FD-207 critical section: read .seq → bump → decide identity →
    #     write .seq → append. flock -w 5: on timeout skip the ledger write
    #     and log (side-effect-never-fails). The subshell exits non-zero on
    #     any internal failure; the outer || true ensures the caller is
    #     never failed.
    (
        exec 207>"$lock_file"
        flock -w 5 207 || {
            echo "v11_ledger_append: FD-207 flock timeout for project=$project — skipping ledger write" >&2
            exit 1
        }
        # Byte-accurate `${#var}` for the PIPE_BUF check further down (jq's
        # own JSON handling is UTF-8-always and unaffected by LC_ALL — this
        # only changes what bash's `${#}` counts). Scoped to this subshell.
        local LC_ALL=C

        # review fix (S2 T2/T3/R2 batch, MEDIUM #2): pair_activate dedupe at
        # append time. Under a flock-timeout on STATE_FILE.lock (_V11_SYNC_RACED=1,
        # sync-tasks proceeds unserialized), two racing TaskUpdate(completed)
        # calls on the same paired parent can each read shadow
        # metadata.parent_status=="pending_parent" before either write lands, so
        # both build a pair_activate event for the same shadow task_id. This
        # FD-207 critical section IS the one place both calls serialize (each
        # v11_ledger_append acquires it in turn), so check-then-append here is
        # atomic: skip the append (no seqno burned, no duplicate row) if a
        # pair_activate for this task_id is already on the ledger.
        if [ "$ev_type" = "pair_activate" ] && [ -n "$_ev_task_id" ] && [ -s "$jsonl_file" ] \
           && jq -e --arg tid "$_ev_task_id" 'select(.ev == "pair_activate" and .task_id == $tid)' \
                "$jsonl_file" >/dev/null 2>&1; then
            echo "v11_ledger_append: duplicate pair_activate for task_id=$_ev_task_id project=$project — skipping (already ledgered)" >&2
            exit 0
        fi

        # Step 1: load .seq, defaulting/normalizing it, with __seqno__
        # already bumped (1 fork, 1 jq — was 4 forks/2 jq: a `jq empty`
        # probe, a `cat`, a separate structure-validate, then a bump).
        local seq_json="" _sv=""
        { IFS= read -r -d '' seq_json; IFS= read -r -d '' _sv; } \
            < <(jq -j "$_V11_JQ_LA_SEQLOAD" "$seq_file" 2>/dev/null)
        if [ -z "$seq_json" ]; then
            seq_json='{"__seqno__":1,"subjects":{},"status":{},"status_version":0}'
            _sv="0"
        fi

        # Step 2: for a `created` event that needs a continuation decision
        # (a rehydrate target was named, or the continuation lever is on and
        # this event carries a real subject) — same gate the old code used
        # (`[ -s "$jsonl_file" ] && { target-named || plain-continuation-
        # eligible }`) — resolve it via the warm map (fast) or, the first
        # time this project needs one since the map gained a `status_version`
        # field, via one ledger slurp that also builds that map (cold; see
        # _V11_JQ_LA_CONT_COLD above). Every other event type, and a
        # `created` with nothing to check, skips this step entirely (0
        # forks): $cont_seq/$cont_norm/$refused stay empty and $bootstrap_map
        # stays null, so Step 3 mints.
        #
        # The map is trusted (fast path) only when, IN ADDITION to
        # status_version==1, `_status_sync_file` exists, is not older than
        # `$jsonl_file` (`[[ -nt ]]`, a stat()-only builtin test — 0 forks),
        # AND its CONTENT is the empty "confirmed" sentinel (a builtin `read`
        # — 0 forks). v11_ledger_append itself always re-touches
        # `_status_sync_file` AFTER the jsonl append below (never before —
        # HIGH-A already forces the .seq write, which the map lives in, to
        # happen BEFORE the jsonl append, so a same-call self-comparison
        # would otherwise always look stale), so its own successful appends
        # never trip this. An out-of-band writer that touches the jsonl file
        # without knowing about the marker — any writer, not just the three
        # known ones patched to delete it explicitly — leaves the marker
        # exactly as old as it was, so the jsonl's newer mtime is caught
        # here and forces the cold rebuild.
        # fix review #16 (S2-T5 MEDIUM): the content check closes a second
        # crash window the mtime check alone cannot: Step 4 below writes the
        # PENDING sentinel (marking the .seq write about to happen as
        # unconfirmed) immediately before the .seq write, and only writes
        # the confirmed "" sentinel after the jsonl append succeeds. A crash
        # between the PENDING write and the append leaves `.seq`'s `status`
        # map possibly describing an event the jsonl never durably got —
        # but the marker still reads PENDING (jsonl's mtime never moved, so
        # the mtime check alone would miss this), so the content check
        # forces the cold rebuild instead of trusting it.
        local _cont_seq="" _cont_norm="" _refused="" _bootstrap_map="null"
        if [ "$ev_type" = "created" ] && [ -s "$jsonl_file" ] \
           && { [ -n "$_rt_sn" ] || { [ "${V11_IDENTITY_CONTINUATION:-on}" != "off" ] \
                  && [ -n "$subject_norm" ] && [ "$subject_norm" != "__empty__" ]; }; }; then
            local _cont_on=true
            [ "${V11_IDENTITY_CONTINUATION:-on}" = "off" ] && _cont_on=false
            local _al_file="${ledger_dir}/${project}.aliases.json"
            local -a _al_arg=(--argjson al '[]')
            [ "$_rh_on" = true ] && [ -s "$_al_file" ] && _al_arg=(--slurpfile al "$_al_file")
            local _cont=""
            local _map_fresh=0
            if [ "$_sv" = "1" ] && [[ -e "$_status_sync_file" && ! "$jsonl_file" -nt "$_status_sync_file" ]]; then
                # fix review #16 (S2-T5 MEDIUM): mtime alone isn't enough — a
                # PENDING marker (see Step 4) can be mtime-fresh (just
                # written) yet still mean "a .seq write is/was in flight,
                # not yet confirmed by the append". Builtin `read`, 0 forks.
                local _sync_content=""
                IFS= read -r _sync_content < "$_status_sync_file" 2>/dev/null || true
                [ -z "$_sync_content" ] && _map_fresh=1
            fi
            if [ "$_map_fresh" = "1" ]; then
                { IFS= read -r -d '' _cont_seq; IFS= read -r -d '' _cont_norm; IFS= read -r -d '' _refused; } \
                    < <(jq -j --arg norm "$subject_norm" --arg tsn "$_rt_sn" --arg tcs "$_rt_cs" \
                            --arg tss "$_rt_ss" --arg tsi "$_rt_id" \
                            --argjson cont_on "$_cont_on" --argjson rh "$_rh_on" "${_al_arg[@]}" \
                            "$_V11_JQ_LA_CONT_FAST" <<<"$seq_json" 2>/dev/null) \
                    || { [ "${_al_arg[0]}" = "--slurpfile" ] && \
                         { IFS= read -r -d '' _cont_seq; IFS= read -r -d '' _cont_norm; IFS= read -r -d '' _refused; } \
                             < <(jq -j --arg norm "$subject_norm" --arg tsn "$_rt_sn" --arg tcs "$_rt_cs" \
                                     --arg tss "$_rt_ss" --arg tsi "$_rt_id" \
                                     --argjson cont_on "$_cont_on" --argjson rh "$_rh_on" --argjson al '[]' \
                                     "$_V11_JQ_LA_CONT_FAST" <<<"$seq_json" 2>/dev/null); }
            else
                { IFS= read -r -d '' _cont_seq; IFS= read -r -d '' _cont_norm; IFS= read -r -d '' _refused; \
                  IFS= read -r -d '' _bootstrap_map; } \
                    < <(jq -j -s --arg norm "$subject_norm" --arg tsn "$_rt_sn" --arg tcs "$_rt_cs" \
                            --arg tss "$_rt_ss" --arg tsi "$_rt_id" \
                            --argjson cont_on "$_cont_on" --argjson rh "$_rh_on" "${_al_arg[@]}" \
                            "$_V11_JQ_LA_CONT_COLD" "$jsonl_file" 2>/dev/null) \
                    || { [ "${_al_arg[0]}" = "--slurpfile" ] && \
                         { IFS= read -r -d '' _cont_seq; IFS= read -r -d '' _cont_norm; IFS= read -r -d '' _refused; \
                           IFS= read -r -d '' _bootstrap_map; } \
                             < <(jq -j -s --arg norm "$subject_norm" --arg tsn "$_rt_sn" --arg tcs "$_rt_cs" \
                                     --arg tss "$_rt_ss" --arg tsi "$_rt_id" \
                                     --argjson cont_on "$_cont_on" --argjson rh "$_rh_on" --argjson al '[]' \
                                     "$_V11_JQ_LA_CONT_COLD" "$jsonl_file" 2>/dev/null); }
            fi
            [ -n "$_bootstrap_map" ] || _bootstrap_map="null"
        elif [ -n "$_rt_sn" ]; then
            _refused="unknown"
        fi

        # Step 3: mint-or-confirm + status-map upsert + complete_line, in
        # one call (1 fork, 1 jq — see _V11_JQ_LA_WRITE above).
        local _tle_json="null"
        [[ ${_V11_TL_EPOCH:-} =~ $_V11_TLR_EPOCH_ERE ]] && _tle_json="$_V11_TL_EPOCH"
        local _wr_status="" seq_json2="" complete_line="" this_create_seq=""
        { IFS= read -r -d '' _wr_status; IFS= read -r -d '' seq_json2; \
          IFS= read -r -d '' complete_line; IFS= read -r -d '' this_create_seq; } \
            < <(jq -j --argjson event "$event_json" --arg ev_type "$ev_type" \
                    --arg cont_seq "$_cont_seq" --arg cont_norm "$_cont_norm" --arg refused "$_refused" \
                    --argjson bootstrap_map "$_bootstrap_map" --argjson tle "$_tle_json" \
                    "$_V11_JQ_LA_WRITE" <<<"$seq_json" 2>/dev/null)

        if [ "$_wr_status" = "SKIP" ]; then
            echo "sync-tasks: LEDGER-IDENTITY-MISS task=$(jq -r '.task_id // "?"' <<<"$event_json" 2>/dev/null) project=$project — no _idk on STATE record; ledger line SKIPPED (run scripts/migrate-ledger / verify backfill)" >&2
            exit 1
        elif [ "$_wr_status" != "OK" ] || [ -z "$seq_json2" ] || [ -z "$complete_line" ]; then
            echo "v11_ledger_append: jq failed to build complete line for project=$project — skipping" >&2
            exit 1
        fi

        # fix review #16 (S2-T5 MEDIUM): mark the status-sync marker PENDING
        # BEFORE the .seq write below (builtin printf, 0 forks). `.seq`'s
        # `status` map is about to be updated for THIS event, but the jsonl
        # append that makes it real hasn't happened yet (HIGH-A requires the
        # .seq write to stay before the append). A crash anywhere from here
        # through the append leaves this marker on disk reading "PENDING"
        # (only the OK-confirmed write below, after the append, ever clears
        # it back to empty) — Step 2's freshness check above now checks this
        # marker's CONTENT, not just its mtime, so the next call correctly
        # refuses to trust a `status` map whose confirming append may never
        # have landed, instead of silently reading a phantom status.
        printf 'PENDING\n' > "$_status_sync_file" 2>/dev/null || true

        # Step 4: atomic write .seq (tmp in same dir + rename). Written
        # directly (builtin printf, 0 forks — was a second `jq '.'` pass,
        # 2 forks): $seq_json2 is already-validated compact JSON from Step 3.
        # HIGH-A: if this write FAILS, log and exit WITHOUT appending.
        local seq_tmp="${seq_file}.tmp.$$"
        if ! printf '%s\n' "$seq_json2" > "$seq_tmp" 2>/dev/null || ! [ -s "$seq_tmp" ]; then
            rm -f "$seq_tmp" 2>/dev/null
            echo "LEDGER-SEQ-WRITE-FAIL: aborting ledger line (seqno gaps; no duplicate) project=$project" >&2
            exit 1
        fi
        if ! mv "$seq_tmp" "$seq_file" 2>/dev/null; then
            rm -f "$seq_tmp" 2>/dev/null
            echo "LEDGER-SEQ-WRITE-FAIL: aborting ledger line (seqno gaps; no duplicate) project=$project" >&2
            exit 1
        fi

        # Validate no embedded newline (ADR §1.1: one compact JSON object per
        # line). `case` pattern matching, not `grep -q $'\n'` (false
        # positives on some systems on the implicit line-end match).
        case "$complete_line" in
            *$'\n'*)
                echo "v11_ledger_append: line contains embedded newline — skipping (malformed event)" >&2
                exit 1
                ;;
        esac

        # ADR §4.1 MED-2: ≤PIPE_BUF (4096 byte) line-size invariant — O_APPEND
        # cannot atomically write a line bigger than PIPE_BUF on Linux, and a
        # torn write breaks the §4.3 "only the tail fragment may be torn"
        # guarantee. Truncate lowest-priority optional fields in priority
        # order: description, metadata, artifacts. Identity fields and
        # counters_delta are NEVER truncated. `${#complete_line}` is exact
        # bytes here (LC_ALL=C, set above) — 0 forks in the common case
        # (was a `wc -c` fork every call); the rare re-jq fallbacks below are
        # unchanged (only triggered when actually over budget).
        if [ "${#complete_line}" -gt 4096 ]; then
            local reduced rb
            reduced=$(jq -c 'del(.description)' <<<"$complete_line" 2>/dev/null)
            rb=${#reduced}
            if [ -n "$reduced" ] && [ "$rb" -le 4096 ]; then
                complete_line="$reduced"
                echo "v11_ledger_append: truncated description to fit PIPE_BUF for project=$project" >&2
            else
                reduced=$(jq -c 'del(.description,.metadata)' <<<"$complete_line" 2>/dev/null)
                rb=${#reduced}
                if [ -n "$reduced" ] && [ "$rb" -le 4096 ]; then
                    complete_line="$reduced"
                    echo "v11_ledger_append: truncated description+metadata to fit PIPE_BUF for project=$project" >&2
                else
                    reduced=$(jq -c 'del(.description,.metadata,.artifacts)' <<<"$complete_line" 2>/dev/null)
                    rb=${#reduced}
                    if [ -n "$reduced" ] && [ "$rb" -le 4096 ]; then
                        complete_line="$reduced"
                        echo "v11_ledger_append: truncated description+metadata+artifacts to fit PIPE_BUF for project=$project" >&2
                    else
                        echo "v11_ledger_append: PIPE_BUF un-reducible for project=$project — skipping line (writer bug: identity fields too large)" >&2
                        exit 1
                    fi
                fi
            fi
        fi

        # O_APPEND write: builtin printf + redirect (0 forks — was also a
        # builtin, unchanged) issues a single write(2) the kernel appends
        # atomically for lines <= PIPE_BUF.
        printf '%s\n' "$complete_line" >> "$jsonl_file"

        # Re-stamp the status-map staleness marker AFTER the jsonl append
        # (builtin printf + redirect, 0 forks) — this specific ordering is
        # what keeps v11_ledger_append's OWN appends from tripping the
        # `[[ jsonl -nt marker ]]` staleness check on the very next call: the
        # marker is now at least as new as the line this call just wrote,
        # whether or not this event was status-type (a non-status append,
        # e.g. review/prescope, still moves the jsonl's mtime forward and
        # would otherwise falsely read as "changed since sync" next time).
        # fix review #16 (S2-T5 MEDIUM): also the ONLY place the PENDING
        # sentinel written above is ever cleared back to "confirmed" (empty)
        # — reached only once the append this .seq write described has
        # actually landed. Any exit before this line (crash or an early
        # `exit 1` above) leaves PENDING on disk, which Step 2's content
        # check now treats as unconditionally stale.
        printf '' > "$_status_sync_file" 2>/dev/null || true

        # ADR §2.3 (LOW): for `created` events, print the FD-207-confirmed
        # create_seq on stdout (builtin printf, 0 forks) so the caller can
        # stamp it into _idk. #111: a create that carried rehydrate_target
        # prints "create_seq<TAB>subject_norm" — the identity actually used
        # (the target's when accepted, else its own) — every other create
        # prints create_seq alone. Matches
        # tests/test_ledger_rehydrate_identity.py's stdout contract exactly.
        if [ "$ev_type" = "created" ]; then
            if [ -n "$_rt_sn" ]; then
                printf '%s\t%s' "$this_create_seq" "${_cont_norm:-$subject_norm}"
            else
                printf '%s' "$this_create_seq"
            fi
        fi

    ) || true
    # || true: side-effect-never-fails — any failure in the subshell is suppressed.
    # The per-session STATE write (sync-tasks ~line 948) already happened before
    # this call; the ledger is durable enrichment, not a replacement for STATE.
    return 0
}


# v11_ledger_identity_fallback PROJECT SUBJECT [SCAN_CAP]
#   ADR Addendum A §A.2 — Phase-1 lock-free reverse-scan fallback.
#   For cross-session reopens where open_tasks._idk and _terminal_idk both miss.
#   Returns "SUBJECT_NORM CREATE_SEQ" on stdout, or "MISS" on not found.
#   This is a READ-ONLY Phase-1 operation: no FD-207 held during scan.
#   FD-207 is acquired by the caller (v11_ledger_append) for Phase-2 only.
#
#   Algorithm (ADR §A.2, Phase 1):
#     1. Open <project>.jsonl O_RDONLY, capture scan_end_off = file size
#     2. Reverse-scan backward from scan_end_off, line-by-line, JSON-parse each
#     3. Skip torn final fragment (§4.3): only the last partial line is tolerated
#     4. On first ev=="created" with subject_norm==normalize(subject): return it
#     5. If lines_scanned > SCAN_CAP → return MISS (bounded, never a latency cliff)
#     6. Close fd (NO lock held at any point)
#   The caller (sync-tasks identity-resolution step 3) uses the returned
#   (subject_norm, create_seq) and passes them into v11_ledger_append for Phase-2.
#
#   Side-effect-never-fails: returns "MISS" on any internal error.
v11_ledger_identity_fallback() {
    local project="$1"
    local subject="$2"
    local scan_cap="${3:-50000}"

    # SEC-C-02: validate project
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        printf 'MISS'
        return 0
    fi

    local ledger_file="${METRICS_DIR}/ledger/${project}.jsonl"
    if [ ! -f "$ledger_file" ] || [ ! -s "$ledger_file" ]; then
        printf 'MISS'
        return 0
    fi

    # Normalize the subject to match against ledger entries
    local target_norm
    target_norm=$(v11_normalize_subject "$subject" 2>/dev/null) || target_norm="__empty__"
    [ -z "$target_norm" ] && target_norm="__empty__"

    # Delegate the bounded reverse-scan to Python (bash can't efficiently reverse-scan large files)
    V11_LEDGER_FALLBACK_FILE="$ledger_file" \
    V11_LEDGER_FALLBACK_NORM="$target_norm" \
    V11_LEDGER_FALLBACK_PROJECT="$project" \
    V11_LEDGER_FALLBACK_CAP="$scan_cap" \
    V11_LEDGER_FALLBACK_V11HOME="$V11_HOME" \
    python3 - <<'FALLBACK_PYEOF' 2>/dev/null
import os, sys, json

ledger_path  = os.environ.get("V11_LEDGER_FALLBACK_FILE", "")
target_norm  = os.environ.get("V11_LEDGER_FALLBACK_NORM", "")
project      = os.environ.get("V11_LEDGER_FALLBACK_PROJECT", "")
scan_cap     = int(os.environ.get("V11_LEDGER_FALLBACK_CAP", "50000"))
v11_home     = os.environ.get("V11_LEDGER_FALLBACK_V11HOME", "")

if not ledger_path or not target_norm or not project:
    print("MISS", end=""); sys.exit(0)

# Phase 1: lock-free read — capture scan_end_off
try:
    with open(ledger_path, "rb") as fh:
        fh.seek(0, 2)  # SEEK_END
        scan_end_off = fh.tell()
        if scan_end_off == 0:
            print("MISS", end=""); sys.exit(0)
        # Read entire file up to scan_end_off (all existing content at snapshot time)
        fh.seek(0)
        raw_bytes = fh.read(scan_end_off)
except OSError:
    print("MISS", end=""); sys.exit(0)

# Split into lines — last line may be torn (§4.3: skip if not \n-terminated)
try:
    raw_text = raw_bytes.decode("utf-8", errors="replace")
except Exception:
    print("MISS", end=""); sys.exit(0)

lines = raw_text.split("\n")
# If the last element is non-empty, it's a torn tail fragment → skip it
if lines and lines[-1] != "":
    lines = lines[:-1]  # drop torn tail

# Reverse-scan: find most-recent `created` with matching subject_norm
lines_scanned = 0
for raw in reversed(lines):
    if raw == "":
        continue
    lines_scanned += 1
    if lines_scanned > scan_cap:
        # SCAN_CAP reached: bounded MISS (ADR §A.2)
        print(f"LEDGER-IDENTITY-MISS-SCAN-CAP: scan_cap={scan_cap} project={project}", file=__import__("sys").stderr)
        print("MISS", end=""); sys.exit(0)
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if not isinstance(ev, dict):
        continue
    if ev.get("ev") != "created":
        continue
    if ev.get("project") != project:
        continue
    sn = ev.get("subject_norm", "")
    if sn == target_norm:
        cs = ev.get("create_seq")
        if cs is not None:
            # Use tab as separator — subject_norm never contains tabs (§2.1 normalizer
            # collapses all Unicode whitespace incl. tabs to a single ASCII space).
            # The caller splits on the LAST tab: ${_FALLBACK##*$'\t'} → create_seq,
            #                                     ${_FALLBACK%$'\t'*} → subject_norm.
            print(f"{sn}\t{cs}", end=""); sys.exit(0)

print("MISS", end=""); sys.exit(0)
FALLBACK_PYEOF
}

# v11_ledger_resolve_by_task_id PROJECT TASK_ID [SESSION_UUID] [SCAN_CAP]
#   W5-T16 (improvements/09) — bounded reverse-scan identity recovery keyed
#   by task_id rather than subject text. The CLI `review-queue mark-done
#   --verdict-file` path only has a task_id in hand (no subject string to
#   normalize), so v11_ledger_identity_fallback (subject-keyed) doesn't fit;
#   this mirrors the fold-reconcile create_seq scan (scripts/fold-reconcile:
#   141-214) as a live lock-free lookup instead of an offline batch pass.
#   S1-P3 (#97): task_ids are session-local and reused across sessions, so a
#   bare id can name several parents. The latest event carrying the id used
#   to win, which bound S1-T8's verdict to the planning session's task 10.
#     - SESSION_UUID given and it holds one task under TASK_ID: that task.
#       If it holds several (the id reused after the first closed), the one
#       that has completed; none or several completed → AMBIGUOUS.
#     - SESSION_UUID that is not a UUID (review #61: review-daemon passed its
#       own id), or that holds no task under TASK_ID: treated as no session,
#       with a NOTE when that still binds.
#     - no SESSION_UUID: binds only when every identity-bearing event for
#       TASK_ID names one identity; otherwise prints "AMBIGUOUS\t<detail>"
#       and the caller must refuse rather than guess.
#   ev:"review"/"prescope" rows are never candidates: a review row names the
#   identity it was (possibly wrongly) bound to, and prescope rows carry the
#   subject_norm=""/create_seq=-1 sentinel.
#   Returns "SUBJECT_NORM\tCREATE_SEQ" (tab-separated) on stdout, optionally
#   followed by a second line "NOTE\t<text>", or "MISS", or "AMBIGUOUS\t<detail>".
#   Side-effect-never-fails: returns "MISS" on any internal error.
#   S2-T0b-3 (#113): the rules above are the v11.46 path, kept under
#   V11_TASK_RESOLVER=legacy. By default this delegates to v11_resolve_identity
#   (scripts/lib/task_epoch.py, rules R0-R4) with the same signature and TSV
#   contract; SCAN_CAP is ignored (the index reads the whole ledger). A task_id
#   one session reused (a TaskList that restarted at 1) binds the claim at the
#   row's position, not "the completed one"; AMBIGUOUS is left for a real tie.
#   Extra arguments after SCAN_CAP pass through to the resolver:
#   --identity SN:CS (R0), --epoch E (R1), --at TS [--seqno N], --subject TEXT.
v11_ledger_resolve_by_task_id() {
    if [ "${V11_TASK_RESOLVER:-shared}" = "legacy" ]; then
        _v11_ledger_resolve_by_task_id_legacy "$@"
        return 0
    fi
    local project="$1" task_id="$2" session_uuid="${3:-}"
    [ $# -gt 4 ] && shift 4 || set --
    V11_IDENTITY_HELPER=on v11_resolve_identity "$project" "$task_id" "$session_uuid" "" --format tsv "$@"
}
_v11_ledger_resolve_by_task_id_legacy() {
    local project="$1"
    local task_id="$2"
    local session_uuid="${3:-}"
    local scan_cap="${4:-50000}"

    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        printf 'MISS'
        return 0
    fi
    if [ -z "$task_id" ]; then
        printf 'MISS'
        return 0
    fi

    local ledger_file="${METRICS_DIR}/ledger/${project}.jsonl"
    if [ ! -f "$ledger_file" ] || [ ! -s "$ledger_file" ]; then
        printf 'MISS'
        return 0
    fi

    V11_LRT_FILE="$ledger_file" \
    V11_LRT_TASK="$task_id" \
    V11_LRT_SESSION="$session_uuid" \
    V11_LRT_PROJECT="$project" \
    V11_LRT_CAP="$scan_cap" \
    python3 - <<'RESOLVE_PYEOF' 2>/dev/null
import os, re, sys, json

ledger_path = os.environ.get("V11_LRT_FILE", "")
target_task = os.environ.get("V11_LRT_TASK", "")
target_sess = os.environ.get("V11_LRT_SESSION", "")
project     = os.environ.get("V11_LRT_PROJECT", "")
scan_cap    = int(os.environ.get("V11_LRT_CAP", "50000"))

if not ledger_path or not target_task or not project:
    print("MISS", end=""); sys.exit(0)

try:
    with open(ledger_path, "rb") as fh:
        raw_bytes = fh.read()
except OSError:
    print("MISS", end=""); sys.exit(0)
if not raw_bytes:
    print("MISS", end=""); sys.exit(0)

try:
    raw_text = raw_bytes.decode("utf-8", errors="replace")
except Exception:
    print("MISS", end=""); sys.exit(0)

lines = raw_text.split("\n")
if lines and lines[-1] != "":
    lines = lines[:-1]  # drop torn tail (§4.3)
lines = [ln for ln in lines if ln != ""]
if len(lines) > scan_cap:
    print(f"LEDGER-IDENTITY-SCAN-CAP: scan_cap={scan_cap} project={project} — "
          f"only the newest {scan_cap} lines were considered", file=sys.stderr)
    lines = lines[-scan_cap:]

candidates = []  # every identity-bearing event for TASK_ID: (identity, session_uuid, ev), newest first
completed = set()  # identities with a `completed` event
for raw in reversed(lines):
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if not isinstance(ev, dict):
        continue
    if ev.get("project") != project:
        continue
    if str(ev.get("task_id", "")) != str(target_task):
        continue
    if ev.get("ev") in ("review", "prescope"):
        continue
    sn = ev.get("subject_norm") or ""
    cs = ev.get("create_seq")
    if not sn or not isinstance(cs, int) or isinstance(cs, bool) or cs < 0:
        continue
    if ev.get("ev") == "completed":
        completed.add((sn, cs))
    candidates.append(((sn, cs), str(ev.get("session_uuid") or ""), ev.get("ev")))


def distinct(cands):
    out = {}  # identity -> sessions that carry it (newest identity first)
    for ident, sess, _ev in cands:
        out.setdefault(ident, set()).add(sess)
    return out


def describe(idents):
    return "; ".join(
        f"session {','.join(sorted(s[:8] for s in sessions if s)) or '?'}: "
        f"\"{sn[:60]}\" (create_seq {cs})"
        for (sn, cs), sessions in idents.items())


def bind(ident, note=""):
    print(f"{ident[0]}\t{ident[1]}" + (f"\nNOTE\t{note}" if note else ""), end="")
    sys.exit(0)


is_uuid = bool(re.fullmatch(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", target_sess))
if is_uuid:
    mine = distinct([c for c in candidates if c[1] == target_sess])
    if len(mine) == 1:
        bind(next(iter(mine)))
    if len(mine) > 1:
        done = [i for i in mine if i in completed]
        if len(done) == 1:
            bind(done[0])
        print(f"AMBIGUOUS\tsession {target_sess} holds {len(mine)} tasks under task_id "
              f"{target_task} and {len(done) or 'none'} of them completed — {describe(mine)}",
              end="")
        sys.exit(0)

identities = distinct(candidates)
if not identities:
    print("MISS", end=""); sys.exit(0)
if len(identities) == 1:
    only = next(iter(identities))
    note = ""
    if target_sess:
        owners = ",".join(sorted(s[:8] for s in identities[only] if s)) or "?"
        why = (f"session {target_sess} holds no task {target_task}" if is_uuid
               else f"'{target_sess}' is not a session UUID")
        note = f"{why}; bound to the only task carrying that id (session {owners})"
    bind(only, note)
why = ""
if target_sess:
    why = (f" (session {target_sess} holds none of them)" if is_uuid
           else f" ('{target_sess}' is not a session UUID)")
print(f"AMBIGUOUS\ttask_id {target_task} names more than one task in the {project} ledger — "
      f"{describe(identities)}. Pass the parent's session UUID as SESSION_UUID{why} "
      f"(4th argument; `review-queue pending {project} --json` lists it)", end="")
sys.exit(0)
RESOLVE_PYEOF
}

# v11_resolve_identity PROJECT TASK_ID SESSION_UUID [SUBJECT]
#   v11.42 W1-T3 — canonical-identity resolver for downstream consumers.
#   Recon #1 (sessions/v11-task-state-integrity/recon-notes/README.md#recon-1)
#   confirmed create_seq is correct and monotonic per (project, subject_norm);
#   apparent non-monotonicity across a task_id was two unrelated subjects
#   reusing the same session-local, ephemeral task_id slot (documented at
#   common.sh:2744). Canonical identity is (project, subject_norm, create_seq)
#   — see idk() at common.sh:3092. Callers correlating ledger events across
#   time MUST resolve through this helper, not compare task_id directly.
#
#   Bounded reverse-scan of the project ledger for the most-recent `created`
#   event matching (session_uuid, task_id). When SUBJECT is non-empty, the
#   match additionally requires subject_norm(SUBJECT) to equal the event's
#   subject_norm — mirrors the (session, task_id, subject_norm) key proven
#   correct by ~/.claude/skills/align-aggregate/align_aggregate.py
#   index_events() (v1.1 fix for the same task_id-reuse trap).
#
#   Emits JSON on stdout:
#     {"create_seq": N, "subject_norm": "...", "found": true}
#   or on no match / any internal error (side-effect-never-fails):
#     {"create_seq": null, "subject_norm": null, "found": false}
#
#   Rollback: V11_IDENTITY_HELPER=off emits the not-found shape unconditionally.
#
#   S2-T0b-3 (#113): the scan above is the v11.46 path, kept under
#   V11_TASK_RESOLVER=legacy. By default this is the bash wrapper on
#   scripts/lib/task_epoch.py resolve, the resolver every reader shares (rules
#   R0-R4 in its docstring):
#     v11_resolve_identity PROJECT TASK_ID SESSION_UUID [SUBJECT]
#         [--identity SN:CS] [--epoch E] [--at TS [--seqno N]] [--format json|tsv]
#   SESSION_UUID may be empty (R3). SUBJECT no longer filters: R2/R3 prefer
#   the claim whose norms hold it, and R4 on a stamped current TaskList epoch
#   binds that epoch's claim whatever it says. The JSON keeps the three fields above and
#   adds status (bound|unresolved|ambiguous), basis, note and candidates;
#   found is true only when bound. --format tsv prints the
#   v11_ledger_resolve_by_task_id contract (SN\tCS[\nNOTE\t..] | MISS |
#   AMBIGUOUS\t..). V11_IDENTITY_HELPER=off applies to the JSON form only.
#   One python3 run plus a ledger replay: never call it on a hook hot path.
#   Values reach task_epoch.py as --opt=VALUE and the positionals after --, so
#   a subject, norm or id starting with '-' is data, never an option (review
#   #23). task_epoch.py's stderr (notes, warnings, usage errors) passes through
#   to the caller's stderr; a non-zero exit adds a line and reads as MISS.
v11_resolve_identity() {
    if [ "${V11_TASK_RESOLVER:-shared}" = "legacy" ]; then
        _v11_resolve_identity_legacy "$@"
        return 0
    fi
    local project="${1:-}" task_id="${2:-}" session_uuid="${3:-}" subject="${4:-}" fmt="json"
    local _not_found='{"create_seq":null,"subject_norm":null,"found":false}'
    [ $# -gt 4 ] && shift 4 || set --
    local _ri_args=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --format) fmt="${2:-json}"; shift; [ $# -gt 0 ] && shift ;;
            --format=*) fmt="${1#--format=}"; shift ;;
            --identity|--epoch|--at|--seqno|--subject) _ri_args+=("$1=${2:-}"); shift; [ $# -gt 0 ] && shift ;;
            *) _ri_args+=("$1"); shift ;;
        esac
    done
    [ "$fmt" = "tsv" ] || fmt="json"
    local _miss="MISS"
    if [ "$fmt" = "json" ]; then
        _miss="$_not_found"
        if [ "${V11_IDENTITY_HELPER:-on}" = "off" ]; then
            printf '%s' "$_not_found"
            return 0
        fi
    fi
    if [ -z "$project" ] || [ -z "$task_id" ] || ! [[ "$project" =~ ^[a-zA-Z0-9._-]{1,64}$ ]] \
       || [ ! -s "${METRICS_DIR}/ledger/${project}.jsonl" ]; then
        printf '%s' "$_miss"
        return 0
    fi
    [ -n "$subject" ] && _ri_args+=("--subject=$subject")
    local _out="" _rc=0
    _out=$(python3 "$V11_HOME/scripts/lib/task_epoch.py" resolve \
        "--session=$session_uuid" "--metrics-dir=$METRICS_DIR" "--format=$fmt" \
        "${_ri_args[@]+"${_ri_args[@]}"}" -- "$project" "$task_id") || { _rc=$?; _out=""; }
    [ "$_rc" -eq 0 ] || echo "v11_resolve_identity: task_epoch.py resolve exited $_rc for task $task_id; read as unresolved" >&2
    if [ "$fmt" = "tsv" ]; then
        printf '%s' "${_out:-MISS}"
        return 0
    fi
    _out=$(printf '%s' "$_out" | jq -c '
        {create_seq: (.identity.create_seq // null), subject_norm: (.identity.subject_norm // null),
         found: (.status == "bound"), status: (.status // "unresolved"), basis: (.basis // null),
         note: (.note // ""), candidates: (.candidates // [])}' 2>/dev/null) || _out=""
    printf '%s' "${_out:-$_not_found}"
    return 0
}
_v11_resolve_identity_legacy() {
    local project="$1"
    local task_id="$2"
    local session_uuid="$3"
    local subject="${4:-}"
    local _not_found='{"create_seq":null,"subject_norm":null,"found":false}'

    if [ "${V11_IDENTITY_HELPER:-on}" = "off" ]; then
        printf '%s' "$_not_found"
        return 0
    fi

    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        printf '%s' "$_not_found"
        return 0
    fi
    if [ -z "$task_id" ] || [ -z "$session_uuid" ]; then
        printf '%s' "$_not_found"
        return 0
    fi

    local ledger_file="${METRICS_DIR}/ledger/${project}.jsonl"
    if [ ! -f "$ledger_file" ] || [ ! -s "$ledger_file" ]; then
        printf '%s' "$_not_found"
        return 0
    fi

    local target_norm=""
    if [ -n "$subject" ]; then
        target_norm=$(v11_normalize_subject "$subject" 2>/dev/null) || target_norm=""
    fi

    local _result
    _result=$(
        V11_RI_FILE="$ledger_file" \
        V11_RI_TASK="$task_id" \
        V11_RI_SESSION="$session_uuid" \
        V11_RI_PROJECT="$project" \
        V11_RI_NORM="$target_norm" \
        V11_RI_CAP="50000" \
        python3 - <<'RESOLVE_IDENTITY_PYEOF' 2>/dev/null
import os, sys, json

ledger_path = os.environ.get("V11_RI_FILE", "")
target_task = os.environ.get("V11_RI_TASK", "")
target_sess = os.environ.get("V11_RI_SESSION", "")
project     = os.environ.get("V11_RI_PROJECT", "")
target_norm = os.environ.get("V11_RI_NORM", "")
scan_cap    = int(os.environ.get("V11_RI_CAP", "50000"))

MISS = json.dumps({"create_seq": None, "subject_norm": None, "found": False})

if not ledger_path or not target_task or not target_sess or not project:
    print(MISS, end=""); sys.exit(0)

try:
    with open(ledger_path, "rb") as fh:
        fh.seek(0, 2)
        scan_end_off = fh.tell()
        if scan_end_off == 0:
            print(MISS, end=""); sys.exit(0)
        fh.seek(0)
        raw_bytes = fh.read(scan_end_off)
except OSError:
    print(MISS, end=""); sys.exit(0)

try:
    raw_text = raw_bytes.decode("utf-8", errors="replace")
except Exception:
    print(MISS, end=""); sys.exit(0)

lines = raw_text.split("\n")
if lines and lines[-1] != "":
    lines = lines[:-1]  # drop torn tail (§4.3)

lines_scanned = 0
for raw in reversed(lines):
    if raw == "":
        continue
    lines_scanned += 1
    if lines_scanned > scan_cap:
        print(f"LEDGER-IDENTITY-MISS-SCAN-CAP: scan_cap={scan_cap} project={project}", file=sys.stderr)
        print(MISS, end=""); sys.exit(0)
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if not isinstance(ev, dict):
        continue
    if ev.get("ev") != "created":
        continue
    if ev.get("project") != project:
        continue
    if str(ev.get("session_uuid", "")) != target_sess:
        continue
    if str(ev.get("task_id", "")) != str(target_task):
        continue
    sn = ev.get("subject_norm", "") or ""
    if target_norm and sn != target_norm:
        continue
    cs = ev.get("create_seq")
    if cs is None:
        continue
    print(json.dumps({"create_seq": int(cs), "subject_norm": sn, "found": True}), end="")
    sys.exit(0)

print(MISS, end="")
RESOLVE_IDENTITY_PYEOF
    ) || true

    if [ -z "$_result" ]; then
        _result="$_not_found"
    fi
    printf '%s' "$_result"
    return 0
}

# v11_replay_ledger PROJECT
#   Pure function of $METRICS_DIR/ledger/<project>.jsonl.
#   Folds all events via the ADR §3.1–§3.5 single-pass algorithm and emits the
#   project aggregate JSON on stdout.  Zero session-dir reads.
#
#   Implements:
#     §3.2  Sort: (ts, seqno) ascending; last-event-wins per identity.
#     §3.3  Counter fold: additive counters_delta accumulation.
#     §3.4  Per-identity state machine; reconcile(scope=project) sets absolute;
#           reconcile(scope=identity) forces one identity's status then
#           post-fold counter re-derivation from by_id (ground truth).
#     MED-B Sentinel: scope=project reconcile asserts subject_norm=="" &&
#                     create_seq==-1 and MUST continue before any by_id path.
#     §3.5  Aggregate projection equal-or-superset of current aggregate schema;
#           open_tasks_by_session excludes completed AND blocked (HIGH-B).
#
#   Returns 0 + emits JSON on success.
#   Returns non-zero + emits nothing on irrecoverable error (unknown version,
#   ledger missing, invalid project name).
v11_replay_ledger() {
    local project="$1"
    [ -z "$project" ] && return 1
    if ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_replay_ledger: rejected invalid project name" >&2
        return 1
    fi

    local ledger_file="$METRICS_DIR/ledger/${project}.jsonl"
    if [ ! -f "$ledger_file" ]; then
        echo "v11_replay_ledger: ledger file not found: $ledger_file" >&2
        return 1
    fi

    # Delegate the stateful fold to Python.
    # jq cannot handle the stateful accumulation cleanly; Python matches the
    # existing review-ledger helper pattern in sync-tasks.
    V11_REPLAY_PROJECT="$project" \
    V11_REPLAY_LEDGER="$ledger_file" \
    V11_REPLAY_V11HOME="$V11_HOME" \
    V11_REPLAY_NOW="$(date -Iseconds)" \
    V11_CANCELLED_FILTERS_REPLAY="${V11_CANCELLED_FILTERS_REPLAY:-on}" \
    V11_CANCELLED_UNFOLD_SINCE_TS="${V11_CANCELLED_UNFOLD_SINCE_TS:-}" \
    python3 - <<'PYEOF'
import os, sys, json, datetime

project     = os.environ.get("V11_REPLAY_PROJECT", "")
ledger_path = os.environ.get("V11_REPLAY_LEDGER", "")
v11_home    = os.environ.get("V11_REPLAY_V11HOME", "")
now         = os.environ.get("V11_REPLAY_NOW") or datetime.datetime.now().isoformat()

# improvements/48 (v11.39-1): V11_CANCELLED_FILTERS_REPLAY gates the cancelled-
# fold branch in the open-view construction (line ~3469). Default "on" preserves
# #17's F1 behavior (cancelled is terminal, absent from open_tasks). When "off",
# cancelled events are unfolded ONLY when cancelled_at >= V11_CANCELLED_UNFOLD_
# SINCE_TS (default now-1h). The paired cutoff prevents R2 swarm's retroactive-
# unfold silent failure on stale cancelled events surfacing in long sessions.
cancelled_filters_replay = os.environ.get("V11_CANCELLED_FILTERS_REPLAY", "on")

def _v11_parse_iso(s):
    """Tolerant ISO-8601 parse; return None on any failure or empty input."""
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

_cancelled_cutoff_dt = None
if cancelled_filters_replay == "off":
    _cancelled_cutoff_dt = _v11_parse_iso(os.environ.get("V11_CANCELLED_UNFOLD_SINCE_TS", ""))
    if _cancelled_cutoff_dt is None:
        _now_dt = _v11_parse_iso(now) or datetime.datetime.now()
        _cancelled_cutoff_dt = _now_dt - datetime.timedelta(hours=1)

# Import the canonical normalize_subject from scripts/lib (ADR §2.1, Risk #4).
# This is the ONLY normalization path — no reimplementation here.
if v11_home:
    sys.path.insert(0, v11_home + "/scripts/lib")
try:
    from normalize_subject import normalize_subject
except ImportError:
    # Fallback stub (should never fire in production, but guards test isolation)
    import unicodedata, re as _re
    _ID_PRE = _re.compile(r"^\s*(?:#?\d+[.):\-]?\s+|t-?\d+[.):\-]?\s+|task\s+#?\d+[.):\-]?\s+)", _re.IGNORECASE)
    _WS = _re.compile(r"\s+"); _PU = _re.compile(r"[.,:;!?_/\\|\-]+")
    _SC = ' \t\r\n.,:;!?\\-_/\\|"\'`()[]{}'
    def normalize_subject(s):
        s = unicodedata.normalize("NFC", s).casefold()
        s = _ID_PRE.sub("", s, 1)
        s = _WS.sub(" ", s).strip(_SC)
        s = _PU.sub(" ", s); s = _WS.sub(" ", s).strip()
        s = s[:200]
        return s or "__empty__"

# S1-P3 (review #61): the one waived/void correction rule, shared with
# agent-scorecard (scripts/lib/review_corrections.py).
try:
    from review_corrections import correction_outcomes
except ImportError:
    def correction_outcomes(rows):  # test-isolation stub; void rows are still skipped
        return {}

# S2-T0b-1 (#113): the (session_uuid, tl_epoch, task_id) keying rule, shared
# with scripts/lib/task_epoch.py. tl_epoch is None on an unstamped event, so an
# unstamped ledger keys exactly as the v11.46 (session_uuid, task_id) index did.
# Review #20: imported from the import-free task_key.py (not task_epoch.py) and
# computed once per event (memo on id(ev); `events` outlives every call).
# Rollback: V11_TASK_RESOLVER=legacy (v11.46 keying, alias-only sibling norms,
# no tl_epoch/identity fields).
_RESOLVER_LEGACY = os.environ.get("V11_TASK_RESOLVER", "shared") == "legacy"
try:
    from task_key import claim_key as _claim_key
except ImportError:
    def _claim_key(ev):  # test-isolation stub: every event reads as unstamped
        _t = ev.get("task_id")
        return (str(ev.get("session_uuid") or ""), None, "" if _t is None else str(_t))
_ck_memo = {}

def claim_key(ev):
    _ck = _ck_memo.get(id(ev))
    if _ck is None:
        _ck = _claim_key(ev)
        if _RESOLVER_LEGACY:
            _ck = (_ck[0], None, _ck[2])
        _ck_memo[id(ev)] = _ck
    return _ck


# ---------------------------------------------------------------------------
# §4.3  Parse ledger — skip malformed/truncated lines safely
# ---------------------------------------------------------------------------
def parse_ledger(path, project_name):
    """Yield valid event dicts, skipping malformed lines (ADR §4.3)."""
    try:
        raw_text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        print(f"v11_replay_ledger: cannot read ledger {path}: {exc}", file=sys.stderr)
        sys.exit(1)

    lines = raw_text.split("\n")
    skipped = 0
    events = []
    for i, raw in enumerate(lines):
        if raw == "":
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            # ADR §4.3: only tolerate torn final fragment (last non-empty line)
            remaining = [l for l in lines[i+1:] if l != ""]
            if not remaining:
                skipped += 1
                continue
            # Non-terminal undecodable → hard error + skip
            print(f"v11_replay_ledger: non-terminal undecodable line {i+1} in {path} — skipped", file=sys.stderr)
            skipped += 1
            continue
        if not isinstance(ev, dict) or "ev" not in ev or "v" not in ev:
            skipped += 1
            continue
        v = ev.get("v")
        if v != 1:
            print(f"v11_replay_ledger: unknown ledger version {v!r}", file=sys.stderr)
            sys.exit(1)
        # §1.2: project assertion — mismatched lines skipped + counted
        if ev.get("project") != project_name:
            skipped += 1
            continue
        events.append(ev)
    if skipped:
        print(f"v11_replay_ledger: skipped {skipped} malformed/mismatched lines in {path}", file=sys.stderr)
    return events


# ---------------------------------------------------------------------------
# §3.2  Sort: (ts, seqno) ascending — strict total order
# ---------------------------------------------------------------------------
_UTC = datetime.timezone.utc
_TS_MIN = datetime.datetime.min.replace(tzinfo=_UTC)

def sort_key(ev):
    # improvements/60: order by the parsed UTC instant, seqno as tiebreak.
    # The ts STRING is not an order (the ledger mixes +02:00 and +00:00),
    # and seqno alone is not either (hand-appended events carry none).
    # Rollback: V11_REPLAY_ORDER=ts-string.
    if _REPLAY_ORDER_LEGACY:
        return (ev.get("ts", ""), int(ev.get("seqno", 0) or 0))
    d = _v11_parse_iso(ev.get("ts", ""))
    if d is None:
        d = _TS_MIN
    elif d.tzinfo is None:
        d = d.replace(tzinfo=_UTC)
    else:
        d = d.astimezone(_UTC)
    return (d, int(ev.get("seqno", 0) or 0))

_REPLAY_ORDER_LEGACY = os.environ.get("V11_REPLAY_ORDER", "") == "ts-string"


# ---------------------------------------------------------------------------
# §3.4  Identity key  (project, subject_norm, create_seq) → string
# ---------------------------------------------------------------------------
def idk(ev):
    return ev.get("project", "") + "\x00" + ev.get("subject_norm", "") + "\x00" + str(ev.get("create_seq", 0))


def fresh():
    return {
        "status": "pending",
        "subject": "",
        "description": "",
        "metadata": {},
        "recommended_agent": None,
        "owner": None,
        "sprint": None,
        "gate": None,
        "created_ts": None,
        "completed_at": None,
        "blocked_at": None,
        "blocked_reason": None,
        "cancelled_at": None,
        "cancelled_reason": None,
        "artifacts": None,
        "task_id": None,
        "session_uuid": None,
        "task_id_by_session": {},   # §3.5 HIGH-2: session_uuid -> task_id
        "reconciled": False,
        # F3 fix (production-readiness): True only while this by_id record's
        # sole origin is a "review" event for an identity/task_id that has no
        # "created" event anywhere in the ledger. Such records must NEVER
        # count toward total/pending/completed — including via the realign
        # derivation below — since they represent no real task, just an
        # orphaned review verdict pointer. Cleared the moment any real
        # (created/in_progress/completed/blocked/reconcile) event lands on
        # the same identity.
        "review_only": False,
    }


def deep_merge(base, overlay):
    """Per-key last-write-wins merge (ADR §3.3)."""
    result = dict(base or {})
    for k, v in (overlay or {}).items():
        result[k] = v
    return result


# ---------------------------------------------------------------------------
# §3.3 / §3.4  Single-pass fold
# ---------------------------------------------------------------------------
events = parse_ledger(ledger_path, project)
# {(seqno, ts): "waived"|"void"} — computed in file order, before the sort.
review_corrected = correction_outcomes(events)
events.sort(key=sort_key)

counters = {"total": 0, "pending": 0, "in_progress": 0, "completed": 0, "blocked": 0, "cancelled": 0}
by_id = {}
# improvements/24: (session_uuid, task_id) -> idk key, built from
# identity-bearing events only. Status events appended WITHOUT subject_norm
# (e.g. hand-appended "cancelled" events per #17's remediation, plus a
# handful of historical "completed" events) would otherwise phantom-key to
# (project, "", create_seq) and never touch the real record — the fold
# result silently kept them open. Mirrors the review branch's E1
# unresolved-identity handling, but resolves to the REAL record instead of
# a sentinel, since status events must advance the actual state machine.
#
# AMBIGUITY (adversarial finding #1, 2026-08-06): a session CAN legitimately
# reuse a local task_id for two distinct identities (real example: HAM
# session bd617d7c created task_id=6 twice — TaskList wipe + re-create).
# Once a SECOND distinct identity claims a (session_uuid, task_id) pair, a
# subject_norm-less event for that pair is irreducibly ambiguous — resolving
# to the newest claimant can cancel/complete the WRONG task, which is worse
# than phantom-keying. The pair goes permanently AMBIGUOUS and lookups
# refuse (legacy phantom fallthrough). Resolution before the second claim
# still lands on the then-only claimant (closest-preceding semantics).
# S2-T0b-1 (#113): the index is keyed on claim_key(ev) = (session_uuid,
# tl_epoch, task_id). A resumed conversation keeps its hook session but gets a
# new TaskList that reuses ids 1..N, and hooks/sync-tasks stamps each event
# with the TaskList epoch it ran in (tl_epoch). A stamped pair is exact per
# epoch; every claim is also noted under the unstamped (session, None, id)
# key, which unstamped events look up with the sticky rule above, unchanged.
sess_task_index = {}
sess_task_claims = {}  # every identity that ever claimed a claim_key
sess_task_last = {}    # (session, None, task_id) -> the latest claimant noted
epoch_open = {}        # (session, tl_epoch) -> tl_open of the create that opened it
# Per project (review #20): epoch_open sees only this project's ledger, so the
# replay stays one incremental file read. TaskIndex.epochs() reads every
# ledger (C13). When a create in ANOTHER project opened the epoch `fresh`, a
# stamped subject_norm-less row here stays unresolved (a phantom key) where
# TaskIndex binds it by inference_cross_epoch. It fails safe: no wrong bind.
_stamped_fb = {}       # id(ev) -> the fold's answer for a stamped event
_IDK_AMBIGUOUS = object()
# Every stamped claim_key a claim holds, anywhere in the ledger (review #19
# C11): a stamped row whose epoch claims its id only later names an older
# task. A claim is what task_epoch.py R1 counts (review #20): an
# identity-bearing `created`; other identity-bearing rows only for a
# (session, task_id) with no `created` at all (a task older than the ledger).
# A later status row in a reuse epoch whose create was dropped is no claim, so
# an earlier subject_norm-less row there stays unresolved. Empty for an
# unstamped ledger.
_stamped_claims, _created_pairs, _stamped_other = set(), set(), []
for _e in events:
    if not _e.get("subject_norm") or _e.get("ev") in ("review", "prescope"):
        continue
    _ck = claim_key(_e)
    if _e.get("ev") == "created":
        _created_pairs.add((_ck[0], _ck[2]))
        if _ck[1] is not None:
            _stamped_claims.add(_ck)
    elif _ck[1] is not None:
        _stamped_other.append(_ck)
_stamped_claims.update(_ck for _ck in _stamped_other if (_ck[0], _ck[2]) not in _created_pairs)

def sess_index_note(ev, key):
    """Record `key` as a claimant of this event's claim_key.
    Call ONLY for identity-bearing (subject_norm-carrying) events."""
    _s = ev.get("session_uuid")
    _t = ev.get("task_id")
    if not _s or _t is None:
        return
    _ck = claim_key(ev)
    _keys = (_ck,) if _ck[1] is None else (_ck, (_ck[0], None, _ck[2]))
    for _k in _keys:
        sess_task_claims.setdefault(_k, set()).add(key)
        _prev = sess_task_index.get(_k)
        if _prev is None or _prev == key:
            sess_task_index[_k] = key
        else:
            sess_task_index[_k] = _IDK_AMBIGUOUS  # sticky — never resolves again
    sess_task_last[_keys[-1]] = key

def _stamped_resolve(ck):
    _fb = sess_task_index.get(ck)
    if _fb is not None:
        return None if _fb is _IDK_AMBIGUOUS else _fb
    # No claim in the event's own epoch so far (task_epoch.py rule R1). When
    # the epoch claims the id later (C11: the row predates that create, so it
    # names an older task), or the epoch opened `fresh` (first create of the
    # session, or the epoch record was lost) and continues the TaskList before
    # it, the latest earlier claimant binds. A `reuse` epoch, or one whose
    # opening create is not in the ledger, never binds into an older epoch:
    # its create was never ledgered.
    if ck not in _stamped_claims and epoch_open.get((ck[0], ck[1])) != "fresh":
        return None
    return sess_task_last.get((ck[0], None, ck[2]))

def sess_index_resolve(ev):
    """Fallback idk key for a subject_norm-less event, or None when there is
    no unambiguous well-formed precedent for its claim_key."""
    _ck = claim_key(ev)
    if _ck[1] is not None:
        # Resolved once, at the event's place in the fold; the walks after
        # the fold reuse that answer instead of the index's final state.
        if id(ev) not in _stamped_fb:
            _stamped_fb[id(ev)] = _stamped_resolve(_ck)
        return _stamped_fb[id(ev)]
    _fb = sess_task_index.get(_ck)
    if _fb is None or _fb is _IDK_AMBIGUOUS:
        return None
    return _fb

# S1-T2c: rehydrate aliases. v11-resume-tasks stamps a rehydrated task's source
# identity into metadata.rehydrated_from.identity. For a task renamed before the
# restart, the rehydrated `created` carries the NEW subject_norm, so
# v11_ledger_append's continuation (keyed on subject_norm) mints a fresh
# identity and the original stays open forever (v11-leverage-program #71 ->
# #1). A `created` whose rehydrated_from.identity names a different identity
# already in by_id is an ALIAS: every event of its own identity folds into the
# original. Only an identity's first event can alias it (one with history is a
# separate task, never merged); a malformed rehydrated_from, or a target never
# seen, is ignored. Targets are always by_id keys and aliases never enter
# by_id, so chains stay one hop; alias_resolve still refuses a loop.
# A target already completed or cancelled is never aliased (review #3): the
# alias heals originals left OPEN, and a stale handoff (v11-resume-tasks does
# no ledger check) that rehydrates a finished task would otherwise reopen it.
# The fold runs in (ts, seqno) order, so this is the target's status as of the
# alias's own `created`.
# Read-side, so existing ledgers heal without a rewrite.
# Rollback: V11_REPLAY_REHYDRATE_ALIAS=off.
_REHYDRATE_ALIAS = os.environ.get("V11_REPLAY_REHYDRATE_ALIAS", "on") != "off"
alias_of = {}     # alias idk key -> the identity key it folds into
alias_norms = {}  # target key -> subject_norms of its aliases (sibling link)
alias_src = {}    # alias idk key -> the `created` that made it (identity view)

def alias_resolve(key):
    _seen = set()
    while key in alias_of and key not in _seen:
        _seen.add(key)
        key = alias_of[key]
    return key

def alias_note(ev, key):
    """Register `key`, a created event's own identity, as an alias of the
    identity its metadata.rehydrated_from.identity names, when valid."""
    if not _REHYDRATE_ALIAS or key in by_id or key in alias_of:
        return
    md = ev.get("metadata")
    rf = md.get("rehydrated_from") if isinstance(md, dict) else None
    ident = rf.get("identity") if isinstance(rf, dict) else None
    if not isinstance(ident, dict):
        return
    sn, cs = ident.get("subject_norm"), ident.get("create_seq")
    if (not isinstance(sn, str) or not sn or isinstance(cs, bool)
            or not isinstance(cs, int) or cs < 0):
        return
    target = alias_resolve(ev.get("project", "") + "\x00" + sn + "\x00" + str(cs))
    if (target == key or target not in by_id or by_id[target].get("review_only")
            or by_id[target]["status"] in ("completed", "cancelled")):
        return
    alias_of[key] = target
    alias_norms.setdefault(target, set()).add(ev.get("subject_norm"))
    alias_src[key] = ev

# S2-T0b-1 (design §6.6): every subject an identity went by, for the
# sibling-follows-parent link. key_norms(key) = its own norm, its aliases'
# norms, and the normalized subject of each `created` and renaming
# field_update folded into it: a renamed or rehydrated parent keeps its first
# norm while its review sibling says "Review: <new subject>". Subjects are
# normalized only when a sibling asks. task_epoch.py builds the same set.
key_subjects = {}     # identity key -> raw subjects (created / field_update)
tl_epoch_by_key = {}  # identity key -> {session_uuid: last tl_epoch stamped on it}
_key_norms_memo = {}

def key_norms(key):
    if key not in _key_norms_memo:
        _n = {key.split("\x00")[1]} | alias_norms.get(key, set())
        if not _RESOLVER_LEGACY:
            _n |= {normalize_subject(_s) for _s in key_subjects.get(key, ())}
        _key_norms_memo[key] = _n
    return _key_norms_memo[key]

# S1-T2c: every `created` folded into an identity, for the identity view
# (scripts/wave-check binds review_of by task-id epoch from these).
created_claims = {}
project_pinned_at = None
last_ts = ""
phase = "discovery"

# Archive-aware accounting (HIGH wave-review finding, ledger-archive R7):
# scripts/ledger-archive physically removes archived-sprint events from the
# live ledger and appends ONE "sprint_archived" summary event carrying
# tasks_total/tasks_completed for the tasks it removed. Those tasks' original
# created/completed events are gone, so by_id can never re-derive them — a
# fresh replay would silently undercount vs. the pre-archive aggregate.
# Fold the summary counts in separately (not via by_id, which has no record
# for archived identities) and add them back into both the additive
# `counters` fold and the by_id-derived `derived` re-alignment below, so
# archived history is never lost from a replay.
archived_total = 0
archived_completed = 0

for ev in events:
    ev_type = ev.get("ev")
    ev_ts = ev.get("ts", "")
    if ev_ts > last_ts:
        last_ts = ev_ts

    # ------------------------------------------------------------------
    # sprint_archived branch — accumulate summary counts only; NEVER key
    # by_id (there is no real identity behind the summary event, and the
    # per-task events it summarizes are gone from this ledger by design).
    # ------------------------------------------------------------------
    if ev_type == "sprint_archived":
        try:
            archived_total += int(ev.get("tasks_total", 0) or 0)
        except (TypeError, ValueError):
            pass
        try:
            archived_completed += int(ev.get("tasks_completed", 0) or 0)
        except (TypeError, ValueError):
            pass
        continue

    # ------------------------------------------------------------------
    # reconcile branch
    # ------------------------------------------------------------------
    if ev_type == "reconcile":
        # ADR §1.3: defensively IGNORE any counters_delta on reconcile
        scope = ev.get("scope", "")

        if scope == "project":
            # MED-B invariant: assert sentinel fields, then MUST continue
            # before touching by_id
            sn = ev.get("subject_norm", "")
            cs = ev.get("create_seq", -1)
            if sn != "" or cs != -1:
                print(
                    f"v11_replay_ledger: MED-B violation — project-scope reconcile "
                    f"has non-sentinel subject_norm={sn!r} create_seq={cs!r}; "
                    f"ignored",
                    file=sys.stderr,
                )
                # Fall through to `continue` — NEVER key by_id
            else:
                abs_c = ev.get("counters_abs")
                if isinstance(abs_c, dict):
                    for k in ("total", "pending", "in_progress", "completed", "blocked"):
                        if k in abs_c:
                            counters[k] = int(abs_c[k])
                    project_pinned_at = ev.get("seqno")
            # MUST continue before any by_id path (MED-B)
            continue

        elif scope == "identity":
            # identity-scope reconcile IS permitted to key by_id
            _rkey = alias_resolve(idk(ev))
            rec = by_id.setdefault(_rkey, fresh())
            # improvements/24 (adversarial finding #2): an identity-bearing
            # reconcile also registers its claim so a later subject_norm-less
            # status event can heal through it — relevant post-archive, where
            # the reconcile may be the only surviving identity-bearing event
            # for a task. Subject_norm-less identity reconciles get no F1
            # fallback (out of scope — reconcile emitters are our own
            # tooling and always stamp identity).
            if ev.get("subject_norm"):
                sess_index_note(ev, _rkey)
            forced = ev.get("identity_status")
            if forced in ("pending", "in_progress", "completed", "blocked"):
                rec["status"] = forced
            rec["reconciled"] = True
            # F3 fix: an explicit reconcile targeting this identity is a real
            # event about a real task — clear any review_only phantom flag.
            rec["review_only"] = False
        # reconcile never applies counters_delta
        continue

    # ------------------------------------------------------------------
    # review branch (W5-T16, improvements/09) — status-neutral,
    # counters_delta-free per identity. Mirrors the identity-scope
    # reconcile's counter skip above: NEVER advances the state machine,
    # NEVER applies counters_delta. Only records the last review verdict
    # pointer on the identity (last_review_severity/last_review_ts +
    # verdict_ref/verdict_sha when present) for downstream lookups.
    # ------------------------------------------------------------------
    if ev_type == "review":
        # S1-P3 (review #61): a void row is no review, and neither is the row it
        # voids. last_review_* reaches only the identity view, so the default
        # aggregate is byte-identical either way.
        if (str(ev.get("outcome") or "").lower() == "void"
                or review_corrected.get((ev.get("seqno"), ev.get("ts"))) == "void"):
            continue
        # E1 fix (adversarial-lite): identity-unresolved review events share
        # the sentinel subject_norm=="" / create_seq==-1 key, which collapses
        # ALL unresolved reviews for a project onto one by_id record and lets
        # each task's verdict pointer clobber the previous task's. Key
        # unresolved reviews by task_id instead so distinct tasks keep
        # distinct verdict pointers; resolved events keep the normal idk(ev).
        if ev.get("identity_unresolved") or ev.get("create_seq") in (None, -1):
            _key = (ev.get("project", ""), "__unresolved__", ev.get("task_id", ""))
        else:
            _key = alias_resolve(idk(ev))
        _review_new = _key not in by_id
        rec = by_id.setdefault(_key, fresh())
        if _review_new:
            # F3 fix: this record exists ONLY because of this review event —
            # no created/in_progress/completed/blocked event ever keyed this
            # identity. Never let it count toward counters/derived below.
            rec["review_only"] = True
        rec["last_review_severity"] = ev.get("review_severity")
        rec["last_review_ts"] = ev.get("ts")
        if ev.get("verdict_ref"):
            rec["last_verdict_ref"] = ev.get("verdict_ref")
        if ev.get("verdict_sha"):
            rec["last_verdict_sha"] = ev.get("verdict_sha")
        continue

    # ------------------------------------------------------------------
    # prescope branch (S1-B2, improvements/10) — status-neutral, pure
    # telemetry: never keys by_id, never applies counters_delta. Unlike
    # "review" (which stores a last-verdict pointer per identity via
    # by_id, protected from inflating counts by review_only), prescope rows
    # carry no per-identity state worth folding into the aggregate — they
    # are advisory-firing counts meant for direct jsonl grep/jq, not the
    # STATE projection. Skipping by_id entirely also sidesteps the
    # identity_unresolved sentinel-collision the review branch's E1 fix had
    # to solve: every prescope row for a project shares idk() ==
    # (project, "", -1), so keying by_id here would collapse ALL of them
    # onto one ever-mutating phantom record and corrupt total/pending.
    # ------------------------------------------------------------------
    if ev_type == "prescope":
        continue

    # ------------------------------------------------------------------
    # Normal event: additive counter fold (ADR §3.3)
    # ------------------------------------------------------------------
    delta = ev.get("counters_delta") or {}
    if isinstance(delta, dict):
        for k, d in delta.items():
            if k in counters:
                counters[k] = counters[k] + int(d)

    # ------------------------------------------------------------------
    # Per-identity state machine — last-event-wins (ADR §3.3/§3.4)
    # ------------------------------------------------------------------
    _key = idk(ev)
    if ev_type == "created" and ev.get("tl_open") in ("fresh", "reuse"):
        _ck = claim_key(ev)
        if _ck[1] is not None:
            epoch_open.setdefault((_ck[0], _ck[1]), ev["tl_open"])
    if not ev.get("subject_norm"):
        # improvements/24 fallback: no identity fields on this event —
        # resolve through the (session_uuid, task_id) index so the status
        # transition lands on the real record. Fires ONLY when subject_norm
        # is missing/empty (where current behavior is already a phantom
        # record), so well-formed events are keyed exactly as before. If the
        # index has no unambiguous match (no identity-bearing precedent, or
        # 2+ identities claimed the pair — see _IDK_AMBIGUOUS above), fall
        # through to the legacy phantom key unchanged.
        _fb = sess_index_resolve(ev)
        if _fb is not None:
            _key = _fb
    else:
        if ev_type == "created":
            alias_note(ev, _key)
        _key = alias_resolve(_key)
        sess_index_note(ev, _key)
    # improvements/60: a non-status event (artifact_warn, field_update, ...)
    # updates an existing task; it never creates one. Without this an
    # identity-less artifact_warn became a blank pending task (6 projects).
    # Rollback: V11_NONSTATUS_CREATES_TASK=on.
    if (ev_type not in ("created", "in_progress", "completed", "blocked", "cancelled")
            and _key not in by_id
            and os.environ.get("V11_NONSTATUS_CREATES_TASK", "off") != "on"):
        continue
    rec = by_id.setdefault(_key, fresh())
    # F3 fix: a real (non-review, non-reconcile) event landing on this
    # identity proves it corresponds to an actual task — clear any
    # review_only phantom flag a prior orphaned review event may have set.
    rec["review_only"] = False

    if ev_type == "created":
        rec["status"] = "pending"
        rec["created_ts"] = ev.get("ts")
        _cmd = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
        _claim = {
            "session_uuid": ev.get("session_uuid"),
            "task_id":      ev.get("task_id"),
            "seqno":        ev.get("seqno"),
            "ts":           ev.get("ts"),
            "review_of":    _cmd.get("review_of"),
        }
        if not _RESOLVER_LEGACY:
            # S2-T0b-1: the TaskList epoch of this create, and the identity it
            # carried (differs from the record's own only for a rehydrate alias).
            _claim["tl_epoch"] = claim_key(ev)[1]
            _claim["identity"] = {"subject_norm": ev.get("subject_norm"),
                                  "create_seq": ev.get("create_seq")}
        created_claims.setdefault(_key, []).append(_claim)
    elif ev_type == "in_progress":
        rec["status"] = "in_progress"
    elif ev_type == "completed":
        rec["status"] = "completed"
        rec["completed_at"] = ev.get("at") or ev.get("ts")
    elif ev_type == "blocked":
        rec["status"] = "blocked"
        rec["blocked_reason"] = ev.get("reason")
        rec["blocked_at"] = ev.get("at") or ev.get("ts")
    elif ev_type == "cancelled":
        # improvements/17 F1: a cancelled task must become TERMINAL — never
        # reappear in open_tasks/active_task_ids/active_task_ids_by_session
        # regardless of replay order or rebuild count. Without this branch,
        # ev_type=="cancelled" matched none of the above elifs, so rec["status"]
        # was silently left at whatever it was before (usually "in_progress")
        # forever — the cancellation never actually took.
        rec["status"] = "cancelled"
        rec["cancelled_reason"] = ev.get("reason")
        rec["cancelled_at"] = ev.get("at") or ev.get("ts")

    if ev_type in ("created", "field_update") and isinstance(ev.get("subject"), str) and ev["subject"]:
        key_subjects.setdefault(_key, set()).add(ev["subject"])

    # field updates — any event type may carry these; None/"" means no change
    for fld in ("subject", "description", "owner", "sprint", "gate", "recommended_agent"):
        val = ev.get(fld)
        if val not in (None, ""):
            rec[fld] = val

    md = ev.get("metadata")
    if isinstance(md, dict) and md:
        rec["metadata"] = deep_merge(rec.get("metadata"), md)

    art = ev.get("artifacts")
    if art is not None:
        rec["artifacts"] = art

    # phase tracking (from metadata)
    md_phase = (rec.get("metadata") or {}).get("phase")
    if md_phase:
        phase = md_phase

    rec["task_id"] = ev.get("task_id")
    rec["session_uuid"] = ev.get("session_uuid")

    # §3.5 HIGH-2: task_id_by_session re-expansion (last-seen task_id per session)
    sess = ev.get("session_uuid")
    tid  = ev.get("task_id")
    if sess and tid:
        rec["task_id_by_session"][sess] = tid
        _tle = claim_key(ev)[1]
        if _tle is not None:
            tl_epoch_by_key.setdefault(_key, {})[sess] = _tle


# ---------------------------------------------------------------------------
# §3.3  Post-fold: clamp negatives, then re-derive from by_id
# ---------------------------------------------------------------------------
for k in list(counters.keys()):
    if counters[k] < 0:
        counters[k] = 0

# Fold archived-sprint summary counts into the additive fold. These tasks'
# own events are gone from this ledger, so counters_delta never saw them;
# add them back once here so `counters` matches `derived` below.
counters["total"] += archived_total
counters["completed"] += archived_completed

# improvements/58 item 3: a V11.21 review sibling follows its parent into
# cancellation. The sibling is its own identity (metadata.review_of = the
# parent's session-local task_id), so the parent's `cancelled` event never
# reached it and it stayed open forever. task_id alone is not a link:
# sessions reuse ids across subjects, so an unrelated task can be the only
# claimant of (session_uuid, review_of). A parent counts only if it claimed
# that pair in a session the sibling lived in AND its subject_norm equals
# the sibling's "Review: <parent subject>" remainder, normalized. No such
# parent → stay open (never guess). Follow only when every matching parent
# is cancelled; completed parents keep their sibling (the pending review).
# Rollback: V11_SIBLING_FOLLOWS_PARENT=off.
if os.environ.get("V11_SIBLING_FOLLOWS_PARENT", "on") != "off":
    for rec in by_id.values():
        if rec["status"] not in ("pending", "in_progress", "blocked"):
            continue
        _ro = (rec.get("metadata") or {}).get("review_of")
        if _ro in (None, ""):
            continue
        _subj = rec.get("subject") or ""
        if not _subj.startswith("Review: "):
            continue
        _want = normalize_subject(_subj[len("Review: "):])
        _parents = []
        for _s in rec["task_id_by_session"]:
            for _pk in sess_task_claims.get((str(_s), None, str(_ro)), ()):
                _parts = _pk.split("\x00")
                # S1-T2c: an aliased parent also answers to its aliases' norms;
                # S2-T0b-1: and to every subject it went by (key_norms).
                if len(_parts) == 3 and _pk in by_id and _want in key_norms(_pk):
                    _parents.append(by_id[_pk])
        if _parents and all(p["status"] == "cancelled" for p in _parents):
            rec["status"] = "cancelled"
            rec["cancelled_reason"] = "parent_cancelled"
            # Latest by parsed instant, not string order: offsets are mixed
            # (+02:00 / +00:00), and the cancelled-unfold path parses this.
            def _utc(s):
                d = _v11_parse_iso(s)
                if d is None:
                    return None
                return d.astimezone(datetime.timezone.utc) if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
            _cas = [p.get("cancelled_at") for p in _parents if _utc(p.get("cancelled_at"))]
            rec["cancelled_at"] = max(_cas, key=_utc) if _cas else None

derived = {
    "pending":     sum(1 for r in by_id.values() if r["status"] == "pending" and not r.get("review_only")),
    "in_progress": sum(1 for r in by_id.values() if r["status"] == "in_progress" and not r.get("review_only")),
    "completed":   sum(1 for r in by_id.values() if r["status"] == "completed" and not r.get("review_only")) + archived_completed,
    "blocked":     sum(1 for r in by_id.values() if r["status"] == "blocked" and not r.get("review_only")),
    # v11.42 W1-T1 (RC4): populate .cancelled so consumers see the count that
    # matches open_tasks[]'s already-correct cancelled exclusion. Additive; no
    # existing consumer reads this field (per recon-6). Rollback: V11_CANCELLED_COUNTER=off.
    "cancelled":   sum(1 for r in by_id.values() if r["status"] == "cancelled" and not r.get("review_only")) if os.environ.get("V11_CANCELLED_COUNTER", "on") != "off" else 0,
}
# F3 fix: review_only phantom records (orphaned review events for identities
# that never had a created event) must never inflate total, including via
# this realign derivation.
derived["total"] = sum(1 for r in by_id.values() if not r.get("review_only")) + archived_total

if any(derived[k] != counters.get(k, 0) for k in derived):
    print(
        "v11_replay_ledger: counters realigned to per-identity set "
        "(delta drift or identity-scope reconcile)",
        file=sys.stderr,
    )
    counters.update(derived)


# ---------------------------------------------------------------------------
# §3.5  Aggregate projection — equal-or-superset of current aggregate schema
# ---------------------------------------------------------------------------

# active_task: most recent in_progress identity by (ts, seqno)
# Walk events reversed (already sorted asc) to find last in_progress identity
seen_active = set()
active_rec = None
for ev in reversed(events):
    # improvements/24 (adversarial finding #4): key subject_norm-less events
    # through the same fallback the main fold used, so this walk agrees with
    # by_id instead of relying on the by-reference invariant. Ambiguous or
    # precedent-less events keep raw idk(ev) — same as the fold did.
    k = alias_resolve(idk(ev))
    if not ev.get("subject_norm"):
        _fbk = sess_index_resolve(ev)
        if _fbk is not None:
            k = _fbk
    if k in seen_active:
        continue
    if k in by_id and by_id[k]["status"] == "in_progress":
        seen_active.add(k)
        if active_rec is None:
            active_rec = by_id[k]

active_task        = active_rec["subject"]  if active_rec else None
active_agent_id    = active_rec["owner"]    if active_rec else None
active_task_sprint = active_rec["sprint"]   if active_rec else None
active_task_gate   = active_rec["gate"]     if active_rec else None
# improvements/18 sibling defect / #12 M1: was a SET comprehension, which
# silently deduped when two DIFFERENT identities (different by_id keys,
# i.e. genuinely different in-progress tasks) happened to carry the same
# per-session-local task_id string -- undercounting distinct active tasks.
# Now a list (duplicates preserved) so the count reflects reality. This is
# a shape-preserving fix (still list[str], sorted) -- disambiguating WHICH
# session each entry belongs to remains active_task_ids_by_session's job,
# not this field's; changing this field's shape (unlike open_tasks) was
# not part of the approved design decision for this task.
active_task_ids    = sorted([
    r["task_id"] for r in by_id.values()
    if r["status"] == "in_progress" and r["task_id"]
])

# §3.5 HIGH-2 / HIGH-B: open_tasks_by_session — exclude completed, blocked,
# AND cancelled (improvements/17 F1 — cancelled is terminal, same as blocked)
#
# KNOWN RESIDUAL (improvements/24 remediation, 2026-08-06): this per-session
# dict is keyed by local t_id, so two SIMULTANEOUSLY-OPEN identities sharing
# a (session, task_id) pair collapse to one display entry (last wins) — the
# within-session sibling of the cross-session collision #18 fixed. by_id,
# counters, and active_task_ids all still carry both (truth is unaffected);
# only this view and the flat open_tasks built from it lose one. Live task
# ids only recur within a session via complete-then-recreate (never both
# open), so this is a display-only edge under anomalous ledgers. Fixing it
# means changing this dict's shape — a consumer-breaking change deliberately
# NOT bundled into the #24 remediation.
open_tasks_by_session = {}
_open_key = {}  # (session_uuid, t_id) -> the by_id key its entry shows (last wins, as above)
for _k, rec in by_id.items():
    if rec["status"] in ("completed", "blocked"):
        continue
    if rec["status"] == "cancelled":
        # improvements/48 (v11.39-1): default = fold (V11_CANCELLED_FILTERS_
        # REPLAY=on, matches #17 F1). When =off, unfold ONLY when cancelled_at
        # >= V11_CANCELLED_UNFOLD_SINCE_TS (default now-1h). Unparseable or
        # missing cancelled_at → fold (safe default).
        if _cancelled_cutoff_dt is None:
            continue
        _ca_dt = _v11_parse_iso(rec.get("cancelled_at"))
        if _ca_dt is None:
            continue
        # v11.39.1 (Layer B fix): normalize BOTH datetimes to UTC-aware via
        # astimezone() rather than force one's tzinfo onto the other with
        # .replace(). Forcing offsets silently misclassifies when cancelled_at
        # and cutoff carry different real offsets (e.g. one +02:00, one UTC).
        _cutoff_cmp = _cancelled_cutoff_dt
        if _ca_dt.tzinfo is None:
            _ca_dt = _ca_dt.replace(tzinfo=datetime.timezone.utc)
        else:
            _ca_dt = _ca_dt.astimezone(datetime.timezone.utc)
        if _cutoff_cmp.tzinfo is None:
            _cutoff_cmp = _cutoff_cmp.replace(tzinfo=datetime.timezone.utc)
        else:
            _cutoff_cmp = _cutoff_cmp.astimezone(datetime.timezone.utc)
        if _ca_dt < _cutoff_cmp:
            continue
    for sess_uuid, t_id in rec["task_id_by_session"].items():
        open_tasks_by_session.setdefault(sess_uuid, {})[t_id] = {
            "subject":     rec["subject"],
            "description": rec["description"],
            "status":      rec["status"],
            "metadata":    rec["metadata"],
        }
        _open_key[(sess_uuid, t_id)] = _k

# active_task_ids_by_session (diagnostic parity, §3.5)
active_task_ids_by_session = {}
for _k, rec in by_id.items():
    if rec["status"] != "in_progress":
        continue
    for sess_uuid, t_id in rec["task_id_by_session"].items():
        lst = active_task_ids_by_session.setdefault(sess_uuid, [])
        if t_id not in lst:
            lst.append(t_id)

# open_tasks flat convenience view (§3.5) — improvements/18 F1 / #12 M1:
# was a dict[task_id]->record, which silently collided when two DIFFERENT
# identities (by_id keys) from DIFFERENT sessions happened to share the same
# per-session-local task_id integer (every session's TaskCreate counter
# starts at 1) -- last dict write wins, no warning, no signal. Now a LIST of
# self-describing records, each carrying its OWN task_id + session_uuid,
# making the collision structurally impossible. Flattened directly from the
# already collision-safe open_tasks_by_session above (not rebuilt
# independently) -- the same flatten-with-session_uuid pattern
# scripts/handoff's own generator already uses for its "everything open,
# across sessions" view.
open_tasks = [
    {
        "task_id":      t_id,
        "session_uuid": sess_uuid,
        "subject":      task_rec["subject"],
        "description":  task_rec["description"],
        "status":       task_rec["status"],
        "metadata":     task_rec["metadata"],
    }
    for sess_uuid, sess_tasks in open_tasks_by_session.items()
    for t_id, task_rec in sess_tasks.items()
]
# S2-T0b-1 (#113): an entry whose task was stamped with a TaskList epoch in
# that session also carries the epoch and its identity, so a reader binds it
# exactly (task_epoch.py R0/R1) instead of by the reused id. Unstamped entries
# are unchanged, so the aggregate of an unstamped ledger is byte-identical,
# except the §6.6 key_norms sibling link on renamed/rehydrated parents: a
# review sibling also matches every subject its parent went by, so it can now
# follow a cancelled parent (review #20).
if not _RESOLVER_LEGACY:
    for _e in open_tasks:
        _ok = _open_key.get((_e["session_uuid"], _e["task_id"]))
        _tle = tl_epoch_by_key.get(_ok, {}).get(_e["session_uuid"]) if _ok else None
        if _tle is None:
            continue
        _p = _ok.split("\x00")
        try:
            _pcs = int(_p[2])
        except ValueError:
            _pcs = None
        _e["tl_epoch"] = _tle
        _e["identity"] = {"subject_norm": _p[1], "create_seq": _pcs}

# recent_completed — top 10 by completed_at desc (§3.5)
completed_recs = [
    {
        "id":           rec["task_id"],
        "subject":      rec["subject"],
        "at":           rec["completed_at"] or "",
        "session_uuid": rec["session_uuid"],
    }
    for rec in by_id.values() if rec["status"] == "completed"
]
completed_recs.sort(key=lambda x: x["at"] or "", reverse=True)
recent_completed = completed_recs[:10]

# blocked_tasks — top 5 by at desc (§3.5)
blocked_recs = [
    {
        "id":           rec["task_id"],
        "subject":      rec["subject"],
        "reason":       rec["blocked_reason"],
        "at":           rec["blocked_at"] or "",
        "session_uuid": rec["session_uuid"],
    }
    for rec in by_id.values() if rec["status"] == "blocked"
]
blocked_recs.sort(key=lambda x: x["at"] or "", reverse=True)
blocked_tasks = blocked_recs[:5]

# recommended_agents (§3.5)
recommended_agents = {}
for rec in by_id.values():
    if rec["recommended_agent"] and rec["task_id"]:
        recommended_agents[rec["task_id"]] = rec["recommended_agent"]

# task_artifacts (§3.5)
task_artifacts = {}
for rec in by_id.values():
    if rec["artifacts"] is not None and rec["task_id"]:
        task_artifacts[rec["task_id"]] = rec["artifacts"]

# review_summary — additive fold of completed.review_summary_delta (§3.5)
rs_total = rs_errors = rs_crit = rs_high = rs_med = rs_low = 0
rs_fixed = rs_esc = 0
rs_diff_sum = 0.0; rs_diff_n = 0
for ev in events:
    if ev.get("ev") == "completed":
        rsd = ev.get("review_summary_delta")
        if isinstance(rsd, dict):
            tr = int(rsd.get("tasks_reviewed", 0))
            rs_total  += tr
            rs_errors += int(rsd.get("total_errors", 0))
            bysev = rsd.get("by_severity") or {}
            rs_crit += int(bysev.get("critical", 0))
            rs_high += int(bysev.get("high", 0))
            rs_med  += int(bysev.get("medium", 0))
            rs_low  += int(bysev.get("low", 0))
            rs_fixed += int(rsd.get("auto_fixed", 0))
            rs_esc   += int(rsd.get("escalated", 0))
            d = rsd.get("difficulty")
            if d is not None and tr > 0:
                rs_diff_sum += float(d) * tr
                rs_diff_n   += tr

review_summary = None
if rs_total > 0:
    review_summary = {
        "tasks_reviewed": rs_total,
        "total_errors":   rs_errors,
        "by_severity": {
            "critical": rs_crit,
            "high":     rs_high,
            "medium":   rs_med,
            "low":      rs_low,
        },
        "auto_fixed":     rs_fixed,
        "escalated":      rs_esc,
        "avg_difficulty": (rs_diff_sum / rs_diff_n) if rs_diff_n > 0 else None,
    }

# aggregated_from (§3.5)
aggregated_from = sorted({r["session_uuid"] for r in by_id.values() if r["session_uuid"]})

# finding_tasks + findings_summary (parity)
finding_tasks = {}
for ev in events:
    md = ev.get("metadata") or {}
    if md.get("type") == "finding" and md.get("severity") and ev.get("task_id"):
        finding_tasks[ev["task_id"]] = md["severity"]

findings_summary = None
if finding_tasks:
    def _count_sev(s):
        return sum(1 for v in finding_tasks.values() if v == s)
    findings_summary = {
        "critical":  _count_sev("critical"),
        "high":      _count_sev("high"),
        "medium":    _count_sev("medium"),
        "low":       _count_sev("low"),
        "total_raw": len(finding_tasks),
    }

# dark_code_advisories (parity, additive)
dark_code_advisories = {
    "str_missing_count": 0, "str_missing_complex": 0,
    "str_missing_novel": 0, "completions_without_str": 0,
    "last_advisory_at": None,
}
for ev in events:
    dca = (ev.get("metadata") or {}).get("dark_code_advisories")
    if isinstance(dca, dict):
        for k in ("str_missing_count", "str_missing_complex",
                  "str_missing_novel", "completions_without_str"):
            dark_code_advisories[k] += int(dca.get(k, 0))
        lat = dca.get("last_advisory_at")
        if lat:
            cur = dark_code_advisories["last_advisory_at"]
            dark_code_advisories["last_advisory_at"] = max(lat, cur) if cur else lat

aggregate = {
    "project":                    project,
    "total":                      counters["total"],
    "completed":                  counters["completed"],
    "pending":                    counters["pending"],
    "in_progress":                counters["in_progress"],
    "blocked":                    counters["blocked"],
    "cancelled":                  counters["cancelled"],
    "phase":                      phase,
    "active_task":                active_task,
    "active_agent_id":            active_agent_id,
    "active_task_sprint":         active_task_sprint,
    "active_task_gate":           active_task_gate,
    "active_task_ids":            active_task_ids,
    "active_task_ids_by_session": active_task_ids_by_session,
    "open_tasks_by_session":      open_tasks_by_session,
    "open_tasks":                 open_tasks,
    "recent_completed":           recent_completed,
    "blocked_tasks":              blocked_tasks,
    "recommended_agents":         recommended_agents,
    "task_artifacts":             task_artifacts,
    "review_summary":             review_summary,
    "findings_summary":           findings_summary,
    "finding_tasks":              finding_tasks,
    "dark_code_advisories":       dark_code_advisories,
    "aggregated_from":            aggregated_from,
    "last_updated":               last_ts or now,
    "aggregate_built_at":         now,
    "ledger_source":              "ledger",
}
# review #3 (S1-T2c): each rehydrate alias folds a second identity into its
# original, so total is one lower than a replay without aliases counted. The
# cutover REGRESSION-GUARD adds this back (alias_carveout). Only emitted when
# an alias fired, so the aggregate stays byte-identical without one.
if alias_of:
    aggregate["alias_count"] = len(alias_of)
# S2-R4: the review-sibling age-out cancellations this replay folded (the
# align-aggregate sweep writes them with reason "review_sibling_ageout"). The
# cutover REGRESSION-GUARD adds back only those a prior aggregate did not
# already reflect (ageout_carveout). Only emitted when one exists, like
# alias_count.
_ageout_n = sum(1 for ev in events
                if ev.get("ev") == "cancelled" and ev.get("reason") == "review_sibling_ageout")
if _ageout_n:
    aggregate["ageout_count"] = _ageout_n

# improvements/96 (S1-T16): opt-in per-identity view. The aggregate keeps
# closed tasks only as counts (recent_completed is a top-10 display list), so
# a consumer that must see a whole sprint, completed and cancelled included
# (scripts/wave-check), reads this instead of re-folding the ledger itself.
# Off by default, so the aggregate every other caller writes is unchanged.
if os.environ.get("V11_REPLAY_EMIT_IDENTITIES", "off") == "on":
    # Review fields for this view come from a second walk, so the fold above
    # (and the aggregate every default caller gets) is untouched:
    #   - the latest valid ev:"review" per identity (the fold's review-branch
    #     key) with its severity, outcome, verdict_ref and verdict_sha.
    #     Corrections follow scripts/lib/review_corrections.py (review_corrected,
    #     the same rule agent-scorecard uses): outcome=void (S1-P3: e.g. a
    #     verdict the resolver misattributed) erases the original, and the void
    #     row is no review either; outcome=waived marks the original waived, and
    #     the correction row is itself a waived review;
    #   - the last review_summary_delta a completion carried: the severity
    #     counts survive the PIPE_BUF cap that drops a large verdict (#102);
    #   - the outcome / waiver_reason of the last cancellation.
    # created_claims lists every `created` folded into the identity (session,
    # task_id, seqno, ts, review_of), rehydrate aliases included (S1-T2c);
    # S2-T0b-1 adds each create's tl_epoch and the identity it carried, and
    # the record's norms (key_norms). scripts/lib/task_epoch.py reads its
    # aliases from here.
    _last_rev, _last_rsd, _last_cancel = {}, {}, {}

    def _correction(ev):
        """"void" / "waived" when a later row corrects this review, else None."""
        return review_corrected.get((ev.get("seqno"), ev.get("ts")))

    for ev in events:
        _t = ev.get("ev")
        if _t == "review":
            if str(ev.get("outcome") or "").lower() == "void" or _correction(ev) == "void":
                continue
            if ev.get("identity_unresolved") or ev.get("create_seq") in (None, -1):
                continue
            _last_rev[alias_resolve(idk(ev))] = ev
        elif _t in ("completed", "cancelled"):
            _ek = alias_resolve(idk(ev))
            if not ev.get("subject_norm"):
                _fb = sess_index_resolve(ev)
                if _fb is not None:
                    _ek = _fb
            if _t == "cancelled":
                _last_cancel[_ek] = ev
            elif isinstance(ev.get("review_summary_delta"), dict):
                _last_rsd[_ek] = ev["review_summary_delta"]
    identities = []
    for _k, rec in by_id.items():
        # review_only records are orphaned verdict pointers, not tasks; their
        # unresolved-review keys are tuples, never idk() strings.
        if rec.get("review_only") or not isinstance(_k, str):
            continue
        _parts = _k.split("\x00")
        if len(_parts) != 3:
            continue
        try:
            _cs = int(_parts[2])
        except ValueError:
            _cs = None
        _rev = _last_rev.get(_k) or {}
        _outcome = _rev.get("outcome")
        if _rev and _correction(_rev) == "waived":
            _outcome = "waived"
        _cev = _last_cancel.get(_k) or {}
        identities.append({
            "subject_norm":         _parts[1],
            "create_seq":           _cs,
            "task_id":              rec["task_id"],
            "session_uuid":         rec["session_uuid"],
            "task_id_by_session":   rec["task_id_by_session"],
            "status":               rec["status"],
            "subject":              rec["subject"],
            "sprint":               rec["sprint"],
            "metadata":             rec["metadata"],
            "artifacts":            rec["artifacts"],
            # From the void-aware walk, not the fold's raw last review.
            "last_review_severity": _rev.get("review_severity") if _rev else None,
            "last_review_outcome":  _outcome,
            "last_review_verdict_ref": _rev.get("verdict_ref"),
            "last_review_verdict_sha": _rev.get("verdict_sha"),
            "review_summary_delta": _last_rsd.get(_k),
            "cancelled_outcome":    _cev.get("outcome"),
            "cancelled_waiver_reason": _cev.get("waiver_reason"),
            "completed_at":         rec["completed_at"],
            "cancelled_at":         rec["cancelled_at"],
            "cancelled_reason":     rec["cancelled_reason"],
            "created_claims":       created_claims.get(_k, []),
        })
        if not _RESOLVER_LEGACY:
            identities[-1]["norms"] = sorted(key_norms(_k))
    aggregate["identities"] = identities
    if not _RESOLVER_LEGACY:
        # S2-T0b-1 (review #19 C6): the alias map itself, so a writer can
        # materialise legacy aliases once (a sidecar) instead of scanning
        # the ledger on every append.
        def _ident_obj(k):
            _p = k.split("\x00")
            try:
                return {"subject_norm": _p[1], "create_seq": int(_p[2])}
            except (IndexError, ValueError):
                return {"subject_norm": _p[1] if len(_p) > 1 else "", "create_seq": None}
        aggregate["aliases"] = [
            {"alias": _ident_obj(_a), "target": _ident_obj(_t),
             "session_uuid": alias_src[_a].get("session_uuid"),
             "task_id": alias_src[_a].get("task_id"),
             "seqno": alias_src[_a].get("seqno"), "ts": alias_src[_a].get("ts")}
            for _a, _t in sorted(alias_of.items())
        ]

print(json.dumps(aggregate, separators=(",", ":")))
PYEOF
}

# ──────────────────────────────────────────────────────────────────────────────
# V11.19 — Review Queue (per-task adversarial-lite review enforcement)
# ──────────────────────────────────────────────────────────────────────────────
# Root-cause fix for the V11.15 silent-skip: the per-task review loop was wired
# (sync-tasks reads metadata.artifacts.review on terminal completed TaskUpdate
# and writes per-agent ledgers) but had no positive trigger when a task
# completed WITHOUT a review. Completed-without-review was byte-identical to
# completed-with-review, so the orchestrator could skip Phase 4r entirely with
# zero observable consequence.
#
# Structural fix: completed-without-review becomes an observable, surfaced
# state by enqueuing the task in a durable per-project queue. Consumers
# (detect-project, handoff, orchestrator DETECT dashboard) read the queue.
# The orchestrator cannot miss what every consumer surface displays.
#
# Schema (one JSONL line per event, append-only):
#   {"v":1,"ev":"pending"|"done","ts":ISO8601,"project":P,"task_id":T,
#    "agent_id":A,"subject":S,"files_changed":[],"session_uuid":U,
#    "review_severity":SEV (done only)}
#
# Replay semantics: scan file, fold by task_id, latest event wins.
# Pending = task_id whose latest event has ev=="pending".
#
# Rollback: V11_REVIEW_ENFORCEMENT=off disables enqueue+nudge (read still works).

# v11_session_is_live SESSION_UUID [MAX_AGE_MINUTES]
#   General-purpose session-liveness check, reused by review-queue drainage
#   (improvement 03 §B/C) instead of inventing a new "who's active" tracker.
#   A session is "live" if $METRICS_DIR/sessions/$SESSION_UUID/ exists AND its
#   most-recently-touched TOP-LEVEL file (active-project, task-state.json,
#   markers, .heartbeat) was modified within MAX_AGE_MINUTES (default:
#   V11_SESSION_LIVENESS_MINUTES, 15). Deliberately -maxdepth 1: subdirectory
#   writes (e.g. per-project ledger/review-queue dirs) do NOT count, so
#   hooks/sync-tasks touches sessions/$uuid/.heartbeat on every invocation --
#   the guaranteed-fresh top-level signal that keeps an actively-working
#   session (whose real writes may land only in subdirs) from being
#   misjudged dead and having its claims stolen by another session.
#   "legacy-cli" (the v11_session_uuid fallback identity shared by CLI scripts
#   with no real session) is NEVER considered live -- it isn't a real,
#   exclusively-owned session, so claims/ownership under it are always stale.
#   Returns 0 (true) if live, 1 otherwise. Never fails loudly (missing dir = not live).
v11_session_is_live() {
    local session_uuid="$1"
    local max_age_min="${2:-${V11_SESSION_LIVENESS_MINUTES:-15}}"
    [ -z "$session_uuid" ] && return 1
    [ "$session_uuid" = "legacy-cli" ] && return 1
    v11_valid_session_id "$session_uuid" || return 1
    local sdir="$METRICS_DIR/sessions/$session_uuid"
    [ -d "$sdir" ] || return 1
    local newest
    newest=$(find "$sdir" -maxdepth 1 -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
    [ -z "$newest" ] && return 1
    local now age_min
    now=$(date +%s)
    age_min=$(( (now - ${newest%.*}) / 60 ))
    [ "$age_min" -le "$max_age_min" ]
}

# v11_review_queue_path PROJECT TYPE
#   TYPE ∈ {jsonl, lock}. Validates project name (SEC-C-02 whitelist).
v11_review_queue_path() {
    local project="$1" type="$2"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_review_queue_path: invalid project name '$project' (SEC-C-02)" >&2
        return 1
    fi
    local queue_dir="${METRICS_DIR}/review-queue"
    case "$type" in
        jsonl) printf '%s' "${queue_dir}/${project}.jsonl" ;;
        lock)  printf '%s' "${queue_dir}/${project}.jsonl.lock" ;;
        *)
            echo "v11_review_queue_path: unknown type '$type' (must be jsonl|lock)" >&2
            return 1
            ;;
    esac
}

# v11_review_queue_check_project_scope TARGET_PROJECT FILES_CHANGED_JSON
#   Returns 0 if the entry is in-scope for TARGET_PROJECT.
#   Returns 1 if any path in FILES_CHANGED_JSON starts with a known root that belongs
#   to a DIFFERENT project (cross-project bleed of well-formed entries).
#
#   Project root discovery (dynamic):
#     - $SESSIONS_ROOT/<name>/ -> project name is <name>
#     - $HERCULES_ROOT/<target_project>/ is also accepted for the target project
#   Path matching is anchored prefix with trailing slash to prevent false substring matches
#   (e.g. $HOME/example-project will NOT match $HOME/example-project-old).
#
#   Gated by V11_REVIEW_CROSS_PROJECT_CHECK (default on). Off -> always return 0.
#   On mismatch: writes JSON line to $METRICS_DIR/cross-project-rejections.log.
#   Called from v11_review_queue_add AFTER skeletal check, BEFORE append.
#   S55-T2: 2026-06-02
v11_review_queue_check_project_scope() {
    local target_project="$1"
    local files_json="${2:-[]}"

    # Gate
    local _scope_check="${V11_REVIEW_CROSS_PROJECT_CHECK:-on}"
    [ "$_scope_check" = "off" ] && return 0

    # Empty or non-array files_changed -> no paths to check -> in-scope (ambiguous, accepted)
    local _fc_len
    _fc_len=$(printf '%s' "${files_json}" | jq -r 'if type == "array" then length else 0 end' 2>/dev/null || echo "0")
    [ "$_fc_len" = "0" ] && return 0

    # Accepted roots for the target project (always allowed):
    #   - $SESSIONS_ROOT/<target_project>/
    #   - $HERCULES_ROOT/<target_project>/
    local _sessions_root="${SESSIONS_ROOT:-$HERCULES_ROOT/sessions}"
    local _target_root_sessions="${_sessions_root}/${target_project}/"
    local _target_root_main="${HERCULES_ROOT}/${target_project}/"

    # Build a registry of (project_name, root_prefix) pairs from $SESSIONS_ROOT.
    # One ls call; each subdirectory name = project name; root = $SESSIONS_ROOT/<name>/.
    # We pass this to Python as a newline-separated "proj:root/" string.
    local _registry=""
    if [ -d "$_sessions_root" ]; then
        local _entry
        while IFS= read -r _entry; do
            [ -z "$_entry" ] && continue
            _registry="${_registry}${_entry}:${_sessions_root}/${_entry}/"$'\n'
        done < <(ls -1 "$_sessions_root" 2>/dev/null | grep -vE '^\.|^_|^CLAUDE' || true)
    fi

    # Also ingest project-paths.json if present for richer root coverage
    # (handles projects with roots outside $SESSIONS_ROOT like $HOME/example-project).
    local _reg_extra=""
    if [ -f "${REGISTRY_FILE:-}" ]; then
        _reg_extra=$(jq -r '
            to_entries[]
            | select(.key | test("^[a-zA-Z0-9._-]{1,64}$"))
            | .key as $proj
            | .value
            | if type == "array" then .[] else . end
            | select(type == "string" and length > 0)
            | [$proj, .] | @tsv
        ' "$REGISTRY_FILE" 2>/dev/null | while IFS=$'\t' read -r _rp _rroot; do
            [ -z "$_rp" ] || [ -z "$_rroot" ] && continue
            [[ "$_rroot" != */ ]] && _rroot="${_rroot}/"
            printf '%s:%s\n' "$_rp" "$_rroot"
        done) || _reg_extra=""
    fi
    [ -n "$_reg_extra" ] && _registry="${_registry}${_reg_extra}"$'\n'

    # Run a single Python subprocess to check all paths against all non-target roots.
    # files_json is passed via V11_FILES_JSON env var (not stdin) so that the heredoc
    # body can use stdin for the script text without conflict.
    local _conflict
    _conflict=$(V11_TARGET_PROJ="$target_project" \
        V11_TARGET_ROOT_SESS="$_target_root_sessions" \
        V11_TARGET_ROOT_MAIN="$_target_root_main" \
        V11_REGISTRY="$_registry" \
        V11_FILES_JSON="$files_json" \
        python3 - <<'PYEOF' 2>/dev/null
import os, json, sys

target = os.environ.get("V11_TARGET_PROJ", "")
target_roots = set(filter(None, [
    os.environ.get("V11_TARGET_ROOT_SESS", ""),
    os.environ.get("V11_TARGET_ROOT_MAIN", ""),
]))

# Parse registry: "project:root/" newline-separated
registry_raw = os.environ.get("V11_REGISTRY", "")
other_roots = {}  # root_prefix -> project_name
for line in registry_raw.splitlines():
    line = line.strip()
    if not line or ":" not in line:
        continue
    proj, root = line.split(":", 1)
    proj = proj.strip()
    root = root.strip()
    if not proj or not root:
        continue
    if not root.endswith("/"):
        root += "/"
    # Only register as a non-target root if it belongs to a different project
    # AND is not already accepted as a target root
    if proj != target and root not in target_roots:
        other_roots[root] = proj

# Read files_changed from environment variable (avoids heredoc stdin conflict)
files_raw = os.environ.get("V11_FILES_JSON", "[]")
try:
    files = json.loads(files_raw)
    if not isinstance(files, list):
        files = []
except Exception:
    files = []

conflicts = []
# Policy: any single foreign-project path in files_changed[] triggers
# rejection (strict). A legitimate cross-project edit (e.g. example-project task
# that also patches a shared utility under sessions/dreamscape/) will be
# silently rejected. Override via V11_REVIEW_CROSS_PROJECT_CHECK=off.
for fpath in files:
    if not isinstance(fpath, str) or not fpath:
        continue
    # Short-circuit: if the path is under any of the target project's own roots,
    # it is in-scope regardless of whether a sub-project root also matches.
    # This prevents false rejections when a sub-project (e.g. agents-manifest) has a
    # root that is a subdirectory of the target's main checkout root.
    if any(fpath.startswith(tr) for tr in target_roots if tr):
        continue
    for root, proj in other_roots.items():
        if fpath.startswith(root):
            conflicts.append({"path": fpath, "detected_project": proj, "matched_root": root})
            break

if conflicts:
    print(json.dumps(conflicts))
PYEOF
    )

    if [ -n "$_conflict" ]; then
        # Detected cross-project path(s) -- log and reject
        local _reject_ts _reject_log _reject_payload _detected_proj _conflict_paths
        _reject_ts="$(date -u +%Y-%m-%dT%H:%M:%S+00:00 2>/dev/null || echo "unknown")"
        _reject_log="${METRICS_DIR}/cross-project-rejections.log"
        _detected_proj=$(printf '%s' "$_conflict" | jq -r '.[0].detected_project // "unknown"' 2>/dev/null || echo "unknown")
        _conflict_paths=$(printf '%s' "$_conflict" | jq -r '[.[].path]' 2>/dev/null || echo "[]")
        _reject_payload=$(jq -cn \
            --arg rejected_at "$_reject_ts" \
            --arg target_project "$target_project" \
            --arg detected_project "$_detected_proj" \
            --argjson conflicting_paths "${_conflict_paths}" \
            --argjson original_files "${files_json}" \
            '{rejected_at:$rejected_at, target_project:$target_project,
              detected_project:$detected_project,
              conflicting_paths:$conflicting_paths,
              original_files_changed:$original_files}' \
            2>/dev/null) || \
            _reject_payload="{\"rejected_at\":\"$_reject_ts\",\"target_project\":\"$target_project\",\"detected_project\":\"$_detected_proj\"}"
        printf '%s\n' "$_reject_payload" >> "$_reject_log" 2>/dev/null || true
        echo "v11_review_queue_add: cross-project scope rejection -- target=$target_project detected=$_detected_proj; see $_reject_log" >&2
        return 1
    fi

    return 0
}

# v11_review_queue_add PROJECT TASK_ID AGENT_ID SUBJECT [FILES_CHANGED_JSON] [SESSION_UUID]
#                      [PARENT_SUBJECT_NORM PARENT_CREATE_SEQ [TL_EPOCH]]
#   Append a pending event IF no current pending entry exists for (project, task_id).
#   Idempotent: re-calling for an already-pending task is a no-op.
#   S2-T0b-2 (#113, #97 going forward): with the parent's identity, the row
#   carries parent_identity {subject_norm, create_seq} (and tl_epoch, the
#   TaskList epoch it was completed in), and a row that names a DIFFERENT
#   parent_identity under the same task_id (a reused id) no longer counts as
#   "already pending". Rows without one keep the bare-task_id rule.
#   Echoes "added" or "exists" on stdout (advisory). Returns 0 on success or no-op.
#   Side-effect-never-fails: any internal failure → silent skip.
#   Returns 0 on enqueue success or silent-skip (legacy never-fails contract).
#   Returns 1 ONLY when V11_REVIEW_ENQUEUE_VALIDATE=on AND entry fails validation.
#   Returns 1 ALSO when V11_REVIEW_CROSS_PROJECT_CHECK=on AND entry has cross-project paths.
#   Callers MUST tolerate non-zero in that case.
#   Audited callers (2026-06-02): only test_review_queue_helpers.py — all check return codes explicitly.
v11_review_queue_add() {
    local project="$1" task_id="$2" agent_id="$3" subject="$4"
    local files_json="${5:-[]}" session_uuid="${6:-}"
    local parent_sn="${7:-}" parent_cs="${8:-}" parent_tle="null"
    [[ $parent_cs =~ $_V11_TLR_NUM_ERE ]] && [ "$parent_cs" != "0" ] && [ -n "$parent_sn" ] \
        || { parent_sn=""; parent_cs=""; }
    [[ ${9:-} =~ $_V11_TLR_EPOCH_ERE ]] && parent_tle="$9"

    # SEC-C-02 + arg presence
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_review_queue_add: invalid project name '$project'" >&2
        return 0
    fi
    if [ -z "$task_id" ]; then
        echo "v11_review_queue_add: empty task_id — skipping" >&2
        return 0
    fi
    # Validate task_id charset (matches sync-tasks parsing — alphanumeric/-/_)
    if ! printf '%s' "$task_id" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_review_queue_add: invalid task_id '$task_id'" >&2
        return 0
    fi

    # V11_REVIEW_ENQUEUE_VALIDATE (default on) — reject skeletal / degraded entries.
    # Catches skeletal bleed entry patterns (sentinel subject or unknown+empty files).
    # Well-formed cross-project entries are caught upstream by the sync-tasks project-mismatch check.
    # Legitimate enqueues from sync-tasks may have files_changed=[] when no files are
    # tracked yet, so files_changed=[] alone is NOT rejected (only combined with sentinel subject).
    # Rollback: export V11_REVIEW_ENQUEUE_VALIDATE=off to restore permissive behavior.
    local _enqueue_validate="${V11_REVIEW_ENQUEUE_VALIDATE:-on}"
    if [ "$_enqueue_validate" != "off" ]; then
        local _reject_reason=""
        # Rule A: subject must be non-empty and not a sentinel value
        if [ -z "${subject:-}" ] || [ "$subject" = "?" ]; then
            _reject_reason="subject missing or '?' sentinel (got: '${subject:-}')"
        fi
        # Rule B: "unknown" subject combined with empty files_changed = skeletal bleed entry
        if [ -z "$_reject_reason" ] && [ "${subject:-}" = "unknown" ]; then
            local _fc_len
            _fc_len=$(printf '%s' "${files_json:-[]}" | jq -r 'if type == "array" then length else 0 end' 2>/dev/null || echo "0")
            if [ "$_fc_len" = "0" ]; then
                _reject_reason="skeletal bleed entry: subject='unknown' + files_changed=[] (cross-project contamination)"
            fi
        fi
        if [ -n "$_reject_reason" ]; then
            local _reject_ts
            _reject_ts="$(date -u +%Y-%m-%dT%H:%M:%S+00:00 2>/dev/null || echo "unknown")"
            local _reject_log="${METRICS_DIR}/enqueue-rejections.log"
            local _reject_payload
            _reject_payload=$(jq -cn \
                --arg rejected_at "$_reject_ts" \
                --arg reason "$_reject_reason" \
                --arg project "$project" \
                --arg task_id "$task_id" \
                --arg agent_id "${agent_id:-}" \
                --arg subject "${subject:-}" \
                --argjson files "${files_json:-[]}" \
                '{rejected_at:$rejected_at, reason:$reason, original_payload:{project:$project, task_id:$task_id, agent_id:$agent_id, subject:$subject, files_changed:$files}}' \
                2>/dev/null) || _reject_payload="{\"rejected_at\":\"$_reject_ts\",\"reason\":\"$_reject_reason\",\"original_payload\":{\"project\":\"$project\",\"task_id\":\"$task_id\"}}"
            printf '%s\n' "$_reject_payload" >> "$_reject_log" 2>/dev/null || true
            echo "v11_review_queue_add: rejected skeletal entry for project=$project task_id=$task_id — $_reject_reason; see $_reject_log" >&2
            return 1
        fi
    fi

    # V11_REVIEW_CROSS_PROJECT_CHECK (default on) — reject well-formed entries whose
    # files_changed[] paths belong to a different known V11 project.
    # Catches the bleed lane missed by skeletal validator (real subject + real files
    # from wrong project, e.g. music-session task ending up in example-project.jsonl).
    # Rollback: export V11_REVIEW_CROSS_PROJECT_CHECK=off to restore permissive behavior.
    if ! v11_review_queue_check_project_scope "$project" "${files_json:-[]}"; then
        return 1
    fi

    # Validate files_json is a JSON array
    if ! printf '%s' "$files_json" | jq -e 'type == "array"' >/dev/null 2>&1; then
        files_json="[]"
    fi

    # V11 S1 T5: trace + WARN when agent_id is "unknown".
    # agent_id="unknown" is a LEGITIMATE orchestrator/background-agent fallback
    # (see sync-tasks:1238 and the default at line 3041). NEVER reject on unknown
    # agent_id — Rule A/B already guard the real rejection cases (sentinel subject
    # or subject+files skeletal pattern). For unknown agent_id, ADMIT the entry,
    # add a trace field so operators can track the source path, and emit a WARN.
    # Kill switch: V11_RQ_TRACE_UNKNOWN=off (default on).
    # This fires only for entries that already passed Rule A, Rule B, and the
    # cross-project scope check — i.e., entries that will actually be admitted.
    local _rq_trace="null"
    if [ "${V11_RQ_TRACE_UNKNOWN:-on}" != "off" ] && [ "${agent_id:-}" = "unknown" ]; then
        local _trace_ts _trace_caller_kind
        _trace_ts="$(date -u +%Y-%m-%dT%H:%M:%S+00:00 2>/dev/null || echo "unknown")"
        _trace_caller_kind="$(v11_caller_kind 2>/dev/null || echo "")"
        _rq_trace=$(jq -cn \
            --arg ts "$_trace_ts" \
            --arg project "$project" \
            --arg task_id "$task_id" \
            --arg caller_kind "${_trace_caller_kind:-unknown}" \
            --arg session_uuid "${session_uuid:-}" \
            --arg marker "V11_WARN_UNKNOWN_AGENT_AT_ENQUEUE" \
            '{ts:$ts, project:$project, task_id:$task_id,
              caller_kind:$caller_kind, session_uuid:$session_uuid,
              marker:$marker}' 2>/dev/null || echo 'null')
        echo "v11_review_queue_add: WARN agent_id=unknown for project=$project task_id=$task_id (caller_kind=${_trace_caller_kind:-unknown}) — entry admitted with trace; set V11_RQ_TRACE_UNKNOWN=off to suppress" >&2
    fi

    local queue_dir="${METRICS_DIR}/review-queue"
    local jsonl_file lock_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl) || return 0
    lock_file=$(v11_review_queue_path "$project" lock) || return 0

    mkdir -p "$queue_dir" 2>/dev/null || {
        echo "v11_review_queue_add: failed to create queue dir — skipping" >&2
        return 0
    }

    local now status
    now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

    # Build the event line (compact JSON, single line — line-atomic O_APPEND).
    # When _rq_trace is a JSON object (not null), include it as the trace field.
    local event_line
    event_line=$(jq -cn \
        --arg ts "$now" \
        --arg project "$project" \
        --arg task_id "$task_id" \
        --arg agent_id "${agent_id:-unknown}" \
        --arg subject "${subject:-}" \
        --argjson files "$files_json" \
        --arg session_uuid "${session_uuid:-}" \
        --argjson trace "${_rq_trace}" \
        --arg psn "$parent_sn" --arg pcs "$parent_cs" --argjson ptle "$parent_tle" \
        '({v:1, ev:"pending", ts:$ts, project:$project, task_id:$task_id,
          agent_id:$agent_id, subject:$subject, files_changed:$files,
          session_uuid:$session_uuid, claimed_by:null}) +
         (if ($trace | type) == "object" then {trace: $trace} else {} end) +
         (if $psn != "" then {parent_identity: {subject_norm: $psn, create_seq: ($pcs | tonumber)}} else {} end) +
         (if $ptle != null then {tl_epoch: $ptle} else {} end)' \
        2>/dev/null) || {
        echo "v11_review_queue_add: failed to build event JSON — skipping" >&2
        return 0
    }

    # FD-208 critical section (separate from FD-207 ledger lock to allow concurrency).
    # Read-fold-decide-write inside one hold to make idempotency race-safe.
    (
        exec 208>"$lock_file"
        flock -w 5 208 || {
            echo "v11_review_queue_add: FD-208 flock timeout for project=$project — skipping" >&2
            exit 1
        }

        # Check current status by replaying the file (latest event per task_id wins)
        local current_status="absent"
        if [ -f "$jsonl_file" ] && [ -s "$jsonl_file" ]; then
            current_status=$(V11_RQ_FILE="$jsonl_file" V11_RQ_TASK="$task_id" \
                V11_RQ_PSN="$parent_sn" V11_RQ_PCS="$parent_cs" python3 - <<'PYEOF' 2>/dev/null || echo "absent"
import os, json
path = os.environ.get("V11_RQ_FILE", "")
target = os.environ.get("V11_RQ_TASK", "")
# S2-T0b-2: with the parent's identity, rows naming another parent_identity
# under this task_id are another task's (a reused id) and are skipped.
psn = os.environ.get("V11_RQ_PSN", "")
pcs = os.environ.get("V11_RQ_PCS", "")
want = (psn, int(pcs)) if psn and pcs.isdigit() else None
latest = None
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if str(ev.get("task_id", "")) == target:
                pi = ev.get("parent_identity")
                if (want is not None and isinstance(pi, dict)
                        and (pi.get("subject_norm"), pi.get("create_seq")) != want):
                    continue
                latest = ev.get("ev", "")
except Exception:
    pass
print(latest or "absent", end="")
PYEOF
)
        fi

        if [ "$current_status" = "pending" ]; then
            echo "exists"
            exit 0
        fi

        # Append the pending event (line-atomic O_APPEND)
        printf '%s\n' "$event_line" >> "$jsonl_file"
        echo "added"
    ) || true

    return 0
}

# _v11_review_verdict_store PROJECT TASK_ID VERDICT_FILE
#   B1 (improvements/09, W5-T16): persist the full verdict JSON durably at
#   ~/.agent-metrics/review-verdicts/{project}/{task_id}-{ts}.json — an
#   append-only store, one file per verdict. mkdir -p; atomic tmp+mv.
#   Echoes the destination path on success, nothing on failure.
_v11_review_verdict_store() {
    local project="$1" task_id="$2" verdict_file="$3"
    local store_dir="${METRICS_DIR}/review-verdicts/${project}"
    mkdir -p "$store_dir" 2>/dev/null || return 1
    local ts dest tmp
    # F4 fix (production-readiness): second-granularity ts collided when two
    # verdicts landed for the same task in the same second, silently
    # overwriting via mv. Uniquify with nanoseconds (%N; falls back to "0" on
    # date builds lacking it, e.g. non-GNU date) PLUS a collision-avoidance
    # suffix loop as a belt-and-suspenders guard against even a nanosecond
    # collision (or a %N-less date). Existing verdict_ref filenames
    # (task_id-<second-ts>.json, no nanosecond/suffix) remain valid — this
    # only changes the shape of newly-written filenames.
    ts="$(date -u +%Y%m%dT%H%M%S.%NZ 2>/dev/null)"
    case "$ts" in
        *.%NZ|*..*|"") ts="$(date -u +%Y%m%dT%H%M%SZ)" ;;
    esac
    dest="${store_dir}/${task_id}-${ts}.json"
    local suffix=2
    while [ -e "$dest" ]; do
        dest="${store_dir}/${task_id}-${ts}-${suffix}.json"
        suffix=$((suffix + 1))
    done
    tmp="${dest}.tmp.$$"
    if ! jq '.' "$verdict_file" > "$tmp" 2>/dev/null || [ ! -s "$tmp" ]; then
        rm -f "$tmp" 2>/dev/null
        return 1
    fi
    if ! mv "$tmp" "$dest" 2>/dev/null; then
        rm -f "$tmp" 2>/dev/null
        return 1
    fi
    printf '%s' "$dest"
    return 0
}

# _v11_review_ledger_event PROJECT TASK_ID SEVERITY VERDICT_FILE VERDICT_REF VERDICT_SHA [OUTCOME] [RESOLVED]
#   B2 (improvements/09, W5-T16): append the ev:"review" ledger event.
#   OUTCOME (S1-T11): written as `outcome` only when non-empty (today: "waived"),
#   so a waiver never lands as a clean NONE review; every other call keeps its bytes.
#   Status-neutral and counters_delta-free by construction — see the
#   `ev_type == "review"` branch in v11_replay_ledger. RESOLVED (S1-P3) is the
#   caller's v11_ledger_resolve_by_task_id result; without it the bare task_id
#   is resolved here. An AMBIGUOUS resolution writes nothing and returns 2. On
#   MISS, appends anyway with create_seq:null/identity_unresolved:
#   true (a flagged event beats a dropped verdict — unattributed-never-
#   dropped doctrine). session_uuid is the DRAINER's own session (v11_session_
#   uuid), distinct from the done-event's owner/session_uuid argument.
_v11_review_ledger_event() {
    local project="$1" task_id="$2" severity="$3" verdict_file="$4" verdict_ref="$5" verdict_sha="$6"
    local outcome="${7:-}" resolved="${8:-}"

    if [ -z "$resolved" ]; then
        resolved=$(v11_ledger_resolve_by_task_id "$project" "$task_id" 2>/dev/null || echo "MISS")
    fi
    resolved="${resolved%%$'\n'*}"  # drop the resolver's NOTE line
    [ "${resolved%%$'\t'*}" = "AMBIGUOUS" ] && return 2

    local subject_norm="" create_seq="" identity_unresolved="false"
    if [ -z "$resolved" ] || [ "$resolved" = "MISS" ]; then
        identity_unresolved="true"
    else
        subject_norm="${resolved%$'\t'*}"
        create_seq="${resolved##*$'\t'}"
    fi

    local error_count
    error_count=$(jq '(.errors // []) | length' "$verdict_file" 2>/dev/null)
    case "$error_count" in ''|*[!0-9]*) error_count=0 ;; esac

    # v11.38 W3-T1 (#49 fix): populate `owner` for attribution — was 100% gap
    # (209/209 review events unattributed in v11.37 30d audit). Read reviewer
    # identity from the verdict file's `reviewer` field, falling back to the
    # canonical adversarial-lite-reviewer name when the verdict file predates
    # the identity contract.
    local reviewer_identity
    reviewer_identity=$(jq -r '.reviewer // "adversarial-lite-reviewer"' "$verdict_file" 2>/dev/null)
    [ -z "$reviewer_identity" ] || [ "$reviewer_identity" = "null" ] && reviewer_identity="adversarial-lite-reviewer"

    local now drainer_session
    now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
    drainer_session="$(v11_session_uuid)"

    local event_json
    if [ "$identity_unresolved" = "true" ]; then
        event_json=$(jq -cn \
            --arg ts "$now" --arg project "$project" --arg task_id "$task_id" \
            --arg session_uuid "$drainer_session" --arg severity "$severity" \
            --arg verdict_sha "$verdict_sha" --arg verdict_ref "$verdict_ref" \
            --arg owner "$reviewer_identity" --arg outcome "$outcome" \
            --argjson error_count "${error_count:-0}" \
            '{v:1, ev:"review", ts:$ts, project:$project, subject_norm:"", task_id:$task_id,
              create_seq:null, identity_unresolved:true, session_uuid:$session_uuid,
              review_severity:$severity, reviewer_agent:$owner, owner:$owner,
              error_count:$error_count, verdict_sha:$verdict_sha, verdict_ref:$verdict_ref,
              source:"cli-drain"}
             + (if $outcome == "" then {} else {outcome:$outcome} end)' 2>/dev/null) || return 1
    else
        event_json=$(jq -cn \
            --arg ts "$now" --arg project "$project" --arg task_id "$task_id" \
            --arg subject_norm "$subject_norm" --argjson create_seq "$create_seq" \
            --arg session_uuid "$drainer_session" --arg severity "$severity" \
            --arg verdict_sha "$verdict_sha" --arg verdict_ref "$verdict_ref" \
            --arg owner "$reviewer_identity" --arg outcome "$outcome" \
            --argjson error_count "${error_count:-0}" \
            '{v:1, ev:"review", ts:$ts, project:$project, subject_norm:$subject_norm, task_id:$task_id,
              create_seq:$create_seq, session_uuid:$session_uuid,
              review_severity:$severity, reviewer_agent:$owner, owner:$owner,
              error_count:$error_count, verdict_sha:$verdict_sha, verdict_ref:$verdict_ref,
              source:"cli-drain"}
             + (if $outcome == "" then {} else {outcome:$outcome} end)' 2>/dev/null) || return 1
    fi

    v11_ledger_append "$project" "$event_json"
}

# _v11_prescope_ledger_event PROJECT TASK_ID SESSION_UUID REASON...
#   S1-B2 (improvements/10), S2-T5 (#83): append ONE status-neutral
#   ev:"prescope" ledger event covering every fired TaskCreate advisory
#   (V11_PRESCOPE_ADVISORY / V11_SCOPE_WARN / V11_PRESCOPE_SMELL —
#   S1-A1/A2/A3/B1) in ONE call — was one ~42-fork v11_ledger_append call
#   PER REASON, so a task that tripped e.g. both scope_large and a smell
#   check paid for two full appends. REASON... is one or more of
#   missing_scope|invalid_scope|scope_large|complex_no_deliverable|
#   smell_conjunction|smell_runbook_steps|smell_length, stamped as the
#   `reasons` array. Ledgers are append-only: rows written before this
#   change still carry the old singular `reason:<str>` shape, and readers
#   (scripts/prescope-check) accept both indefinitely.
#
#   Mirrors the ev:"review" pattern above (_v11_review_ledger_event): the
#   identity_unresolved:true / subject_norm:"" / create_seq:null sentinel is
#   used UNCONDITIONALLY here (not just as a MISS fallback) because this
#   fires from INSIDE the same TaskCreate call that produces the task's own
#   "created" ledger event — the FD-207-confirmed create_seq for this
#   task_id isn't assigned until v11_ledger_append runs for that "created"
#   event later in the same call, so there is no real identity yet to
#   resolve against (a lookup via v11_ledger_resolve_by_task_id would always
#   MISS for a task created in this very call).
#
#   v11_replay_ledger has a dedicated `ev_type == "prescope"` branch
#   (mirroring the "review" branch's status-neutral `continue`) that skips
#   by_id entirely — required because every identity_unresolved prescope row
#   for a project shares the same sentinel idk() key (project, "", -1); left
#   ungated it would collapse all rows onto one ever-mutating phantom by_id
#   record and corrupt total/pending counts (the same collision class the
#   review branch's E1 fix addressed for ev:"review").
#
#   Side-effect-never-fails: v11_ledger_append itself never fails the caller.
_v11_prescope_ledger_event() {
    local project="$1" task_id="$2" session_uuid="$3"
    shift 3
    [ "$#" -gt 0 ] || return 0

    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

    local event_json
    event_json=$(jq -cn \
        --arg ts "$now" --arg project "$project" --arg task_id "$task_id" \
        --arg session_uuid "$session_uuid" --args \
        '{v:1, ev:"prescope", ts:$ts, project:$project, subject_norm:"", task_id:$task_id,
          create_seq:null, identity_unresolved:true, session_uuid:$session_uuid,
          reasons:$ARGS.positional}' "$@" 2>/dev/null) || return 1

    v11_ledger_append "$project" "$event_json"
}

# _v11_review_queue_rows_py: the python both helpers below share. A queue row
#   belongs to (session, identity): its session_uuid when that is a UUID (else
#   none), and its parent_identity "SN:CS" (S2-T0b-2 writes it on pending rows,
#   mark-done on done rows); a done row without one takes the identity of the
#   latest pending/parked row before it that its session matches. A missing
#   session or identity matches any.
_V11_RQ_ROWS_PY='
import json, re, sys
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
def ident_of(v):
    if isinstance(v, dict):
        sn, cs = v.get("subject_norm"), v.get("create_seq")
        if isinstance(sn, str) and sn and isinstance(cs, int) and not isinstance(cs, bool) and cs >= 0:
            return f"{sn}:{cs}"
    return ""
def same(a, b):
    return not a or not b or a == b
def queue_rows(path, tid):
    out, opened = [], []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict) or str(ev.get("task_id", "")) != tid:
                continue
            sess = str(ev.get("session_uuid") or "")
            sess = sess if UUID.fullmatch(sess) else ""
            ident = ident_of(ev.get("parent_identity"))
            kind = ev.get("ev", "")
            if kind in ("pending", "parked"):
                opened.append((sess, ident))
            elif kind == "done" and not ident:
                ident = next((i for s, i in reversed(opened) if same(s, sess)), "")
            out.append((kind, sess, ident, ev))
    return out
'

# _v11_review_queue_anchor QUEUE_FILE TASK_ID [SESSION_UUID]
#   S2-T0b-3: the open queue row of TASK_ID (the latest row SESSION_UUID
#   matches, when it is pending or parked): prints session, parent identity
#   SN:CS, tl_epoch, ts and subject, each NUL-terminated (all empty when none).
_v11_review_queue_anchor() {
    V11_RQ_FILE="$1" V11_RQ_TASK="$2" V11_RQ_SESS="${3:-}" python3 -c "$_V11_RQ_ROWS_PY"'
import os
rows = [r for r in queue_rows(os.environ["V11_RQ_FILE"], os.environ["V11_RQ_TASK"])
        if same(r[1], os.environ.get("V11_RQ_SESS", ""))]
f = [""] * 5
if rows and rows[-1][0] in ("pending", "parked"):
    kind, sess, ident, ev = rows[-1]
    tle = ev.get("tl_epoch")
    tle = str(tle) if isinstance(tle, int) and not isinstance(tle, bool) and tle > 0 else (
        tle if isinstance(tle, str) and tle.isdigit() else "")
    subj = ev.get("subject")
    f = [sess, ident, tle, str(ev.get("ts") or ""),
         " ".join(subj.split()) if isinstance(subj, str) and subj not in ("", "?", "unknown") else ""]
sys.stdout.write("".join(x.replace("\0", "") + "\0" for x in f))
' 2>/dev/null || printf '\0\0\0\0\0'
}

# _v11_review_queue_status QUEUE_FILE TASK_ID SESSION IDENTITY [OPEN_IDENTITY] [IDENTITY_SET]
#   S2-T0b-3 (#97 F19): mark-done's one read of the queue, under its lock
#   (review #23: no second python for the anchor on the sync-tasks path). The
#   open row is the one _v11_review_queue_anchor finds (SESSION counts only
#   when it is a UUID). The fold matches SESSION when it is a UUID, else the
#   open row's session; and IDENTITY when IDENTITY_SET is 1 (the caller bound
#   it, or found it unbound: empty), else the open row's parent_identity.
#   Prints "<ev><TAB><masks><TAB><identity>": ev of the latest row of TASK_ID
#   that matches (session, identity), either may be empty ("absent" when none
#   does); masks 1 when the bare id's latest row is open (pending/parked) for
#   another task: both identities known and different (OPEN_IDENTITY: the
#   caller's resolution of that row when it carries no parent_identity), else
#   0 (a done row appended then would close that entry in every task_id-keyed
#   queue view); identity: the one the done row carries.
_v11_review_queue_status() {
    V11_RQ_FILE="$1" V11_RQ_TASK="$2" V11_RQ_SESS="${3:-}" V11_RQ_IDENT="${4:-}" V11_RQ_OPEN="${5:-}" \
    V11_RQ_IDENT_SET="${6:-0}" python3 -c "$_V11_RQ_ROWS_PY"'
import os
rows = queue_rows(os.environ["V11_RQ_FILE"], os.environ["V11_RQ_TASK"])
want_s = os.environ.get("V11_RQ_SESS", "")
want_s = want_s if UUID.fullmatch(want_s) else ""
mine = [r for r in rows if same(r[1], want_s)]
open_s, open_i = (mine[-1][1], mine[-1][2]) if mine and mine[-1][0] in ("pending", "parked") else ("", "")
want_s = want_s or open_s
want_i = os.environ.get("V11_RQ_IDENT", "") if os.environ.get("V11_RQ_IDENT_SET") == "1" else open_i
latest, last = "absent", None
for kind, sess, ident, _ev in rows:
    last = (kind, sess, ident)
    if same(sess, want_s) and same(ident, want_i):
        latest = kind or latest
masks = False
if last is not None and last[0] in ("pending", "parked"):
    kind, sess, ident = last
    if not ident and same(sess, want_s):
        ident = os.environ.get("V11_RQ_OPEN", "")
    masks = not same(ident, want_i)
sys.stdout.write(f"{latest}\t{int(masks)}\t{want_i}")
' 2>/dev/null || printf 'absent'
}

# v11_review_queue_mark_done PROJECT TASK_ID [REVIEW_SEVERITY] [SESSION_UUID] [VERDICT_FILE] [IDENTITY]
#   Append a done event. Idempotent: if latest is already done, no-op.
#   REVIEW_SEVERITY is informational (max severity from review.errors[*]) for the queue surface.
#   VERDICT_FILE (optional, W5-T16/improvements/09): when given and
#   V11_REVIEW_LEDGER != "off", triggers B1 (durable verdict store) + B2
#   (ev:"review" ledger event); the resulting verdict_ref/verdict_sha are
#   also folded into this done event (B4). Without VERDICT_FILE, behavior
#   (including the done event's shape) is byte-identical to today.
#   S1-P3 (#97): with VERDICT_FILE, SESSION_UUID also names the parent task's
#   session — the verdict binds to the task that session created under
#   TASK_ID. Without SESSION_UUID a task_id reused across sessions is refused
#   (stderr message, return 2, nothing written) rather than bound to a guess.
#   Echoes "marked", "already_done", or "absent" on stdout.
#   S2-T0b-3 (#113, #97 F19). IDENTITY ("SUBJECT_NORM:CREATE_SEQ", review-queue
#   mark-done --identity) names the parent exactly. The verdict binds, in order,
#   to: IDENTITY (R0; one the ledger does not know is refused, return 2); the
#   open queue row's parent_identity (R0); its tl_epoch (R1); its ts and
#   subject (R2); else (session, task_id) alone. The open queue row is the
#   latest pending/parked row for the task_id in SESSION_UUID (any session when
#   SESSION_UUID is empty or not a UUID, whose session then stands in). The
#   done row carries the bound identity as parent_identity (the open row's own
#   when its parent_identity is not in the ledger and the fold fell back to the
#   row's epoch/position: it closes that row, review #23), and already_done
#   matches (session, task_id, identity) instead of the bare task_id: a row
#   without a session or identity matches any, and a done row without
#   parent_identity takes the one of the row it closed. V11_TASK_RESOLVER=legacy
#   keeps the v11.46 behaviour and bytes.
v11_review_queue_mark_done() {
    local project="$1" task_id="$2"
    local severity="${3:-NONE}" session_uuid="${4:-}" verdict_file="${5:-}" identity_arg="${6:-}"
    local _rq_shared=1
    [ "${V11_TASK_RESOLVER:-shared}" = "legacy" ] && _rq_shared=0

    # V11.28.1: normalize severity to the canonical enum {NONE,LOW,MEDIUM,HIGH,CRITICAL}
    # at the single write chokepoint. Any non-severity code (no_op, waived, misrouted,
    # skipped, the historical `--severity` flag-leak, etc.) is routed to an `outcome`
    # field and the severity neutralized to NONE — so agent-scorecard aggregates a clean
    # 5-value scale instead of the ~20-value dumping ground it had. (Loop-audit 2026-07-01.)
    local _rq_outcome=""
    case "$(printf '%s' "$severity" | tr '[:lower:]' '[:upper:]')" in
        NONE|"")       severity="NONE" ;;
        LOW)           severity="LOW" ;;
        MED|MEDIUM)    severity="MEDIUM" ;;
        HIGH)          severity="HIGH" ;;
        CRIT|CRITICAL) severity="CRITICAL" ;;
        *)             _rq_outcome="$(printf '%s' "$severity" | tr '[:upper:]' '[:lower:]' \
                          | tr -c 'a-z0-9_-' '_' | sed 's/^[_-]*//; s/[_-]*$//')"
                       severity="NONE" ;;
    esac

    # S1-T11: a verdict file that says WAIVED is a waiver even when the severity
    # was derived from its (empty) errors[] — `review-queue mark-done --verdict-file`
    # with no SEV passes NONE, which is how the 19 S0 waivers landed as clean reviews.
    if [ -z "$_rq_outcome" ] && [ -n "$verdict_file" ] && [ -f "$verdict_file" ] \
       && [ "$(jq -r '(.verdict // "") | ascii_downcase' "$verdict_file" 2>/dev/null)" = "waived" ]; then
        _rq_outcome="waived"
    fi

    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        return 0
    fi
    if [ -z "$task_id" ] || ! printf '%s' "$task_id" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        return 0
    fi

    local queue_dir="${METRICS_DIR}/review-queue"
    local jsonl_file lock_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl) || return 0
    lock_file=$(v11_review_queue_path "$project" lock) || return 0

    mkdir -p "$queue_dir" 2>/dev/null || return 0

    # S2-T0b-3: the open queue row this fold answers, and the identity it names.
    # Read here only when a resolver call needs it (a verdict to bind, or
    # IDENTITY); otherwise the status read under the lock finds it, so the
    # sync-tasks TaskUpdate fold (no verdict file) forks what v11.46 did.
    local _rq_sess_ok=0 _rq_target="" _rq_target_set=0 _rq_anchor_sess="" _rq_row_ident=""
    local _rq_anchor=("" "" "" "" "")  # session, parent identity SN:CS, tl_epoch, ts, subject
    [[ "$session_uuid" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] && _rq_sess_ok=1
    if [ "$_rq_shared" = 1 ]; then
        if [ -n "$identity_arg" ]; then
            if ! [[ "$identity_arg" =~ ^.+:[0-9]+$ ]]; then
                echo "review-queue mark-done: --identity must be SUBJECT_NORM:CREATE_SEQ, got '$identity_arg'. Nothing was written." >&2
                return 2
            fi
            _rq_target="$identity_arg"
            _rq_target_set=1
        fi
        if [ -s "$jsonl_file" ] && { [ -n "$identity_arg" ] || { [ -n "$verdict_file" ] && [ -f "$verdict_file" ] \
                && [ "${V11_REVIEW_LEDGER:-on}" != "off" ]; }; }; then
            [ "$_rq_sess_ok" = 1 ] && _rq_anchor_sess="$session_uuid"
            mapfile -t -d '' _rq_anchor < <(_v11_review_queue_anchor "$jsonl_file" "$task_id" "$_rq_anchor_sess")
            [ "${#_rq_anchor[@]}" -eq 5 ] || _rq_anchor=("" "" "" "" "")
            [ -z "$_rq_target" ] && _rq_target="${_rq_anchor[1]}"
        fi
    fi

    # B1+B2 (improvements/09, W5-T16): verdict fold-back, gated by
    # V11_REVIEW_LEDGER (new lever, default on). Never fails mark-done —
    # a verdict-store/ledger failure just means verdict_ref/verdict_sha
    # stay empty on the done event (falls back to today's severity-only shape).
    local verdict_ref="" verdict_sha=""
    if [ -n "$verdict_file" ] && [ -f "$verdict_file" ] && [ "${V11_REVIEW_LEDGER:-on}" != "off" ]; then
        # S1-P3: bind the parent before anything is written, so a refusal
        # leaves no verdict file, ledger row or queue row behind.
        local resolved _rq_note=""
        if [ "$_rq_shared" = 1 ]; then
            local _rq_rsess="$session_uuid" _rq_flags=()
            if [ "$_rq_sess_ok" = 0 ] \
               && [[ "${_rq_anchor[0]}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
                _rq_rsess="${_rq_anchor[0]}"
            fi
            # --opt=VALUE: a subject or norm starting with '-' stays a value (review
            # #23); the resolver's own stderr notes pass through to the caller.
            [ -n "${_rq_anchor[2]}" ] && _rq_flags+=("--epoch=${_rq_anchor[2]}")
            [ -n "${_rq_anchor[3]}" ] && _rq_flags+=("--at=${_rq_anchor[3]}")
            [ -n "${_rq_anchor[4]}" ] && _rq_flags+=("--subject=${_rq_anchor[4]}")
            _rq_target_set=1
            if [ -n "$_rq_target" ]; then
                resolved=$(v11_ledger_resolve_by_task_id "$project" "$task_id" "$_rq_rsess" "" \
                    "--identity=$_rq_target" || echo "MISS")
                # A queue row's parent_identity the ledger does not know falls
                # back to the row's epoch/position; an explicit IDENTITY never does.
                if [ -z "$identity_arg" ] && { [ -z "$resolved" ] || [ "$resolved" = "MISS" ]; }; then
                    echo "review-queue mark-done: note — the queue row's parent_identity '$_rq_target' is not in the $project ledger; binding by the row's TaskList epoch and position" >&2
                    # The fold still answers that row: the done row carries the
                    # row's own identity, so it closes the entry (review #23).
                    _rq_row_ident="$_rq_target"
                    _rq_target=""
                fi
            fi
            if [ -z "$_rq_target" ]; then
                resolved=$(v11_ledger_resolve_by_task_id "$project" "$task_id" "$_rq_rsess" "" \
                    "${_rq_flags[@]+"${_rq_flags[@]}"}" || echo "MISS")
            fi
        else
            resolved=$(v11_ledger_resolve_by_task_id "$project" "$task_id" "$session_uuid" 2>/dev/null || echo "MISS")
        fi
        case "$resolved" in *$'\n'*) _rq_note="${resolved#*$'\n'}"; resolved="${resolved%%$'\n'*}" ;; esac
        if [ "${resolved%%$'\t'*}" = "AMBIGUOUS" ]; then
            echo "review-queue mark-done: ${resolved#*$'\t'}. Nothing was written." >&2
            return 2
        fi
        if [ -n "$identity_arg" ] && [ "$_rq_shared" = 1 ] && { [ -z "$resolved" ] || [ "$resolved" = "MISS" ]; }; then
            echo "review-queue mark-done: identity '$identity_arg' is not in the $project ledger. Nothing was written." >&2
            return 2
        fi
        if [ "$_rq_shared" = 1 ] && [ -n "$resolved" ] && [ "$resolved" != "MISS" ]; then
            _rq_target="${resolved%$'\t'*}:${resolved##*$'\t'}"
        fi
        [ -n "$_rq_note" ] && echo "review-queue mark-done: note — ${_rq_note#NOTE$'\t'}" >&2
        if [ -n "$session_uuid" ] && { [ -z "$resolved" ] || [ "$resolved" = "MISS" ]; }; then
            echo "review-queue mark-done: session $session_uuid has no task $task_id in the $project ledger — the verdict is recorded with identity_unresolved:true" >&2
        fi
        verdict_ref=$(_v11_review_verdict_store "$project" "$task_id" "$verdict_file" 2>/dev/null || true)
        if [ -n "$verdict_ref" ] && [ -f "$verdict_ref" ]; then
            verdict_sha=$(sha256sum "$verdict_ref" 2>/dev/null | awk '{print $1}')
            # Only a waiver's outcome reaches the ledger row; other outcome codes
            # (no_op, misrouted, ...) keep today's bytes until S3-T6 reworks this.
            local _rl_outcome=""
            [ "$_rq_outcome" = "waived" ] && _rl_outcome="waived"
            _v11_review_ledger_event "$project" "$task_id" "$severity" "$verdict_file" "$verdict_ref" "$verdict_sha" "$_rl_outcome" "${resolved:-MISS}" 2>/dev/null || true
        else
            verdict_ref=""
        fi
    fi

    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

    # --identity may name another task than the open queue row does (a verdict
    # kept from an earlier TaskList): resolve that row's own task, so the done
    # row never closes it (see _v11_review_queue_status "masks").
    local _rq_open_ident="${_rq_anchor[1]}"
    if [ "$_rq_shared" = 1 ] && [ -n "$identity_arg" ] && [ -z "$_rq_open_ident" ] && [ -n "${_rq_anchor[3]}" ]; then
        local _rq_asess="$session_uuid" _rq_ares="" _rq_aflags=("--at=${_rq_anchor[3]}")
        [ "$_rq_sess_ok" = 1 ] || _rq_asess="${_rq_anchor[0]}"
        [ -n "${_rq_anchor[2]}" ] && _rq_aflags+=("--epoch=${_rq_anchor[2]}")
        [ -n "${_rq_anchor[4]}" ] && _rq_aflags+=("--subject=${_rq_anchor[4]}")
        _rq_ares=$(v11_ledger_resolve_by_task_id "$project" "$task_id" "$_rq_asess" "" \
            "${_rq_aflags[@]}" || echo "MISS")
        _rq_ares="${_rq_ares%%$'\n'*}"
        case "$_rq_ares" in
            ""|MISS|AMBIGUOUS*) ;;
            *) _rq_open_ident="${_rq_ares%$'\t'*}:${_rq_ares##*$'\t'}" ;;
        esac
    fi

    (
        exec 208>"$lock_file"
        flock -w 5 208 || exit 1

        # The done row's parent_identity: the bound identity, else (shared mode)
        # the open queue row's, which the status read below finds.
        local current_status="absent" _rq_pi="$_rq_target" _rq_st=""
        if [ -f "$jsonl_file" ] && [ -s "$jsonl_file" ] && [ "$_rq_shared" = 1 ]; then
            _rq_st=$(_v11_review_queue_status "$jsonl_file" "$task_id" "$session_uuid" \
                "${_rq_row_ident:-$_rq_target}" "$_rq_open_ident" "$_rq_target_set")
            case "$_rq_st" in
                *$'\t'*$'\t'*)
                    current_status="${_rq_st%%$'\t'*}"
                    _rq_st="${_rq_st#*$'\t'}"
                    _rq_pi="${_rq_st#*$'\t'}"
                    if [ "${_rq_st%%$'\t'*}" = 1 ]; then
                        echo "review-queue mark-done: note — the open queue entry for task_id $task_id names another task; it stays open (the verdict is in the ledger, no done row written)" >&2
                        case "$current_status" in done) echo "already_done" ;; *) echo "absent" ;; esac
                        exit 0
                    fi
                    ;;
                *) current_status="${_rq_st:-absent}" ;;
            esac
        elif [ -f "$jsonl_file" ] && [ -s "$jsonl_file" ]; then
            current_status=$(V11_RQ_FILE="$jsonl_file" V11_RQ_TASK="$task_id" python3 - <<'PYEOF' 2>/dev/null || echo "absent"
import os, json
path = os.environ.get("V11_RQ_FILE", "")
target = os.environ.get("V11_RQ_TASK", "")
latest = None
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if str(ev.get("task_id", "")) == target:
                latest = ev.get("ev", "")
except Exception:
    pass
print(latest or "absent", end="")
PYEOF
)
        fi

        [ "$current_status" = done ] && { echo "already_done"; exit 0; }

        local event_line
        event_line=$(jq -cn \
            --arg ts "$now" \
            --arg project "$project" \
            --arg task_id "$task_id" \
            --arg severity "$severity" \
            --arg outcome "$_rq_outcome" \
            --arg session_uuid "${session_uuid:-}" \
            --arg verdict_ref "${verdict_ref:-}" \
            --arg verdict_sha "${verdict_sha:-}" \
            --arg pi "$_rq_pi" \
            '{v:1, ev:"done", ts:$ts, project:$project, task_id:$task_id,
              review_severity:$severity, session_uuid:$session_uuid}
             + (if $outcome == "" then {} else {outcome:$outcome} end)
             + (if $verdict_ref == "" then {} else {verdict_ref:$verdict_ref} end)
             + (if $verdict_sha == "" then {} else {verdict_sha:$verdict_sha} end)
             + (if ($pi | test("^.+:[0-9]+$")) then
                  ($pi | capture("^(?<sn>.+):(?<cs>[0-9]+)$")
                   | {parent_identity: {subject_norm: .sn, create_seq: (.cs | tonumber)}})
                else {} end)' 2>/dev/null) || exit 0

        case "$current_status" in
            absent) echo "absent" ;;  # No prior pending — still record the done for audit trail
            *) echo "marked" ;;
        esac

        printf '%s\n' "$event_line" >> "$jsonl_file"
    ) || true

    return 0
}

# v11_review_queue_pending_count PROJECT
#   Echo integer count of tasks whose latest event is "pending". 0 if file missing.
v11_review_queue_pending_count() {
    local project="$1"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        printf '0'
        return 0
    fi
    local jsonl_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl 2>/dev/null) || { printf '0'; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        printf '0'
        return 0
    fi

    V11_RQ_FILE="$jsonl_file" python3 - <<'PYEOF' 2>/dev/null || printf '0'
import os, json
path = os.environ.get("V11_RQ_FILE", "")
latest = {}
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            tid = str(ev.get("task_id", ""))
            if not tid:
                continue
            latest[tid] = ev.get("ev", "")
except Exception:
    print(0, end="")
    raise SystemExit(0)
pending = sum(1 for s in latest.values() if s == "pending")
print(pending, end="")
PYEOF
}

# --- Improvement 03: review-queue drainage (§B claiming, §D backstop support) ---
# 2026-07-01 (v11-loop-keystone Fix 2). Ships v11/improvements/03-review-queue-drainage.md.

# v11_review_queue_claim PROJECT TASK_ID CLAIMANT_SESSION_UUID
#   Attempts to claim a pending review entry for draining by CLAIMANT_SESSION_UUID.
#   Append-only: writes a fresh "pending" event (same task_id) carrying the
#   updated claimed_by/claimed_at — replay-latest-wins means this event
#   supersedes the prior claim state without mutating history.
#   Idempotent: re-claiming by the same session, or claiming an entry whose
#   existing claim is stale (owning session no longer live per
#   v11_session_is_live), succeeds. A claim held by a DIFFERENT still-live
#   session is refused.
#   Echoes one of: claimed | already_mine | owned_by_other | absent | not_pending
v11_review_queue_claim() {
    local project="$1" task_id="$2" claimant="$3"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "absent"; return 0
    fi
    if [ -z "$task_id" ] || [ -z "$claimant" ]; then
        echo "absent"; return 0
    fi
    local jsonl_file lock_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl 2>/dev/null) || { echo "absent"; return 0; }
    lock_file=$(v11_review_queue_path "$project" lock 2>/dev/null) || { echo "absent"; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        echo "absent"; return 0
    fi

    (
        exec 208>"$lock_file"
        flock -w 5 208 || { echo "absent"; exit 0; }

        local latest
        latest=$(V11_RQ_FILE="$jsonl_file" V11_RQ_TASK="$task_id" python3 - <<'PYEOF' 2>/dev/null
import os, json
path = os.environ.get("V11_RQ_FILE", "")
target = os.environ.get("V11_RQ_TASK", "")
latest = None
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if str(ev.get("task_id", "")) == target:
                latest = ev
except Exception:
    pass
print(json.dumps(latest) if latest is not None else "null")
PYEOF
)
        if [ -z "$latest" ] || [ "$latest" = "null" ]; then
            echo "absent"
            exit 0
        fi

        local ev_type claimed_by
        ev_type=$(printf '%s' "$latest" | jq -r '.ev // ""' 2>/dev/null)
        if [ "$ev_type" != "pending" ]; then
            echo "not_pending"
            exit 0
        fi
        claimed_by=$(printf '%s' "$latest" | jq -r '.claimed_by // ""' 2>/dev/null)

        if [ "$claimed_by" = "$claimant" ]; then
            echo "already_mine"
            exit 0
        fi
        if [ -n "$claimed_by" ] && v11_session_is_live "$claimed_by"; then
            echo "owned_by_other"
            exit 0
        fi

        local now new_line
        now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
        new_line=$(printf '%s' "$latest" | jq -c --arg cb "$claimant" --arg ts "$now" \
            '. + {claimed_by: $cb, claimed_at: $ts}' 2>/dev/null)
        if [ -z "$new_line" ]; then
            echo "absent"
            exit 0
        fi
        printf '%s\n' "$new_line" >> "$jsonl_file"
        echo "claimed"
    )
    return 0
}

# v11_review_queue_park PROJECT TASK_ID REASON [VERDICT_KEPT] [RC] [BY]
#   Sprint-close review (S1): parks a pending entry whose verdict cannot be
#   folded. `mark-done --verdict-file` exits 2 when the S1-P3 resolver finds
#   the task_id names several tasks (a TaskList restart that reuses ids), and
#   it will refuse the same way on every later run. Left pending, the nightly
#   review-daemon cadence re-drains the entry and pays for a new headless
#   review each time. Append-only, like claim: a copy of the latest pending
#   event with ev:"parked", the claim cleared, and parked_at, park_reason,
#   parked_by, plus park_rc/verdict_kept when given. Every drain path selects
#   ev=="pending" only, so a parked entry is neither drainable nor done.
#   Echoes one of: parked | already_parked | not_pending | absent | lock_timeout
v11_review_queue_park() {
    _v11_review_queue_park_transition park "$@"
}

# v11_review_queue_unpark PROJECT TASK_ID [BY]
#   Reverses v11_review_queue_park: appends the parked event back as
#   ev:"pending" (claim cleared, park fields dropped, unparked_at/unparked_by
#   added; ts, and so pending_since, kept), so the next drain picks it up.
#   Echoes one of: unparked | not_parked | absent | lock_timeout
v11_review_queue_unpark() {
    local project="$1" task_id="$2" by="${3:-}"
    _v11_review_queue_park_transition unpark "$project" "$task_id" "" "" "" "$by"
}

_v11_review_queue_park_transition() {
    local mode="$1" project="$2" task_id="$3" reason="${4:-}" kept="${5:-}" rc="${6:-}" by="${7:-}"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "absent"; return 0
    fi
    [ -z "$task_id" ] && { echo "absent"; return 0; }
    [ -z "$by" ] && by="$(v11_session_uuid 2>/dev/null || echo "legacy-cli")"
    local jsonl_file lock_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl 2>/dev/null) || { echo "absent"; return 0; }
    lock_file=$(v11_review_queue_path "$project" lock 2>/dev/null) || { echo "absent"; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        echo "absent"; return 0
    fi

    (
        exec 208>"$lock_file"
        flock -w 5 208 || { echo "lock_timeout"; exit 0; }
        V11_RQ_FILE="$jsonl_file" V11_RQ_TASK="$task_id" V11_RQ_MODE="$mode" \
        V11_RQ_REASON="$reason" V11_RQ_KEPT="$kept" V11_RQ_RC="$rc" V11_RQ_BY="$by" \
        python3 - <<'PYEOF' 2>/dev/null || echo "absent"
import os, json
from datetime import datetime, timezone

path = os.environ["V11_RQ_FILE"]
target = os.environ["V11_RQ_TASK"]
mode = os.environ.get("V11_RQ_MODE", "")
latest = None
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if str(ev.get("task_id", "")) == target:
            latest = ev
if latest is None:
    print("absent")
    raise SystemExit(0)

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
PARK_FIELDS = ("parked_at", "park_reason", "park_rc", "verdict_kept", "parked_by")
new = dict(latest)
new["claimed_by"] = None
new.pop("claimed_at", None)
if mode == "park":
    if latest.get("ev") == "parked":
        print("already_parked")
        raise SystemExit(0)
    if latest.get("ev") != "pending":
        print("not_pending")
        raise SystemExit(0)
    for k in ("unparked_at", "unparked_by"):
        new.pop(k, None)
    new.update(ev="parked", parked_at=now, park_reason=os.environ.get("V11_RQ_REASON", ""),
               parked_by=os.environ.get("V11_RQ_BY", ""))
    rc = os.environ.get("V11_RQ_RC", "")
    if rc.isdigit():
        new["park_rc"] = int(rc)
    kept = os.environ.get("V11_RQ_KEPT", "")
    if kept:
        new["verdict_kept"] = kept
    result = "parked"
else:
    if latest.get("ev") != "parked":
        print("not_parked")
        raise SystemExit(0)
    for k in PARK_FIELDS:
        new.pop(k, None)
    new.update(ev="pending", unparked_at=now, unparked_by=os.environ.get("V11_RQ_BY", ""))
    result = "unparked"
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(new, separators=(",", ":")) + "\n")
print(result)
PYEOF
    )
    return 0
}

# v11_review_queue_gc PROJECT [MAX_AGE_MINUTES]
#   Clears claimed_by on pending entries whose claim is stale: claimed_by set,
#   still pending (no later done event -- guaranteed by only inspecting the
#   latest event per task_id), and claimed_at/ts older than MAX_AGE_MINUTES.
#
#   Liveness/GC coupling: v11_session_is_live (V11_SESSION_LIVENESS_MINUTES,
#   default 15) decides whether a claim is steal-able RIGHT NOW. GC's window
#   is intentionally a grace period AFTER a holder goes not-live -- it must be
#   >= the liveness window, never equal to or shorter than it, or GC would
#   reap a claim before the liveness check itself would ever consider it
#   stealable, and a session merely slow (but still within its liveness
#   window) could have its claim reaped out from under it.
#   Default (when V11_REVIEW_GC_STALE_MINUTES is unset): 2x the *effective*
#   V11_SESSION_LIVENESS_MINUTES, so the historical default of 30 (2x15) is
#   preserved for backcompat while the coupling is explicit rather than two
#   independently-hardcoded numbers that can drift apart. An explicit
#   V11_REVIEW_GC_STALE_MINUTES env override always wins over the derived
#   default.
#   Emits JSON: {"project":P,"cleared":N,"checked":M}
v11_review_queue_gc() {
    local project="$1"
    local _liveness_min="${V11_SESSION_LIVENESS_MINUTES:-15}"
    local max_age_min="${2:-${V11_REVIEW_GC_STALE_MINUTES:-$((2 * _liveness_min))}}"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        printf '{"project":"","cleared":0,"checked":0}'
        return 0
    fi
    local jsonl_file lock_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl 2>/dev/null) || jsonl_file=""
    lock_file=$(v11_review_queue_path "$project" lock 2>/dev/null) || lock_file=""
    if [ -z "$jsonl_file" ] || [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        printf '{"project":"%s","cleared":0,"checked":0}' "$project"
        return 0
    fi

    # Post-adversarial-review fix (2026-07-01, task #6/original-#2 review, E1):
    # age alone is not sufficient to release a claim -- a live session running
    # a slow review (>max_age_min) would have its claim silently revoked,
    # reopening the exact double-dispatch race claim/gc exists to prevent.
    # Build the set of currently-live claimant session_uuids (same liveness
    # rule as v11_review_queue_claim's own check) and pass it through so
    # python only clears entries whose claimant is NOT live.
    local live_claimants=""
    if command -v jq >/dev/null 2>&1; then
        local _candidate
        for _candidate in $(jq -r 'select(.ev=="pending") | .claimed_by // empty' "$jsonl_file" 2>/dev/null | sort -u); do
            if v11_session_is_live "$_candidate"; then
                live_claimants="$live_claimants $_candidate"
            fi
        done
    fi

    local gc_out
    gc_out=$(
        exec 208>"$lock_file"
        flock -w 5 208 || { printf '{"cleared":0,"checked":0}'; exit 0; }
        V11_RQ_FILE="$jsonl_file" V11_RQ_MAXAGE="$max_age_min" V11_RQ_LIVE_CLAIMANTS="$live_claimants" python3 - <<'PYEOF'
import os, json
from datetime import datetime, timezone

path = os.environ.get("V11_RQ_FILE", "")
max_age = float(os.environ.get("V11_RQ_MAXAGE", "30"))
live_claimants = set(os.environ.get("V11_RQ_LIVE_CLAIMANTS", "").split())

latest = {}
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            tid = str(ev.get("task_id", ""))
            if not tid:
                continue
            latest[tid] = ev
except Exception:
    print(json.dumps({"cleared": 0, "checked": 0}))
    raise SystemExit(0)

now = datetime.now(timezone.utc).timestamp()
to_clear = []
checked = 0
for ev in latest.values():
    if ev.get("ev") != "pending":
        continue
    cb = ev.get("claimed_by") or ""
    if not cb:
        continue
    checked += 1
    if cb in live_claimants:
        # Claimant session is still live (touched within
        # V11_SESSION_LIVENESS_MINUTES) -- age alone does not mean the claim
        # is stale, it means the review is taking a while. Never release a
        # live session's claim out from under it.
        continue
    ts_raw = ev.get("claimed_at") or ev.get("ts") or ""
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        continue
    age_min = (now - ts) / 60.0
    if age_min > max_age:
        to_clear.append(ev)

out_lines = []
for ev in to_clear:
    new_ev = dict(ev)
    new_ev["claimed_by"] = None
    new_ev.pop("claimed_at", None)
    new_ev["gc_released_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    out_lines.append(json.dumps(new_ev, separators=(",", ":")))

if out_lines:
    with open(path, "a", encoding="utf-8") as f:
        for line in out_lines:
            f.write(line + "\n")

print(json.dumps({"cleared": len(to_clear), "checked": checked}))
PYEOF
    )
    printf '%s' "$gc_out" | jq -c --arg p "$project" '. + {project:$p}' 2>/dev/null \
        || printf '{"project":"%s","cleared":0,"checked":0}' "$project"
    return 0
}

# v11_review_queue_classify PROJECT MY_SESSION_UUID
#   Classifies every currently-pending review entry for PROJECT as drainable
#   by MY_SESSION_UUID or blocked by a DIFFERENT still-live session. Two
#   independent conflict signals (either blocks):
#     1. claimed_by is set to a different session that is still live (§B claim).
#     2. files_changed overlaps another pending entry authored/claimed by a
#        different still-live session -- heuristic proxy for "a concurrent
#        session is actively touching these files". V11 has no live file-lock
#        registry; this reuses the session_uuid already recorded on every
#        queue entry (per task instructions: reuse existing session tracking,
#        don't invent a new one) rather than fabricating file-level locking.
#   Emits JSON array: [{task_id, drainable(bool), conflict_owner(str|null), conflict_reason(str|null)}]
v11_review_queue_classify() {
    local project="$1" my_session="$2"
    local jsonl_file
    jsonl_file=$(v11_review_queue_path "$project" jsonl 2>/dev/null) || { printf '[]'; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        printf '[]'
        return 0
    fi

    local pending_min
    pending_min=$(V11_RQ_FILE="$jsonl_file" python3 - <<'PYEOF' 2>/dev/null
import os, json
path = os.environ.get("V11_RQ_FILE", "")
latest = {}
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            tid = str(ev.get("task_id", ""))
            if not tid:
                continue
            latest[tid] = ev
except Exception:
    print("[]")
    raise SystemExit(0)
out = []
for tid, ev in latest.items():
    if ev.get("ev") != "pending":
        continue
    out.append({
        "task_id": tid,
        "session_uuid": ev.get("session_uuid") or "",
        "claimed_by": ev.get("claimed_by") or "",
        "files_changed": ev.get("files_changed") or [],
    })
print(json.dumps(out, separators=(",", ":")))
PYEOF
)
    [ -z "$pending_min" ] && pending_min="[]"

    # Determine liveness for every distinct owning session referenced (claimed_by
    # first, falling back to authoring session_uuid), excluding my own session.
    local sessions_seen live_map="{}" s
    sessions_seen=$(printf '%s' "$pending_min" | jq -r '.[] | (if (.claimed_by // "") != "" then .claimed_by else .session_uuid end)' 2>/dev/null | sort -u | grep -v '^$' || true)
    while IFS= read -r s; do
        [ -z "$s" ] && continue
        [ "$s" = "$my_session" ] && continue
        if v11_session_is_live "$s"; then
            live_map=$(printf '%s' "$live_map" | jq --arg s "$s" '.[$s]=true' 2>/dev/null || echo "$live_map")
        fi
    done <<< "$sessions_seen"

    V11_RQ_PENDING="$pending_min" V11_RQ_LIVE="$live_map" V11_RQ_MY="$my_session" python3 - <<'PYEOF' 2>/dev/null
import os, json
pending = json.loads(os.environ.get("V11_RQ_PENDING", "[]"))
live = json.loads(os.environ.get("V11_RQ_LIVE", "{}"))
my_session = os.environ.get("V11_RQ_MY", "")


def owner_of(e):
    return e.get("claimed_by") or e.get("session_uuid") or ""


out = []
for e in pending:
    tid = e["task_id"]
    owner = owner_of(e)
    conflict_owner = None
    reason = None
    if owner and owner != my_session and live.get(owner):
        conflict_owner = owner
        reason = "claimed" if e.get("claimed_by") else "authored_by_live_session"
    else:
        files = set(e.get("files_changed") or [])
        if files:
            for other in pending:
                if other["task_id"] == tid:
                    continue
                o_owner = owner_of(other)
                if not o_owner or o_owner == my_session or not live.get(o_owner):
                    continue
                if files & set(other.get("files_changed") or []):
                    conflict_owner = o_owner
                    reason = "files_overlap"
                    break
    out.append({
        "task_id": tid,
        "drainable": conflict_owner is None,
        "conflict_owner": conflict_owner,
        "conflict_reason": reason,
    })
print(json.dumps(out, separators=(",", ":")))
PYEOF
    return 0
}

# v11_fold_manifest_read PROJECT
#   Echo the contents of $SESSIONS_ROOT/<project>/.handoff-fold-manifest.json
#   if the file exists and is valid JSON, else echo {}. First-session guard:
#   the file may not exist on a brand-new project — [ -f ] before any read.
#   Source ref: scripts/handoff writes this file (~handoff:1272).
v11_fold_manifest_read() {
    local project="$1"
    local _mft="$SESSIONS_ROOT/$project/.handoff-fold-manifest.json"
    if [ -f "$_mft" ] && jq empty "$_mft" 2>/dev/null; then
        cat "$_mft"
    else
        printf '{}'
    fi
}

# v11_retro_counter_read PROJECT
#   Echo the integer in $SESSIONS_ROOT/<project>/.retro-counter (strip
#   non-digits; default 0). First-session guard: file may not exist on a
#   brand-new project.
#   Source ref: hooks/session-end increments this counter (~session-end:170).
v11_retro_counter_read() {
    local project="$1"
    local _rf="$SESSIONS_ROOT/$project/.retro-counter"
    if [ -f "$_rf" ]; then
        local _v
        _v=$(tr -dc '0-9' < "$_rf" 2>/dev/null || echo "0")
        printf '%s' "${_v:-0}"
    else
        printf '0'
    fi
}

# --- V11.20: Cross-layer attribution helpers ---
#
# Three helpers wire the four-layer audit pipeline (runtime / lite / wave / swarm):
#   v11_caller_kind                   — distinguish orchestrator vs subagent on every audit event
#   v11_compute_attribution_key       — deterministic SHA256 dedup key for wave/swarm findings
#   v11_resolve_file_to_task          — map a finding's file back to the task that produced it
#
# All three are pure-stdlib (no new deps). Rollback levers:
#   V11_CALLER_KIND=off  → v11_caller_kind returns empty string (legacy behavior; field unset on write)
#   no rollback for the other two — they are read-only helpers, no side effects.

# v11_caller_kind — echo subagent | orchestrator | unknown | (empty if disabled)
#
# Detection rules (per spec, in priority order):
#   1. V11_CALLER_KIND=off              → empty (rollback; caller treats as legacy/absent)
#   2. V11_SUBAGENT=1 (or non-empty != "0")
#                                       → subagent  (explicit signal from Agent-tool launches)
#   3. V11_PARENT_SESSION_ID is set AND != V11_SESSION_ID
#                                       → subagent  (cross-validation: has a different parent)
#   4. V11_PARENT_SESSION_ID is set AND  == V11_SESSION_ID
#                                       → orchestrator  (own session — main lane)
#   5. None of the above                → unknown
#
# Caveat (V11.20 launch): V11_SUBAGENT and V11_PARENT_SESSION_ID are NEW conventions.
# Until the Claude Code Agent-tool launcher (or a future track-agents pre-hook) injects them,
# most events will fall through to 'unknown'. Once the upstream setter is wired (out of scope
# for V11.20 — tracked separately), the helper "just starts working" — no code change here.
#
# Stdout: one of "subagent" "orchestrator" "unknown" or empty.
# Exit code: always 0.
v11_caller_kind() {
    if [ "${V11_CALLER_KIND:-}" = "off" ]; then
        # Rollback: emit nothing. Callers that compose JSON should branch on `[ -n "$kind" ]`
        # and either omit the caller_kind field entirely (preserving legacy schema) or
        # write a literal null.
        return 0
    fi

    local sub="${V11_SUBAGENT:-}"
    if [ -n "$sub" ] && [ "$sub" != "0" ]; then
        printf 'subagent'
        return 0
    fi

    local parent="${V11_PARENT_SESSION_ID:-}"
    local self="${V11_SESSION_ID:-}"
    if [ -n "$parent" ]; then
        # A non-empty parent session id means "this process was launched by another session"
        # — even if our own V11_SESSION_ID is missing for some reason. So presence of a parent
        # alone is enough to label this a subagent UNLESS parent matches self (the V11.20
        # convention for "orchestrator pointing at its own session").
        if [ -n "$self" ] && [ "$parent" = "$self" ]; then
            printf 'orchestrator'
            return 0
        fi
        printf 'subagent'
        return 0
    fi

    printf 'unknown'
}

# v11_compute_attribution_key PROJECT TASK_ID FILE LINE ERROR_ID
#
# SHA256 hex digest of '|'.join(args). Deterministic — same args = same key, always.
# Used by wave-review-attribute / swarm-review-attribute (V11.20 Layer 3/4) to dedup
# findings against ~/.agent-metrics/attribution-keys.jsonl before appending to
# ~/.agent-metrics/agent-errors.jsonl.
#
# Empty-arg handling: empty fields ARE preserved as empty segments — "p1||f|10|e1" is a
# valid input and produces a distinct hash from "p1|t1|f|10|e1". Callers MUST normalize
# missing values consistently (use empty string "", not "null" or "None") to avoid
# accidentally producing two keys for the same logical finding.
#
# Stdout: 64-char lowercase hex string.
v11_compute_attribution_key() {
    local project="${1:-}"
    local task_id="${2:-}"
    local file="${3:-}"
    local line="${4:-}"
    local error_id="${5:-}"
    # awk's `print` always adds \n; use `printf` to keep stdout to exactly 64 hex chars.
    # `|| true` guards the parent hook from being killed by `set -eo pipefail` if
    # sha256sum is missing or fails — callers detect failure via empty stdout.
    {
        printf '%s|%s|%s|%s|%s' "$project" "$task_id" "$file" "$line" "$error_id" \
            | sha256sum \
            | awk '{printf "%s", $1}'
    } || true
}

# v11_canonical_actor RAW   (v11.44 — orchestrator-quality)
#
# Read-side actor canonicalization. Folds the orchestrator identity family
# (orchestrator / orchestrator-self / orchestrator-direct / team-orchestrator /
# drift-orchestrator / main) -> canonical "orchestrator" so the orchestrator is one
# scoreable actor instead of five free-form spellings. Non-family inputs pass through
# UNCHANGED (non-lossy — real project agents are never forced to "unknown").
#
# SINGLE SOURCE OF TRUTH is hooks/lib/actor-canonical.json, shared with the Python
# reader scripts/lib/actor_canonical.py (agent-scorecard / agent-effectiveness). A
# cross-language identity test asserts bash and Python agree.
#
# Rollback: V11_ORCH_QUALITY=off echoes RAW verbatim (legacy literal-string match).
# A missing/corrupt table degrades to identity (echo RAW) — never breaks a caller.
v11_canonical_actor() {
    local raw="${1:-}"
    if [ "${V11_ORCH_QUALITY:-}" = "off" ]; then
        printf '%s' "$raw"
        return 0
    fi
    local table="${V11_ACTOR_CANONICAL_TABLE:-$V11_HOME/hooks/lib/actor-canonical.json}"
    local mapped=""
    if [ -f "$table" ]; then
        mapped=$(jq -r --arg a "$raw" '.fold[$a] // empty' "$table" 2>/dev/null || true)
    fi
    if [ -n "$mapped" ]; then
        printf '%s' "$mapped"
    else
        printf '%s' "$raw"
    fi
}

# v11_brief_attribution_key PROJECT SUBJECT_NORM CREATE_SEQ   (v11.44)
#
# SHA256 hex of 'project|subject_norm|create_seq|brief' — the idempotency key for
# brief-layer findings written by scripts/grade-briefs. Uses CANONICAL identity
# (project, subject_norm, create_seq) NOT task_id, which is session-local/ephemeral
# (CLAUDE.md §4). Same brief across sessions/rehydrates => same key => no duplicate.
# Mirrors v11_compute_attribution_key's guard semantics (empty stdout on failure).
v11_brief_attribution_key() {
    local project="${1:-}"
    local subject_norm="${2:-}"
    local create_seq="${3:-}"
    {
        printf '%s|%s|%s|%s' "$project" "$subject_norm" "$create_seq" "brief" \
            | sha256sum \
            | awk '{printf "%s", $1}'
    } || true
}

# v11_resolve_file_to_task PROJECT FILE
#
# Scan PROJECT's aggregate task-state JSON for the most-recent task whose
# task_artifacts[task_id].files_changed includes FILE. Returns the task_id on stdout,
# empty if no match. Uses TASK_STATE_DIR / HERCULES_ROOT / V11_HOME from the
# sourcing hook; all have built-in fallback defaults, so the function works
# standalone. Internal V11_RFT_* env vars are set-and-consumed inline.
#
# Tie-breaker order:
#   1. Highest completed_at (from recent_completed[].at lookup by id)
#   2. Highest task_id (numeric; falls back to lexicographic for non-numeric ids)
#
# FILE matching:
#   - Tries exact match first
#   - Then tries with V11_HOME stripped (handles relative paths like "hooks/lib/common.sh")
#   - Then tries with HERCULES_ROOT stripped
#   - Final fallback: basename match (least precise; documented in unattributed reason)
#
# Empty stdout (no match) is a contract: callers route to unattributed-findings.jsonl.
v11_resolve_file_to_task() {
    local project="${1:-}"
    local file="${2:-}"
    if [ -z "$project" ] || [ -z "$file" ]; then
        return 0
    fi

    # $TASK_STATE_DIR is set by common.sh init (line ~9) when sourced from a hook,
    # but a novel consumer (standalone script, sourced indirectly) may have it unset.
    # The `:-` fallback derives it the same way common.sh does, so the function is
    # safe under `set -u` regardless of init order.
    local tsdir="${TASK_STATE_DIR:-${HERCULES_ROOT:-$HOME}/.agent-metrics/task-state}"
    local state_file="$tsdir/${project}.json"
    if [ ! -f "$state_file" ]; then
        return 0
    fi

    V11_RFT_PROJECT="$project" V11_RFT_FILE="$file" V11_RFT_STATE="$state_file" \
    V11_RFT_HERCULES_ROOT="${HERCULES_ROOT:-$HOME}" \
    V11_RFT_V11_HOME="${V11_HOME:-$HOME/v11}" \
    python3 - <<'PYEOF' 2>/dev/null || true
import os, json, re

state_path = os.environ.get("V11_RFT_STATE", "")
target_file = os.environ.get("V11_RFT_FILE", "")
hercules_root = os.environ.get("V11_RFT_HERCULES_ROOT", "$HOME").rstrip("/")
v11_home = os.environ.get("V11_RFT_V11_HOME", "$HOME/v11").rstrip("/")

try:
    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)
except Exception:
    raise SystemExit(0)

artifacts = state.get("task_artifacts") or {}
if not artifacts:
    raise SystemExit(0)

# Build set of candidate file representations to match against task artifact entries.
# A finding's `file` might come in as absolute, repo-relative, or basename-only.
candidates = {target_file}
abs_form = target_file
if target_file.startswith("/"):
    # absolute → also add v11-relative and hercules-relative forms
    if target_file.startswith(v11_home + "/"):
        candidates.add(target_file[len(v11_home)+1:])
    if target_file.startswith(hercules_root + "/"):
        candidates.add(target_file[len(hercules_root)+1:])
else:
    # relative → also add absolute forms
    candidates.add(f"{v11_home}/{target_file}")
    candidates.add(f"{hercules_root}/{target_file}")
basename = os.path.basename(target_file) if "/" in target_file else target_file

# completed_at lookup table from recent_completed[]
completed_at = {}
for rec in state.get("recent_completed") or []:
    # Legacy fleet data may contain non-dict entries (observed: bare strings).
    if not isinstance(rec, dict):
        continue
    tid = str(rec.get("id", ""))
    if tid:
        completed_at[tid] = rec.get("at", "")

# Find matching tasks. Track match_quality: 2=exact (any candidate), 1=basename, 0=skip.
matches = []  # list of (match_quality, completed_at, task_id_numeric, task_id_str)
for tid_raw, art in artifacts.items():
    if not isinstance(art, dict):
        continue
    files = art.get("files_changed") or []
    if not isinstance(files, list):
        continue
    quality = 0
    for f in files:
        if not isinstance(f, str):
            continue
        if f in candidates:
            quality = max(quality, 2)
            break
        if os.path.basename(f) == basename:
            quality = max(quality, 1)
    if quality == 0:
        continue
    tid_str = str(tid_raw)
    try:
        tid_num = int(tid_str)
    except Exception:
        tid_num = -1  # non-numeric ids sort last by numeric
    at = completed_at.get(tid_str, "")
    matches.append((quality, at, tid_num, tid_str))

if not matches:
    raise SystemExit(0)

# Sort: highest match_quality first, then highest completed_at, then highest task_id_num,
# then lex task_id_str as a final tiebreaker for determinism.
matches.sort(key=lambda m: (m[0], m[1], m[2], m[3]), reverse=True)
print(matches[0][3], end="")
PYEOF
}

# --- Lane lease (V11.29) ---
# Per-project task-execution lease so two concurrent orchestrator sessions
# can't both execute the same task. Clones the review-queue claim machinery
# (v11_review_queue_claim/_gc/_classify, ~:3372/3456/3577): flock-guarded
# append-only JSONL, replay-latest-wins, steal only from not-live holders via
# v11_session_is_live, idempotent claims. Uses its own flock fd (209 — fds
# 207/208 are already used by other guarded sections in this file) and its
# own storage directory ($METRICS_DIR/lanes/) so lane leases and review-queue
# claims never contend on the same lock.
#
# Schema (one JSONL line per event, append-only):
#   {"v":1,"ev":"claim"|"release","ts":ISO8601,"task_id":T,"session_uuid":U}
# Replay semantics: scan file, fold by task_id, latest event wins.
# Held = task_id whose latest event has ev=="claim".
#
# Rollback: V11_LANE_LEASE=off -> every function below is a no-op success
# (v11_lane_claim echoes "claimed" so callers proceed unblocked).

# v11_lane_path PROJECT TYPE
#   TYPE in {jsonl, lock}. Validates project name (SEC-C-02 whitelist).
v11_lane_path() {
    local project="$1" type="$2"
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "v11_lane_path: invalid project name '$project' (SEC-C-02)" >&2
        return 1
    fi
    local lane_dir="${METRICS_DIR}/lanes"
    case "$type" in
        jsonl) printf '%s' "${lane_dir}/${project}.jsonl" ;;
        lock)  printf '%s' "${lane_dir}/${project}.jsonl.lock" ;;
        *)
            echo "v11_lane_path: unknown type '$type' (must be jsonl|lock)" >&2
            return 1
            ;;
    esac
}

# v11_lane_claim PROJECT TASK_ID [CLAIMANT_SESSION_UUID]
#   Attempts to claim the execution lane for TASK_ID under PROJECT for
#   CLAIMANT_SESSION_UUID (defaults to v11_session_uuid). Append-only: writes
#   a fresh "claim" event (same task_id) -- replay-latest-wins means this
#   event supersedes any prior claim/release state without mutating history.
#   Idempotent: re-claiming by the same session succeeds ("already_mine").
#   A lane held (latest event == claim) by a DIFFERENT still-live session is
#   refused ("owned_by_other:<uuid>"). A lane held by a session that is no
#   longer live is stolen (claimed).
#   Echoes one of: claimed | already_mine | owned_by_other:<uuid> | absent
v11_lane_claim() {
    local project="$1" task_id="$2" claimant="${3:-$(v11_session_uuid)}"
    if [ "${V11_LANE_LEASE:-on}" = "off" ]; then
        echo "claimed"; return 0
    fi
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "absent"; return 0
    fi
    if [ -z "$task_id" ] || [ -z "$claimant" ]; then
        echo "absent"; return 0
    fi
    local jsonl_file lock_file
    jsonl_file=$(v11_lane_path "$project" jsonl 2>/dev/null) || { echo "absent"; return 0; }
    lock_file=$(v11_lane_path "$project" lock 2>/dev/null) || { echo "absent"; return 0; }
    mkdir -p "$(dirname "$jsonl_file")" 2>/dev/null

    (
        exec 209>"$lock_file"
        flock -w 5 209 || { echo "absent"; exit 0; }

        local latest_ev latest_who
        if [ -s "$jsonl_file" ]; then
            local latest_json
            latest_json=$(V11_LN_FILE="$jsonl_file" V11_LN_TASK="$task_id" python3 - <<'PYEOF' 2>/dev/null
import os, json
path = os.environ.get("V11_LN_FILE", "")
target = os.environ.get("V11_LN_TASK", "")
latest = None
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if str(ev.get("task_id", "")) == target:
                latest = ev
except Exception:
    pass
print(json.dumps(latest) if latest is not None else "null")
PYEOF
)
            if [ -n "$latest_json" ] && [ "$latest_json" != "null" ]; then
                latest_ev=$(printf '%s' "$latest_json" | jq -r '.ev // ""' 2>/dev/null)
                latest_who=$(printf '%s' "$latest_json" | jq -r '.session_uuid // ""' 2>/dev/null)
            fi
        fi

        if [ "$latest_ev" = "claim" ]; then
            if [ "$latest_who" = "$claimant" ]; then
                echo "already_mine"
                exit 0
            fi
            if [ -n "$latest_who" ] && v11_session_is_live "$latest_who"; then
                echo "owned_by_other:$latest_who"
                exit 0
            fi
        fi

        local now new_line
        now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
        new_line=$(jq -cn --arg tid "$task_id" --arg su "$claimant" --arg ts "$now" \
            '{v:1, ev:"claim", ts:$ts, task_id:$tid, session_uuid:$su}' 2>/dev/null)
        if [ -z "$new_line" ]; then
            echo "absent"
            exit 0
        fi
        printf '%s\n' "$new_line" >> "$jsonl_file"
        echo "claimed"
    )
    return 0
}

# v11_lane_release PROJECT TASK_ID [CLAIMANT_SESSION_UUID]
#   Appends a "release" event for TASK_ID if the lane is currently held
#   (latest event == claim) by CLAIMANT_SESSION_UUID (defaults to
#   v11_session_uuid). Idempotent: releasing an already-released or
#   never-claimed lane, or a lane held by a DIFFERENT session, is a no-op
#   success (does not steal/clear another session's claim).
#   Echoes one of: released | not_held | absent
v11_lane_release() {
    local project="$1" task_id="$2" claimant="${3:-$(v11_session_uuid)}"
    if [ "${V11_LANE_LEASE:-on}" = "off" ]; then
        echo "released"; return 0
    fi
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "absent"; return 0
    fi
    if [ -z "$task_id" ] || [ -z "$claimant" ]; then
        echo "absent"; return 0
    fi
    local jsonl_file lock_file
    jsonl_file=$(v11_lane_path "$project" jsonl 2>/dev/null) || { echo "absent"; return 0; }
    lock_file=$(v11_lane_path "$project" lock 2>/dev/null) || { echo "absent"; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        echo "not_held"; return 0
    fi

    (
        exec 209>"$lock_file"
        flock -w 5 209 || { echo "absent"; exit 0; }

        local latest_json latest_ev latest_who
        latest_json=$(V11_LN_FILE="$jsonl_file" V11_LN_TASK="$task_id" python3 - <<'PYEOF' 2>/dev/null
import os, json
path = os.environ.get("V11_LN_FILE", "")
target = os.environ.get("V11_LN_TASK", "")
latest = None
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if str(ev.get("task_id", "")) == target:
                latest = ev
except Exception:
    pass
print(json.dumps(latest) if latest is not None else "null")
PYEOF
)
        if [ -z "$latest_json" ] || [ "$latest_json" = "null" ]; then
            echo "not_held"
            exit 0
        fi
        latest_ev=$(printf '%s' "$latest_json" | jq -r '.ev // ""' 2>/dev/null)
        latest_who=$(printf '%s' "$latest_json" | jq -r '.session_uuid // ""' 2>/dev/null)

        if [ "$latest_ev" != "claim" ] || [ "$latest_who" != "$claimant" ]; then
            echo "not_held"
            exit 0
        fi

        local now new_line
        now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
        new_line=$(jq -cn --arg tid "$task_id" --arg su "$claimant" --arg ts "$now" \
            '{v:1, ev:"release", ts:$ts, task_id:$tid, session_uuid:$su}' 2>/dev/null)
        if [ -z "$new_line" ]; then
            echo "absent"
            exit 0
        fi
        printf '%s\n' "$new_line" >> "$jsonl_file"
        echo "released"
    )
    return 0
}

# v11_lane_force_release PROJECT TASK_ID [ACTOR_SESSION_UUID]
#   Used by `scripts/lanes release --force`. Unconditionally releases the
#   lane for TASK_ID regardless of which session currently holds it (unlike
#   v11_lane_release, which only clears the CLAIMANT's own claim). Appends a
#   "release" event tagged force:true carrying the dispossessed holder's
#   session_uuid, so the caller can print a warning naming who got bumped.
#   No-op if the lane isn't currently held.
#   Echoes one of: released:<dispossessed_session_uuid> | not_held | absent
v11_lane_force_release() {
    local project="$1" task_id="$2" actor="${3:-$(v11_session_uuid)}"
    if [ "${V11_LANE_LEASE:-on}" = "off" ]; then
        echo "not_held"; return 0
    fi
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        echo "absent"; return 0
    fi
    if [ -z "$task_id" ]; then
        echo "absent"; return 0
    fi
    local jsonl_file lock_file
    jsonl_file=$(v11_lane_path "$project" jsonl 2>/dev/null) || { echo "absent"; return 0; }
    lock_file=$(v11_lane_path "$project" lock 2>/dev/null) || { echo "absent"; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        echo "not_held"; return 0
    fi

    (
        exec 209>"$lock_file"
        flock -w 5 209 || { echo "absent"; exit 0; }

        local latest_json latest_ev latest_who
        latest_json=$(V11_LN_FILE="$jsonl_file" V11_LN_TASK="$task_id" python3 - <<'PYEOF' 2>/dev/null
import os, json
path = os.environ.get("V11_LN_FILE", "")
target = os.environ.get("V11_LN_TASK", "")
latest = None
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if str(ev.get("task_id", "")) == target:
                latest = ev
except Exception:
    pass
print(json.dumps(latest) if latest is not None else "null")
PYEOF
)
        if [ -z "$latest_json" ] || [ "$latest_json" = "null" ]; then
            echo "not_held"
            exit 0
        fi
        latest_ev=$(printf '%s' "$latest_json" | jq -r '.ev // ""' 2>/dev/null)
        latest_who=$(printf '%s' "$latest_json" | jq -r '.session_uuid // ""' 2>/dev/null)

        if [ "$latest_ev" != "claim" ]; then
            echo "not_held"
            exit 0
        fi

        local now new_line
        now="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
        new_line=$(jq -cn --arg tid "$task_id" --arg su "$actor" --arg ts "$now" --arg disp "$latest_who" \
            '{v:1, ev:"release", ts:$ts, task_id:$tid, session_uuid:$su, force:true, dispossessed:$disp}' 2>/dev/null)
        if [ -z "$new_line" ]; then
            echo "absent"
            exit 0
        fi
        printf '%s\n' "$new_line" >> "$jsonl_file"
        echo "released:${latest_who}"
    )
    return 0
}

# v11_lane_gc PROJECT [MAX_AGE_MINUTES]
#   Releases lanes whose latest event is "claim", whose holder session is
#   NOT live (v11_session_is_live), AND whose claim is older than
#   MAX_AGE_MINUTES (default: V11_LANE_GC_STALE_MINUTES, 30 -- same
#   derivation as v11_review_queue_gc). A live holder's claim is NEVER
#   released by age alone (mirrors the review-queue GC fix for slow-running
#   live sessions).
#   Emits JSON: {"project":P,"released":N,"checked":M}
v11_lane_gc() {
    local project="$1"
    local max_age_min="${2:-${V11_LANE_GC_STALE_MINUTES:-30}}"
    if [ "${V11_LANE_LEASE:-on}" = "off" ]; then
        printf '{"project":"%s","released":0,"checked":0}' "$project"
        return 0
    fi
    if [ -z "$project" ] || ! printf '%s' "$project" | grep -qE '^[a-zA-Z0-9._-]{1,64}$'; then
        printf '{"project":"","released":0,"checked":0}'
        return 0
    fi
    local jsonl_file lock_file
    jsonl_file=$(v11_lane_path "$project" jsonl 2>/dev/null) || jsonl_file=""
    lock_file=$(v11_lane_path "$project" lock 2>/dev/null) || lock_file=""
    if [ -z "$jsonl_file" ] || [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        printf '{"project":"%s","released":0,"checked":0}' "$project"
        return 0
    fi

    # Build the set of currently-live holder session_uuids so age alone never
    # releases a live session's claim (same rule as v11_review_queue_gc's
    # live_claimants set).
    local live_holders=""
    if command -v jq >/dev/null 2>&1; then
        local _candidate
        for _candidate in $(jq -r 'select(.ev=="claim") | .session_uuid // empty' "$jsonl_file" 2>/dev/null | sort -u); do
            if v11_session_is_live "$_candidate"; then
                live_holders="$live_holders $_candidate"
            fi
        done
    fi

    local gc_out
    gc_out=$(
        exec 209>"$lock_file"
        flock -w 5 209 || { printf '{"released":0,"checked":0}'; exit 0; }
        V11_LN_FILE="$jsonl_file" V11_LN_MAXAGE="$max_age_min" V11_LN_LIVE_HOLDERS="$live_holders" python3 - <<'PYEOF'
import os, json
from datetime import datetime, timezone

path = os.environ.get("V11_LN_FILE", "")
max_age = float(os.environ.get("V11_LN_MAXAGE", "30"))
live_holders = set(os.environ.get("V11_LN_LIVE_HOLDERS", "").split())

latest = {}
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            tid = str(ev.get("task_id", ""))
            if not tid:
                continue
            latest[tid] = ev
except Exception:
    print(json.dumps({"released": 0, "checked": 0}))
    raise SystemExit(0)

now = datetime.now(timezone.utc).timestamp()
to_release = []
checked = 0
for ev in latest.values():
    if ev.get("ev") != "claim":
        continue
    who = ev.get("session_uuid") or ""
    if not who:
        continue
    checked += 1
    if who in live_holders:
        # Holder session still live -- age alone does not mean the claim is
        # stale; never release a live session's lane out from under it.
        continue
    ts_raw = ev.get("ts") or ""
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        continue
    age_min = (now - ts) / 60.0
    if age_min > max_age:
        to_release.append(ev)

out_lines = []
for ev in to_release:
    new_ev = {
        "v": 1,
        "ev": "release",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "task_id": ev.get("task_id"),
        "session_uuid": ev.get("session_uuid"),
        "gc_released": True,
    }
    out_lines.append(json.dumps(new_ev, separators=(",", ":")))

if out_lines:
    with open(path, "a", encoding="utf-8") as f:
        for line in out_lines:
            f.write(line + "\n")

print(json.dumps({"released": len(to_release), "checked": checked}))
PYEOF
    )
    printf '%s' "$gc_out" | jq -c --arg p "$project" '. + {project:$p}' 2>/dev/null \
        || printf '{"project":"%s","released":0,"checked":0}' "$project"
    return 0
}

# v11_lane_status PROJECT
#   Emits a JSON array of currently-held lanes (latest event per task_id ==
#   "claim"): [{task_id, session_uuid, claimed_at, live(bool)}, ...].
#   Gated by V11_LANE_LEASE=off -> always "[]".
v11_lane_status() {
    local project="$1"
    if [ "${V11_LANE_LEASE:-on}" = "off" ]; then
        printf '[]'
        return 0
    fi
    local jsonl_file
    jsonl_file=$(v11_lane_path "$project" jsonl 2>/dev/null) || { printf '[]'; return 0; }
    if [ ! -f "$jsonl_file" ] || [ ! -s "$jsonl_file" ]; then
        printf '[]'
        return 0
    fi

    local held_min
    held_min=$(V11_LN_FILE="$jsonl_file" python3 - <<'PYEOF' 2>/dev/null
import os, json
path = os.environ.get("V11_LN_FILE", "")
latest = {}
try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            tid = str(ev.get("task_id", ""))
            if not tid:
                continue
            latest[tid] = ev
except Exception:
    print("[]")
    raise SystemExit(0)
out = []
for tid, ev in latest.items():
    if ev.get("ev") != "claim":
        continue
    out.append({
        "task_id": tid,
        "session_uuid": ev.get("session_uuid") or "",
        "claimed_at": ev.get("ts") or "",
    })
print(json.dumps(out, separators=(",", ":")))
PYEOF
)
    [ -z "$held_min" ] && held_min="[]"

    local sessions_seen live_map="{}" s
    sessions_seen=$(printf '%s' "$held_min" | jq -r '.[].session_uuid' 2>/dev/null | sort -u | grep -v '^$' || true)
    while IFS= read -r s; do
        [ -z "$s" ] && continue
        if v11_session_is_live "$s"; then
            live_map=$(printf '%s' "$live_map" | jq --arg s "$s" '.[$s]=true' 2>/dev/null || echo "$live_map")
        fi
    done <<< "$sessions_seen"

    printf '%s' "$held_min" | jq -c --argjson live "$live_map" '
        map(. + {live: (($live[.session_uuid] // false))})
    ' 2>/dev/null || printf '[]'
}

# Backward-compatibility aliases (V10 → V11)
v10_parse_input() { v11_parse_input "$@"; }
v10_detect_project() { v11_detect_project "$@"; }
v10_risk_level() { v11_risk_level "$@"; }
v10_check_risk() { v11_check_risk "$@"; }
v10_check_autonomy() { v11_check_autonomy "$@"; }
v10_check_file_ownership() { v11_check_file_ownership "$@"; }
v10_is_metadata_file() { v11_is_metadata_file "$@"; }
v10_resolve_tool_policy() { v11_resolve_tool_policy "$@"; }
