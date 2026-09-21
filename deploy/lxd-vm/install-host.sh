#!/bin/bash
set -euo pipefail

[ "$(id -u)" -eq 0 ] || {
    echo "run as root: sudo $0" >&2
    exit 1
}

. /etc/os-release
case "${ID:-}:${VERSION_ID:-}" in
    ubuntu:22.04|ubuntu:24.04) ;;
    *)
        echo "supported hosts are Ubuntu 22.04 and 24.04; found ${PRETTY_NAME:-unknown}" >&2
        exit 1
        ;;
esac

grep -Eq '(vmx|svm)' /proc/cpuinfo || {
    echo "CPU virtualization extensions are not visible" >&2
    exit 1
}

apt-get update
apt-get install -y ca-certificates curl git iproute2 jq python3 qemu-kvm snapd zstd
if ! snap list lxd >/dev/null 2>&1; then
    snap install lxd
fi

modprobe kvm
[ -c /dev/kvm ] || {
    echo "/dev/kvm was not created; check firmware virtualization settings" >&2
    exit 1
}

login_user=${SUDO_USER:-}
if [ -n "$login_user" ] && [ "$login_user" != root ]; then
    usermod -aG lxd "$login_user"
fi

if ! lxc storage list --format csv 2>/dev/null | grep -q .; then
    lxd init --minimal
fi

echo "LXD VM host is ready. Re-enter the login session or run: newgrp lxd"
