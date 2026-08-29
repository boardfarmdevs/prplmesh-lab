#!/bin/bash
set -euo pipefail

BACKUP=${1:?usage: import.sh PRPLMESH-LXD-BACKUP}
NAME=${PRPLMESH_VM_NAME:-prplmesh-lab-0828}
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
lxc config device add "$NAME" topology-ui proxy \
    listen="tcp:${HOST_IP}:${TOPOLOGY_PORT}" connect=tcp:127.0.0.1:8090
lxc config device add "$NAME" controller-ui proxy \
    listen="tcp:${HOST_IP}:${UI_PORT}" connect=tcp:127.0.0.1:8091
lxc start "$NAME"

echo "LXD VM started: $NAME"
echo "topology adapter: http://${HOST_IP}:${TOPOLOGY_PORT}/"
echo "Controller UI:    http://${HOST_IP}:${UI_PORT}/"
echo "monitor: lxc exec $NAME -- journalctl -fu prplmesh-lab.service"
