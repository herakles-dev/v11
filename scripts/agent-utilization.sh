#!/bin/bash
# V11.36 Script: agent-utilization.sh
# Per-agent launch-volume ranker: which of the full agent roster actually got
# used in the last N days, and which sat idle (candidate demotion queue).
#
# Sources:
#   ~/.agent-registry/agents.json   (full roster — .agents is a name-keyed
#                                    object; total_agents in .metadata is NOT
#                                    used here, we always count roster keys)
#   ~/.agent-metrics/usage.jsonl    (per-launch events; historically a mix of
#                                    compact single-line and legacy pretty-
#                                    printed multi-line records — jq -s
#                                    normalizes both transparently)
#
# Usage:
#   agent-utilization.sh                    # last 30 days, Used table first
#   agent-utilization.sh --days 7           # last 7 days
#   agent-utilization.sh --sort unused      # Idle table first
#
set -euo pipefail

HERCULES_ROOT="${HERCULES_ROOT:-$HOME}"
METRICS_DIR="${METRICS_DIR:-$HERCULES_ROOT/.agent-metrics}"
REGISTRY_FILE="${REGISTRY_FILE:-$HERCULES_ROOT/.agent-registry/agents.json}"
USAGE_LEDGER="$METRICS_DIR/usage.jsonl"

DAYS=30
SORT="used"

if [ "${1:-}" == "--help" ] || [ "${1:-}" == "-h" ]; then
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --days) DAYS="${2:-30}"; shift ;;
        --sort) SORT="${2:-used}"; shift ;;
        *) echo "agent-utilization: unknown arg '$1'" >&2; exit 2 ;;
    esac
    shift
done

case "$DAYS" in
    ''|*[!0-9]*) echo "agent-utilization: --days must be a positive integer (got: $DAYS)" >&2; exit 2 ;;
esac
if [ "$DAYS" -eq 0 ]; then
    echo "agent-utilization: --days must be a positive integer >= 1 (got: $DAYS)" >&2
    exit 2
fi
case "$SORT" in
    used|unused) ;;
    *) echo "agent-utilization: --sort must be used|unused (got: $SORT)" >&2; exit 2 ;;
esac

if ! command -v jq >/dev/null 2>&1; then
    echo "agent-utilization: jq is required but not found" >&2
    exit 1
fi

if [ ! -f "$REGISTRY_FILE" ]; then
    echo "agent-utilization: agent registry not found at $REGISTRY_FILE — cannot build roster." >&2
    exit 1
fi

if ! ROSTER_JSON=$(jq -c '[.agents | keys[]]' "$REGISTRY_FILE" 2>/dev/null); then
    echo "agent-utilization: failed to parse registry at $REGISTRY_FILE" >&2
    exit 1
fi
ROSTER_COUNT=$(echo "$ROSTER_JSON" | jq 'length')

# Event volume can exceed exec's ARG_MAX when passed as an env var (observed:
# ~290KB payload on a session with a large pre-existing environment tripped
# "Argument list too long"), so hand data to python3 via temp files instead.
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
ROSTER_FILE="$WORKDIR/roster.json"
EVENTS_FILE="$WORKDIR/events.json"
echo "$ROSTER_JSON" > "$ROSTER_FILE"

if [ "$ROSTER_COUNT" -eq 0 ]; then
    echo "agent-utilization: registry at $REGISTRY_FILE has zero agents — nothing to report." >&2
    exit 1
fi

if [ ! -d "$METRICS_DIR" ] || [ ! -f "$USAGE_LEDGER" ]; then
    echo "agent-utilization: no usage ledger found at $USAGE_LEDGER — cannot compute utilization."
    echo "Total: $ROSTER_COUNT agents, Used: 0 (0%), Idle: $ROSTER_COUNT (100%) [unmeasured — no ledger data]"
    exit 0
fi

# jq -s (slurp) reads the whole file as a stream of concatenated JSON values,
# which correctly spans both the compact single-line records and the legacy
# pretty-printed multi-line records that coexist in this ledger's history.
if ! jq -c -s '[.[] | select(.agent != null and .timestamp != null) | {agent: .agent, timestamp: .timestamp}]' "$USAGE_LEDGER" > "$EVENTS_FILE" 2>/dev/null; then
    echo "agent-utilization: unable to determine metric schema in $USAGE_LEDGER; contribute to spec follow-up." >&2
    echo "Total: $ROSTER_COUNT agents, Used: 0 (0%), Idle: $ROSTER_COUNT (100%) [ledger unreadable]"
    exit 0
fi

V11_AU_ROSTER_FILE="$ROSTER_FILE" V11_AU_EVENTS_FILE="$EVENTS_FILE" V11_AU_DAYS="$DAYS" V11_AU_SORT="$SORT" \
python3 - <<'PYEOF'
import os, json, datetime

with open(os.environ["V11_AU_ROSTER_FILE"]) as fh:
    roster = json.load(fh)
with open(os.environ["V11_AU_EVENTS_FILE"]) as fh:
    events = json.load(fh)
days = int(os.environ["V11_AU_DAYS"])
sort_mode = os.environ["V11_AU_SORT"]

def parse_ts(s):
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt

now = datetime.datetime.now(datetime.timezone.utc)
cutoff = now - datetime.timedelta(days=days)

counts = {}
for e in events:
    ts = parse_ts(e.get("timestamp"))
    if ts is None or ts < cutoff:
        continue
    aid = e.get("agent")
    if not aid:
        continue
    counts[aid] = counts.get(aid, 0) + 1

roster_set = set(roster)
used, idle = [], []
for aid in roster:
    c = counts.get(aid, 0)
    (used if c > 0 else idle).append((aid, c))

used.sort(key=lambda x: (-x[1], x[0]))
idle.sort(key=lambda x: x[0])

# Orphans: agents that fired ledger events but were never registered in
# agents.json's .agents keys. See ticket #38 (registry-vs-ledger roster
# gap) — this table only reports the gap, it does not reconcile it.
orphans = [(aid, c) for aid, c in counts.items() if aid not in roster_set]
orphans.sort(key=lambda x: (-x[1], x[0]))

total = len(roster)
used_n, idle_n = len(used), len(idle)
orphan_n = len(orphans)
orphan_events = sum(c for _, c in orphans)

def print_used():
    print(f"Used in last {days} days ({used_n} agents):")
    if not used:
        print("  (none)")
        return
    width = max(len(a) for a, _ in used)
    for aid, c in used:
        print(f"  {aid:<{width}}  {c}")

def print_idle():
    print(f"Idle — 0 uses in last {days} days ({idle_n} agents, candidate demotion queue):")
    if not idle:
        print("  (none)")
        return
    for aid, _ in idle:
        print(f"  {aid}")

def print_orphans():
    print(f"Orphan — in ledger but not in registry ({orphan_n} agents, {orphan_events} events):")
    if not orphans:
        print("  (none)")
        return
    width = max(len(a) for a, _ in orphans)
    for aid, c in orphans:
        print(f"  {aid:<{width}}  {c}")

print(f"Agent Utilization — last {days} days")
print(f"Registry: {total} agents | Ledger events in window: {sum(counts.values())}")
print()

if sort_mode == "unused":
    print_idle()
    print()
    print_used()
else:
    print_used()
    print()
    print_idle()

print()
print_orphans()

print()
print(f"Total: {total} registered agents ({used_n} used, {idle_n} idle) + {orphan_n} orphan agents observed in ledger (see ticket #38)")
PYEOF
