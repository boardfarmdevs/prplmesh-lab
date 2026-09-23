#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
systemctl mask --now \
    apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer \
    snapd.service snapd.socket snapd.seeded.service unattended-upgrades.service 2>/dev/null || true
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    ca-certificates curl iperf3 iproute2 iputils-ping iw libnl-3-200 libnl-genl-3-200 \
    libnl-route-3-200 libssl3 procps psmisc python3 tcpdump >/dev/null
apt-get purge -y -qq snapd unattended-upgrades >/dev/null 2>&1 || true
tar -C /usr/local -xzf /mnt/project/artifacts/hostap-runtime-2.10.tar.gz \
    ./sbin/wpa_supplicant ./bin/wpa_cli
for binary in /usr/local/sbin/wpa_supplicant /usr/local/bin/wpa_cli; do
    dependencies=$(ldd "$binary")
    if grep -q 'not found' <<<"$dependencies"; then
        printf '%s\n' "$dependencies" >&2
        exit 1
    fi
done
for binary in wpa_supplicant wpa_cli iw ip ping iperf3 tcpdump python3; do
    command -v "$binary" >/dev/null
done
test ! -e /opt/prpl-install-nl80211
test ! -e /usr/local/sbin/hostapd
mkdir -p /var/run/wpa_supplicant
systemctl disable --now wpa_supplicant iperf3 2>/dev/null || true
apt-get clean
rm -rf /var/lib/apt/lists/* /var/cache/apt/* /var/cache/snapd /var/lib/snapd
