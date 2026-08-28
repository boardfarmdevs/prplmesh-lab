#!/bin/bash
set -euo pipefail

role=${1:?controller or agent}
case "$role" in
    controller)
        al_mac=02:00:00:27:01:01
        mode=Multi-AP-Controller-and-Agent
        ;;
    agent)
        al_mac=02:00:00:27:02:01
        mode=Multi-AP-Agent
        ;;
    *) echo "unknown role: $role" >&2; exit 2 ;;
esac

install=/opt/prpl-install-nl80211
project=/mnt/project
test -x "$install/scripts/prplmesh_utils.sh"
tar -C /usr/local -xzf "$project/artifacts/hostap-runtime-2.10.tar.gz"

"$install/scripts/prplmesh_utils.sh" stop >/dev/null 2>&1 || true
pkill -x hostapd 2>/dev/null || true
pkill -x ubusd 2>/dev/null || true
rm -rf /tmp/beerocks /var/run/hostapd/* /var/run/ubus/ubus.sock
mkdir -p /tmp/beerocks /var/run/hostapd /var/run/ubus

backhaul_ip=$(ip -4 -o addr show dev eth1 | awk '{print $4; exit}')
ip link show br-lan >/dev/null 2>&1 || ip link add br-lan type bridge
ip link set br-lan address "$al_mac"
ip link set eth1 master br-lan
ip address flush dev eth1
if [ -n "$backhaul_ip" ]; then
    ip address replace "$backhaul_ip" dev br-lan
fi
ip link set eth1 up
ip link set br-lan up

for iface in wlan0 wlan2 wlan4; do
    test -d "/sys/class/net/$iface" || {
        echo "$role is missing assigned radio $iface" >&2
        exit 1
    }
    install -m 0644 "$project/manifests/hostapd-$iface.conf" \
        "/etc/hostapd/$iface.conf"
    hostapd -B -P "/run/hostapd-$iface.pid" \
        -f "/tmp/hostapd-$iface.log" "/etc/hostapd/$iface.conf"
done

/usr/sbin/ubusd
"$install/scripts/prplmesh_utils.sh" start --cert true --mode "$mode"

for iface in wlan0 wlan2 wlan4; do
    hostapd_cli -i "$iface" ping | grep -q PONG
done
