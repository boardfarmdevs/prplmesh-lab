#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
ACTION=${1:-status}
RUNTIME_IMAGE=prpl-runtime-local
CONTROLLER=prpl-controller
AGENT=prpl-agent-01
CLIENTS=(prpl-client-01 prpl-client-02 prpl-client-03)

ensure_network()
{
    lxc network show prplbh0 >/dev/null 2>&1 || \
        lxc network create prplbh0 ipv4.address=10.88.28.1/24 \
            ipv4.nat=false ipv6.address=none
}

create_node()
{
    local name=$1 first_radio=$2
    lxc info "$name" >/dev/null 2>&1 && return
    lxc init "$RUNTIME_IMAGE" "$name" -c security.privileged=true
    lxc config device add "$name" project disk source="$ROOT" path=/mnt/project
    lxc config device add "$name" backhaul nic network=prplbh0 name=eth1
    lxc config device add "$name" radio0 nic nictype=physical \
        parent="wlan$first_radio" name=wlan0
    lxc config device add "$name" radio1 nic nictype=physical \
        parent="wlan$((first_radio + 1))" name=wlan2
    lxc config device add "$name" radio2 nic nictype=physical \
        parent="wlan$((first_radio + 2))" name=wlan4
    lxc config set "$name" boot.autostart false
}

create_client()
{
    local name=$1 radio=$2
    lxc info "$name" >/dev/null 2>&1 && return
    lxc init "$RUNTIME_IMAGE" "$name" -c security.privileged=true
    lxc config device add "$name" project disk source="$ROOT" path=/mnt/project
    lxc config device add "$name" radio nic nictype=physical \
        parent="wlan$radio" name=wlan0
    lxc config set "$name" boot.autostart false
}

start_medium()
{
    if [ -r /run/prpl-wmediumd.pid ] && \
       kill -0 "$(cat /run/prpl-wmediumd.pid)" 2>/dev/null; then
        return
    fi
    "$ROOT/build/bin/wmediumd" -l 6 -c "$ROOT/manifests/wmediumd.conf" \
        > /tmp/prpl-wmediumd.log 2>&1 &
    echo $! > /run/prpl-wmediumd.pid
    sleep 1
    kill -0 "$(cat /run/prpl-wmediumd.pid)"
}

start_container()
{
    local name=$1
    if ! lxc info "$name" | grep -q '^Status: RUNNING$'; then
        lxc start "$name"
    fi
}

case "$ACTION" in
    deploy)
        ensure_network
        create_node "$CONTROLLER" 0
        create_node "$AGENT" 3
        create_client "${CLIENTS[0]}" 6
        create_client "${CLIENTS[1]}" 7
        create_client "${CLIENTS[2]}" 8
        ;;
    start)
        start_medium
        start_container "$CONTROLLER"
        lxc exec "$CONTROLLER" -- /mnt/project/scripts/container/setup-nl80211-node.sh controller
        sleep 5
        start_container "$AGENT"
        lxc exec "$AGENT" -- /mnt/project/scripts/container/setup-nl80211-node.sh agent
        ;;
    clients)
        bands=(2.4 5 5)
        for index in 0 1 2; do
            name=${CLIENTS[$index]}
            lxc start "$name" 2>/dev/null || true
            lxc exec "$name" -- /mnt/project/scripts/container/setup-client.sh \
                "$((index + 1))" "${bands[$index]}"
        done
        ;;
    stop)
        for name in "${CLIENTS[@]}" "$AGENT" "$CONTROLLER"; do
            lxc stop "$name" --timeout 30 2>/dev/null || true
        done
        if [ -r /run/prpl-wmediumd.pid ]; then
            kill "$(cat /run/prpl-wmediumd.pid)" 2>/dev/null || true
            rm -f /run/prpl-wmediumd.pid
        fi
        ;;
    status)
        lxc list '^prpl-(controller|agent|client)-' -c ns4
        if lxc info "$CONTROLLER" | grep -q RUNNING; then
            lxc exec "$CONTROLLER" -- \
                /opt/prpl-install-nl80211/bin/beerocks_cli -c bml_conn_map || true
        fi
        for name in "${CLIENTS[@]}"; do
            if lxc info "$name" | grep -q RUNNING; then
                echo "[$name]"
                lxc exec "$name" -- wpa_cli -i wlan0 status | \
                    grep -E '^(bssid|ssid|freq|wpa_state)=' || true
            fi
        done
        ;;
    *) echo "usage: $0 {deploy|start|clients|stop|status}" >&2; exit 2 ;;
esac
