#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
agents=${PRPL_AGENT_COUNT:-4}
targets=(controller)
for ordinal in $(seq 1 "$agents"); do targets+=("agent-$ordinal"); done

# One private and one IoT station on each band. Every station is moved across
# every active EasyMesh device; steer-client requires both physical and NBAPI
# ownership to reach the requested BSSID after each BTM request.
clients=(sta-01 iot-01 sta-02 iot-02 sta-04 iot-04)
status_section "Two-SSID, tri-band steering matrix"
status_note "Moving ${#clients[@]} representative clients across ${#targets[@]} controller/agent targets."
for client in "${clients[@]}"; do
    for target in "${targets[@]}"; do
        status_action "Matrix move: $client to $target."
        "$ROOT/scripts/steer-client.sh" "$client" "$target"
    done
done

status_pass "${#clients[@]} clients x ${#targets[@]} targets passed the steering matrix."
