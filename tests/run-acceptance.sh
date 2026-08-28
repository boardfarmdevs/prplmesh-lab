#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}
topology=${PRPL_TOPOLOGY:-chain}
topology_output=$(mktemp)
trap 'rm -f "$topology_output"' EXIT

"$ROOT/scripts/topology-visualizer.sh" start >/dev/null
for attempt in $(seq 1 12); do
    if "$ROOT/tests/topology-acceptance.py" \
        --agents "$agents" --clients "$clients" --topology "$topology" \
        --require-metrics >"$topology_output" 2>&1; then
        cat "$topology_output"
        break
    fi
    [ "$attempt" -lt 12 ] && sleep 5
done
if [ "$attempt" -eq 12 ] && ! grep -q '^PASS ' "$topology_output"; then
    cat "$topology_output" >&2
    exit 1
fi
PRPL_AGENT_COUNT=$agents "$ROOT/scripts/test-steering.sh"
PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients \
    "$ROOT/tests/data-plane.sh"
PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients \
    "$ROOT/tests/resource-acceptance.sh"

if grep -Eq 'assert|segmentation fault|AddressSanitizer' /tmp/prpl-wmediumd.log; then
    echo "wmediumd fatal diagnostic found" >&2
    exit 1
fi

echo "PASS: prplMesh expanded acceptance suite"
