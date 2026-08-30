#!/bin/bash
set -euo pipefail

role=${1:?controller or agent}
ordinal=${2:-0}
backhaul_mode=${3:-wired}
backhaul_bssid=${4:-02:00:00:00:01:02}
case "$role" in
    controller)
        al_mac=02:00:00:27:01:01
        mode=Multi-AP-Controller-and-Agent
        ordinal=0
        ;;
    agent)
        case "$ordinal" in
            ''|*[!0-9]*|0) echo "agent ordinal must be a positive integer" >&2; exit 2 ;;
        esac
        printf -v al_mac '02:00:00:27:%02x:01' "$((ordinal + 1))"
        mode=Multi-AP-Agent
        ;;
    *) echo "unknown role: $role" >&2; exit 2 ;;
esac

install=/opt/prpl-install-nl80211
project=/mnt/project
test -x "$install/scripts/prplmesh_utils.sh"
tar -C /usr/local -xzf "$project/artifacts/hostap-runtime-2.10.tar.gz"

"$install/scripts/prplmesh_utils.sh" stop >/dev/null 2>&1 || true
tar -C /opt -xzf "$project/artifacts/prpl-install-nl80211-6.0.0.tar.gz"
# Upstream hostapd does not emit prplMesh's raw association-frame event. The
# lab's wpa_supplicant is built with WNM/802.11v, so allow the agent to issue
# BTM requests even though the missing frame leaves supports_11v unknown.
sed -i 's/^send_btm_to_non_11v_sta=.*/send_btm_to_non_11v_sta=1/' \
    "$install/config/beerocks_agent.conf"
pkill -x hostapd 2>/dev/null || true
pkill -x wpa_supplicant 2>/dev/null || true
pkill -x ubusd 2>/dev/null || true
rm -rf /tmp/beerocks /var/run/hostapd/* /var/run/ubus/ubus.sock
rm -rf /var/run/wpa_supplicant/*
mkdir -p /tmp/beerocks /var/run/hostapd /var/run/ubus /var/run/wpa_supplicant

ip link show br-lan >/dev/null 2>&1 || ip link add br-lan type bridge
ip link set br-lan address "$al_mac"
if [ "$backhaul_mode" = wired ]; then
    test -d /sys/class/net/eth1 || {
        echo "$role $ordinal is missing wired backhaul eth1" >&2
        exit 1
    }
    backhaul_ip=$(ip -4 -o addr show dev eth1 | awk '{print $4; exit}')
    ip link set eth1 master br-lan
    ip address flush dev eth1
    if [ -n "$backhaul_ip" ]; then
        ip address replace "$backhaul_ip" dev br-lan
    fi
    ip link set eth1 up
elif [ "$backhaul_mode" != wireless ]; then
    echo "backhaul mode must be wired or wireless" >&2
    exit 2
fi
ip link set br-lan up
if [ "$role" = controller ]; then
    # The lab uses a self-contained L2 data plane.  Keep its address separate
    # from the LXD management interface so traffic tests must cross the mesh
    # bridge and, for leaf clients, every wireless backhaul hop.
    ip address replace 192.168.77.1/24 dev br-lan
fi

for iface in wlan0 wlan2 wlan4; do
    test -d "/sys/class/net/$iface" || {
        echo "$role is missing assigned radio $iface" >&2
        exit 1
    }
    install -m 0644 "$project/manifests/hostapd-$iface.conf" \
        "/etc/hostapd/$iface.conf"
done

if [ "$backhaul_mode" = wireless ]; then
    iw dev wlan3 del 2>/dev/null || true
    iw dev wlan2 interface add wlan3 type station
    printf -v bsta_suffix '%02x' "$ordinal"
    ip link set wlan3 down
    ip link set wlan3 address "02:00:00:30:${bsta_suffix}:00"
    iw dev wlan3 set 4addr on
    ip link set wlan3 up

    # The 6.0.0 Linux platform maps a radio's supplicant path back to its AP
    # interface. Preserve a separate hwsim STA VIF and provide both lookup
    # keys until the corresponding native-platform patch is rebuilt.
    platform_db="$install/share/prplmesh_platform_db"
    sed -i \
        's#^wpa_supplicant_ctrl_path_wlan2=.*#wpa_supplicant_ctrl_path_wlan2=/var/run/wpa_supplicant/wlan3#' \
        "$platform_db"
    grep -q '^wpa_supplicant_ctrl_path_wlan3=' "$platform_db" ||
        echo 'wpa_supplicant_ctrl_path_wlan3=/var/run/wpa_supplicant/wlan3' >> "$platform_db"
fi

install -m 0644 /etc/hostapd/wlan0.conf /var/run/hostapd-phy0.conf
install -m 0644 /etc/hostapd/wlan2.conf /var/run/hostapd-phy1.conf
install -m 0644 /etc/hostapd/wlan4.conf /var/run/hostapd-phy2.conf
hostapd -B -g /var/run/hostapd/global -P /run/hostapd.pid \
    -f /tmp/hostapd.log \
    /etc/hostapd/wlan0.conf /etc/hostapd/wlan2.conf /etc/hostapd/wlan4.conf

if [ "$backhaul_mode" = wireless ]; then
    install -m 0644 "$project/manifests/wpa_backhaul.conf" \
        /etc/wpa_supplicant-backhaul.conf
    sed -i "s/@TARGET_BSSID@/$backhaul_bssid/" \
        /etc/wpa_supplicant-backhaul.conf
    wpa_supplicant -B -Dnl80211 -i wlan3 -b br-lan \
        -c /etc/wpa_supplicant-backhaul.conf -f /tmp/wpa_backhaul.log
    for unused in $(seq 1 60); do
        state=$(wpa_cli -i wlan3 status 2>/dev/null | \
            sed -n 's/^wpa_state=//p' || true)
        [ "$state" = COMPLETED ] && break
        sleep 0.5
    done
    [ "${state:-}" = COMPLETED ] || {
        wpa_cli -i wlan3 status >&2 || true
        echo "wireless backhaul did not associate with $backhaul_bssid" >&2
        exit 1
    }
    ip link set wlan3 master br-lan
fi

/usr/sbin/ubusd > /tmp/ubusd.log 2>&1 &
echo $! > /run/ubusd.pid
for unused in $(seq 1 50); do
    [ -S /var/run/ubus/ubus.sock ] && break
    sleep 0.1
done
[ -S /var/run/ubus/ubus.sock ]
"$install/scripts/prplmesh_utils.sh" start --cert false --mode "$mode"

for iface in wlan0 wlan2 wlan4; do
    hostapd_cli -i "$iface" ping | grep -q PONG
done
