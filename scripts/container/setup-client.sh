#!/bin/bash
set -euo pipefail

ordinal=${1:?client ordinal}
cohort=${2:?private or iot}
band=${3:-5}
tar -C /usr/local -xzf /mnt/project/artifacts/hostap-runtime-2.10.tar.gz

case "$band" in
    2.4) key_mgmt=WPA-PSK; frequency=2437 ;;
    5)   key_mgmt=WPA-PSK; frequency=5180 ;;
    6)   key_mgmt=SAE; frequency=5975 ;;
    *) echo "band must be 2.4, 5, or 6" >&2; exit 2 ;;
esac

case "$cohort" in
    private)
        ssid=private_ssid
        prefix=10
        client_index=$((ordinal * 2 - 1))
        ;;
    iot)
        ssid=iot_ssid
        prefix=20
        client_index=$((ordinal * 2))
        ;;
    *) echo "cohort must be private or iot" >&2; exit 2 ;;
esac

printf -v suffix '%02x' "$ordinal"
iw dev wlan0 disconnect 2>/dev/null || true
ip link set wlan0 down
ip link set wlan0 address "02:00:00:${prefix}:${suffix}:00"
ip link set wlan0 up

pkill -x wpa_supplicant 2>/dev/null || true
for unused in $(seq 1 50); do
    pgrep -x wpa_supplicant >/dev/null 2>&1 || break
    sleep 0.1
done
pkill -KILL -x wpa_supplicant 2>/dev/null || true
rm -rf /var/run/wpa_supplicant/*
mkdir -p /var/run/wpa_supplicant

install -m 0644 /mnt/project/manifests/wpa_supplicant.conf \
    /etc/wpa_supplicant-prpl.conf
sed -i "s/@SSID@/$ssid/; s/@KEY_MGMT@/$key_mgmt/; s/@FREQUENCY@/$frequency/" \
    /etc/wpa_supplicant-prpl.conf

wpa_supplicant -B -Dnl80211 -i wlan0 -c /etc/wpa_supplicant-prpl.conf \
    -f /tmp/wpa_supplicant.log

for unused in $(seq 1 30); do
    state=$(wpa_cli -i wlan0 status 2>/dev/null | \
        sed -n 's/^wpa_state=//p' || true)
    [ "$state" = COMPLETED ] && break
    sleep 1
done

if [ "${state:-}" != COMPLETED ]; then
    wpa_cli -i wlan0 status >&2
    exit 1
fi

# Deterministic addresses make the isolated fronthaul/backhaul bridge directly
# testable without introducing a DHCP server into this comparison lab.
ip address replace "192.168.77.$((100 + client_index))/24" dev wlan0
