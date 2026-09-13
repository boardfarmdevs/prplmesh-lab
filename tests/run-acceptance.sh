#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}
topology=${PRPL_TOPOLOGY:-chain}
medium_backend=${PRPL_MEDIUM_BACKEND:-userspace}
topology_output=$(mktemp)
trap 'rm -f "$topology_output"' EXIT

expected_patchset=$(
    cd "$ROOT"
    sha256sum patches/prplmesh/*.patch | sha256sum | awk '{print $1}'
)
expected_ubus_patchset=$(
    cd "$ROOT"
    sha256sum patches/ubus/*.patch | sha256sum | awk '{print $1}'
)
status_section "prplMesh expanded acceptance"
status_action "Verifying runtime provenance on the controller and $agents agent(s)."
for node in prpl-controller $(seq -f 'prpl-agent-%02g' 1 "$agents"); do
    provenance=$(
        lxc exec "$node" -- cat \
            /opt/prpl-install-nl80211/share/prplmesh-lab/provenance.env \
            2>/dev/null || true
    )
    if ! grep -Fxq "PRPL_PATCHSET_SHA256=$expected_patchset" <<<"$provenance"; then
        echo "$node uses a stale or unidentifiable prplMesh runtime artifact" >&2
        exit 1
    fi
    if ! lxc exec "$node" -- env EXPECTED_UBUS_PATCHSET="$expected_ubus_patchset" bash -ec '
        provenance=/usr/share/prplmesh-lab/ubus-provenance.env
        grep -Fxq "UBUS_COMMIT=13a4438b4ebdf85d301999e0a615640ac4c9b0a8" "$provenance"
        grep -Fxq "UBUS_PATCHSET_SHA256=$EXPECTED_UBUS_PATCHSET" "$provenance"
        digest=$(sha256sum /usr/lib/libubus.so)
        grep -Fxq "UBUS_LIBRARY_SHA256=${digest%% *}" "$provenance"
    '; then
        echo "$node uses a stale or unidentifiable ubus dependency" >&2
        exit 1
    fi
done
status_pass "Every mesh node uses the expected patch set."

status_action "Starting the topology adapter and validating $topology with $clients clients."
"$ROOT/scripts/topology-adapter.sh" start >/dev/null
for attempt in $(seq 1 12); do
    if "$ROOT/tests/topology-acceptance.py" \
        --agents "$agents" --clients "$clients" --topology "$topology" \
        --require-metrics >"$topology_output" 2>&1; then
        cat "$topology_output"
        break
    fi
    [ "$attempt" -lt 12 ] && status_wait_seconds 5 "topology and metrics are still converging (attempt $attempt/12)"
done
if [ "$attempt" -eq 12 ] && ! grep -q '^PASS ' "$topology_output"; then
    cat "$topology_output" >&2
    exit 1
fi
status_pass "Topology and metrics satisfy the selected profile."
status_action "Running representative two-SSID, tri-band BTM steering."
PRPL_AGENT_COUNT=$agents "$ROOT/scripts/test-steering.sh"
status_action "Checking every client data path through the active backhaul topology."
PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients \
    "$ROOT/tests/data-plane.sh"
status_action "Checking process cardinality and runtime footprint."
PRPL_AGENT_COUNT=$agents PRPL_CLIENT_COUNT=$clients \
    "$ROOT/tests/resource-acceptance.sh"

if [ "$medium_backend" = userspace ] &&
   grep -Eq 'assert|segmentation fault|AddressSanitizer' /tmp/prpl-wmediumd.log; then
    echo "wmediumd fatal diagnostic found" >&2
    exit 1
fi

status_pass "prplMesh expanded acceptance suite passed."
echo "PASS: prplMesh expanded acceptance suite"
