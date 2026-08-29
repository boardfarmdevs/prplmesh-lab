#!/bin/bash
set -euo pipefail

ROOT=${1:-/opt/prplmesh-lab}

[ "$(id -u)" -eq 0 ] || {
    echo "run as root: sudo $0 [repository]" >&2
    exit 1
}

# A generic netplan survives both LXD's virtio NIC and VirtualBox's emulated
# adapter names. DNS is explicit because nested build/runtime nodes must not
# depend on a host-local resolver stub.
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

# The standard public Vagrant development key is intentionally public and is
# replaced by Vagrant on first boot when supported by the provider.
id vagrant >/dev/null 2>&1 || useradd -m -s /bin/bash vagrant
install -d -m 0700 -o vagrant -g vagrant /home/vagrant/.ssh
install -m 0600 -o vagrant -g vagrant /dev/stdin \
    /home/vagrant/.ssh/authorized_keys <<'EOF'
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6NF8iallvQVp22WDkTkyrtvp9eWW6A8YVr+kz4TjGYe7gHzIw+niNltGEFHzD8+v1I2YJ6oXevct1YeS0o9HZyN1Q9qgCgzUFtdOKLv6IedplqoPkcmF0aYet2PkEDo3MlTBckFXPITAMzF8dJSIFo9D8HfdOV0IAdx4O7PtixWKn5y2hMNG0zQPyUecp4pzC6kivAIhyfHilFR61RGL+GPXQ2MWZWFYbAGjyiYJnAmCP3NOTd0jMZEnDkbUvxhMmBYSdETk1rRgm+R4LOzFUGaHqHDLKLX+FIPKcF96hrucXzcWyLbIbEgE98OHlnVYCzRdK8jlqm8tehUc9c9WhQ== vagrant insecure public key
EOF
printf 'vagrant ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/vagrant
chmod 0440 /etc/sudoers.d/vagrant

"$ROOT/deploy/guest/install-service.sh" "$ROOT"
systemctl disable --now prplmesh-lab.service 2>/dev/null || true
systemctl enable prplmesh-lab.service
netplan generate
echo 'Guest is prepared for LXD or VirtualBox appliance packaging.'
