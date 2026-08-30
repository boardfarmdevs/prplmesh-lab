#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# Runtime containers are appliances, not general Ubuntu hosts. Background
# package refresh and snap seed installation make every node consume CPU and
# memory independently, and at scale can prevent LXD lifecycle calls from
# completing. Disable them before installing the fixed runtime dependencies.
systemctl mask --now \
    apt-daily.service apt-daily-upgrade.service \
    apt-daily.timer apt-daily-upgrade.timer \
    snapd.service snapd.socket snapd.seeded.service \
    unattended-upgrades.service 2>/dev/null || true
apt-get update -qq
apt-get install -y -qq \
    bridge-utils ebtables hostapd iw iproute2 iputils-ping libcap-ng0 \
    libevent-2.1-7 libjson-c5 libnl-3-200 libnl-genl-3-200 \
    libnl-route-3-200 libssl3 liburiparser1 libyajl2 psmisc tcpdump \
    wpasupplicant >/dev/null
apt-get purge -y -qq snapd unattended-upgrades >/dev/null 2>&1 || true

tar -C / -xzf /mnt/project/artifacts/prpl-runtime-deps-6.0.0.tar.gz
tar -C /opt -xzf /mnt/project/artifacts/prpl-install-nl80211-6.0.0.tar.gz
tar -C /usr/local -xzf /mnt/project/artifacts/hostap-runtime-2.10.tar.gz
ldconfig
mkdir -p /var/run/ubus /var/run/hostapd /var/run/wpa_supplicant

for binary in beerocks_agent beerocks_controller beerocks_fronthaul ieee1905_transport; do
    if ldd "/opt/prpl-install-nl80211/bin/$binary" | grep -q 'not found'; then
        ldd "/opt/prpl-install-nl80211/bin/$binary" >&2
        exit 1
    fi
done

systemctl disable --now hostapd wpa_supplicant 2>/dev/null || true
apt-get clean
rm -rf /var/lib/apt/lists/* /var/cache/snapd /var/lib/snapd
