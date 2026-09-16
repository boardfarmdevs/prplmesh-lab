#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"
# shellcheck source=device-property.sh
source "$ROOT/deploy/lxd-vm/device-property.sh"
PROFILE=$(prplmesh_profile_name "${PRPLMESH_LAB_PROFILE:-unified}")
CLIENTS=$(prplmesh_profile_clients "$PROFILE")
RADIOS=$(prplmesh_profile_radios "$PROFILE")
NAME=${PRPLMESH_VM_NAME:-$(prplmesh_profile_release_name "$PROFILE")}
IMAGE=${PRPLMESH_VM_IMAGE:-ubuntu:24.04}
NETWORK=${PRPLMESH_LXD_NETWORK:-lxdbr0}
CPUS=${PRPLMESH_VM_CPUS:-$(prplmesh_profile_cpus "$PROFILE")}
MEMORY=${PRPLMESH_VM_MEMORY:-$(prplmesh_profile_memory "$PROFILE")}
DISK=${PRPLMESH_VM_DISK:-$(prplmesh_profile_disk "$PROFILE")}
KERNEL=${PRPLMESH_KERNEL:-7.0.0-30-generic}
HOST_IP=${PRPLMESH_UI_HOST_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null |
    awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
HOST_IP=${HOST_IP:-127.0.0.1}
CONSOLE_PORT=${PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT:-8090}
UI_PORT=${PRPLMESH_UI_HOST_PORT:-8091}
ROOM_PORT=${PRPLMESH_ROOM_DEMO_HOST_PORT:-18891}
RUNTIME_DEPS=${PRPL_RUNTIME_DEPS_ARCHIVE:-}
PRPL_INSTALL=${PRPL_INSTALL_ARCHIVE:-}
HOSTAP_RUNTIME=${PRPL_HOSTAP_ARCHIVE:-}

usage()
{
    cat <<EOF
usage: $0 {build|status|check|stop|start|restart|delete}

Clean-build inputs:
  PRPL_RUNTIME_DEPS_ARCHIVE=/path/to/prpl-runtime-deps-6.0.0.tar.gz
  PRPL_INSTALL_ARCHIVE=/path/to/prpl-install-nl80211-6.0.0.tar.gz
  PRPL_HOSTAP_ARCHIVE=/path/to/hostap-runtime-2.10.tar.gz

Site overrides:
  PRPLMESH_LAB_PROFILE=$CLIENTS (fixed capacity: 100 clients)
  PRPLMESH_VM_NAME=$NAME
  PRPLMESH_UI_HOST_IP=$HOST_IP
  PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT=$CONSOLE_PORT
  PRPLMESH_UI_HOST_PORT=$UI_PORT
  PRPLMESH_ROOM_DEMO_HOST_PORT=$ROOM_PORT
  PRPLMESH_LXD_STORAGE=<outer LXD storage pool>
EOF
}

exists() { lxc info "$NAME" >/dev/null 2>&1; }
state() { lxc info "$NAME" 2>/dev/null | sed -n 's/^Status: //p'; }

wait_agent()
{
    for unused in $(seq 1 120); do
        lxc exec "$NAME" -- true >/dev/null 2>&1 && return 0
        sleep 2
    done
    echo "$NAME did not expose its VM agent within 240 seconds" >&2
    return 1
}

select_guest_ipv4()
{
    local cidr used
    cidr=$(lxc network get "$NETWORK" ipv4.address)
    used=$(lxc network list-leases "$NETWORK" --format csv |
        awk -F, '$3 ~ /^[0-9]+\./ {print $3}' | paste -sd, -)
    python3 - "$cidr" "$used" <<'PY'
import ipaddress
import sys
network = ipaddress.ip_network(sys.argv[1], strict=False)
used = {ipaddress.ip_address(item) for item in sys.argv[2].split(",") if item}
for offset in range(5, min(network.num_addresses - 2, 256)):
    candidate = network.broadcast_address - offset
    if candidate not in used:
        print(candidate)
        break
else:
    raise SystemExit(f"no free appliance address on {network}")
PY
}

run()
{
    lxc exec "$NAME" -- "$@"
}

start_vm()
{
    exists
    [ "$(state)" = RUNNING ] || lxc start "$NAME"
    wait_agent
    run systemctl start prplmesh-lab.service
}

stop_vm()
{
    exists
    [ "$(state)" != RUNNING ] || lxc stop "$NAME" --timeout 300
}

check_vm() (
    local optimizer_pair optimizer_client optimizer_target
    start_vm || return
    restore_room=false
    trap 'result=$?; if "$restore_room"; then run systemctl start prplmesh-room-demo.service || result=$?; fi; exit "$result"' EXIT
    room_state=$(run systemctl show prplmesh-room-demo.service -p ActiveState --value)
    case "$room_state" in active|activating) restore_room=true ;; esac
    run systemctl stop prplmesh-room-demo.service || return
    run env PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT="$CLIENTS" PRPL_TOPOLOGY=star \
        PROVISIONED_CLIENT_COUNT="$CLIENTS" HWSIM_RADIOS="$RADIOS" \
        PRPL_WMEDIUMD_CONFIG=/var/lib/prplmesh-lab/wmediumd.conf \
        /opt/prplmesh-lab/tests/run-acceptance.sh || return
    optimizer_pair=$(run bash -c '
        set -eu
        inventory=$(mktemp /tmp/prpl-check-inventory.XXXXXX.json)
        trap "rm -f -- $inventory" EXIT
        cd /opt/prplmesh-lab/wmediumd/configurator
        python3 -m wmdcfg.cli inventory -o "$inventory" >/dev/null
        /opt/prplmesh-lab/deploy/lxd-vm/select-optimizer-stimulus.py \
            "$inventory" prpl-agent-02
    ') || return
    read -r optimizer_client optimizer_target <<<"$optimizer_pair"
    echo "optimizer acceptance pair: $optimizer_client -> $optimizer_target"
    run env PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT="$CLIENTS" PRPL_TOPOLOGY=star \
        PROVISIONED_CLIENT_COUNT="$CLIENTS" HWSIM_RADIOS="$RADIOS" \
        PRPL_WMEDIUMD_CONFIG=/var/lib/prplmesh-lab/wmediumd.conf \
        /opt/prplmesh-lab/tests/optimizer-dynamic.sh recommend \
        "$optimizer_client" "$optimizer_target"
)

build_vm()
{
    local stage bundle commit guest_ip artifact storage_pool boot_mode_error
    [ -z "$(git -C "$ROOT" status --porcelain)" ] || {
        echo "source checkout must be clean" >&2
        exit 1
    }
    for artifact in "$RUNTIME_DEPS" "$PRPL_INSTALL" "$HOSTAP_RUNTIME"; do
        [ -f "$artifact" ] || {
            echo "all three PRPL_*_ARCHIVE inputs are required" >&2
            exit 2
        }
    done
    exists && {
        echo "$NAME already exists; delete it explicitly before a clean build" >&2
        exit 1
    }
    storage_pool=${PRPLMESH_LXD_STORAGE:-${PRPLMESH_LXD_STORAGE_POOL:-$(lxc profile device get default root pool)}}
    [ -n "$storage_pool" ] || {
        echo "cannot determine the LXD storage pool from the default profile" >&2
        exit 2
    }
    "$ROOT/deploy/lxd-vm/storage-preflight.sh" "$PROFILE" "$storage_pool"

    stage=$(mktemp -d /tmp/prplmesh-lxd-build.XXXXXX)
    trap "rm -rf -- '$stage'" EXIT
    bundle="$stage/prplmesh-lab.bundle"
    commit=$(git -C "$ROOT" rev-parse HEAD)
    git -C "$ROOT" bundle create "$bundle" HEAD
    git bundle verify "$bundle" >/dev/null
    cp --reflink=auto "$RUNTIME_DEPS" "$PRPL_INSTALL" "$HOSTAP_RUNTIME" "$stage/"
    (
        cd "$stage"
        sha256sum prplmesh-lab.bundle \
            "$(basename "$RUNTIME_DEPS")" \
            "$(basename "$PRPL_INSTALL")" \
            "$(basename "$HOSTAP_RUNTIME")" > SHA256SUMS
    )

    lxc init "$IMAGE" "$NAME" --vm --storage "$storage_pool" \
        --config limits.cpu="$CPUS" --config limits.memory="$MEMORY" </dev/null
    if ! boot_mode_error=$(lxc config set "$NAME" boot.mode uefi-nosecureboot 2>&1); then
        case "$boot_mode_error" in
            *'"boot.mode" is not supported'*)
                lxc config set "$NAME" security.secureboot false
                ;;
            *)
                echo "$boot_mode_error" >&2
                exit 1
                ;;
        esac
    fi
    lxc config set "$NAME" boot.autostart false
    lxd_set_device_property "$NAME" root size "$DISK"
    guest_ip=$(select_guest_ipv4)
    lxd_set_device_property "$NAME" eth0 network "$NETWORK"
    lxd_set_device_property "$NAME" eth0 ipv4.address "$guest_ip"
    lxc config device add "$NAME" wmediumd-console proxy nat=true \
        listen="tcp:$HOST_IP:$CONSOLE_PORT" connect="tcp:$guest_ip:8090"
    lxc config device add "$NAME" controller-ui proxy nat=true \
        listen="tcp:$HOST_IP:$UI_PORT" connect="tcp:$guest_ip:8091"
    lxc config device add "$NAME" room-demo-viewer proxy nat=true \
        listen="tcp:$HOST_IP:$ROOM_PORT" connect="tcp:$guest_ip:8891"
    lxc start "$NAME"
    wait_agent

    run env DEBIAN_FRONTEND=noninteractive bash -c '
        apt-get update
        apt-get install -y --no-install-recommends ca-certificates curl git zstd
    '
    run env DEBIAN_FRONTEND=noninteractive bash -c \
        "apt-get install -y --no-install-recommends linux-image-$KERNEL linux-modules-$KERNEL linux-headers-$KERNEL"
    run update-initramfs -u -k "$KERNEL"
    run update-grub
    lxc restart "$NAME" --timeout 300
    wait_agent
    [ "$(run uname -r)" = "$KERNEL" ]

    run install -d /opt/prplmesh-stage /opt/prplmesh-lab
    for artifact in "$stage"/*; do
        lxc file push "$artifact" "$NAME/opt/prplmesh-stage/$(basename "$artifact")"
    done
    run bash -c '
        cd /opt/prplmesh-stage
        sha256sum -c SHA256SUMS
        rm -rf /opt/prplmesh-lab
        git clone prplmesh-lab.bundle /opt/prplmesh-lab
    '
    [ "$(run git -C /opt/prplmesh-lab rev-parse HEAD)" = "$commit" ]
    run install -d -m 0755 /var/lib/prplmesh-lab
    run python3 /opt/prplmesh-lab/scripts/generate-wmediumd-config.py \
        --radios "$RADIOS" --output /var/lib/prplmesh-lab/wmediumd.conf
    run bash -c "cat > /etc/default/prplmesh-lab <<'EOF'
PRPLMESH_LAB_PROFILE=$PROFILE
PROVISIONED_AGENT_COUNT=4
PROVISIONED_CLIENT_COUNT=$CLIENTS
ACTIVE_AGENT_COUNT=4
ACTIVE_CLIENT_COUNT=$CLIENTS
DEFAULT_TOPOLOGY=star
HWSIM_RADIOS=$RADIOS
HWSIM_CHANNELS=3
PRPLMESH_APPLIANCE_WMEDIUMD_CONFIG=/var/lib/prplmesh-lab/wmediumd.conf
EOF"
    run install -m 0644 "/opt/prplmesh-stage/$(basename "$RUNTIME_DEPS")" \
        /opt/prplmesh-lab/artifacts/prpl-runtime-deps-6.0.0.tar.gz
    run install -m 0644 "/opt/prplmesh-stage/$(basename "$PRPL_INSTALL")" \
        /opt/prplmesh-lab/artifacts/prpl-install-nl80211-6.0.0.tar.gz
    run install -m 0644 "/opt/prplmesh-stage/$(basename "$HOSTAP_RUNTIME")" \
        /opt/prplmesh-lab/artifacts/hostap-runtime-2.10.tar.gz
    run bash -c '
        cd /opt/prplmesh-lab/artifacts
        sha256sum *.tar.gz > SHA256SUMS
    '

    run env DEBIAN_FRONTEND=noninteractive bash -c '
        apt-get update
        apt-get install -y build-essential ca-certificates curl dpkg-dev git golang-go iperf3 iproute2 iptables iputils-ping iw jq \
          libconfig-dev libnl-3-dev libnl-genl-3-dev libnl-route-3-dev meson \
          nftables ninja-build patch pkg-config python3 python3-venv rsync snapd util-linux
        sed "s/^Types: deb$/Types: deb-src/" /etc/apt/sources.list.d/ubuntu.sources \
          > /etc/apt/sources.list.d/prplmesh-src.sources
        apt-get update
        snap list lxd >/dev/null 2>&1 || snap install lxd
        snap start lxd
        lxd waitready
        lxc storage show default >/dev/null 2>&1 || lxd init --auto --storage-backend dir </dev/null
    '
    run bash /opt/prplmesh-lab/scripts/install-from-artifacts.sh
    run bash /opt/prplmesh-lab/controller-ui/install.sh
    run bash /opt/prplmesh-lab/deploy/guest/prepare-appliance.sh /opt/prplmesh-lab
    run rm -rf /opt/prplmesh-stage
    run systemctl start prplmesh-lab.service
    check_vm
    # package.sh reruns acceptance and exports only the instance. Avoid a
    # full disk copy on non-copy-on-write outer storage pools.
    trap - EXIT
    rm -rf -- "$stage"
}

case "${1:-}" in
    build) build_vm ;;
    status) exists; lxc list "$NAME" -c nst4m; [ "$(state)" != RUNNING ] || run prplmesh-lab-start status ;;
    check) check_vm ;;
    start) start_vm ;;
    stop) stop_vm ;;
    restart) stop_vm; start_vm ;;
    delete) exists; lxc list "$NAME" -c nst4m; lxc delete "$NAME" --force ;;
    -h|--help|help|'') usage ;;
    *) usage >&2; exit 2 ;;
esac
