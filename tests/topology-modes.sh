#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}

status_section "Backhaul topology reconstruction"
status_note "Each topology is built with agents only first; the final chain then receives all clients."
for topology in star branch chain; do
    status_action "Stopping the current mesh and constructing the $topology parent map."
    "$ROOT/scripts/topology-adapter.sh" stop >/dev/null 2>&1 || true
    "$ROOT/scripts/radio-lab.sh" stop
    PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients PRPL_TOPOLOGY=$topology \
        "$ROOT/scripts/radio-lab.sh" start
    "$ROOT/scripts/topology-adapter.sh" start >/dev/null
    "$ROOT/tests/topology-acceptance.py" \
        --agents "$agents" --clients 0 --topology "$topology"
    status_pass "$topology topology is physically and logically correct."
done

status_action "Starting all $clients clients on the final chain topology."
PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients PRPL_TOPOLOGY=chain \
    "$ROOT/scripts/radio-lab.sh" clients
status_wait_seconds 45 "allowing associations and RCPI telemetry to converge"
"$ROOT/tests/topology-acceptance.py" \
    --agents "$agents" --clients "$clients" --topology chain --require-metrics

status_pass "Star, branch and chain topology reconstruction passed."
echo "PASS: star, branch and chain topology reconstruction"
