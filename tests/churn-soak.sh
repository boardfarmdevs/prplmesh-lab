#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
iterations=${PRPL_CHURN_ITERATIONS:-3}
agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}
topology=${PRPL_TOPOLOGY:-chain}

inventory_hash()
{
    for node in prpl-controller $(printf 'prpl-agent-%02d ' $(seq 1 "$agents")) \
                $(printf 'prpl-client-%02d ' $(seq 1 "$clients")); do
        lxc config device show "$node" | \
            sed -n '/^radio/,/^$/p' | grep -E '^(radio|  name:|  parent:)' || true
    done | sha256sum | awk '{print $1}'
}

before_hash=$(inventory_hash)
medium_pid=$(cat /run/prpl-wmediumd/wmediumd.pid)
kill -0 "$medium_pid"

for iteration in $(seq 1 "$iterations"); do
    echo "=== churn iteration $iteration/$iterations ==="
    "$ROOT/scripts/steer-client.sh" iot-06 controller
    PRPL_TOPOLOGY=$topology "$ROOT/scripts/radio-lab.sh" restart-agent "$agents"
    "$ROOT/scripts/steer-client.sh" iot-06 "agent-$agents"
    "$ROOT/tests/topology-acceptance.py" \
        --agents "$agents" --clients "$clients" --topology "$topology"
    PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients \
        "$ROOT/tests/resource-acceptance.sh" >/tmp/prpl-resource-iteration.txt
    [ "$(cat /run/prpl-wmediumd/wmediumd.pid)" = "$medium_pid" ]
    kill -0 "$medium_pid"
done

after_hash=$(inventory_hash)
[ "$before_hash" = "$after_hash" ] || {
    echo "radio inventory changed: $before_hash -> $after_hash" >&2
    exit 1
}

echo "PASS: $iterations leaf restart/steering cycles; inventory and wmediumd PID unchanged"
