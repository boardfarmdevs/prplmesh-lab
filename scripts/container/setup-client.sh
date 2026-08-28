#!/bin/bash
set -euo pipefail

ordinal=${1:?client ordinal}
band=${2:-5}
tar -C /usr/local -xzf /mnt/project/artifacts/hostap-runtime-2.10.tar.gz

case "$band" in
    2.4) key_mgmt=WPA-PSK; frequency=2437 ;;
    5)   key_mgmt=WPA-PSK; frequency=5180 ;;
    6)   key_mgmt=SAE; frequency=5975 ;;
    *) echo "band must be 2.4, 5, or 6" >&2; exit 2 ;;
esac

pkill -x wpa_supplicant 2>/dev/null || true
rm -rf /var/run/wpa_supplicant/*
mkdir -p /var/run/wpa_supplicant

install -m 0644 /mnt/project/manifests/wpa_supplicant.conf \
    /etc/wpa_supplicant-prpl.conf
sed -i "s/@KEY_MGMT@/$key_mgmt/; s/@FREQUENCY@/$frequency/" \
    /etc/wpa_supplicant-prpl.conf

wpa_supplicant -B -Dnl80211 -i wlan0 -c /etc/wpa_supplicant-prpl.conf \
    -f /tmp/wpa_supplicant.log

for _ in $(seq 1 30); do
    state=$(wpa_cli -i wlan0 status | sed -n 's/^wpa_state=//p')
    [ "$state" = COMPLETED ] && exit 0
    sleep 1
done

wpa_cli -i wlan0 status >&2
exit 1
