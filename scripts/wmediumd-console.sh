#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
if [ -r /etc/default/prplmesh-lab ]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/default/prplmesh-lab
    set +a
fi
# shellcheck source=../manifests/lab.env
source "$ROOT/manifests/lab.env"

ACTION=${1:-status}
RUNTIME=${PRPL_WMEDIUMD_RUNTIME:-/run/prpl-wmediumd}
OBSERVER=${PRPL_WMEDIUMD_OBSERVER:-$RUNTIME/telemetry.sock}
INVENTORY=$RUNTIME/identity-inventory.json
CONFIG_SNAPSHOT=$RUNTIME/wmediumd.conf
DAEMON_MANIFEST=$RUNTIME/wmediumd-binary.sha256
PIDFILE=$RUNTIME/wmediumd.pid
READY=http://127.0.0.1:8090/
HEALTH=http://127.0.0.1:8090/api/v1/health

publish_runtime_metadata()
{
    local config pid executable sha256
    config=${PRPL_WMEDIUMD_CONFIG:-${PRPLMESH_APPLIANCE_WMEDIUMD_CONFIG:-$ROOT/manifests/wmediumd.conf}}
    if [ -r "$config" ]; then
        install -m 0644 "$config" "$CONFIG_SNAPSHOT"
    fi
    [ -r "$PIDFILE" ] || return 0
    pid=$(cat "$PIDFILE")
    [ -e "/proc/$pid/exe" ] || return 0
    executable=$(readlink -f "/proc/$pid/exe")
    sha256=$(sha256sum "$executable" | awk '{print $1}')
    printf '%s\t%s\t%s\n' "$pid" "$sha256" "$executable" \
        > "$DAEMON_MANIFEST"
    chmod 0644 "$DAEMON_MANIFEST"
}

start_console()
{
    getent group wmediumd-console >/dev/null || {
        echo 'wmediumd-console service is not installed' >&2
        return 1
    }
    publish_runtime_metadata
    python3 "$ROOT/scripts/generate-wmediumd-identity-inventory.py" \
        --radios "$HWSIM_RADIOS" \
        --agents "$PROVISIONED_AGENT_COUNT" \
        --clients "$PROVISIONED_CLIENT_COUNT" \
        --radios-per-node "$RADIOS_PER_MESH_NODE" \
        --output "$INVENTORY"
    chgrp wmediumd-console "$INVENTORY"
    chmod 0640 "$INVENTORY"
    if [ -S "$OBSERVER" ]; then
        chgrp wmediumd-console "$OBSERVER"
        chmod 0660 "$OBSERVER"
    fi
    systemctl restart wmediumd-console.service
    for unused in $(seq 1 30); do
        curl -fsS "$READY" >/dev/null 2>&1 && {
            echo 'wmediumd Console: http://127.0.0.1:8090/'
            return 0
        }
        sleep 1
    done
    echo 'wmediumd Console did not become ready' >&2
    systemctl --no-pager --full status wmediumd-console.service >&2 || true
    return 1
}

case "$ACTION" in
    start|restart) start_console ;;
    stop) systemctl stop wmediumd-console.service 2>/dev/null || true ;;
    status)
        systemctl --no-pager --full status wmediumd-console.service || true
        curl -fsS "$HEALTH" || true
        ;;
    *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
