#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
agents=${PRPL_AGENT_COUNT:-4}
topology=${PRPL_TOPOLOGY:-chain}
leaf=$agents
printf -v node 'prpl-agent-%02d' "$leaf"
client=iot-06
printf -v leaf_prefix '02:00:00:00:%02x:' "$((leaf * 3 + 2))"

# Put a known 6 GHz IoT client on the leaf so the outage has an observable
# fronthaul consequence in addition to controller topology aging.
"$ROOT/scripts/steer-client.sh" "$client" "agent-$leaf"
before=$(lxc exec prpl-client-12 -- wpa_cli -i wlan0 status | sed -n 's/^bssid=//p')

PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" stop-agent "$leaf"
[ "$(lxc list "$node" -c s --format csv)" = STOPPED ]

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

agent_id=$(printf '02:00:00:27:%02x:01' "$((leaf + 1))")
for attempt in $(seq 1 30); do
    if ! timeout 30 curl -fsS http://127.0.0.1:8092/api/topology | \
            grep -F "$agent_id" >/dev/null; then
        aged=1
        break
    fi
    sleep 1
done
[ "${aged:-0}" = 1 ] || {
    echo "$node did not age out of the active NBAPI topology" >&2
    exit 1
}

PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" start-agent "$leaf"
"$ROOT/scripts/steer-client.sh" "$client" "agent-$leaf"

echo "PASS: $node aged out, $client moved from $before to $after, and the agent rejoined with stable identity"
