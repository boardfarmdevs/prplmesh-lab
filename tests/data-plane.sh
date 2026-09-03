#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
clients=${PRPL_CLIENT_COUNT:-20}
agents=${PRPL_AGENT_COUNT:-4}
topology=${PRPL_TOPOLOGY:-chain}
controller_ip=192.168.77.1

failures=0
status_section "Mesh data-plane acceptance"
status_wait "Checking deterministic DHCP ownership and sending traffic from all $clients clients."
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
status_pass "All $clients clients have the expected address and reach the controller."

# Prove a data path through the deepest active backhaul, not merely through a
# client that happens to be attached to the colocated controller agent.
if [ "$agents" -gt 0 ]; then
    leaf_container=
    leaf_bssid=
    case "$topology" in
        chain) candidate_agents=$agents ;;
        branch) candidate_agents=$(seq "$agents" -1 2) ;;
        star) candidate_agents=$(seq "$agents" -1 1) ;;
        *) echo "PRPL_TOPOLOGY must be star, branch or chain" >&2; exit 2 ;;
    esac
    for candidate_agent in $candidate_agents; do
        for ordinal in $(seq 1 "$clients"); do
            printf -v container 'prpl-client-%02d' "$ordinal"
            bssid=$(lxc exec "$container" -- wpa_cli -i wlan0 status | \
                sed -n 's/^bssid=//p')
            case "$bssid" in
                02:00:00:00:*:00|02:00:00:00:*:01) ;;
                *) continue ;;
            esac
            radio_octet=$(printf '%s\n' "$bssid" | cut -d: -f5)
            case "$radio_octet" in
                ''|*[!0-9a-fA-F]*) continue ;;
            esac
            [ "$((16#$radio_octet / 3))" -eq "$candidate_agent" ] || continue
            leaf_container=$container
            leaf_bssid=$bssid
            leaf_agent=$candidate_agent
            break 2
        done
    done
    [ -n "$leaf_container" ] || {
        echo "FAIL: no client is associated with a BSSID on a deepest $topology agent" >&2
        exit 1
    }
    status_action "Proving a representative path through deepest $topology agent-$leaf_agent."
    echo "deepest data path: $leaf_container via agent-$leaf_agent ($leaf_bssid)"
    summary=$(lxc exec "$leaf_container" -- \
        ping -q -c 10 -W 2 "$controller_ip" | tail -n 2)
    printf '%s\n' "$summary"
fi

status_pass "$clients/$clients clients reach the controller over the mesh data plane."
echo "PASS: $clients/$clients clients reach the controller over the mesh data plane"
