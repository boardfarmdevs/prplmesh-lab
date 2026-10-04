#!/usr/bin/env bash
# The lab's archives in artifacts/: the native ones (prplMesh, its dependencies, hostap 2.10)
# built in a builder container, and the Alpine clients' supplicant. Either comes from the
# artifact store when it holds one built from the same inputs (artifact-store.sh,
# native-inputs.sh: EASYMESH_ARTIFACT_STORE); EASYMESH_ARTIFACT_PUBLISH publishes what is
# built here; BUILD_FORCE=1 builds anyway.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source-path=SCRIPTDIR source=instance-config.sh
source "$ROOT/deploy/lxd-vm/instance-config.sh"
# shellcheck source-path=SCRIPTDIR source=artifact-store.sh
source "$ROOT/deploy/lxd-vm/artifact-store.sh"
# shellcheck source-path=SCRIPTDIR source=native-inputs.sh
source "$ROOT/deploy/lxd-vm/native-inputs.sh"
prplmesh_instance_config
export BUILD_CONTAINER=${BUILD_CONTAINER:-$PRPLMESH_VM_NAME-builder}
export PRPL_BUILD_STORAGE=${PRPL_BUILD_STORAGE:-$PRPLMESH_VM_NAME-build-pool}
export MANAGEMENT_NETWORK=${MANAGEMENT_NETWORK:-pb-$(printf '%s' "$PRPLMESH_VM_NAME" | sha256sum | cut -c1-10)}
export MANAGEMENT_IPV4=${MANAGEMENT_IPV4:-auto}
export PRPL_BUILD_ONLY=1
command -v lxc >/dev/null || { echo 'Run deploy/lxd-vm/install-host.sh first.' >&2; exit 2; }
mkdir -p "$ROOT/build-evidence" "$ROOT/artifacts"
log="$ROOT/build-evidence/artifacts-$PRPLMESH_VM_NAME-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$log") 2>&1

key=$(prplmesh_native_key)
fetched=$(mktemp -d)
trap 'rm -rf -- "$fetched"' EXIT
if [ "${BUILD_FORCE:-0}" != 1 ] && artifact_fetch prplmesh-native "$key" "$fetched"; then
    for archive in "${PRPLMESH_NATIVE_ARCHIVES[@]}"; do
        install -m 0644 "$fetched/$archive" "$ROOT/artifacts/$archive"
    done
else
    prplmesh_ensure_storage "$PRPL_BUILD_STORAGE"
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
    if [ -n "${EASYMESH_ARTIFACT_PUBLISH:-}" ]; then
        for archive in "${PRPLMESH_NATIVE_ARCHIVES[@]}"; do
            cp --reflink=auto "$ROOT/artifacts/$archive" "$fetched/$archive"
        done
        # shellcheck source-path=SCRIPTDIR source=../../manifests/lab.env
        (source "$ROOT/manifests/lab.env"
         printf 'KEY=%s\nCOMMIT=%s\nHOST=%s\nBUILT=%s\n' "$key" "$(git -C "$ROOT" rev-parse HEAD)" \
             "$(hostname)" "$(date -u +%FT%TZ)"
         printf 'PRPL_RELEASE=%s\nPRPL_COMMIT=%s\nHOSTAP_COMMIT=%s\n' "$PRPL_RELEASE" \
             "$PRPL_COMMIT" "$HOSTAP_COMMIT") > "$fetched/provenance.env"
        artifact_publish prplmesh-native "$key" "$fetched"
    fi
fi
printf '%s\n' "$key" > "$ROOT/artifacts/prplmesh-native.key"
bash "$ROOT/scripts/build-client-artifact.sh"
prplmesh_artifact_sums
echo "Artifacts verified (native key $key). Log: $log. Next: bash deploy/lxd-vm/build.sh build"
