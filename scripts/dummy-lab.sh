#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/manifests/lab.env"
ACTION=${1:-status}

create_runtime_container()
{
    name=$1
    if lxc info "$name" >/dev/null 2>&1; then
        return
    fi
    lxc copy "$BUILD_CONTAINER" "$name"
    lxc config device add "$name" eth0 nic network="$MANAGEMENT_NETWORK" name=eth0
    lxc config device add "$name" backhaul nic network="$BACKHAUL_NETWORK" name=eth1
    lxc config set "$name" boot.autostart false
}

case "$ACTION" in
    deploy)
        lxc stop "$BUILD_CONTAINER" --timeout 30 2>/dev/null || true
        create_runtime_container "$CONTROLLER_CONTAINER"
        create_runtime_container "$AGENT_CONTAINER"
        ;;
    start)
        for name in "$CONTROLLER_CONTAINER" "$AGENT_CONTAINER"; do
            lxc start "$name" 2>/dev/null || true
            lxc file push "$ROOT/scripts/container/setup-dummy.sh" \
                "$name/root/setup-dummy.sh" --mode=0755
        done
        lxc exec "$CONTROLLER_CONTAINER" -- /root/setup-dummy.sh controller
        lxc exec "$AGENT_CONTAINER" -- /root/setup-dummy.sh agent
        ;;
    stop)
        for name in "$AGENT_CONTAINER" "$CONTROLLER_CONTAINER"; do
            lxc exec "$name" -- /opt/prpl-install-dummy/scripts/prplmesh_utils.sh stop 2>/dev/null || true
            lxc stop "$name" --timeout 30 2>/dev/null || true
        done
        ;;
    status)
        lxc list "$CONTROLLER_CONTAINER" "$AGENT_CONTAINER" -c ns4
        if lxc info "$CONTROLLER_CONTAINER" | grep -q RUNNING; then
            lxc exec "$CONTROLLER_CONTAINER" -- \
                /opt/prpl-install-dummy/scripts/prplmesh_utils.sh status
        fi
        ;;
    *) echo "usage: $0 {deploy|start|stop|status}" >&2; exit 2 ;;
esac
