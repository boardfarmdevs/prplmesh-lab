#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -r "$SCRIPT_DIR/release.env" ]; then
    # shellcheck disable=SC1091
    . "$SCRIPT_DIR/release.env"
fi
BACKUP=${1:-}
if [ -z "$BACKUP" ]; then
    mapfile -t candidates < <(find "$SCRIPT_DIR" -maxdepth 1 -type f \
        -name '*.tar.zst' -printf '%p\n' | sort)
    [ "${#candidates[@]}" -eq 1 ] || {
        echo "usage: $0 PRPLMESH-LXD-BACKUP.tar.zst" >&2
        echo "automatic selection requires exactly one .tar.zst beside import.sh" >&2
        exit 2
    }
    BACKUP=${candidates[0]}
fi
NAME=${PRPLMESH_VM_NAME:-${LAB_DEFAULT_NAME:-prplmesh-20-0829}}
NETWORK=${PRPLMESH_LXD_NETWORK:-lxdbr0}
HOST_IP=${PRPLMESH_UI_HOST_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null | \
    awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
HOST_IP=${HOST_IP:-127.0.0.1}
TOPOLOGY_PORT=${PRPLMESH_TOPOLOGY_HOST_PORT:-8090}
UI_PORT=${PRPLMESH_UI_HOST_PORT:-8091}

[ -c /dev/kvm ] || { echo "/dev/kvm is unavailable; enable hardware virtualization" >&2; exit 1; }
command -v lxc >/dev/null 2>&1 || { echo "lxc is not installed; run install-host.sh" >&2; exit 1; }
[ -r "$BACKUP" ] || { echo "backup is not readable: $BACKUP" >&2; exit 1; }
lxc network show "$NETWORK" >/dev/null 2>&1 || {
    echo "LXD network does not exist: $NETWORK" >&2
    exit 1
}
if lxc info "$NAME" >/dev/null 2>&1; then
    echo "LXD instance already exists: $NAME" >&2
    echo "stop and delete it explicitly before importing a replacement" >&2
    exit 1
fi

lxc import "$BACKUP" "$NAME"
instance_uuid=$(cat /proc/sys/kernel/random/uuid)
vsock_id=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')
lxc config unset "$NAME" volatile.eth0.hwaddr
lxc config set "$NAME" volatile.uuid "$instance_uuid"
lxc config set "$NAME" volatile.uuid.generation "$instance_uuid"
lxc config set "$NAME" volatile.cloud-init.instance-id "$instance_uuid"
lxc config set "$NAME" volatile.vsock_id "$vsock_id"
lxc config set "$NAME" limits.cpu "${PRPLMESH_VM_CPUS:-${LAB_DEFAULT_CPUS:-6}}"
lxc config set "$NAME" limits.memory "${PRPLMESH_VM_MEMORY:-${LAB_DEFAULT_MEMORY:-8GiB}}"
lxc config set "$NAME" boot.autostart true
if lxc config device show "$NAME" | grep -q '^canonical-source:'; then
    lxc config device remove "$NAME" canonical-source
fi
for device in topology-ui controller-ui; do
    if lxc config device show "$NAME" | grep -q "^${device}:"; then
        lxc config device remove "$NAME" "$device"
    fi
done
lxc_cidr=$(lxc network get "$NETWORK" ipv4.address)
used=$(lxc network list-leases "$NETWORK" --format csv \
    | awk -F, '$3 ~ /^[0-9]+\./ {print $3}' | paste -sd, -)
guest_ip=$(python3 - "$lxc_cidr" "$used" <<'PY'
import ipaddress
import sys

network = ipaddress.ip_network(sys.argv[1], strict=False)
used = {ipaddress.ip_address(value) for value in sys.argv[2].split(",") if value}
for offset in range(5, min(network.num_addresses - 2, 256)):
    candidate = network.broadcast_address - offset
    if candidate not in used:
        print(candidate)
        break
else:
    raise SystemExit(f"no free appliance address found near the end of {network}")
PY
)
lxc config device set "$NAME" eth0 network "$NETWORK"
lxc config device set "$NAME" eth0 ipv4.address "$guest_ip"
lxc start "$NAME"

# LXD virtual machines support only NAT-mode proxy devices. Connect each
# proxy to the selected static guest address rather than guest loopback.
lxc config device add "$NAME" topology-ui proxy nat=true \
    listen="tcp:${HOST_IP}:${TOPOLOGY_PORT}" connect="tcp:${guest_ip}:8090"
lxc config device add "$NAME" controller-ui proxy nat=true \
    listen="tcp:${HOST_IP}:${UI_PORT}" connect="tcp:${guest_ip}:8091"

echo "LXD VM started: $NAME"
echo "profile:          ${LAB_CLIENTS:-unknown} clients (${LAB_PROFILE:-unknown})"
echo "topology adapter: http://${HOST_IP}:${TOPOLOGY_PORT}/"
echo "Controller UI:    http://${HOST_IP}:${UI_PORT}/"
echo "monitor: lxc exec $NAME -- journalctl -fu prplmesh-lab.service"
