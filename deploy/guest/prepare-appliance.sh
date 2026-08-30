#!/bin/bash
set -euo pipefail

ROOT=${1:-/opt/prplmesh-lab}

[ "$(id -u)" -eq 0 ] || {
    echo "run as root: sudo $0 [repository]" >&2
    exit 1
}

# A generic netplan survives LXD VM image import on a different host. DNS is
# explicit because nested build/runtime nodes must not depend on a host-local
# resolver stub.
install -m 0600 /dev/stdin /etc/netplan/50-prplmesh-appliance.yaml <<'EOF'
network:
  version: 2
  ethernets:
    appliance:
      match:
        name: "en*"
      dhcp4: true
      dhcp4-overrides:
        use-dns: false
      nameservers:
        addresses: [1.1.1.1, 1.0.0.1]
EOF
rm -f /etc/netplan/50-cloud-init.yaml

"$ROOT/deploy/guest/install-service.sh" "$ROOT"
systemctl disable --now prplmesh-lab.service 2>/dev/null || true
systemctl enable prplmesh-lab.service
netplan generate
echo 'Guest is prepared for LXD VM appliance packaging.'
