#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE_IMAGE=${SOURCE_IMAGE:-}
role=${1:-mesh}
case "$role" in
    mesh) default_alias=${PRPLMESH_RUNTIME_IMAGE:-prpl-runtime-local}; setup=setup-runtime-base.sh; default_builder=prpl-runtime-image-build ;;
    client) default_alias=${PRPLMESH_CLIENT_IMAGE:-prpl-client-local}; setup=setup-client-base.sh; default_builder=prpl-client-image-build ;;
    *) echo "usage: $0 [mesh|client]" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo "usage: $0 [mesh|client]" >&2; exit 2; }
IMAGE_ALIAS=${IMAGE_ALIAS:-$default_alias}
BUILDER=${RUNTIME_IMAGE_BUILDER:-$default_builder}

if [ -z "$SOURCE_IMAGE" ]; then
    SOURCE_IMAGE=$(lxc image list -c fd --format csv | \
        awk -F, '$2 ~ /^ubuntu 22[.]04 LTS/ { print $1; exit }')
fi
[ -n "$SOURCE_IMAGE" ] || {
    echo "no cached Ubuntu 22.04 base image; set SOURCE_IMAGE explicitly" >&2
    exit 1
}

if lxc info "$BUILDER" >/dev/null 2>&1; then
    lxc delete "$BUILDER" --force
fi

lxc init "$SOURCE_IMAGE" "$BUILDER" -c security.privileged=true </dev/null
lxc config device add "$BUILDER" project disk source="$ROOT" path=/mnt/project
lxc start "$BUILDER"
log=${RUNTIME_IMAGE_BUILD_LOG:-/tmp/$default_builder.log}
if ! lxc exec --mode non-interactive "$BUILDER" -- \
    "/mnt/project/scripts/container/$setup" </dev/null >"$log" 2>&1; then
    tail -200 "$log" >&2
    exit 1
fi
lxc stop "$BUILDER" --timeout 30 || lxc stop "$BUILDER" --force

if lxc image alias list --format csv | cut -d, -f1 | grep -Fx "$IMAGE_ALIAS" >/dev/null; then
    lxc image alias delete "$IMAGE_ALIAS"
fi
lxc publish "$BUILDER" --alias "$IMAGE_ALIAS"
lxc delete "$BUILDER"

lxc image info "$IMAGE_ALIAS"
