#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE="$ROOT/build/wmediumd-source"
UPSTREAM=https://github.com/bcopeland/wmediumd
COMMIT=717e5d7fcc23eecbc8e32bd897a8fd4b1e3ba640
PATCHES=(
    0001-wmediumd-multichannel-per-freq-interference.patch
    0002-wmediumd-use-learned-vif-owner-for-delivery.patch
    0003-wmediumd-remove-per-frame-ack-file-logging.patch
    0004-wmediumd-schedule-independent-frequency-contexts.patch
    0005-wmediumd-handle-linux-7-rate-flags.patch
    0006-wmediumd-filter-multicast-by-frequency.patch
    0007-wmediumd-enlarge-netlink-receive-buffer.patch
    0009-wmediumd-honor-configured-default-snr.patch
    0010-wmediumd-require-tx-learning-before-multicast.patch
    0011-wmediumd-classify-transient-clone-rejections.patch
)

if [ ! -d "$SOURCE/.git" ]; then
    mkdir -p "$(dirname "$SOURCE")"
    git clone "$UPSTREAM" "$SOURCE"
fi

git -C "$SOURCE" fetch origin
git -C "$SOURCE" reset --hard "$COMMIT"
git -C "$SOURCE" clean -fdx

for name in "${PATCHES[@]}"; do
    patch="$ROOT/patches/wmediumd/$name"
    git -C "$SOURCE" apply --check "$patch"
    git -C "$SOURCE" apply "$patch"
done

make -C "$SOURCE" -j"$(nproc)"
install -D -m 0755 "$SOURCE/wmediumd/wmediumd" \
    "$ROOT/build/bin/wmediumd"
echo "Built $ROOT/build/bin/wmediumd from $COMMIT"
