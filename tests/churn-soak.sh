#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
iterations=${PRPL_CHURN_ITERATIONS:-3}
agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}
topology=${PRPL_TOPOLOGY:-chain}
medium_backend=${PRPL_MEDIUM_BACKEND:-userspace}

inventory_hash()
{
    for node in prpl-controller $(printf 'prpl-agent-%02d ' $(seq 1 "$agents")) \
                $(printf 'prpl-client-%02d ' $(seq 1 "$clients")); do
        lxc config device show "$node" | \
            sed -n '/^radio/,/^$/p' | grep -E '^(radio|  name:|  parent:)' || true
    done | sha256sum | awk '{print $1}'
}

before_hash=$(inventory_hash)
case "$medium_backend" in
    userspace) medium_pid=$(cat /run/prpl-wmediumd/wmediumd.pid) ;;
    kernel) medium_pid=$(cat /run/prpl-wmediumd/kernel-metrics-proxy.pid) ;;
    *) echo "PRPL_MEDIUM_BACKEND must be userspace or kernel" >&2; exit 2 ;;
esac
kill -0 "$medium_pid"

status_section "Bounded lifecycle churn"
status_note "Running $iterations leaf restart/steering cycle(s) without replacing the $medium_backend medium."
for iteration in $(seq 1 "$iterations"); do
    status_action "Iteration $iteration/$iterations: move iot-06 to the controller."
    "$ROOT/scripts/steer-client.sh" iot-06 controller
    status_action "Restarting leaf agent-$agents with its permanent radio identity."
    PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" restart-agent "$agents"
    status_action "Moving iot-06 back to the recovered leaf and checking topology/resources."
    "$ROOT/scripts/steer-client.sh" iot-06 "agent-$agents"
    "$ROOT/tests/topology-acceptance.py" \
        --agents "$agents" --clients "$clients" --topology "$topology"
    PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients \
        "$ROOT/tests/resource-acceptance.sh" >/tmp/prpl-resource-iteration.txt
    if [ "$medium_backend" = userspace ]; then
        [ "$(cat /run/prpl-wmediumd/wmediumd.pid)" = "$medium_pid" ]
    else
        [ "$(cat /run/prpl-wmediumd/kernel-metrics-proxy.pid)" = "$medium_pid" ]
        [ "$(cat /sys/module/mac80211_hwsim/parameters/kernel_medium)" = Y ]
    fi
    kill -0 "$medium_pid"
    status_pass "Iteration $iteration preserved topology, processes and medium identity."
done

after_hash=$(inventory_hash)
[ "$before_hash" = "$after_hash" ] || {
    echo "radio inventory changed: $before_hash -> $after_hash" >&2
    exit 1
}

status_pass "$iterations leaf restart/steering cycles passed; inventory and $medium_backend medium identity are unchanged."
