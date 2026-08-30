#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=${PRPLMESH_VM_NAME:-prplmesh-lab-0829}
IMAGE=${PRPLMESH_VM_IMAGE:-ubuntu:24.04}
NETWORK=${PRPLMESH_LXD_NETWORK:-lxdbr0}
CPUS=${PRPLMESH_VM_CPUS:-6}
MEMORY=${PRPLMESH_VM_MEMORY:-8GiB}
DISK=${PRPLMESH_VM_DISK:-80GiB}
KERNEL=${PRPLMESH_KERNEL:-7.0.0-30-generic}
HOST_IP=${PRPLMESH_UI_HOST_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null |
    awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
HOST_IP=${HOST_IP:-127.0.0.1}
TOPOLOGY_PORT=${PRPLMESH_TOPOLOGY_HOST_PORT:-8090}
UI_PORT=${PRPLMESH_UI_HOST_PORT:-8091}
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
  PRPLMESH_VM_NAME=$NAME
  PRPLMESH_UI_HOST_IP=$HOST_IP
  PRPLMESH_TOPOLOGY_HOST_PORT=$TOPOLOGY_PORT
  PRPLMESH_UI_HOST_PORT=$UI_PORT
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

check_vm()
{
    start_vm
    run env PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=star \
        /opt/prplmesh-lab/tests/run-acceptance.sh
    run env PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=star \
        /opt/prplmesh-lab/tests/optimizer-dynamic.sh recommend \
        prpl-client-07 prpl-agent-02
}

build_vm()
{
    local stage bundle commit guest_ip artifact
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

    stage=$(mktemp -d /tmp/prplmesh-lxd-build.XXXXXX)
    trap 'rm -rf -- "$stage"' EXIT
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

    lxc init "$IMAGE" "$NAME" --vm \
        --config limits.cpu="$CPUS" --config limits.memory="$MEMORY"
    lxc config set "$NAME" security.secureboot false
    lxc config set "$NAME" boot.autostart true
    lxc config device override "$NAME" root size="$DISK"
    guest_ip=$(select_guest_ipv4)
    lxc config device override "$NAME" eth0 network="$NETWORK" ipv4.address="$guest_ip"
    lxc config device add "$NAME" topology-ui proxy nat=true \
        listen="tcp:$HOST_IP:$TOPOLOGY_PORT" connect="tcp:$guest_ip:8090"
    lxc config device add "$NAME" controller-ui proxy nat=true \
        listen="tcp:$HOST_IP:$UI_PORT" connect="tcp:$guest_ip:8091"
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
        apt-get install -y build-essential ca-certificates dpkg-dev git golang-go iw jq \
          libconfig-dev libnl-3-dev libnl-genl-3-dev libnl-route-3-dev meson \
          ninja-build patch pkg-config python3 python3-venv rsync snapd
        sed "s/^Types: deb$/Types: deb deb-src/" /etc/apt/sources.list.d/ubuntu.sources \
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
    lxc snapshot "$NAME" accepted
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
