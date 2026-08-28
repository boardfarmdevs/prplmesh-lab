#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}

for topology in star branch chain; do
    echo "=== topology: $topology ==="
    "$ROOT/scripts/topology-visualizer.sh" stop >/dev/null 2>&1 || true
    "$ROOT/scripts/radio-lab.sh" stop
    PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients PRPL_TOPOLOGY=$topology \
        "$ROOT/scripts/radio-lab.sh" start
    "$ROOT/scripts/topology-visualizer.sh" start >/dev/null
    "$ROOT/tests/topology-acceptance.py" \
        --agents "$agents" --clients 0 --topology "$topology"
done

PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients PRPL_TOPOLOGY=chain \
    "$ROOT/scripts/radio-lab.sh" clients
sleep 45
"$ROOT/tests/topology-acceptance.py" \
    --agents "$agents" --clients "$clients" --topology chain --require-metrics

echo "PASS: star, branch and chain topology reconstruction"
