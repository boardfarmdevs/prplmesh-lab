#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
agents=${PRPL_AGENT_COUNT:-4}
targets=(controller)
for ordinal in $(seq 1 "$agents"); do targets+=("agent-$ordinal"); done

# One private and one IoT station on each band. Every station is moved across
# every active EasyMesh device; steer-client requires both physical and NBAPI
# ownership to reach the requested BSSID after each BTM request.
clients=(sta-01 iot-01 sta-02 iot-02 sta-04 iot-04)
for client in "${clients[@]}"; do
    for target in "${targets[@]}"; do
        "$ROOT/scripts/steer-client.sh" "$client" "$target"
    done
done

echo "PASS: ${#clients[@]} clients x ${#targets[@]} targets two-SSID tri-band steering matrix"
