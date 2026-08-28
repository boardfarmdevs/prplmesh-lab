#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
clients=${PRPL_CLIENT_COUNT:-20}
agents=${PRPL_AGENT_COUNT:-4}
controller_ip=192.168.77.1

failures=0
for ordinal in $(seq 1 "$clients"); do
    printf -v container 'prpl-client-%02d' "$ordinal"
    expected_ip="192.168.77.$((100 + ordinal))"
    actual_ip=$(lxc exec "$container" -- ip -4 -o address show dev wlan0 | \
        awk '{sub(/\/.*/, "", $4); print $4; exit}')
    if [ "$actual_ip" != "$expected_ip" ]; then
        echo "FAIL: $container address=${actual_ip:-none} expected=$expected_ip" >&2
        failures=$((failures + 1))
        continue
    fi
    if ! lxc exec "$container" -- ping -q -c 3 -W 2 "$controller_ip" >/dev/null; then
        echo "FAIL: $container cannot reach controller $controller_ip" >&2
        failures=$((failures + 1))
    fi
done

[ "$failures" -eq 0 ] || {
    echo "FAIL: $failures/$clients client data paths failed" >&2
    exit 1
}

# Prove a data path through the deepest active backhaul, not merely through a
# client that happens to be attached to the colocated controller agent.
if [ "$agents" -gt 0 ]; then
    leaf="agent-$agents"
    "$ROOT/scripts/steer-client.sh" iot-06 "$leaf"
    bssid=$(lxc exec prpl-client-12 -- wpa_cli -i wlan0 status | \
        sed -n 's/^bssid=//p')
    expected=$(printf '02:00:00:00:%02x:01' "$((agents * 3 + 2))")
    [ "$bssid" = "$expected" ] || {
        echo "FAIL: iot-06 BSSID=$bssid expected leaf BSSID=$expected" >&2
        exit 1
    }
    summary=$(lxc exec prpl-client-12 -- \
        ping -q -c 10 -W 2 "$controller_ip" | tail -n 2)
    printf '%s\n' "$summary"
fi

echo "PASS: $clients/$clients clients reach the controller over the mesh data plane"
