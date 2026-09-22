#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
source "$ROOT/deploy/lxd-vm/instance-config.sh"
prplmesh_instance_config
export BUILD_CONTAINER=${BUILD_CONTAINER:-$PRPLMESH_VM_NAME-builder}
export PRPL_BUILD_STORAGE=${PRPL_BUILD_STORAGE:-$PRPLMESH_VM_NAME-build-pool}
export MANAGEMENT_NETWORK=${MANAGEMENT_NETWORK:-pb-$(printf '%s' "$PRPLMESH_VM_NAME" | sha256sum | cut -c1-10)}
export MANAGEMENT_IPV4=${MANAGEMENT_IPV4:-auto}
export PRPL_BUILD_ONLY=1
command -v lxc >/dev/null || { echo 'Run deploy/lxd-vm/install-host.sh first.' >&2; exit 2; }
prplmesh_ensure_storage "$PRPL_BUILD_STORAGE"
mkdir -p "$ROOT/build-evidence"
log="$ROOT/build-evidence/artifacts-$PRPLMESH_VM_NAME-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$log") 2>&1
printf 'Native build only: container=%s storage=%s network=%s\n' "$BUILD_CONTAINER" "$PRPL_BUILD_STORAGE" "$MANAGEMENT_NETWORK"
for step in create-build-container.sh build-prplmesh.sh package-build-artifacts.sh; do
    started=$SECONDS
    printf '\n===== %s =====\n' "$step"
    if [[ $step == build-prplmesh.sh ]]; then
        bash "$ROOT/scripts/$step" nl80211
    else
        bash "$ROOT/scripts/$step"
    fi
    printf 'Completed %s in %ss\n' "$step" "$((SECONDS - started))"
done
echo "Artifacts verified. Log: $log. Next: bash deploy/lxd-vm/build.sh build"
