#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/manifests/lab.env"
BUILD_TYPE=${1:-dummy}

case "$BUILD_TYPE" in
    dummy) BWL=DUMMY ;;
    nl80211) BWL=NL80211 ;;
    *) echo "usage: $0 [dummy|nl80211]" >&2; exit 2 ;;
esac

lxc start "$BUILD_CONTAINER" 2>/dev/null || true
lxc file push "$ROOT/scripts/container/build-inside.sh" \
    "$BUILD_CONTAINER/root/build-inside.sh" --mode=0755
lxc file push -p "$ROOT/patches/prplmesh/" \
    "$BUILD_CONTAINER/root/prplmesh-patches/"
lxc exec "$BUILD_CONTAINER" -- env \
    PRPL_RELEASE="$PRPL_RELEASE" PRPL_COMMIT="$PRPL_COMMIT" BWL_TYPE="$BWL" \
    /root/build-inside.sh
