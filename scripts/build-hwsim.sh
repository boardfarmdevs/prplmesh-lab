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
        apt-get source "linux-hwe-7.0=$image_version" || apt-get source linux-hwe-7.0
    )
    driver=$(find "$temporary" -path '*/drivers/net/wireless/virtual/mac80211_hwsim.c' | head -n 1)
    test -n "$driver" || {
        echo "mac80211_hwsim.c not found in linux-hwe-7.0 source" >&2
        exit 1
    }
    install -m 0644 "$driver" "$SOURCE/mac80211_hwsim.c"
    header=$(dirname "$driver")/mac80211_hwsim.h
    test ! -f "$header" || install -m 0644 "$header" "$SOURCE/mac80211_hwsim.h"
    descriptor=$(find "$temporary" -maxdepth 1 -name 'linux-hwe-7.0_*.dsc' -print -quit)
    test -n "$descriptor"
    install -m 0644 "$descriptor" "$SOURCE/source-package.dsc"
    (cd "$SOURCE"; sha256sum mac80211_hwsim.c mac80211_hwsim.h > source.sha256)
fi

apply_patch_file()
{
    local patch_file=$1
    if patch -d "$SOURCE" -p5 --dry-run -N < "$patch_file" >/dev/null 2>&1; then
        patch -d "$SOURCE" -p5 -N < "$patch_file"
    elif patch -d "$SOURCE" -p5 --dry-run -R < "$patch_file" >/dev/null 2>&1; then
        echo "hwsim patch already applied: $(basename "$patch_file")"
    else
        echo "hwsim patch does not apply to $KVER source: $patch_file" >&2
        exit 1
    fi
}

# Patches 0001 and 0002 preserve the established multichannel/6 GHz lab.
# Patches 0003-0007 add an explicitly opt-in kernel data path, its dynamic
# link matrix, rate/PER and timing controls, observability, and the larger
# static-radio ceiling needed by scale profiles. Patch 0008 makes the
# userspace-medium monitor ACK path channel-context safe. Userspace wmediumd
# remains the default because kernel_medium defaults to false.
for patch_file in "$ROOT"/patches/hwsim/[0-9][0-9][0-9][0-9]-*.patch; do
    case "$(basename "$patch_file")" in
        0002-*)
            # Linux 7.0 regtest=5 already selects the strict, 6 GHz-capable
            # custom regulatory domain; the 6.8-only source change is skipped.
            continue
            ;;
    esac
    apply_patch_file "$patch_file"
done

grep -q 'EXPERIMENTAL wmediumd' "$SOURCE/mac80211_hwsim.c"
printf 'obj-m += mac80211_hwsim.o\n' > "$SOURCE/Makefile"
make -C "$KBUILD" M="$SOURCE" modules

cfg80211_options=()
if [ "${INSTALL_MODULE:-0}" = 1 ]; then
    cfg80211_options+=(--install)
fi
bash "$ROOT/scripts/cfg80211/build-cfg80211.sh" "$ROOT/build/cfg80211-source" "${cfg80211_options[@]}"

if [ "${INSTALL_MODULE:-0}" = 1 ]; then
    install -D -m 0644 "$SOURCE/mac80211_hwsim.ko" \
        "/lib/modules/$KVER/updates/mac80211_hwsim.ko"
    depmod -a "$KVER"
fi

if [ "${LOAD_MODULE:-0}" = 1 ]; then
    modprobe cfg80211
    if [ "$(cat /sys/module/cfg80211/version 2>/dev/null)" != lab-netns-owner-1 ]; then
        echo "Reboot the lab VM to load namespace-safe cfg80211 before loading hwsim." >&2
        exit 1
    fi
    modprobe -r mac80211_hwsim 2>/dev/null || true
    module_options=(
        "radios=${HWSIM_RADIOS:-120}"
        "channels=${HWSIM_CHANNELS:-3}"
        "regtest=${HWSIM_REGTEST:-5}"
    )
    if [ "${HWSIM_KERNEL_MEDIUM:-0}" = 1 ]; then
        module_options+=(
            kernel_medium=1
            "kernel_medium_cutoff=${HWSIM_KERNEL_MEDIUM_CUTOFF:--95}"
            "kernel_medium_loss_pct=${HWSIM_KERNEL_MEDIUM_LOSS_PCT:-0}"
            "kernel_medium_rate_per=${HWSIM_KERNEL_MEDIUM_RATE_PER:-0}"
            "kernel_medium_noise_floor=${HWSIM_KERNEL_MEDIUM_NOISE_FLOOR:--91}"
            "kernel_medium_delay_us=${HWSIM_KERNEL_MEDIUM_DELAY_US:-0}"
            "kernel_medium_jitter_us=${HWSIM_KERNEL_MEDIUM_JITTER_US:-0}"
            "kernel_medium_delay_queue_limit=${HWSIM_KERNEL_MEDIUM_QUEUE_LIMIT:-4096}"
        )
    fi
    modprobe mac80211_hwsim "${module_options[@]}"
fi

echo "Built $SOURCE/mac80211_hwsim.ko for $KVER"
