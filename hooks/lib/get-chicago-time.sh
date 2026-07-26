#!/bin/bash
# Business-Timezone Utility — provides inject_chicago_time function
# Called by detect-project hook to cache the business timezone's wall-clock time
# in session-time.json. Uses local TZ conversion only (no external HTTP calls).
#
# OSS dist: two welds parameterized here —
#   1. METRICS_DIR default was hardcoded to the origin deployment's home
#      directory; now derives from $HOME/.v11 to match hooks/lib/common.sh's
#      portable default.
#   2. The business timezone was hardcoded to America/Chicago (the original
#      deployment's timezone); it is now V11_BUSINESS_TZ, overridable per
#      install, defaulting to America/Chicago for behavioral continuity.
# The function/variable names keep the "chicago" name for backward compatibility
# with callers (detect-project) — cosmetic naming only, not a functional weld.

METRICS_DIR="${METRICS_DIR:-$HOME/.v11/.agent-metrics}"
SESSION_TIME_FILE="$METRICS_DIR/session-time.json"
V11_BUSINESS_TZ="${V11_BUSINESS_TZ:-America/Chicago}"

inject_chicago_time() {
  # Only refresh if file missing or >30 minutes old
  if [ -f "$SESSION_TIME_FILE" ]; then
    local age=$(( $(date +%s) - $(stat -c %Y "$SESSION_TIME_FILE" 2>/dev/null || echo 0) ))
    [ "$age" -lt 1800 ] && return 0
  fi

  mkdir -p "$METRICS_DIR"

  local chicago_dt chicago_date chicago_time_str dow
  chicago_dt=$(TZ="$V11_BUSINESS_TZ" date '+%Y-%m-%dT%H:%M:%S')
  chicago_date=$(TZ="$V11_BUSINESS_TZ" date '+%Y-%m-%d')
  chicago_time_str=$(TZ="$V11_BUSINESS_TZ" date '+%H:%M')
  dow=$(TZ="$V11_BUSINESS_TZ" date '+%A')

  jq -n \
    --arg dt "$chicago_dt" \
    --arg d "$chicago_date" \
    --arg t "$chicago_time_str" \
    --arg dow "$dow" \
    --arg tz "$V11_BUSINESS_TZ" \
    '{
      chicago_time: $dt,
      date: $d,
      time: $t,
      day_of_week: $dow,
      timezone: $tz,
      dst_active: null,
      source: "tz-conversion",
      fetched_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ"))
    }' > "$SESSION_TIME_FILE"
}
