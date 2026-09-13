#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../manifests/lab.env
source "$ROOT/manifests/lab.env"

# The upstream release number alone is not sufficient to identify a lab
# runtime: the virtual-radio integration is a reviewed patch series on top of
# that release.  Record one deterministic digest in every runtime artifact so
# deployment and acceptance cannot silently reuse an older local tarball.
PRPL_PATCHSET_SHA256=$(
    cd "$ROOT"
    sha256sum patches/prplmesh/*.patch | sha256sum | awk '{print $1}'
)
UBUS_PATCHSET_SHA256=$(
    cd "$ROOT"
    sha256sum patches/ubus/*.patch | sha256sum | awk '{print $1}'
)
AMXP_PATCHSET_SHA256=$(
    cd "$ROOT"
    sha256sum patches/amxp/*.patch | sha256sum | awk '{print $1}'
)

lxc start "$BUILD_CONTAINER" 2>/dev/null || true
lxc exec "$BUILD_CONTAINER" -- rm -rf /root/hostap-patches
lxc exec "$BUILD_CONTAINER" -- mkdir -p /root/hostap-patches
for patch_file in "$ROOT"/patches/hostap/*.patch; do
    lxc file push "$patch_file" "$BUILD_CONTAINER/root/hostap-patches/$(basename "$patch_file")"
done
lxc file push "$ROOT/scripts/container/build-hostap-inside.sh" \
    "$BUILD_CONTAINER/root/build-hostap-inside.sh" --mode=0755
lxc file push "$ROOT/scripts/container/package-artifacts-inside.sh" \
    "$BUILD_CONTAINER/root/package-artifacts-inside.sh" --mode=0755
lxc exec "$BUILD_CONTAINER" -- env \
    PRPL_RELEASE="$PRPL_RELEASE" PRPL_COMMIT="$PRPL_COMMIT" \
    PRPL_PATCHSET_SHA256="$PRPL_PATCHSET_SHA256" \
    UBUS_PATCHSET_SHA256="$UBUS_PATCHSET_SHA256" \
    AMXP_PATCHSET_SHA256="$AMXP_PATCHSET_SHA256" \
    HOSTAP_COMMIT="$HOSTAP_COMMIT" \
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
