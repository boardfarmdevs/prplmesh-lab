#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=${PRPLMESH_VM_NAME:-prplmesh-lab-0828}
OUTPUT_DIR=${1:-$ROOT/release/0828}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
OUTPUT="$OUTPUT_DIR/prplmesh-lab-0828-${SHORT}-lxd.tar.zst"
WAS_RUNNING=false

mkdir -p "$OUTPUT_DIR"
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

rm -f "$OUTPUT" "$OUTPUT.sha256"
lxc export "$NAME" "$OUTPUT" --instance-only
(cd "$OUTPUT_DIR" && sha256sum "$(basename "$OUTPUT")" > "$(basename "$OUTPUT").sha256")
echo "$OUTPUT"
