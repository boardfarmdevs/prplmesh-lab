#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
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
done

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

if [ "$medium_backend" = userspace ] &&
   grep -Eq 'assert|segmentation fault|AddressSanitizer' /tmp/prpl-wmediumd.log; then
    echo "wmediumd fatal diagnostic found" >&2
    exit 1
fi

echo "PASS: prplMesh expanded acceptance suite"
