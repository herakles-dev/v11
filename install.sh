#!/usr/bin/env bash
# V11 Protocol — Installer
#
# Installs the V11 governance/discipline layer (task-as-truth, write gates,
# autonomy tracking, handoff, adversarial review loop, plus the OPTIONAL
# extras this distribution ships) into a target project.
#
# Usage:
#   ./install.sh [TARGET_PROJECT_DIR]
#
#   TARGET_PROJECT_DIR defaults to the current working directory.
#
# What it does (idempotent — safe to re-run):
#   1. Copies the framework payload (hooks/, schemas/, scripts/, agents/,
#      playbooks/, templates/, formations/, patterns/, mcp-tools/, docs/)
#      into TARGET_PROJECT_DIR/.v11/ — a self-contained copy, no dependency
#      on this distribution directory after install.
#   2. Merges (never clobbers) the V11 hook registrations into
#      TARGET_PROJECT_DIR/.claude/settings.json.
#   3. Bootstraps session-tracking state (active-project pointer, per-project
#      session dir, .autonomy-state, per-session task-state) via the
#      installed scripts/v11-bootstrap-session, and seeds a spec.md from the
#      shipped template.
#   4. Prints a summary + next steps.
#
# Session/task state defaults to $HOME/.v11 (override with V11_WORKSPACE_ROOT).
# See README.md for the full architecture explanation.

set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Resolve paths
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ARG="${1:-$PWD}"

if [ ! -d "$TARGET_ARG" ]; then
    echo "ERROR: target directory does not exist: $TARGET_ARG" >&2
    exit 1
fi

TARGET="$(cd "$TARGET_ARG" && pwd)"
PROJECT_NAME="$(basename "$TARGET")"

# Same whitelist common.sh uses for project ids (path-traversal / injection guard).
if ! [[ "$PROJECT_NAME" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo "ERROR: target directory name '$PROJECT_NAME' is not a valid V11 project id." >&2
    echo "       Project ids must match [a-zA-Z0-9._-]+ — rename the directory or" >&2
    echo "       install into a differently-named path." >&2
    exit 1
fi

V11_INSTALL_DIR="$TARGET/.v11"
CLAUDE_DIR="$TARGET/.claude"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

echo "==> V11 install"
echo "    source:      $SCRIPT_DIR"
echo "    target:      $TARGET"
echo "    project id:  $PROJECT_NAME"
echo ""

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

MISSING_DEPS=()
for dep in jq bash date mkdir; do
    command -v "$dep" >/dev/null 2>&1 || MISSING_DEPS+=("$dep")
done
if [ "${#MISSING_DEPS[@]}" -gt 0 ]; then
    echo "ERROR: missing required tool(s): ${MISSING_DEPS[*]}" >&2
    echo "       V11's hooks/scripts are bash+jq. Install them and re-run." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Copy framework payload into TARGET/.v11/ (idempotent overwrite-in-place)
# ---------------------------------------------------------------------------

PAYLOAD_DIRS="hooks schemas scripts agents playbooks templates formations patterns mcp-tools docs"

mkdir -p "$V11_INSTALL_DIR"
for d in $PAYLOAD_DIRS; do
    if [ ! -d "$SCRIPT_DIR/$d" ]; then
        echo "ERROR: expected payload dir missing from distribution: $SCRIPT_DIR/$d" >&2
        exit 1
    fi
    mkdir -p "$V11_INSTALL_DIR/$d"
    cp -a "$SCRIPT_DIR/$d/." "$V11_INSTALL_DIR/$d/"
done

# Re-assert executable bits (cp -a preserves them, but be defensive — a zip/tar
# re-extraction upstream of this script may not preserve modes).
find "$V11_INSTALL_DIR/hooks" -maxdepth 1 -type f -exec chmod +x {} \;
find "$V11_INSTALL_DIR/hooks/lib" -maxdepth 1 -type f -name '*.sh' -exec chmod +x {} \;
find "$V11_INSTALL_DIR/hooks/git-hooks" -maxdepth 1 -type f -exec chmod +x {} \;
find "$V11_INSTALL_DIR/scripts" -maxdepth 1 -type f -exec chmod +x {} \;

echo "[1/4] Framework payload installed -> $V11_INSTALL_DIR"
echo "      ($(find "$V11_INSTALL_DIR" -type f | wc -l | tr -d ' ') files)"

# Convenience symlinks at project root, matching the documented V11 project
# layout (hooks/ and schemas/ visible at top level). Never clobber a real
# file/dir that isn't already the expected symlink.
for link in hooks schemas; do
    target_rel=".v11/$link"
    if [ -L "$TARGET/$link" ]; then
        : # already a symlink — leave whatever it points at alone (idempotent)
    elif [ -e "$TARGET/$link" ]; then
        echo "      [!] $TARGET/$link already exists and is not a symlink — leaving it alone"
    else
        ln -s "$target_rel" "$TARGET/$link"
    fi
done

# ---------------------------------------------------------------------------
# 2. Merge hook registrations into .claude/settings.json (never clobber)
# ---------------------------------------------------------------------------

mkdir -p "$CLAUDE_DIR"

H="$V11_INSTALL_DIR/hooks"

# (event, matcher, command) triples for every hook this distribution ships.
# matcher == "" means "no matcher key" (PostCompact/Stop fire unconditionally).
# NOTE: fix-team-model / guard-teammate-timeout / enforce-subagent are NOT
# wired here — they are excluded from this distribution (see MANIFEST.md:
# dead code / documented-broken / superseded).
ADDITIONS_JSON=$(jq -nc \
  --arg detect_project      "$H/detect-project" \
  --arg guard_write_gates   "$H/guard-write-gates" \
  --arg guard_enforcement   "$H/guard-enforcement" \
  --arg enforce_test_cov    "$H/enforce-test-coverage" \
  --arg require_producer    "$H/require-producer-script" \
  --arg guard_validation    "$H/guard-validation-lint" \
  --arg guard_effort        "$H/guard-effort" \
  --arg verify_syntax       "$H/verify-syntax" \
  --arg track_autonomy      "$H/track-autonomy" \
  --arg completion_hint     "$H/completion-hint" \
  --arg sync_tasks          "$H/sync-tasks" \
  --arg guard_agent_stall   "$H/guard-agent-stall" \
  --arg guard_stale_task    "$H/guard-stale-task" \
  --arg track_agents        "$H/track-agents" \
  --arg post_compact        "$H/post-compact" \
  --arg session_end         "$H/session-end" \
  '[
    {event:"PreToolUse",  matcher:"Read",       command:$detect_project},
    {event:"PreToolUse",  matcher:"Write|Edit", command:$guard_write_gates},
    {event:"PreToolUse",  matcher:"Write|Edit", command:$guard_enforcement},
    {event:"PreToolUse",  matcher:"Bash",       command:$guard_enforcement},
    {event:"PreToolUse",  matcher:"Bash",       command:$enforce_test_cov},
    {event:"PreToolUse",  matcher:"Bash",       command:$require_producer},
    {event:"PreToolUse",  matcher:"Bash",       command:$guard_validation},
    {event:"PreToolUse",  matcher:"Task|Agent", command:$guard_effort},
    {event:"PostToolUse", matcher:"Write|Edit", command:$verify_syntax},
    {event:"PostToolUse", matcher:"Write|Edit", command:$track_autonomy},
    {event:"PostToolUse", matcher:"Write|Edit", command:$completion_hint},
    {event:"PostToolUse", matcher:"Bash",       command:$track_autonomy},
    {event:"PostToolUse", matcher:"TaskCreate|TaskUpdate|TaskList|TaskGet", command:$sync_tasks},
    {event:"PostToolUse", matcher:"TaskList",   command:$guard_agent_stall},
    {event:"PostToolUse", matcher:"TaskList",   command:$guard_stale_task},
    {event:"PostToolUse", matcher:"Task|Agent", command:$track_agents},
    {event:"PostCompact", matcher:"",           command:$post_compact},
    {event:"Stop",        matcher:"",           command:$session_end}
  ]')

MERGE_JQ='
def add_entry(add):
  (add.event) as $ev
  | (if add.matcher == "" then null else add.matcher end) as $mt
  | (add.command) as $cmd
  | .hooks[$ev] = (
      (.hooks[$ev] // []) as $arr
      | if any($arr[]?; ((.matcher // null) == $mt) and ((.hooks // []) | any(.command == $cmd)))
        then $arr
        else
          if any($arr[]?; (.matcher // null) == $mt)
          then ($arr | map(
                 if (.matcher // null) == $mt
                 then (.hooks = ((.hooks // []) + [{type:"command", command:$cmd}]))
                 else .
                 end))
          else ($arr + [
                 (if $mt == null
                  then {hooks:[{type:"command", command:$cmd}]}
                  else {matcher:$mt, hooks:[{type:"command", command:$cmd}]}
                  end)
               ])
          end
        end
    );
.["$schema"] //= "https://json.schemastore.org/claude-code-settings.json"
| .hooks //= {}
| reduce $additions[] as $a (.; add_entry($a))
| .env //= {}
| .env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS //= "1"
'

if [ -f "$SETTINGS_FILE" ]; then
    if ! jq empty "$SETTINGS_FILE" 2>/dev/null; then
        echo "ERROR: existing $SETTINGS_FILE is not valid JSON — refusing to merge into it." >&2
        echo "       Fix or remove it, then re-run." >&2
        exit 1
    fi
    BASE_JSON="$(cat "$SETTINGS_FILE")"
else
    BASE_JSON='{}'
fi

TMP_SETTINGS="$(mktemp)"
trap 'rm -f "$TMP_SETTINGS"' EXIT

printf '%s' "$BASE_JSON" | jq --argjson additions "$ADDITIONS_JSON" "$MERGE_JQ" > "$TMP_SETTINGS"
mv "$TMP_SETTINGS" "$SETTINGS_FILE"
trap - EXIT

echo "[2/4] Hook registrations merged -> $SETTINGS_FILE"

# ---------------------------------------------------------------------------
# 3. Bootstrap session scaffolding
# ---------------------------------------------------------------------------

# V11_WORKSPACE_ROOT / SESSIONS_ROOT default to $HOME/.v11 (see hooks/lib/common.sh);
# override V11_WORKSPACE_ROOT in your shell if you want session state to live
# somewhere else. This is deliberately a per-user central location shared
# across every V11 project you install (mirrors the upstream architecture),
# NOT a directory inside TARGET.
"$V11_INSTALL_DIR/scripts/v11-bootstrap-session" "$PROJECT_NAME"

_V11_WORKSPACE_ROOT="${V11_WORKSPACE_ROOT:-$HOME/.v11}"
_SESSIONS_ROOT="${SESSIONS_ROOT:-$_V11_WORKSPACE_ROOT/sessions}"
SESSION_DIR="$_SESSIONS_ROOT/$PROJECT_NAME"

# Seed spec.md from the shipped template if the session doesn't have one yet.
if [ ! -f "$SESSION_DIR/spec.md" ]; then
    sed \
      -e "s/\${PROJECT_NAME}/$PROJECT_NAME/g" \
      -e "s/\${DATE}/$(date -I)/g" \
      "$V11_INSTALL_DIR/templates/spec.md.template" > "$SESSION_DIR/spec.md"
    echo "      [+] seeded $SESSION_DIR/spec.md from template (fill in the placeholders)"
fi

# schemas/ symlink inside the session dir, matching the documented layout.
if [ ! -e "$SESSION_DIR/schemas" ]; then
    ln -s "$V11_INSTALL_DIR/schemas" "$SESSION_DIR/schemas"
fi

# Convenience: sessions/<project> -> the real (possibly out-of-tree) session dir.
mkdir -p "$TARGET/sessions"
if [ -L "$TARGET/sessions/$PROJECT_NAME" ]; then
    :
elif [ -e "$TARGET/sessions/$PROJECT_NAME" ]; then
    echo "      [!] $TARGET/sessions/$PROJECT_NAME already exists and is not a symlink — leaving it alone"
else
    ln -s "$SESSION_DIR" "$TARGET/sessions/$PROJECT_NAME"
fi

echo "[3/4] Session scaffolding ready -> $SESSION_DIR"

# ---------------------------------------------------------------------------
# 4. Summary
# ---------------------------------------------------------------------------

echo "[4/4] Done."
echo ""
echo "============================================================"
echo " V11 installed for project: $PROJECT_NAME"
echo "============================================================"
echo ""
echo "  Framework payload : $V11_INSTALL_DIR"
echo "  Hook registrations: $SETTINGS_FILE"
echo "  Session state     : $SESSION_DIR"
echo "  Session shortcut  : $TARGET/sessions/$PROJECT_NAME"
echo ""
echo "Next steps:"
echo "  1. Restart (or start) Claude Code inside $TARGET"
echo "     — settings.json is read once at session boot, so hooks in an"
echo "       ALREADY-RUNNING session won't pick this up."
echo "  2. Fill in $SESSION_DIR/spec.md (intent, stack, constraints)."
echo "  3. Inside the session, run TaskList, then TaskCreate to start the"
echo "     task-as-truth loop. guard-write-gates will now block Write/Edit"
echo "     without an in-progress task."
echo "  4. Read README.md in this distribution for the CORE-vs-OPTIONAL"
echo "     tiering and a one-line-per-hook index."
echo ""
echo "Re-run this installer any time — it only adds what's missing and"
echo "never duplicates or clobbers existing hook entries or session state."
