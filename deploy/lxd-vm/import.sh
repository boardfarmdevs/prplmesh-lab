#!/bin/bash
set -euo pipefail

BACKUP=${1:?usage: import.sh PRPLMESH-LXD-BACKUP}
NAME=${PRPLMESH_VM_NAME:-prplmesh-lab-0829}
HOST_IP=${PRPLMESH_UI_HOST_IP:-127.0.0.1}
TOPOLOGY_PORT=${PRPLMESH_TOPOLOGY_HOST_PORT:-8090}
UI_PORT=${PRPLMESH_UI_HOST_PORT:-8091}

[ -r "$BACKUP" ] || { echo "backup is not readable: $BACKUP" >&2; exit 1; }
if lxc info "$NAME" >/dev/null 2>&1; then
    echo "LXD instance already exists: $NAME" >&2
    echo "stop and delete it explicitly before importing a replacement" >&2
    exit 1
fi

lxc import "$BACKUP" "$NAME"
lxc config set "$NAME" limits.cpu 6
lxc config set "$NAME" limits.memory 8GiB
if lxc config device show "$NAME" | grep -q '^canonical-source:'; then
    lxc config device remove "$NAME" canonical-source
fi
for device in topology-ui controller-ui; do
    if lxc config device show "$NAME" | grep -q "^${device}:"; then
        lxc config device remove "$NAME" "$device"
    fi
done
lxc start "$NAME"

# LXD virtual machines support only NAT-mode proxy devices. Pin the address
# assigned by lxdbr0, then connect each proxy to that address rather than to
# the guest loopback interface.
guest_ip=
for unused in $(seq 1 60); do
    guest_ip=$(lxc list "$NAME" -c 4 --format csv | \
        awk -F '[[:space:]]+[(]' '/[(]enp/ { print $1; exit }')
    [ -z "$guest_ip" ] || break
    sleep 2
done
[ -n "$guest_ip" ] || {
    echo "VM did not obtain an IPv4 address" >&2
    exit 1
}
lxc config device set "$NAME" eth0 ipv4.address "$guest_ip"
lxc config device add "$NAME" topology-ui proxy nat=true \
    listen="tcp:${HOST_IP}:${TOPOLOGY_PORT}" connect="tcp:${guest_ip}:8090"
lxc config device add "$NAME" controller-ui proxy nat=true \
    listen="tcp:${HOST_IP}:${UI_PORT}" connect="tcp:${guest_ip}:8091"

echo "LXD VM started: $NAME"
echo "topology adapter: http://${HOST_IP}:${TOPOLOGY_PORT}/"
echo "Controller UI:    http://${HOST_IP}:${UI_PORT}/"
echo "monitor: lxc exec $NAME -- journalctl -fu prplmesh-lab.service"
