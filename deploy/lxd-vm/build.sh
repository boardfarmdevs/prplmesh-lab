#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"
# shellcheck source=device-property.sh
source "$ROOT/deploy/lxd-vm/device-property.sh"
source "$ROOT/deploy/lxd-vm/instance-config.sh"
# shellcheck source=artifact-store.sh
source "$ROOT/deploy/lxd-vm/artifact-store.sh"
# shellcheck source=native-inputs.sh
source "$ROOT/deploy/lxd-vm/native-inputs.sh"
prplmesh_instance_config
PROFILE=$(prplmesh_profile_name "${PRPLMESH_LAB_PROFILE:-unified}")
CLIENTS=$(prplmesh_profile_clients "$PROFILE")
RADIOS=$(prplmesh_profile_radios "$PROFILE")
# A development lab: fewer clients, quicker to build and lighter to run; no room service
# (it needs the full roster) and never qualified or packaged.
DEV_CLIENTS=${PRPLMESH_DEV_CLIENTS:-}
if [ -n "$DEV_CLIENTS" ]; then
    [[ $DEV_CLIENTS =~ ^[1-9][0-9]?$ ]] || {
        echo "PRPLMESH_DEV_CLIENTS must be 1 to 99 (the full lab has $CLIENTS)" >&2
        exit 2
    }
    CLIENTS=$DEV_CLIENTS
fi
NAME=$PRPLMESH_VM_NAME
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
RUNTIME_DEPS=${PRPL_RUNTIME_DEPS_ARCHIVE:-$ROOT/artifacts/prpl-runtime-deps-6.0.0.tar.gz}
PRPL_INSTALL=${PRPL_INSTALL_ARCHIVE:-$ROOT/artifacts/prpl-install-nl80211-6.0.0.tar.gz}
HOSTAP_RUNTIME=${PRPL_HOSTAP_ARCHIVE:-$ROOT/artifacts/hostap-runtime-2.10.tar.gz}
HOSTAP_CLIENT=${PRPL_HOSTAP_CLIENT_ARCHIVE:-$ROOT/artifacts/$PRPLMESH_CLIENT_ARCHIVE}
BASE_MODE=${PRPLMESH_BASE_IMAGE:-auto}
case "$BASE_MODE" in auto|off|rebuild) ;; *) echo "PRPLMESH_BASE_IMAGE must be auto, off or rebuild" >&2; exit 2 ;; esac
RECORDS=${PRPLMESH_BUILD_RECORDS:-$ROOT/build-evidence}
NESTED_POOL=${PRPLMESH_NESTED_STORAGE_POOL:-prpl-lab}
NESTED_DRIVER=${PRPLMESH_NESTED_STORAGE_DRIVER:-btrfs}
NESTED_SIZE=${PRPLMESH_NESTED_STORAGE_SIZE:-120GiB}

usage()
{
    cat <<EOF
usage: $0 {build|status|urls|check|update|copy NEW|stop|start|restart|delete}

check is the acceptance of a lab as built: every Agent on the controller (a star backhaul),
before a room has formed its own tree; after rooms have run, the room's readiness is the check.

update moves an accepted VM forward to this checkout's commit in place, without a build:
its checkout and submodules (the medium, the optimizer) follow, the room service restarts
and settles. When the commit changes what a build installed from the checkout (the medium's
daemon, console or radio module, the guest's services, the controller UI, the scripts the
containers run) the update makes and installs that too and restarts the VM. It refuses a
commit that changes the native patches or the container images' setup: build instead.

copy NEW copies the VM as NEW in its storage pool (seconds on Btrfs or ZFS) with its own
identities, address and port block (PRPLMESH_COPY_PORT_BASE overrides); left stopped:
PRPLMESH_VM_NAME=NEW $0 start brings it up.

Every build, update and copy writes its phases' times to build-evidence/KIND-NAME-STAMP
(phases.tsv, summary.txt; PRPLMESH_BUILD_RECORDS moves them).

Clean-build inputs (default: archives under artifacts/; build-artifacts.sh creates them, or
fetches them from the artifact store, EASYMESH_ARTIFACT_STORE, by the inputs they are built from):
  PRPL_RUNTIME_DEPS_ARCHIVE=/path/to/prpl-runtime-deps-6.0.0.tar.gz
  PRPL_INSTALL_ARCHIVE=/path/to/prpl-install-nl80211-6.0.0.tar.gz
  PRPL_HOSTAP_ARCHIVE=/path/to/hostap-runtime-2.10.tar.gz
  PRPL_HOSTAP_CLIENT_ARCHIVE=/path/to/hostap-client-2.10-alpine.tar.gz

The base VM image (the Ubuntu VM, its kernel, packages and LXD: what does not depend on the
commit) is an LXD image named by its inputs, prplmesh-base-KEY. A build starts from it when
this host or the artifact store has it, and makes it on the way otherwise:
  PRPLMESH_BASE_IMAGE=auto (or off: every stage; rebuild: make it anew)

A development lab (no room service, never qualified or packaged):
  PRPLMESH_DEV_CLIENTS=20 (clients instead of the full $(prplmesh_profile_clients "$PROFILE"))

Site overrides:
  PRPLMESH_LAB_PROFILE=$CLIENTS (fixed capacity: 100 clients)
  PRPLMESH_VM_NAME=$NAME
  PRPLMESH_UI_HOST_IP=$HOST_IP
  PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT=$CONSOLE_PORT
  PRPLMESH_UI_HOST_PORT=$UI_PORT
  PRPLMESH_ROOM_DEMO_HOST_PORT=$ROOM_PORT
  PRPLMESH_LXD_STORAGE=$PRPLMESH_LXD_STORAGE (retained on delete)
  PRPLMESH_PORT_BASE=$PRPLMESH_PORT_BASE
  PRPLMESH_STORAGE_DRIVER=dir (new pools only; existing pools are reused)
  PRPLMESH_NESTED_STORAGE_DRIVER=btrfs (fresh VM container pool; or dir)
  PRPLMESH_NESTED_STORAGE_POOL=prpl-lab
  PRPLMESH_NESTED_STORAGE_SIZE=120GiB (sparse Btrfs capacity, not preallocation)
  PRPLMESH_SHARED_HOST=0 (1: build and check although another lab VM runs on this host)
EOF
}

exists() { lxc info "$NAME" >/dev/null 2>&1; }

# Lab VMs share a host badly: with prpl-1001 running next to it, 19 of rdk-1001's 100
# clients lost packets in its build's traffic check, alone one did and later checks passed
# (rev140, 1 Oct). A lab VM, prplMesh or RDK, is one with a wmediumd Console proxy.
other_running_labs()
{
    lxc list --format json | python3 -c '
import json, sys
print(" ".join(i["name"] for i in json.load(sys.stdin) if i["name"] != sys.argv[1]
               and i["status"] == "Running" and "wmediumd-console" in (i.get("expanded_devices") or {})))' "$NAME"
}

require_host_to_itself()
{
    local others
    [ "${PRPLMESH_SHARED_HOST:-0}" = 1 ] && return
    others=$(other_running_labs)
    [ -z "$others" ] || {
        echo "another lab VM runs on this host ($others): stop it first, or set PRPLMESH_SHARED_HOST=1" >&2
        exit 1
    }
}
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
    lxc exec --mode non-interactive "$NAME" -- "$@" </dev/null
}

# A build's, update's or copy's record: what it ran on, and each phase's time.
record_dir=
phase_name=
phase_start=0
record_open()       # record_open KIND
{
    local kind=$1 stamp
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    record_dir=$RECORDS/$kind-$NAME-$stamp
    mkdir -p "$record_dir"
    printf 'phase\tstarted\tseconds\n' > "$record_dir/phases.tsv"
    {
        printf 'LAB=%s\nKIND=%s\nHOST=%s\nSTARTED=%s\n' "$NAME" "$kind" "$(hostname)" "$stamp"
        printf 'COMMIT=%s\nIMAGE=%s\nKERNEL=%s\n' "$(git -C "$ROOT" rev-parse HEAD)" "$IMAGE" "$KERNEL"
        printf 'CPUS=%s\nMEMORY=%s\nCLIENTS=%s\n' "$CPUS" "$MEMORY" "$CLIENTS"
        printf 'STORAGE=%s\nSTORAGE_DRIVER=%s\nSHARED_HOST=%s\n' "$(storage_pool)" \
            "$(storage_driver)" "${PRPLMESH_SHARED_HOST:-0}"
    } > "$record_dir/environment.txt"
    ln -sfn "$(basename "$record_dir")" "$RECORDS/latest-$kind-$NAME"
    printf 'build record: %s\n' "$record_dir" >&2
}

phase()             # phase NAME: end the running phase and start NAME ('' only ends it)
{
    local now
    now=$(date +%s)
    if [ -n "$phase_name" ] && [ -n "$record_dir" ]; then
        printf '%s\t%s\t%s\n' "$phase_name" "$phase_start" "$((now - phase_start))" \
            >> "$record_dir/phases.tsv"
        printf '[phase] %s: %ss\n' "$phase_name" "$((now - phase_start))" >&2
    fi
    phase_name=$1
    phase_start=$now
}

record_close()      # record_close STATUS
{
    local status=$1 failed=$phase_name
    [ -n "$record_dir" ] || return 0
    phase ''
    printf '%s\n' "$status" > "$record_dir/exit-code"
    [ "$status" = 0 ] || printf '%s\n' "$failed" > "$record_dir/failed-phase"
    awk -F'\t' 'NR > 1 { printf "%-24s %6d s %6.1f min\n", $1, $3, $3 / 60; total += $3 }
        END { printf "%-24s %6d s %6.1f min\n", "total", total, total / 60 }' \
        "$record_dir/phases.tsv" > "$record_dir/summary.txt"
    cat "$record_dir/summary.txt" >&2
    record_dir=
}

storage_pool()      # the pool the VM is in (a copy's is its original's), or this lab's
{
    lxc config device get "$NAME" root pool 2>/dev/null | grep . || printf '%s\n' "$PRPLMESH_LXD_STORAGE"
}

storage_driver()    # the driver of that pool, or the one a build would create
{
    lxc storage show "$(storage_pool)" 2>/dev/null | awk '$1 == "driver:" {print $2; exit}' \
        | grep . || printf '%s\n' "${PRPLMESH_STORAGE_DRIVER:-dir}"
}

# The base VM: the Ubuntu VM with the lab's kernel, its packages and LXD, nothing from the
# checkout. Runs in the guest (KERNEL set); base_image_key names its inputs.
BASE_PACKAGES='btrfs-progs build-essential ca-certificates curl dpkg-dev git golang-go iperf3
iproute2 iptables iputils-ping iw jq libconfig-dev libnl-3-dev libnl-genl-3-dev
libnl-route-3-dev meson nftables ninja-build patch pkg-config python3 python3-venv rsync
snapd util-linux zstd'
base_host() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends "linux-image-$KERNEL" "linux-modules-$KERNEL" \
        "linux-headers-$KERNEL" ca-certificates curl git zstd
    # shellcheck disable=SC2086 # a list of packages, with what they recommend
    apt-get install -y $BASE_PACKAGES
    update-initramfs -u -k "$KERNEL"
    update-grub
    sed "s/^Types: deb$/Types: deb-src/" /etc/apt/sources.list.d/ubuntu.sources \
        > /etc/apt/sources.list.d/prplmesh-src.sources
    apt-get update
    snap list lxd >/dev/null 2>&1 || snap install lxd
    snap start lxd
    lxd waitready
    lxc storage show default >/dev/null 2>&1 || lxd init --auto --storage-backend dir </dev/null
    # DHCP by the NIC's MAC: VMs made from one image share a machine-id, and with it the
    # client identity by which the bridge's DHCP server would give two labs one lease.
    install -m 0600 /dev/stdin /etc/netplan/50-prplmesh-appliance.yaml <<'EOF'
network:
  version: 2
  ethernets:
    appliance:
      match:
        name: "en*"
      dhcp4: true
      dhcp-identifier: mac
      dhcp4-overrides:
        use-dns: false
      nameservers:
        addresses: [1.1.1.1, 1.0.0.1]
EOF
    rm -f /etc/netplan/50-cloud-init.yaml
    printf '%s\n' 'network: {config: disabled}' > /etc/cloud/cloud.cfg.d/99-prplmesh-network.cfg
    netplan generate
}

base_image_key()
{
    artifact_key "image=$IMAGE" "kernel=$KERNEL" "lxd=$(lxc version 2>/dev/null | awk '/Server/ {print $3}' | cut -d. -f1)" \
        "layout=1" "$(declare -f no_automatic_updates no_on_demand_lxd base_host | sha256sum | cut -c1-16)" \
        "packages=$(printf '%s' "$BASE_PACKAGES" | tr -s ' \n' ' ')"
}

base_image_available()      # base_image_available ALIAS KEY: on this host, or fetched
{
    local alias=$1 key=$2 fetched
    local -a files
    [ "$BASE_MODE" = auto ] || return 1
    lxc image info "$alias" >/dev/null 2>&1 && return 0
    fetched=$(mktemp -d /tmp/prplmesh-base-image.XXXXXX)
    if artifact_fetch prplmesh-base-vm "$key" "$fetched"; then
        mapfile -t files < <(find "$fetched" -maxdepth 1 -type f ! -name SHA256SUMS \
            ! -name provenance.env -printf '%s %p\n' | sort -n | cut -d' ' -f2-)
        lxc image import "${files[@]}" --alias "$alias" </dev/null
        rm -rf -- "$fetched"
        return 0
    fi
    rm -rf -- "$fetched"
    return 1
}

publish_base_image()        # publish_base_image ALIAS KEY: the base VM, stopped and restarted
{
    local alias=$1 key=$2 exported
    run bash -euc 'apt-get clean
        journalctl --rotate >/dev/null 2>&1 || true
        journalctl --vacuum-time=1s >/dev/null 2>&1 || true
        install -d /var/lib/prplmesh-lab
        printf "%s\n" "$1" > /var/lib/prplmesh-lab/base-image.key
        sync' bash "$key"
    lxc stop "$NAME" --timeout 300
    if lxc image info "$alias" >/dev/null 2>&1; then
        lxc image delete "$alias"
    fi
    lxc publish "$NAME" --alias "$alias" --compression zstd \
        description="prplMesh lab base VM ($key)" </dev/null
    lxc start "$NAME"
    wait_agent
    sync_guest_address
    if [ -n "${EASYMESH_ARTIFACT_PUBLISH:-}" ]; then
        exported=$(mktemp -d /tmp/prplmesh-base-export.XXXXXX)
        lxc image export "$alias" "$exported/" </dev/null
        printf 'KEY=%s\nCOMMIT=%s\nBUILT=%s\nHOST=%s\nIMAGE=%s\nKERNEL=%s\n' "$key" \
            "$(git -C "$ROOT" rev-parse HEAD)" "$(date -u +%FT%TZ)" "$(hostname)" "$IMAGE" \
            "$KERNEL" > "$exported/provenance.env"
        artifact_publish prplmesh-base-vm "$key" "$exported"
        rm -rf -- "$exported"
    fi
}

# The guest's address as it runs: a copy, or a VM made from the base image, can come up
# on another address than its reservation (as import.sh found); the reservation and the
# proxies follow it.
sync_guest_address()
{
    local reserved actual device connect
    reserved=$(lxc config device get "$NAME" eth0 ipv4.address 2>/dev/null) || return 0
    for unused in $(seq 1 120); do
        actual=$(run ip -4 -o route get 1.1.1.1 2>/dev/null |
            awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}') || true
        [ -z "$actual" ] || break
        sleep 1
    done
    [ -n "$actual" ] || { echo "$NAME has no routed IPv4 address" >&2; return 1; }
    [ "$actual" != "$reserved" ] || return 0
    echo "$NAME runs on $actual, reserved $reserved: the reservation and proxies follow" >&2
    lxd_set_device_property "$NAME" eth0 ipv4.address "$actual"
    for device in wmediumd-console controller-ui room-demo-viewer; do
        connect=$(lxc config device get "$NAME" "$device" connect 2>/dev/null) || continue
        lxc config device set "$NAME" "$device" connect "tcp:$actual:${connect##*:}"
    done
}

copy_vm()           # copy_vm NEW: a copy in this pool, its own identities, address and ports
(
    local new=${1:?usage: $0 copy NEW} snapshot='' address base uuid vsock device connect port
    exists
    lxc info "$new" >/dev/null 2>&1 && { echo "$new exists" >&2; exit 1; }
    base=${PRPLMESH_COPY_PORT_BASE:-$(PRPLMESH_PORT_BASE='' PRPLMESH_UI_HOST_PORT='' \
        PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT='' PRPLMESH_ROOM_DEMO_HOST_PORT='' \
        LAB_LXD_UI_PORT='' LAB_GRAFANA_PORT='' LAB_OUTER_METRICS_PORT='' \
        bash -c 'source "$1"; prplmesh_instance_config "$2" && printf "%s\n" "$PRPLMESH_PORT_BASE"' \
        bash "$ROOT/deploy/lxd-vm/instance-config.sh" "$new")}
    [[ $base =~ ^[1-9][0-9]{3,4}$ ]] || { echo "no port block for $new" >&2; exit 2; }
    record_open copy
    trap 'record_close "$?"' EXIT
    phase copy
    if [ "$(state)" = RUNNING ]; then
        snapshot=copy-$(date -u +%Y%m%dT%H%M%SZ)
        lxc snapshot "$NAME" "$snapshot"
        lxc copy "$NAME/$snapshot" "$new" --storage "$PRPLMESH_LXD_STORAGE"
        lxc delete "$NAME/$snapshot"
    else
        lxc copy "$NAME" "$new" --instance-only --storage "$PRPLMESH_LXD_STORAGE"
    fi
    phase identity
    uuid=$(cat /proc/sys/kernel/random/uuid)
    vsock=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')
    lxc config unset "$new" volatile.eth0.hwaddr
    lxc config set "$new" volatile.uuid "$uuid"
    lxc config set "$new" volatile.uuid.generation "$uuid"
    lxc config set "$new" volatile.cloud-init.instance-id "$uuid"
    lxc config set "$new" volatile.vsock_id "$vsock"
    address=$(select_guest_ipv4)
    lxd_set_device_property "$new" eth0 ipv4.address "$address"
    for device in controller-ui:0 wmediumd-console:1 room-demo-viewer:2; do
        port=$((base + ${device#*:}))
        device=${device%:*}
        connect=$(lxc config device get "$new" "$device" connect)
        lxc config device set "$new" "$device" listen="tcp:$HOST_IP:$port" \
            connect="tcp:$address:${connect##*:}"
    done
    lxc config set "$new" user.prplmesh.port-base "$base"
    lxc config set "$new" user.prplmesh.copied-from "$NAME${snapshot:+/$snapshot}"
    lxc config set "$new" user.prplmesh.copied-at "$(date -u +%FT%TZ)"
    lxc config set "$new" boot.autostart false
    printf 'lab copy: %s (%s, ports %s-%s); start it: PRPLMESH_VM_NAME=%s %s start\n' \
        "$new" "$address" "$base" "$((base + 2))" "$new" "$0"
    trap - EXIT
    record_close 0
)

# A lab VM takes no automatic updates: an unattended upgrade restarts services under a
# running lab. apt-get and snap refresh by hand keep working. Runs in the guest.
no_automatic_updates() {
    systemctl mask --now apt-daily.timer apt-daily-upgrade.timer
    # a run in flight holds the dpkg lock: it finishes first
    while systemctl show -p ActiveState --value apt-daily.service apt-daily-upgrade.service \
        | grep -Eq '^(activating|active)$'; do
        sleep 2
    done
    systemctl mask apt-daily.service apt-daily-upgrade.service
    systemctl disable --now unattended-upgrades.service 2>/dev/null || true
    printf '%s\n' 'APT::Periodic::Update-Package-Lists "0";' \
        'APT::Periodic::Unattended-Upgrade "0";' \
        > "${APT_CONF_DIR:-/etc/apt/apt.conf.d}/99-lab-no-automatic-updates"
    if command -v snap >/dev/null 2>&1; then
        snap wait system seed.loaded
        snap refresh --hold
    fi
}

# Ubuntu installs LXD on demand, from its own channel, the first time anything runs lxc or
# lxd in the VM (lxd-installer). The lab installs its own LXD below: no on-demand install,
# and one already under way finishes first. Runs in the guest.
no_on_demand_lxd() {
    systemctl mask --now lxd-installer.socket 2>/dev/null || true
    while snap changes 2>/dev/null | grep -Eq '^[0-9]+ +(Do|Doing|Wait) .*Install "lxd"'; do
        sleep 2
    done
}

start_vm()
{
    exists
    [ "$(state)" = RUNNING ] || lxc start "$NAME"
    wait_agent
    sync_guest_address
    run systemctl start prplmesh-lab.service
}

lab_clients()       # the clients the lab VM was built with: a development lab's fewer
{
    local dev
    dev=$(lxc config get "$NAME" user.prplmesh.dev-clients 2>/dev/null) || true
    printf '%s\n' "${dev:-$CLIENTS}"
}

stop_vm()
{
    exists
    [ "$(state)" != RUNNING ] || lxc stop "$NAME" --timeout 300
}

check_vm() (
    local optimizer_pair optimizer_client optimizer_target clients
    require_host_to_itself
    start_vm || return
    clients=$(lab_clients)
    [ "$clients" = "$(prplmesh_profile_clients "$PROFILE")" ] ||
        echo "note: a development lab with $clients clients: checked as such, never qualified" >&2
    restore_room=false
    trap 'result=$?; if "$restore_room"; then run systemctl start prplmesh-room-service.service || result=$?; fi; exit "$result"' EXIT
    room_state=$(run systemctl show prplmesh-room-service.service -p ActiveState --value)
    case "$room_state" in active|activating) restore_room=true ;; esac
    run systemctl stop prplmesh-room-service.service || return
    run env PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT="$clients" PRPL_TOPOLOGY=star \
        PROVISIONED_CLIENT_COUNT="$clients" HWSIM_RADIOS="$RADIOS" \
        PRPL_WMEDIUMD_CONFIG=/var/lib/prplmesh-lab/wmediumd.conf \
        /opt/prplmesh-lab/tests/run-acceptance.sh || return
    optimizer_pair=$(run bash -c '
        set -eu
        inventory=$(mktemp /tmp/prpl-check-inventory.XXXXXX.json)
        trap "rm -f -- $inventory" EXIT
        cd /opt/prplmesh-lab/medium/configurator
        python3 -m wmdcfg.cli inventory -o "$inventory" >/dev/null
        /opt/prplmesh-lab/deploy/lxd-vm/select-optimizer-stimulus.py \
            "$inventory" prpl-agent-02
    ') || return
    read -r optimizer_client optimizer_target <<<"$optimizer_pair"
    echo "optimizer acceptance pair: $optimizer_client -> $optimizer_target"
    run env PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT="$clients" PRPL_TOPOLOGY=star \
        PROVISIONED_CLIENT_COUNT="$clients" HWSIM_RADIOS="$RADIOS" \
        PRPL_WMEDIUMD_CONFIG=/var/lib/prplmesh-lab/wmediumd.conf \
        /opt/prplmesh-lab/tests/optimizer-dynamic.sh recommend \
        "$optimizer_client" "$optimizer_target"
)

# The optimizer: easymesh-optimizer at the commit this lab pins (the optimizer submodule).
optimizer_bundle()
{
    local pinned
    pinned=$(git -C "$ROOT" rev-parse HEAD:optimizer)
    [ "$(git -C "$ROOT/optimizer" rev-parse HEAD 2>/dev/null)" = "$pinned" ] || {
        echo "optimizer is not at the pinned $pinned: git submodule update --init optimizer" >&2
        exit 1
    }
    test -z "$(git -C "$ROOT/optimizer" status --porcelain)"
    git -C "$ROOT/optimizer" bundle create "$1" HEAD
    git bundle verify "$1" >/dev/null
}

update_vm()
(
    local host_commit guest_commit guest_medium stage artifact i state=
    local wmediumd=false console=false radio=false services=false restart=false
    exists
    [ "$(state)" = RUNNING ] || { echo "$NAME is not running: $0 start" >&2; exit 1; }
    wait_agent
    host_commit=$(git -C "$ROOT" rev-parse HEAD)
    test -z "$(git -C "$ROOT" status --porcelain)"
    guest_commit=$(run git -C /opt/prplmesh-lab rev-parse HEAD)
    [ "$guest_commit" != "$host_commit" ] || { echo "$NAME is at $host_commit already"; exit 0; }
    git -C "$ROOT" merge-base --is-ancestor "$guest_commit" "$host_commit" || {
        echo "$NAME is at $guest_commit, not an ancestor of $host_commit: build instead" >&2
        exit 1
    }
    # What a build made from the checkout and installed: the medium's daemon (built in the
    # guest), console (built here) and radio module (built in the guest), the guest's
    # services and the controller UI (which embeds the topology page and the viewer modules
    # it shares). An update makes and installs what changed of them, then restarts the VM.
    guest_medium=$(git -C "$ROOT" rev-parse "$guest_commit:medium")
    git -C "$ROOT/medium" diff --quiet "$guest_medium" HEAD -- wmediumd \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' || wmediumd=true
    git -C "$ROOT/medium" diff --quiet "$guest_medium" HEAD -- observer \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' || console=true
    git -C "$ROOT/medium" diff --quiet "$guest_medium" HEAD -- hwsim \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' || radio=true
    git -C "$ROOT/medium" diff --quiet "$guest_medium" HEAD -- topology-ui \
        $(sed 's|^|configurator/worlds/viewer/|' "$ROOT/medium/topology-ui/shared-modules") \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' || services=true
    git -C "$ROOT" diff --quiet "$guest_commit" "$host_commit" -- deploy/guest controller-ui \
        ':(exclude,glob)**/*.md' || services=true
    # The containers run their scripts from the checkout (/mnt/project) when they start, as
    # the lab's start runs radio-lab.sh: a restart takes them. Their images' setup and the
    # native patches need a build.
    git -C "$ROOT" diff --quiet "$guest_commit" "$host_commit" -- scripts/container \
        scripts/radio-lab.sh scripts/lib scripts/client-setup-with-retry.sh \
        ':(exclude)scripts/container/setup-runtime-base.sh' \
        ':(exclude)scripts/container/setup-client-base.sh' ':(exclude,glob)**/*.md' || restart=true
    git -C "$ROOT" diff --quiet "$guest_commit" "$host_commit" -- patches \
        scripts/container/setup-runtime-base.sh scripts/container/setup-client-base.sh \
        ':(exclude,glob)**/*.md' || {
        echo "the native patches or the container images' setup changed since $guest_commit: build instead" >&2
        exit 1
    }
    ! "$wmediumd" && ! "$console" && ! "$radio" && ! "$services" || restart=true
    record_open update
    printf 'FROM=%s\nWMEDIUMD=%s\nCONSOLE=%s\nRADIO_MODULE=%s\nSERVICES=%s\nRESTART=%s\n' \
        "$guest_commit" "$wmediumd" "$console" "$radio" "$services" "$restart" \
        >> "$record_dir/environment.txt"
    stage=$(mktemp -d /tmp/prplmesh-lxd-update.XXXXXX)
    trap 'record_close "$?"; rm -rf -- "$stage"' EXIT
    phase inputs
    git -C "$ROOT" bundle create "$stage/prplmesh-lab.bundle" HEAD
    git bundle verify "$stage/prplmesh-lab.bundle" >/dev/null
    git -C "$ROOT/medium" bundle create "$stage/easymesh-medium.bundle" HEAD
    git bundle verify "$stage/easymesh-medium.bundle" >/dev/null
    optimizer_bundle "$stage/easymesh-optimizer.bundle"
    if "$console"; then
        bash "$ROOT/medium/observer/build.sh" "$stage/wmediumd-console" >&2
        test -z "$(git -C "$ROOT/medium" status --porcelain)"
    fi
    run install -d /opt/prplmesh-stage
    for artifact in "$stage"/*.bundle; do
        lxc file push "$artifact" "$NAME/opt/prplmesh-stage/$(basename "$artifact")"
    done
    phase checkout
    run env COMMIT="$host_commit" bash -euo pipefail -c '
        cd /opt/prplmesh-lab
        test -z "$(git status --porcelain --untracked-files=no)"
        git fetch -q /opt/prplmesh-stage/prplmesh-lab.bundle HEAD
        test "$(git rev-parse FETCH_HEAD)" = "$COMMIT"
        # A directory the commit turns into a submodule keeps only ignored files (bytecode).
        for path in medium optimizer; do
            [ ! -d "$path" ] || [ -e "$path/.git" ] || git clean -q -fdX -- "$path"
        done
        git merge -q --ff-only FETCH_HEAD
        for path in medium optimizer; do
            [ -e "$path/.git" ] || [ -z "$(ls -A "$path" 2>/dev/null)" ] || {
                echo "$path holds untracked files; it cannot become a submodule" >&2
                exit 1
            }
        done
        git config submodule.medium.url /opt/prplmesh-stage/easymesh-medium.bundle
        git config submodule.optimizer.url /opt/prplmesh-stage/easymesh-optimizer.bundle
        git -c protocol.file.allow=always submodule update --init medium optimizer
        for path in medium optimizer; do
            test "$(git -C "$path" rev-parse HEAD)" = "$(git rev-parse "HEAD:$path")"
        done
        test -z "$(git status --porcelain)"
        echo "$(git rev-parse --short HEAD): medium $(git -C medium rev-parse --short HEAD)," \
            "optimizer $(git -C optimizer rev-parse --short HEAD)"
    '
    lxc config set "$NAME" user.prplmesh.source-commit "$host_commit"
    if "$wmediumd"; then
        # as install-from-artifacts.sh builds it, from the medium the checkout now pins
        phase wmediumd
        run bash -euc 'cd /opt/prplmesh-lab
            medium/wmediumd/build-wmediumd.sh --source build/wmediumd-source --output build/bin'
    fi
    if "$console"; then
        phase console
        lxc file push "$stage/wmediumd-console" "$NAME/opt/prplmesh-lab/medium/observer/wmediumd-console"
        run chmod 0755 /opt/prplmesh-lab/medium/observer/wmediumd-console
    fi
    if "$radio"; then
        # as install-from-artifacts.sh builds it; a live pool is never reloaded: the
        # restart below loads the new module
        phase radio-module
        run bash -euc 'cd /opt/prplmesh-lab
            INSTALL_MODULE=1 medium/hwsim/build-hwsim.sh --source build/hwsim-source \
                --cfg80211 build/cfg80211-source
            depmod -a "$(uname -r)"'
    fi
    if "$services" || "$console"; then
        # the guest's services, the controller UI and the Console, as prepare-appliance.sh
        # installs them
        phase services
        run bash /opt/prplmesh-lab/deploy/guest/install-service.sh /opt/prplmesh-lab
    fi
    if "$restart"; then
        phase restart
        run sync
        lxc restart "$NAME" --timeout 120 || lxc restart "$NAME" --force
        wait_agent
        sync_guest_address
        run systemctl start prplmesh-lab.service
    fi
    if [ "$(lab_clients)" != "$(prplmesh_profile_clients "$PROFILE")" ]; then
        echo "a development lab ($(lab_clients) clients): no room service to settle"
        exit 0
    fi
    phase room
    run systemctl stop prplmesh-room-service.service
    # The room's baseline is every pool client online: it pauses the clients a world
    # leaves dormant and resumes them when its session ends, and its preflight counts all
    # of them (as the RDK lab's gen/lab-bringup.sh room). A client still not associated
    # after 30 s reconnects without its cached SAE keys (prpl-0930: stuck in its handshake).
    run bash -c '
        offline() {
            for client in "$@"; do
                [ "$(lxc exec "$client" -- wpa_cli -i wlan0 status 2>/dev/null |
                    sed -n "s/^wpa_state=//p")" = COMPLETED ] || echo "$client"
            done
        }
        waiting=$(offline $(lxc list -c n -f csv | grep "^prpl-client-"))
        [ -n "$waiting" ] || exit 0
        sleep 30
        waiting=$(offline $waiting)
        for client in $waiting; do
            lxc exec "$client" -- sh -c "wpa_cli -i wlan0 disconnect; wpa_cli -i wlan0 pmksa_flush;
                wpa_cli -i wlan0 reconnect" >/dev/null || true
        done
        for attempt in $(seq 12); do
            [ -n "$waiting" ] || exit 0
            sleep 5
            waiting=$(offline $waiting)
        done
        echo "pool clients not online:" $waiting >&2
        exit 1
    '
    run systemctl start prplmesh-room-service.service
    # settled: the default room's 20 clients online, measured and converged
    for i in $(seq 120); do
        state=$(run bash -c 'curl -fsS --max-time 5 http://127.0.0.1:8891/api/demo/current | python3 -c "
import json, sys
d = json.load(sys.stdin); h = d.get(\"health\", {}); f = (d.get(\"optimizer\") or {}).get(\"fleet\") or {}
ok = (h.get(\"healthy\") and h.get(\"api_total\") == 20 and h.get(\"expected_online_clients\") == 20
      and f.get(\"converged\") and f.get(\"measurement_complete\") and f.get(\"clients_checked\") == 20)
print(\"settled\" if ok else \"waiting\", d.get(\"scenario\"), h.get(\"api_total\"), f.get(\"clients_checked\"))
sys.exit(0 if ok else 1)"' 2>/dev/null) && { echo "room $state"; exit 0; }
        [ "$(run systemctl is-active prplmesh-room-service.service || true)" != failed ] || {
            echo "room service failed (journalctl -u prplmesh-room-service.service)" >&2
            exit 1
        }
        sleep 5
    done
    echo "room not settled after 10 min: ${state:-no answer}" >&2
    exit 1
)

build_vm()
(
    local stage bundle commit guest_ip artifact storage_pool boot_mode_error
    local base_key base_alias from_base=false
    [ -z "$(git -C "$ROOT" status --porcelain)" ] || {
        echo "source checkout must be clean" >&2
        exit 1
    }
    require_host_to_itself
    for artifact in "$RUNTIME_DEPS" "$PRPL_INSTALL" "$HOSTAP_RUNTIME" "$HOSTAP_CLIENT"; do
        [ -f "$artifact" ] || {
            echo "Missing $artifact; run bash deploy/lxd-vm/build-artifacts.sh first." >&2
            exit 2
        }
        python3 - "$artifact" <<'PY'
import hashlib
from pathlib import Path
import sys
archive = Path(sys.argv[1]).resolve()
manifest = archive.parent / 'SHA256SUMS'
if not manifest.is_file():
    raise SystemExit(f'Missing artifact checksums: {manifest}')
expected = [line.split()[0] for line in manifest.read_text().splitlines()
            if len(line.split()) == 2 and line.split()[1].lstrip('*') in (archive.name, './' + archive.name)]
digest = hashlib.sha256()
with archive.open('rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
if expected != [digest.hexdigest()]:
    raise SystemExit(f'Artifact checksum missing, duplicate or mismatched: {archive}')
PY
    done
    exists && {
        echo "$NAME already exists; delete it explicitly before a clean build" >&2
        exit 1
    }
    storage_pool=$PRPLMESH_LXD_STORAGE
    prplmesh_check_ports
    prplmesh_ensure_storage "$storage_pool"
    "$ROOT/deploy/lxd-vm/storage-preflight.sh" "$PROFILE" "$storage_pool"

    record_open build
    stage=$(mktemp -d /tmp/prplmesh-lxd-build.XXXXXX)
    trap 'record_close "$?"; rm -rf -- "$stage"' EXIT
    phase inputs
    bundle="$stage/prplmesh-lab.bundle"
    commit=$(git -C "$ROOT" rev-parse HEAD)
    git -C "$ROOT" bundle create "$bundle" HEAD
    git bundle verify "$bundle" >/dev/null
    # the RF medium: easymesh-medium at the commit this lab pins (the medium submodule)
    medium=$(git -C "$ROOT" rev-parse HEAD:medium)
    [ "$(git -C "$ROOT/medium" rev-parse HEAD 2>/dev/null)" = "$medium" ] || {
        echo "medium is not at the pinned $medium: git submodule update --init medium" >&2
        exit 1
    }
    git -C "$ROOT/medium" bundle create "$stage/easymesh-medium.bundle" HEAD
    git bundle verify "$stage/easymesh-medium.bundle" >/dev/null
    # the Console is built here, as in the RDK lab: the medium does not commit binaries
    bash "$ROOT/medium/observer/build.sh" "$stage/wmediumd-console" >&2
    test -z "$(git -C "$ROOT/medium" status --porcelain)"
    optimizer_bundle "$stage/easymesh-optimizer.bundle"
    cp --reflink=auto "$RUNTIME_DEPS" "$PRPL_INSTALL" "$HOSTAP_RUNTIME" "$HOSTAP_CLIENT" "$stage/"
    (
        cd "$stage"
        sha256sum prplmesh-lab.bundle easymesh-medium.bundle easymesh-optimizer.bundle wmediumd-console \
            "$(basename "$RUNTIME_DEPS")" \
            "$(basename "$PRPL_INSTALL")" \
            "$(basename "$HOSTAP_RUNTIME")" \
            "$(basename "$HOSTAP_CLIENT")" > SHA256SUMS
    )

    phase create
    base_key=$(base_image_key)
    base_alias=prplmesh-base-$base_key
    if base_image_available "$base_alias" "$base_key"; then
        from_base=true
    fi
    printf 'BASE_IMAGE=%s\nFROM_BASE_IMAGE=%s\nBASE_IMAGE_MODE=%s\nDEV_CLIENTS=%s\n' \
        "$base_alias" "$from_base" "$BASE_MODE" "$DEV_CLIENTS" >> "$record_dir/environment.txt"
    if "$from_base"; then
        lxc init "$base_alias" "$NAME" --vm --storage "$storage_pool" \
            --config limits.cpu="$CPUS" --config limits.memory="$MEMORY" </dev/null
    else
        lxc init "$IMAGE" "$NAME" --vm --storage "$storage_pool" \
            --config limits.cpu="$CPUS" --config limits.memory="$MEMORY" </dev/null
    fi
    [ -z "$DEV_CLIENTS" ] || lxc config set "$NAME" user.prplmesh.dev-clients "$DEV_CLIENTS"
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
    lxc config set "$NAME" user.prplmesh.source-commit "$commit"
    lxc config set "$NAME" user.prplmesh.port-base "$PRPLMESH_PORT_BASE"
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
    phase start
    lxc start "$NAME"
    wait_agent
    "$from_base" && sync_guest_address

    if ! "$from_base"; then
        # the base VM: what does not depend on the commit (base_host)
        phase base-host
        run env KERNEL="$KERNEL" BASE_PACKAGES="$BASE_PACKAGES" bash -euc \
            "$(declare -f no_automatic_updates no_on_demand_lxd base_host); no_automatic_updates; no_on_demand_lxd; base_host"
        phase kernel-restart
        lxc restart "$NAME" --timeout 300
        wait_agent
        # DHCP by the MAC from now on (base_host): the reservation follows if it moved
        sync_guest_address
    fi
    [ "$(run uname -r)" = "$KERNEL" ]
    if ! "$from_base" && [ "$BASE_MODE" != off ]; then
        phase base-image
        publish_base_image "$base_alias" "$base_key"
    fi

    phase push-inputs
    run install -d /opt/prplmesh-stage /opt/prplmesh-lab
    for artifact in "$stage"/*; do
        lxc file push "$artifact" "$NAME/opt/prplmesh-stage/$(basename "$artifact")"
    done
    run bash -c '
        cd /opt/prplmesh-stage
        sha256sum -c SHA256SUMS
        rm -rf /opt/prplmesh-lab
        git clone prplmesh-lab.bundle /opt/prplmesh-lab
        git -C /opt/prplmesh-lab config submodule.medium.url /opt/prplmesh-stage/easymesh-medium.bundle
        git -C /opt/prplmesh-lab config submodule.optimizer.url /opt/prplmesh-stage/easymesh-optimizer.bundle
        git -c protocol.file.allow=always -C /opt/prplmesh-lab submodule update --init medium optimizer
        install -m 0755 wmediumd-console /opt/prplmesh-lab/medium/observer/wmediumd-console
    '
    [ "$(run git -C /opt/prplmesh-lab rev-parse HEAD)" = "$commit" ]
    [ "$(run git -C /opt/prplmesh-lab/medium rev-parse HEAD)" = "$medium" ]
    [ "$(run git -C /opt/prplmesh-lab/optimizer rev-parse HEAD)" = "$(git -C "$ROOT" rev-parse HEAD:optimizer)" ]
    run install -d -m 0755 /var/lib/prplmesh-lab
    run python3 /opt/prplmesh-lab/scripts/generate-wmediumd-config.py \
        --radios "$RADIOS" --output /var/lib/prplmesh-lab/wmediumd.conf
    run bash -c "cat > /etc/default/prplmesh-lab <<'EOF'
PRPLMESH_LAB_PROFILE=$PROFILE
PROVISIONED_AGENT_COUNT=4
PROVISIONED_WIRED_AGENT_COUNT=${PRPL_WIRED_AGENTS:-1}
$( [ "${PRPL_WIRED_AGENTS:-1}" -gt 0 ] && echo EASYMESH_ROOM_MANIFEST=rooms/manifests/private-client-room-walk-wired.json )
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
    run install -m 0644 "/opt/prplmesh-stage/$(basename "$HOSTAP_CLIENT")" \
        "/opt/prplmesh-lab/artifacts/$PRPLMESH_CLIENT_ARCHIVE"
    run bash -c '
        cd /opt/prplmesh-lab/artifacts
        sha256sum *.tar.gz > SHA256SUMS
    '

    phase nested-storage
    # the guest's LXD starts with the VM (after base_host's restart, or a base image's boot)
    run lxd waitready --timeout 600
    run env PRPLMESH_NESTED_STORAGE_POOL="$NESTED_POOL" \
        PRPLMESH_NESTED_STORAGE_DRIVER="$NESTED_DRIVER" PRPLMESH_NESTED_STORAGE_SIZE="$NESTED_SIZE" \
        bash /opt/prplmesh-lab/deploy/guest/setup-nested-storage.sh
    phase images-and-modules
    run bash /opt/prplmesh-lab/scripts/install-from-artifacts.sh --prepare-only
    # the guest's nested LXD can hold its shutdown past the timeout (prpl-0930):
    # everything is on the disk by now, so a forced restart loses nothing
    phase module-restart
    run sync
    lxc restart "$NAME" --timeout 120 || lxc restart "$NAME" --force
    wait_agent
    sync_guest_address
    phase radio-pool
    run bash /opt/prplmesh-lab/scripts/radio-lab.sh radio-pool
    phase deploy
    run bash /opt/prplmesh-lab/scripts/radio-lab.sh deploy
    phase services
    run bash /opt/prplmesh-lab/controller-ui/install.sh
    run bash /opt/prplmesh-lab/deploy/guest/prepare-appliance.sh /opt/prplmesh-lab
    run rm -rf /opt/prplmesh-stage
    phase lab-start
    run systemctl start prplmesh-lab.service
    phase acceptance
    check_vm
    # package.sh reruns acceptance and exports only the instance. Avoid a
    # full disk copy on non-copy-on-write outer storage pools.
    trap - EXIT
    record_close 0
    rm -rf -- "$stage"
)

case "${1:-}" in
    build)
        mkdir -p "$ROOT/build-evidence"
        log="$ROOT/build-evidence/vm-$NAME-$(date -u +%Y%m%dT%H%M%SZ).log"
        exec > >(tee "$log") 2>&1
        trap 'result=$?; echo "VM build exit=$result elapsed=${SECONDS}s log=$log"' EXIT
        build_vm
        ;;
    status) exists; lxc list "$NAME" -c nst4m; [ "$(state)" != RUNNING ] || run prplmesh-lab-start status ;;
    check) check_vm ;;
    update) update_vm ;;
    copy) copy_vm "${2:-}" ;;
    urls)
        if exists; then
            lxc query "/1.0/instances/$NAME" | python3 -c '
import json, sys
for name, device in json.load(sys.stdin).get("expanded_devices", {}).items():
    if device.get("type") == "proxy" and device.get("listen", "").startswith("tcp:"):
        scheme = "https" if "lxd" in name or "grafana" in name else "http"
        print(name + ": " + scheme + "://" + device["listen"][4:] + "/")'
        else
            printf 'Planned topology: http://%s:%s/\nPlanned console: http://%s:%s/\nPlanned room: http://%s:%s/\n' "$HOST_IP" "$UI_PORT" "$HOST_IP" "$CONSOLE_PORT" "$HOST_IP" "$ROOM_PORT"
        fi
        ;;
    start) start_vm ;;
    stop) stop_vm ;;
    restart) stop_vm; start_vm ;;
    delete) exists; lxc list "$NAME" -c nst4m; lxc delete "$NAME" --force ;;
    -h|--help|help|'') usage ;;
    *) usage >&2; exit 2 ;;
esac
