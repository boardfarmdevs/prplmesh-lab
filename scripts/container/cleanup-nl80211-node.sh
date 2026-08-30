#!/bin/bash
set -euo pipefail

install=/opt/prpl-install-nl80211
if [ -x "$install/scripts/prplmesh_utils.sh" ]; then
    "$install/scripts/prplmesh_utils.sh" stop >/dev/null 2>&1 || true
fi

pkill -TERM -x hostapd 2>/dev/null || true
pkill -TERM -x wpa_supplicant 2>/dev/null || true
for unused in $(seq 1 30); do
    if ! pgrep -x hostapd >/dev/null 2>&1 &&
       ! pgrep -x wpa_supplicant >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
pkill -KILL -x hostapd 2>/dev/null || true
pkill -KILL -x wpa_supplicant 2>/dev/null || true

# LXD owns only the three base AP netdevs. Remove the station and BSS VIFs
# while the PHY is still in this namespace so LXD returns one clean base
# interface per assigned hwsim radio.
for iface in wlan1 wlan3 wlan5 \
             wlan0.0 wlan0.1 wlan0.2 \
             wlan2.0 wlan2.1 wlan2.2 \
             wlan4.0 wlan4.1 wlan4.2; do
    iw dev "$iface" del 2>/dev/null || true
done

for iface in wlan0 wlan2 wlan4; do
    [ -d "/sys/class/net/$iface" ] || continue
    ip link set "$iface" nomaster 2>/dev/null || true
    ip link set "$iface" down 2>/dev/null || true
done
