#!/bin/bash
set -u -o pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
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

echo "Steering demo: ${#clients[@]} clients, ${#targets[@]} targets, $cycles cycle(s), ${delay}s pause"
echo "Web UI: http://192.168.2.140:8091/"
failures=0
moves=0
for cycle in $(seq 1 "$cycles"); do
    for target in "${targets[@]}"; do
        echo "--- cycle $cycle/$cycles: moving clients to $target ---"
        for client in "${clients[@]}"; do
            if "$ROOT/scripts/steer-client.sh" "$client" "$target"; then
                moves=$((moves + 1))
            else
                failures=$((failures + 1))
                echo "WARN: $client failed to converge on $target; continuing demo" >&2
            fi
            sleep "$delay"
        done
    done
done

echo "Steering demo complete: $moves successful moves, $failures failures"
[ "$failures" -eq 0 ]
