#!/bin/bash
# Chicago Time Utility — provides inject_chicago_time function
# Called by detect-project hook to cache Chicago time in session-time.json
# Uses local TZ conversion only (no external HTTP calls)

METRICS_DIR="${METRICS_DIR:-$HOME/.agent-metrics}"
SESSION_TIME_FILE="$METRICS_DIR/session-time.json"

inject_chicago_time() {
  # Only refresh if file missing or >30 minutes old
  if [ -f "$SESSION_TIME_FILE" ]; then
    local age=$(( $(date +%s) - $(stat -c %Y "$SESSION_TIME_FILE" 2>/dev/null || echo 0) ))
    [ "$age" -lt 1800 ] && return 0
  fi

  mkdir -p "$METRICS_DIR"

  local chicago_dt chicago_date chicago_time_str dow
  chicago_dt=$(TZ=America/Chicago date '+%Y-%m-%dT%H:%M:%S')
  chicago_date=$(TZ=America/Chicago date '+%Y-%m-%d')
  chicago_time_str=$(TZ=America/Chicago date '+%H:%M')
  dow=$(TZ=America/Chicago date '+%A')

  jq -n \
    --arg dt "$chicago_dt" \
    --arg d "$chicago_date" \
    --arg t "$chicago_time_str" \
    --arg dow "$dow" \
    '{
      chicago_time: $dt,
      date: $d,
      time: $t,
      day_of_week: $dow,
      timezone: "America/Chicago",
      dst_active: null,
      source: "tz-conversion",
      fetched_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ"))
    }' > "$SESSION_TIME_FILE"
}
