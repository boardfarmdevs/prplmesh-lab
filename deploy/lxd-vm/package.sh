#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=${PRPLMESH_VM_NAME:-prplmesh-lab-0829}
OUTPUT_DIR=${1:-$ROOT/release/0829}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
BUNDLE="$OUTPUT_DIR/prplmesh-lab-0829-${SHORT}-lxd"
OUTPUT="$BUNDLE/prplmesh-lab-0829-${SHORT}-lxd.tar.zst"
WAS_RUNNING=false

[ -z "$(git -C "$ROOT" status --porcelain)" ] || {
    echo "source checkout must be clean before packaging" >&2
    exit 1
}
rm -rf -- "$BUNDLE"
mkdir -p "$BUNDLE"
[ "$(lxc list "$NAME" -c t --format csv)" = VIRTUAL-MACHINE ] || {
    echo "not an LXD VM: $NAME" >&2
    exit 1
}
[ "$(lxc list "$NAME" -c s --format csv)" != RUNNING ] || WAS_RUNNING=true

if lxc config device show "$NAME" | awk '
    /^[^[:space:]].*:$/ {device=$1; sub(/:$/, "", device); type=""; source=""}
    /^[[:space:]]+type:/ {type=$2}
    /^[[:space:]]+source:/ {source=$2}
    type == "disk" && source ~ /^\// && device != "root" {found=1}
    END {exit !found}
'; then
    echo "$NAME has a host filesystem mount; it is not a portable appliance" >&2
    exit 1
fi

if [ "$(lxc list "$NAME" -c s --format csv)" != RUNNING ]; then
    lxc start "$NAME"
fi
for unused in $(seq 1 120); do
    lxc exec "$NAME" -- true >/dev/null 2>&1 && break
    sleep 2
done
guest_commit=$(lxc exec "$NAME" -- git -C /opt/prplmesh-lab rev-parse HEAD)
[ "$guest_commit" = "$(git -C "$ROOT" rev-parse HEAD)" ] || {
    echo "guest source $guest_commit does not match release source" >&2
    exit 1
}
PRPLMESH_VM_NAME="$NAME" "$ROOT/deploy/lxd-vm/build.sh" check

if [ "$(lxc list "$NAME" -c s --format csv)" = RUNNING ]; then
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
