#!/bin/bash
set -u -o pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
agents=${PRPL_AGENT_COUNT:-4}
cycles=${PRPL_DEMO_CYCLES:-1}
delay=${PRPL_DEMO_DELAY:-8}
clients=(sta-01 iot-01 sta-02 iot-02 sta-04 iot-04)

usage()
{
    cat <<EOF
Usage: $(basename "$0") [--cycles N] [--delay SECONDS] [--agents N]

Visibly moves private and IoT clients from all three bands across every
controller/agent target. The topology Web UI refreshes every two seconds.

Defaults: --cycles $cycles --delay $delay --agents $agents
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --cycles) cycles=${2:?missing cycle count}; shift 2 ;;
        --delay) delay=${2:?missing delay}; shift 2 ;;
        --agents) agents=${2:?missing agent count}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

for value in "$agents" "$cycles"; do
    case "$value" in ''|*[!0-9]*|0) echo "agents and cycles must be positive integers" >&2; exit 2 ;; esac
done
case "$delay" in ''|*[!0-9.]*|0) echo "delay must be a positive number" >&2; exit 2 ;; esac

targets=()
for ordinal in $(seq 1 "$agents"); do targets+=("agent-$ordinal"); done
targets+=(controller)

status_section "Live steering demonstration"
status_note "${#clients[@]} clients, ${#targets[@]} targets, $cycles cycle(s), ${delay}s pause."
ui_url=${PRPL_CONTROLLER_UI_URL:-http://127.0.0.1:8091/}
status_note "Controller UI inside the lab VM: $ui_url"
status_note "Portable appliance users browse to the outer-host proxy configured at import."
failures=0
moves=0
for cycle in $(seq 1 "$cycles"); do
    for target in "${targets[@]}"; do
        status_action "Cycle $cycle/$cycles: moving the client set to $target."
        for client in "${clients[@]}"; do
            if "$ROOT/scripts/steer-client.sh" "$client" "$target"; then
                moves=$((moves + 1))
            else
                failures=$((failures + 1))
                echo "WARN: $client failed to converge on $target; continuing demo" >&2
            fi
            status_wait_seconds "$delay" "keeping the completed move visible before the next client"
        done
    done
done

if [ "$failures" -eq 0 ]; then
    status_pass "Steering demo complete: $moves successful moves."
else
    echo "Steering demo complete: $moves successful moves, $failures failures" >&2
fi
[ "$failures" -eq 0 ]
