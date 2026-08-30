#!/bin/bash
set -euo pipefail

role=${1:?controller or agent}
case "$role" in
    controller) prefix=01; al_mac=02:00:00:27:01:01; mode=Multi-AP-Controller-and-Agent ;;
    agent) prefix=02; al_mac=02:00:00:27:02:01; mode=Multi-AP-Agent ;;
    *) echo "unknown role: $role" >&2; exit 2 ;;
esac

install=/opt/prpl-install-dummy
test -x "$install/scripts/prplmesh_utils.sh"

bridge_ip=$(ip -4 -o addr show dev eth1 | awk '{print $4; exit}')
ip link show br-lan >/dev/null 2>&1 || ip link add br-lan type bridge
ip link set br-lan address "$al_mac"

interfaces='eth0_1 eth0_2 eth0_3 eth0_4 wlan0 wlan0.0 wlan0.1 wlan0.2 wlan0.3 wlan2 wlan2.0 wlan2.1 wlan2.2 wlan2.3'
for iface in $interfaces; do
    ip link show "$iface" >/dev/null 2>&1 || ip link add "$iface" type dummy
done

ip link set wlan0 address "02:00:00:27:$prefix:10"
ip link set wlan2 address "02:00:00:27:$prefix:20"
for suffix in 0 1 2 3; do
    digit=$((suffix + 1))
    ip link set "wlan0.$suffix" address "02:00:00:27:$prefix:1$digit"
    ip link set "wlan2.$suffix" address "02:00:00:27:$prefix:2$digit"
done

ip link set eth1 master br-lan
for iface in $interfaces; do
    ip link set "$iface" master br-lan
    ip link set "$iface" up
done
ip address flush dev eth1
if [ -n "$bridge_ip" ] && ! ip -4 address show dev br-lan | grep -q "$bridge_ip"; then
    ip address add "$bridge_ip" dev br-lan
fi
ip link set br-lan up

mkdir -p /var/run/ubus
pgrep -x ubusd >/dev/null || /usr/sbin/ubusd
"$install/scripts/prplmesh_utils.sh" start --cert true --mode "$mode"
