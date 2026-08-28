#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    bridge-utils ebtables hostapd iw iproute2 iputils-ping libcap-ng0 \
    libevent-2.1-7 libjson-c5 libnl-3-200 libnl-genl-3-200 \
    libnl-route-3-200 libssl3 liburiparser1 libyajl2 psmisc tcpdump \
    wpasupplicant >/dev/null

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
