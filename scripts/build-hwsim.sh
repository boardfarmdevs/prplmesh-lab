#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
KVER=$(uname -r)
GEN=$(printf '%s\n' "$KVER" | sed -E 's/^([0-9]+\.[0-9]+).*/\1/')

if [ "$GEN" != 7.0 ]; then
    echo "Linux 7.0 is required; running $KVER" >&2
    exit 1
fi

KBUILD=/lib/modules/$KVER/build
test -d "$KBUILD" || {
    echo "missing kernel headers: $KBUILD" >&2
    exit 1
}

SOURCE="$ROOT/build/hwsim-source"
mkdir -p "$SOURCE"

if [ ! -f "$SOURCE/mac80211_hwsim.c" ] || [ "${REFETCH:-0}" = 1 ]; then
    if ! grep -Rqs '^Types:.*deb-src' /etc/apt/sources.list.d /etc/apt/sources.list 2>/dev/null; then
        echo "enable Ubuntu deb-src entries before building hwsim" >&2
        exit 1
    fi
    temporary=$(mktemp -d)
    trap 'rm -rf "$temporary"' EXIT
    image_version=$(dpkg-query -W -f='${Version}' "linux-image-$KVER")
    (
        cd "$temporary"
        apt-get source "linux-hwe-7.0=$image_version"
    )
    driver=$(find "$temporary" -path '*/drivers/net/wireless/virtual/mac80211_hwsim.c' | head -n 1)
    test -n "$driver" || {
        echo "mac80211_hwsim.c not found in linux-hwe-7.0 source" >&2
        exit 1
    }
    install -m 0644 "$driver" "$SOURCE/mac80211_hwsim.c"
    header=$(dirname "$driver")/mac80211_hwsim.h
    test ! -f "$header" || install -m 0644 "$header" "$SOURCE/mac80211_hwsim.h"
fi

patch_file="$ROOT/patches/hwsim/0001-mac80211_hwsim-allow-multichannel-wmediumd.patch"
if patch -d "$SOURCE" -p5 --dry-run -N < "$patch_file" >/dev/null 2>&1; then
    patch -d "$SOURCE" -p5 -N < "$patch_file"
elif patch -d "$SOURCE" -p5 --dry-run -R < "$patch_file" >/dev/null 2>&1; then
    echo "hwsim multichannel patch already applied"
else
    echo "hwsim patch does not apply to $KVER source" >&2
    exit 1
fi

grep -q 'EXPERIMENTAL wmediumd' "$SOURCE/mac80211_hwsim.c"
printf 'obj-m += mac80211_hwsim.o\n' > "$SOURCE/Makefile"
make -C "$KBUILD" M="$SOURCE" modules

if [ "${INSTALL_MODULE:-0}" = 1 ]; then
    install -D -m 0644 "$SOURCE/mac80211_hwsim.ko" \
        "/lib/modules/$KVER/updates/mac80211_hwsim.ko"
    depmod -a "$KVER"
fi

if [ "${LOAD_MODULE:-0}" = 1 ]; then
    modprobe -r mac80211_hwsim 2>/dev/null || true
    modprobe mac80211_hwsim radios="${HWSIM_RADIOS:-8}" \
        channels="${HWSIM_CHANNELS:-3}" regtest="${HWSIM_REGTEST:-5}"
fi

echo "Built $SOURCE/mac80211_hwsim.ko for $KVER"
