#!/bin/bash
# The Alpine clients' wpa_supplicant and wpa_cli (artifacts/hostap-client-2.10-alpine.tar.gz):
# hostap at the pinned commit with the lab's hostap patches, built in a throwaway Alpine
# container (scripts/container/build-hostap-client-inside.sh). The artifact store gives it
# instead when it holds one built from the same inputs (deploy/lxd-vm/artifact-store.sh);
# BUILD_FORCE=1 builds it anyway.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source-path=SCRIPTDIR source=../manifests/lab.env
source "$ROOT/manifests/lab.env"
# shellcheck source-path=SCRIPTDIR source=../deploy/lxd-vm/artifact-store.sh
source "$ROOT/deploy/lxd-vm/artifact-store.sh"
# shellcheck source-path=SCRIPTDIR source=../deploy/lxd-vm/native-inputs.sh
source "$ROOT/deploy/lxd-vm/native-inputs.sh"
BUILDER=${PRPL_CLIENT_BUILDER:-prpl-client-artifact-build}
ARCHIVE=$PRPLMESH_CLIENT_ARCHIVE

key=$(prplmesh_client_key)
mkdir -p "$ROOT/artifacts"
if [ "${BUILD_FORCE:-0}" != 1 ] && [ -f "$ROOT/artifacts/$ARCHIVE" ] \
    && [ "$(cat "$ROOT/artifacts/prplmesh-client.key" 2>/dev/null)" = "$key" ]; then
    echo "$ARCHIVE is built from these inputs already (key $key)"
    exit 0
fi
fetched=$(mktemp -d)
trap 'rm -rf -- "$fetched"' EXIT
if [ "${BUILD_FORCE:-0}" != 1 ] && artifact_fetch prplmesh-client "$key" "$fetched"; then
    install -m 0644 "$fetched/$ARCHIVE" "$ROOT/artifacts/$ARCHIVE"
else
    if lxc info "$BUILDER" >/dev/null 2>&1; then
        lxc delete "$BUILDER" --force
    fi
    lxc launch "$PRPLMESH_CLIENT_ALPINE_IMAGE" "$BUILDER" </dev/null
    trap 'rm -rf -- "$fetched"; lxc delete "$BUILDER" --force >/dev/null 2>&1 || true' EXIT
    for attempt in $(seq 1 60); do
        lxc exec "$BUILDER" -- sh -c 'ip -4 route | grep -q default' 2>/dev/null && break
        [ "$attempt" -lt 60 ] || { echo "$BUILDER has no network" >&2; exit 1; }
        sleep 1
    done
    lxc exec "$BUILDER" -- mkdir -p /root/hostap-patches
    for patch in "$ROOT"/patches/hostap/*.patch; do
        lxc file push "$patch" "$BUILDER/root/hostap-patches/$(basename "$patch")"
    done
    lxc file push --mode 0755 "$ROOT/scripts/container/build-hostap-client-inside.sh" \
        "$BUILDER/root/build-hostap-client-inside.sh"
    lxc exec "$BUILDER" -- env HOSTAP_COMMIT="$HOSTAP_COMMIT" \
        /root/build-hostap-client-inside.sh </dev/null
    lxc file pull "$BUILDER/tmp/$ARCHIVE" "$ROOT/artifacts/$ARCHIVE"
    lxc delete "$BUILDER" --force
    if [ -n "${EASYMESH_ARTIFACT_PUBLISH:-}" ]; then
        install -m 0644 "$ROOT/artifacts/$ARCHIVE" "$fetched/$ARCHIVE"
        {
            printf 'KEY=%s\nCOMMIT=%s\nHOST=%s\n' "$key" "$(git -C "$ROOT" rev-parse HEAD)" "$(hostname)"
            tar -xzOf "$ROOT/artifacts/$ARCHIVE" ./hostap-client.provenance.env
        } > "$fetched/provenance.env"
        artifact_publish prplmesh-client "$key" "$fetched"
    fi
fi
printf '%s\n' "$key" > "$ROOT/artifacts/prplmesh-client.key"
prplmesh_artifact_sums
printf '%s: %s (key %s)\n' "$ARCHIVE" "$(sha256sum "$ROOT/artifacts/$ARCHIVE" | cut -c1-16)" "$key"
