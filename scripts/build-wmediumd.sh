#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
. "$ROOT/manifests/lab.env"
SOURCE=${WMEDIUMD_SOURCE_DIR:-$ROOT/build/wmediumd-source}
OUTPUT_DIR=${WMEDIUMD_OUTPUT_DIR:-$ROOT/build/bin}
UPSTREAM=https://github.com/bcopeland/wmediumd
OFFLINE=0
PATCHES=(
    0001-wmediumd-multichannel-per-freq-interference.patch
    0002-wmediumd-use-learned-vif-owner-for-delivery.patch
    0003-wmediumd-remove-per-frame-ack-file-logging.patch
    0004-wmediumd-schedule-independent-frequency-contexts.patch
    0005-wmediumd-handle-linux-7-rate-flags.patch
    0006-wmediumd-filter-multicast-by-frequency.patch
    0007-wmediumd-enlarge-netlink-receive-buffer.patch
    0008-wmediumd-add-atomic-scenario-control-socket.patch
    0009-wmediumd-honor-configured-default-snr.patch
    0010-wmediumd-require-tx-learning-before-multicast.patch
    0011-wmediumd-classify-transient-clone-rejections.patch
    0012-wmediumd-add-frequency-qualified-snr-control.patch
    0013-wmediumd-add-read-only-multi-client-metrics-socket.patch
    0014-wmediumd-add-bounded-observer-telemetry.patch
    0015-wmediumd-resolve-learned-vif-control-identities.patch
    0016-wmediumd-index-hot-path-lookups.patch
    0017-wmediumd-return-tx-frequency.patch
)

case "${1:-}" in
    --offline) OFFLINE=1 ;;
    '') ;;
    *) echo "usage: $0 [--offline]" >&2; exit 2 ;;
esac

if [ ! -d "$SOURCE/.git" ]; then
    [ "$OFFLINE" -eq 0 ] || {
        echo "offline wmediumd build requires an existing source cache: $SOURCE" >&2
        exit 1
    }
    mkdir -p "$(dirname "$SOURCE")"
    git clone "$UPSTREAM" "$SOURCE"
fi

if [ "$OFFLINE" -eq 1 ]; then
    git -C "$SOURCE" cat-file -e "$WMEDIUMD_COMMIT^{commit}" || {
        echo "offline wmediumd source cache lacks $WMEDIUMD_COMMIT" >&2
        exit 1
    }
else
    git -C "$SOURCE" fetch origin
fi
git -C "$SOURCE" checkout --detach "$WMEDIUMD_COMMIT"
git -C "$SOURCE" reset --hard "$WMEDIUMD_COMMIT"
git -C "$SOURCE" clean -fdx

for name in "${PATCHES[@]}"; do
    patch="$ROOT/patches/wmediumd/$name"
    git -C "$SOURCE" apply --check "$patch"
    git -C "$SOURCE" apply "$patch"
done

make -C "$SOURCE" -j"$(nproc)"
install -D -m 0755 "$SOURCE/wmediumd/wmediumd" \
    "$OUTPUT_DIR/wmediumd"
patchset_sha256=$(
    cd "$ROOT"
    sha256sum patches/wmediumd/*.patch | sha256sum | awk '{print $1}'
)
printf '%s\n' \
    "WMEDIUMD_COMMIT=$WMEDIUMD_COMMIT" \
    "WMEDIUMD_PATCHSET_SHA256=$patchset_sha256" \
    > "$OUTPUT_DIR/wmediumd.provenance.env"
echo "Built $OUTPUT_DIR/wmediumd from $WMEDIUMD_COMMIT"
