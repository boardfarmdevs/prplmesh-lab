#!/usr/bin/env bash

prplmesh_instance_config()
{
    local name=${1:-${PRPLMESH_VM_NAME:-prplmesh}} port variable
    [[ $name =~ ^[a-zA-Z][a-zA-Z0-9-]{0,47}$ && $name != *- ]] || {
        echo 'VM name must start with a letter, contain only letters/digits/hyphens, and not end in a hyphen (maximum 48 characters).' >&2
        return 2
    }
    export PRPLMESH_VM_NAME=$name
    export PRPLMESH_LXD_STORAGE=${PRPLMESH_LXD_STORAGE:-${PRPLMESH_LXD_STORAGE_POOL:-$name-pool}}
    [[ $PRPLMESH_LXD_STORAGE =~ ^[a-zA-Z][a-zA-Z0-9_.-]{0,62}$ ]] || {
        echo 'Invalid LXD storage pool name.' >&2
        return 2
    }
    export PRPLMESH_PORT_BASE=${PRPLMESH_PORT_BASE:-$(python3 - "$name" <<'PY'
import hashlib
import sys
print(40000 + int(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8], 16) % 1600 * 6)
PY
)}
    [[ $PRPLMESH_PORT_BASE =~ ^[1-9][0-9]{3,4}$ ]] && (( PRPLMESH_PORT_BASE <= 65530 )) || {
        echo 'PRPLMESH_PORT_BASE must be between 1024 and 65530.' >&2
        return 2
    }
    (( PRPLMESH_PORT_BASE >= 1024 )) || return 2
    export PRPLMESH_UI_HOST_PORT=${PRPLMESH_UI_HOST_PORT:-$PRPLMESH_PORT_BASE}
    export PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT=${PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT:-$((PRPLMESH_PORT_BASE + 1))}
    export PRPLMESH_ROOM_DEMO_HOST_PORT=${PRPLMESH_ROOM_DEMO_HOST_PORT:-$((PRPLMESH_PORT_BASE + 2))}
    export LAB_LXD_UI_PORT=${LAB_LXD_UI_PORT:-$((PRPLMESH_PORT_BASE + 3))}
    export LAB_GRAFANA_PORT=${LAB_GRAFANA_PORT:-$((PRPLMESH_PORT_BASE + 4))}
    export LAB_OUTER_METRICS_PORT=${LAB_OUTER_METRICS_PORT:-$((PRPLMESH_PORT_BASE + 5))}
    local -A selected=()
    for variable in PRPLMESH_UI_HOST_PORT PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT PRPLMESH_ROOM_DEMO_HOST_PORT LAB_LXD_UI_PORT LAB_GRAFANA_PORT LAB_OUTER_METRICS_PORT; do
        port=${!variable}
        [[ $port =~ ^[1-9][0-9]{3,4}$ ]] && (( port >= 1024 && port <= 65535 )) || {
            echo "Invalid TCP port: $variable=$port" >&2
            return 2
        }
        [[ ! ${selected[$port]+present} ]] || { echo "Duplicate TCP port: $port" >&2; return 2; }
        selected[$port]=$variable
    done
}

prplmesh_ensure_storage()
{
    local pool=$1 driver=${PRPLMESH_STORAGE_DRIVER:-dir}
    lxc storage show "$pool" >/dev/null 2>&1 && return 0
    case "$driver" in
        dir) lxc storage create "$pool" dir ;;
        zfs|btrfs) lxc storage create "$pool" "$driver" size="${PRPLMESH_STORAGE_SIZE:-240GiB}" ;;
        *) echo 'Automatic pools support dir, zfs or btrfs; create other pools explicitly first.' >&2; return 2 ;;
    esac
}

prplmesh_check_ports()
{
    local inventory
    inventory=$(lxc list --format json) || return
    PRPL_INSTANCE_INVENTORY=$inventory python3 - <<'PY'
import json
import os
import socket
ports = {int(os.environ[key]) for key in (
    'PRPLMESH_UI_HOST_PORT', 'PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT',
    'PRPLMESH_ROOM_DEMO_HOST_PORT', 'LAB_LXD_UI_PORT', 'LAB_GRAFANA_PORT', 'LAB_OUTER_METRICS_PORT')}
for instance in json.loads(os.environ['PRPL_INSTANCE_INVENTORY']):
    for device in instance.get('expanded_devices', {}).values():
        listen = device.get('listen', '')
        if device.get('type') == 'proxy' and listen.startswith('tcp:'):
            try:
                port = int(listen.rsplit(':', 1)[1])
            except ValueError:
                continue
            if port in ports:
                raise SystemExit(f"Port {port} is reserved by {instance['name']}; select another PRPLMESH_PORT_BASE.")
for port in ports:
    with socket.socket() as listener:
        try:
            listener.bind((os.environ.get('PRPLMESH_UI_HOST_IP', '0.0.0.0'), port))
        except OSError as error:
            raise SystemExit(f'Port {port} is unavailable: {error}; select another PRPLMESH_PORT_BASE.')
PY
}
