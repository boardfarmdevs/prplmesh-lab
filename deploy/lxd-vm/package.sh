#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=${PRPLMESH_VM_NAME:-prplmesh-lab-0829}
OUTPUT_DIR=${1:-$ROOT/release/0829}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
BUNDLE="$OUTPUT_DIR/prplmesh-lab-0829-${SHORT}-lxd"
OUTPUT="$BUNDLE/prplmesh-lab-0829-${SHORT}-lxd.tar.zst"
WAS_RUNNING=false

rm -rf -- "$BUNDLE"
mkdir -p "$BUNDLE"
[ "$(lxc list "$NAME" -c t --format csv)" = VIRTUAL-MACHINE ] || {
    echo "not an LXD VM: $NAME" >&2
    exit 1
}

if [ "$(lxc list "$NAME" -c s --format csv)" = RUNNING ]; then
    WAS_RUNNING=true
    lxc exec "$NAME" -- systemctl stop prplmesh-lab.service 2>/dev/null || true
    lxc stop "$NAME" --timeout 120
fi
restart()
{
    [ "$WAS_RUNNING" = true ] && lxc start "$NAME" || true
}
trap restart EXIT

lxc export "$NAME" "$OUTPUT" --instance-only --compression zstd
install -m 0755 "$ROOT/deploy/lxd-vm/import.sh" "$BUNDLE/import.sh"
install -m 0755 "$ROOT/deploy/lxd-vm/install-host.sh" "$BUNDLE/install-host.sh"
install -m 0644 "$ROOT/deploy/lxd-vm/README.md" "$BUNDLE/README.md"
(
    cd "$BUNDLE"
    sha256sum "$(basename "$OUTPUT")" import.sh install-host.sh README.md \
        > SHA256SUMS
)
echo "$BUNDLE"
