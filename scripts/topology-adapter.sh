#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CONTROLLER=prpl-controller
UNIT=prpl-topology-adapter.service
PROXY_UNIT=prpl-topology-adapter-proxy.service
PORT=${PRPL_TOPOLOGY_ADAPTER_PORT:-8092}
ACTION=${1:-status}

stop_visualizer()
{
    systemctl stop "$PROXY_UNIT" 2>/dev/null || true
    lxc exec "$CONTROLLER" -- systemctl stop "$UNIT" 2>/dev/null || true
}

stop_legacy_visualizer()
{
    # Releases before 0901 exposed a second topology page on port 8090.
    # Stop its proxy before the shared wmediumd Console claims that port.
    systemctl stop prpl-topology-proxy.service 2>/dev/null || true
    lxc exec "$CONTROLLER" -- systemctl stop prpl-topology.service \
        2>/dev/null || true
}

if [ "$ACTION" = restart ]; then
    stop_visualizer
    ACTION=start
fi

case "$ACTION" in
    start)
        stop_legacy_visualizer
        if lxc exec "$CONTROLLER" -- python3 -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=1)" \
                >/dev/null 2>&1 && \
           python3 -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=1)" \
                >/dev/null 2>&1; then
            echo "prplMesh internal topology adapter: http://127.0.0.1:${PORT}/api/topology"
            exit 0
        fi
        lxc exec "$CONTROLLER" -- systemctl stop "$UNIT" 2>/dev/null || true
        lxc exec "$CONTROLLER" -- systemd-run --unit "${UNIT%.service}" \
            --property Restart=on-failure \
            /usr/bin/python3 /mnt/project/topology-adapter/server.py \
            --listen 0.0.0.0 --port "$PORT" >/dev/null
        for unused in $(seq 1 50); do
            if lxc exec "$CONTROLLER" -- python3 -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=1)" \
                >/dev/null 2>&1; then
                break
            fi
            sleep 0.2
        done
        lxc exec "$CONTROLLER" -- python3 -c \
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=1)" \
            >/dev/null 2>&1 || {
                echo "topology adapter did not become ready" >&2
                exit 1
            }
        # The tabular/CSV address column can contain several interfaces and is
        # quoted when it spans lines.  Select the controller's management
        # address from structured state instead of depending on display order.
        target=$(lxc list "$CONTROLLER" --format json | python3 -c '
import json
import sys

network = json.load(sys.stdin)[0]["state"]["network"]
addresses = network.get("eth0", {}).get("addresses", [])
print(next(address["address"] for address in addresses
           if address.get("family") == "inet"
           and address.get("scope") == "global"))
')
        if [ -z "$target" ]; then
            echo "controller management address is unavailable" >&2
            exit 1
        fi
        systemctl stop "$PROXY_UNIT" 2>/dev/null || true
        systemd-run --unit "${PROXY_UNIT%.service}" --property Restart=on-failure \
            /usr/bin/python3 "$ROOT/topology-adapter/proxy.py" \
            --listen 127.0.0.1 --port "$PORT" --target-host "$target" \
            --target-port "$PORT" >/dev/null
        for unused in $(seq 1 50); do
            if python3 -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=1)" \
                >/dev/null 2>&1; then
                echo "prplMesh internal topology adapter: http://127.0.0.1:${PORT}/api/topology"
                exit 0
            fi
            sleep 0.2
        done
        echo "topology adapter proxy did not become ready" >&2
        exit 1
        ;;
    stop)
        stop_visualizer
        ;;
    status)
        systemctl --no-pager status "$PROXY_UNIT" || true
        lxc exec "$CONTROLLER" -- systemctl --no-pager status "$UNIT"
        ;;
    *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
