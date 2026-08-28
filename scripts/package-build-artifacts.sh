#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../manifests/lab.env
source "$ROOT/manifests/lab.env"

lxc start "$BUILD_CONTAINER" 2>/dev/null || true
lxc file push "$ROOT/scripts/container/build-hostap-inside.sh" \
    "$BUILD_CONTAINER/root/build-hostap-inside.sh" --mode=0755
lxc file push "$ROOT/scripts/container/package-artifacts-inside.sh" \
    "$BUILD_CONTAINER/root/package-artifacts-inside.sh" --mode=0755
lxc exec "$BUILD_CONTAINER" -- env \
    PRPL_RELEASE="$PRPL_RELEASE" HOSTAP_COMMIT="$HOSTAP_COMMIT" \
    /root/package-artifacts-inside.sh

mkdir -p "$ROOT/artifacts"
for name in \
    hostap-runtime-2.10.tar.gz \
    "prpl-install-nl80211-${PRPL_RELEASE}.tar.gz" \
    "prpl-runtime-deps-${PRPL_RELEASE}.tar.gz"
do
    lxc file pull "$BUILD_CONTAINER/tmp/$name" "$ROOT/artifacts/$name"
done

(cd "$ROOT/artifacts" && sha256sum *.tar.gz > SHA256SUMS)
(cd "$ROOT/artifacts" && sha256sum -c SHA256SUMS)
echo "Build artifacts are ready in $ROOT/artifacts"
