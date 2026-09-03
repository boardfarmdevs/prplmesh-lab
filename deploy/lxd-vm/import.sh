#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -r "$SCRIPT_DIR/release.env" ]; then
    # shellcheck disable=SC1091
    . "$SCRIPT_DIR/release.env"
fi
usage()
{
    if [ "${LAB_PROFILE_SELECTABLE:-false}" = true ]; then
        echo "usage: $0 --profile 20|50|100 [PRPLMESH-LXD-BACKUP.tar.zst]" >&2
    else
        echo "usage: $0 [PRPLMESH-LXD-BACKUP.tar.zst]" >&2
    fi
}

SELECTED_CLIENTS=
BACKUP=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --profile)
            [ "$#" -ge 2 ] || { usage; exit 2; }
            SELECTED_CLIENTS=$2
            shift 2
            ;;
        -h|--help) usage; exit 0 ;;
        --)
            shift
            [ "$#" -le 1 ] || { usage; exit 2; }
            BACKUP=${1:-}
            shift "$#"
            ;;
        -*) echo "unknown option: $1" >&2; usage; exit 2 ;;
        *)
            [ -z "$BACKUP" ] || { usage; exit 2; }
            BACKUP=$1
            shift
            ;;
    esac
done

PROFILE_SELECTABLE=${LAB_PROFILE_SELECTABLE:-false}
RELEASE_ID=${LAB_RELEASE_ID:-0902}
case "$RELEASE_ID" in
    [0-9][0-9][0-9][0-9]) ;;
    *) echo "invalid LAB_RELEASE_ID: $RELEASE_ID" >&2; exit 2 ;;
esac
if [ "$PROFILE_SELECTABLE" = true ]; then
    case "$SELECTED_CLIENTS" in
        20) SELECTED_PROFILE=small; SELECTED_RADIOS=40; SELECTED_CPUS=6; SELECTED_MEMORY=8GiB ;;
        50) SELECTED_PROFILE=medium; SELECTED_RADIOS=72; SELECTED_CPUS=8; SELECTED_MEMORY=12GiB ;;
        100) SELECTED_PROFILE=stress; SELECTED_RADIOS=120; SELECTED_CPUS=12; SELECTED_MEMORY=20GiB ;;
        *)
            echo "the universal thin release requires --profile 20, 50 or 100" >&2
            usage
            exit 2
            ;;
    esac
    DEFAULT_NAME=prplmesh-${SELECTED_CLIENTS}-${RELEASE_ID}
else
    [ -z "$SELECTED_CLIENTS" ] || {
        echo "--profile is valid only for a profile-selectable thin release" >&2
        exit 2
    }
    SELECTED_CLIENTS=${LAB_CLIENTS:-unknown}
    SELECTED_PROFILE=${LAB_PROFILE:-unknown}
    SELECTED_RADIOS=${LAB_HWSIM_RADIOS:-unknown}
    SELECTED_CPUS=${LAB_DEFAULT_CPUS:-6}
    SELECTED_MEMORY=${LAB_DEFAULT_MEMORY:-8GiB}
    DEFAULT_NAME=${LAB_DEFAULT_NAME:-prplmesh-20-${RELEASE_ID}}
fi

if [ -z "$BACKUP" ]; then
    mapfile -t candidates < <(find "$SCRIPT_DIR" -maxdepth 1 -type f \
        -name '*.tar.zst' -printf '%p\n' | sort)
    [ "${#candidates[@]}" -eq 1 ] || {
        usage
        echo "automatic selection requires exactly one .tar.zst beside import.sh" >&2
        exit 2
    }
    BACKUP=${candidates[0]}
fi
NAME=${PRPLMESH_VM_NAME:-$DEFAULT_NAME}
NETWORK=${PRPLMESH_LXD_NETWORK:-lxdbr0}
HOST_IP=${PRPLMESH_UI_HOST_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null | \
    awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
HOST_IP=${HOST_IP:-127.0.0.1}
CONSOLE_PORT=${PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT:-8090}
UI_PORT=${PRPLMESH_UI_HOST_PORT:-8091}
STORAGE=${PRPLMESH_LXD_STORAGE:-}
NESTED_READY_ATTEMPTS=${PRPLMESH_NESTED_LXD_READY_ATTEMPTS:-120}
NESTED_READY_INTERVAL=${PRPLMESH_NESTED_LXD_READY_INTERVAL:-1}

case "$NESTED_READY_ATTEMPTS" in
    ''|*[!0-9]*|0)
        echo 'PRPLMESH_NESTED_LXD_READY_ATTEMPTS must be a positive integer' >&2
        exit 2
        ;;
esac
case "$NESTED_READY_INTERVAL" in
    ''|*[!0-9]*)
        echo 'PRPLMESH_NESTED_LXD_READY_INTERVAL must be a non-negative integer' >&2
        exit 2
        ;;
esac

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
import_args=()
if [ -n "$STORAGE" ]; then
    lxc storage show "$STORAGE" >/dev/null 2>&1 || {
        echo "LXD storage pool does not exist: $STORAGE" >&2
        exit 1
    }
    import_args+=(--storage "$STORAGE")
fi
# The portable package deliberately omits host-specific proxy devices.  Only
# override the archived NIC in the import transaction; naming a device that is
# absent from the backup makes LXD reject the import.  Fresh proxy devices are
# added below after the instance has a host-local address.
import_args+=(
    --device "eth0,network=$NETWORK"
    --device "eth0,ipv4.address=$guest_ip"
)

lxc import "$BACKUP" "$NAME" "${import_args[@]}"
instance_uuid=$(cat /proc/sys/kernel/random/uuid)
vsock_id=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')
lxc config unset "$NAME" volatile.eth0.hwaddr
lxc config set "$NAME" volatile.uuid "$instance_uuid"
lxc config set "$NAME" volatile.uuid.generation "$instance_uuid"
lxc config set "$NAME" volatile.cloud-init.instance-id "$instance_uuid"
lxc config set "$NAME" volatile.vsock_id "$vsock_id"
lxc config set "$NAME" limits.cpu "${PRPLMESH_VM_CPUS:-$SELECTED_CPUS}"
lxc config set "$NAME" limits.memory "${PRPLMESH_VM_MEMORY:-$SELECTED_MEMORY}"
lxc config set "$NAME" boot.autostart true
if lxc config set "$NAME" boot.mode uefi-nosecureboot 2>/dev/null; then
    lxc config unset "$NAME" security.secureboot 2>/dev/null || true
else
    lxc config set "$NAME" security.secureboot false
fi
if lxc config device show "$NAME" | grep -q '^canonical-source:'; then
    lxc config device remove "$NAME" canonical-source
fi
for device in topology-ui wmediumd-console controller-ui; do
    if lxc config device show "$NAME" | grep -q "^${device}:"; then
        lxc config device remove "$NAME" "$device"
    fi
done
lxc config device set "$NAME" eth0 network "$NETWORK"
lxc config device set "$NAME" eth0 ipv4.address "$guest_ip"
lxc start "$NAME"

agent_ready=false
for unused in $(seq 1 120); do
    if lxc exec "$NAME" -- true >/dev/null 2>&1; then
        agent_ready=true
        break
    fi
    sleep 1
done
[ "$agent_ready" = true ] || {
    echo "$NAME did not expose its LXD VM agent within 120 seconds" >&2
    exit 1
}

# LXD may assign a different address after the imported volatile NIC identity
# is replaced.  Discover the address actually selected by the running guest,
# then pin that address in the managed-network reservation before creating the
# host proxy devices.
runtime_guest_ip=
for unused in $(seq 1 120); do
    runtime_guest_ip=$(lxc exec "$NAME" -- ip -4 -o route get 1.1.1.1 \
        2>/dev/null | awk \
        '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}') || true
    [ -z "$runtime_guest_ip" ] || break
    sleep 1
done
[ -n "$runtime_guest_ip" ] || {
    echo "$NAME did not report a routed IPv4 address within 120 seconds" >&2
    exit 1
}
if [ "$runtime_guest_ip" != "$guest_ip" ]; then
    echo "guest address changed after NIC regeneration: $guest_ip -> $runtime_guest_ip"
    guest_ip=$runtime_guest_ip
    lxc config device set "$NAME" eth0 ipv4.address "$guest_ip"
fi

if [ "$PROFILE_SELECTABLE" = true ]; then
    nested_ready=false
    for unused in $(seq 1 "$NESTED_READY_ATTEMPTS"); do
        if lxc exec "$NAME" -- lxc query /1.0 >/dev/null 2>&1; then
            nested_ready=true
            break
        fi
        sleep "$NESTED_READY_INTERVAL"
    done
    [ "$nested_ready" = true ] || {
        echo "$NAME nested LXD did not become ready after $NESTED_READY_ATTEMPTS attempts" >&2
        exit 1
    }
    lxc exec "$NAME" -- /opt/prplmesh-lab/deploy/guest/select-thin-profile.sh \
        "$SELECTED_CLIENTS"
    lxc exec "$NAME" -- grep -Fx \
        "PROVISIONED_CLIENT_COUNT=$SELECTED_CLIENTS" \
        /var/lib/prplmesh-lab/thin-profile.lock.env >/dev/null
fi

# LXD virtual machines support only NAT-mode proxy devices. Connect each
# proxy to the selected static guest address rather than guest loopback.
lxc config device add "$NAME" wmediumd-console proxy nat=true \
    listen="tcp:${HOST_IP}:${CONSOLE_PORT}" connect="tcp:${guest_ip}:8090"
lxc config device add "$NAME" controller-ui proxy nat=true \
    listen="tcp:${HOST_IP}:${UI_PORT}" connect="tcp:${guest_ip}:8091"

if [ "$PROFILE_SELECTABLE" = true ]; then
    lxc exec "$NAME" -- systemctl reset-failed prplmesh-lab.service
    lxc exec "$NAME" -- systemctl --no-block start prplmesh-lab.service
fi

echo "LXD VM started: $NAME"
echo "profile:          $SELECTED_CLIENTS clients ($SELECTED_PROFILE), $SELECTED_RADIOS radios"
echo "wmediumd Console: http://${HOST_IP}:${CONSOLE_PORT}/"
echo "Controller UI:    http://${HOST_IP}:${UI_PORT}/"
echo "monitor: lxc exec $NAME -- journalctl -fu prplmesh-lab.service"
