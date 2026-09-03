#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
agents=${PRPL_AGENT_COUNT:-4}
topology=${PRPL_TOPOLOGY:-chain}
leaf=$agents
printf -v node 'prpl-agent-%02d' "$leaf"
client=iot-06
printf -v leaf_prefix '02:00:00:00:%02x:' "$((leaf * 3 + 2))"
agent_stopped=0

restore_agent()
{
    if [ "$agent_stopped" = 1 ]; then
        PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" start-agent "$leaf" || true
    fi
}
trap restore_agent EXIT

# Put a known 6 GHz IoT client on the leaf so the outage has an observable
# fronthaul consequence in addition to controller topology aging.
status_section "Leaf-agent outage and recovery"
status_action "Steering $client to leaf agent-$leaf so the outage has a visible client impact."
"$ROOT/scripts/steer-client.sh" "$client" "agent-$leaf"
before=$(lxc exec prpl-client-12 -- wpa_cli -i wlan0 status | sed -n 's/^bssid=//p')

status_action "Stopping $node while the controller and other agents remain active."
PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" stop-agent "$leaf"
agent_stopped=1
[ "$(lxc list "$node" -c s --format csv)" = STOPPED ]

status_wait "Waiting up to 45s for $client to leave the failed leaf and reconnect."
for attempt in $(seq 1 45); do
    state=$(lxc exec prpl-client-12 -- wpa_cli -i wlan0 status 2>/dev/null | sed -n 's/^wpa_state=//p' || true)
    after=$(lxc exec prpl-client-12 -- wpa_cli -i wlan0 status 2>/dev/null | sed -n 's/^bssid=//p' || true)
    case "$after" in "$leaf_prefix"*) on_leaf=1 ;; *) on_leaf=0 ;; esac
    if [ "$state" = COMPLETED ] && [ "$on_leaf" = 0 ]; then break; fi
    sleep 1
done
[ "$state" = COMPLETED ] && [ "$on_leaf" = 0 ] || {
    echo "$client did not recover from $node outage: state=$state bssid=${after:-none}" >&2
    exit 1
}
status_pass "$client moved from the failed leaf to a live BSS."

agent_id=$(printf '02:00:00:27:%02x:01' "$((leaf + 1))")
status_wait "Waiting up to 60s for NBAPI liveness aging to remove $node."
for attempt in $(seq 1 60); do
    if ! timeout 15 curl -fsS http://127.0.0.1:8092/api/topology | \
            jq -e --arg id "$agent_id" \
                '[.devices[]?.id | ascii_downcase] | index($id) != null' \
                >/dev/null; then
        aged=1
        break
    fi
    sleep 1
done
[ "${aged:-0}" = 1 ] || {
    echo "$node did not age out of the active NBAPI topology" >&2
    exit 1
}
status_pass "$node aged out of the active topology."

status_action "Restarting $node with its stable identity, then steering $client back."
PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" start-agent "$leaf"
agent_stopped=0
"$ROOT/scripts/steer-client.sh" "$client" "agent-$leaf"

status_pass "$node aged out, $client moved from $before to $after, and the agent rejoined with stable identity."
echo "PASS: $node aged out, $client moved from $before to $after, and the agent rejoined with stable identity"
