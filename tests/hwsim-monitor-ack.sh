#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
monitor=hwsim0
pidfile=/run/prpl-wmediumd/wmediumd.pid
kernel_log=$(mktemp /tmp/prpl-hwsim-monitor-ack.XXXXXX)
before_lines=$(dmesg | wc -l)

cleanup()
{
    ip link set "$monitor" down 2>/dev/null || true
    rm -f "$kernel_log"
}
trap cleanup EXIT

[ -e "/sys/class/net/$monitor" ] || {
    echo "hwsim monitor interface is absent: $monitor" >&2
    exit 1
}
if ip -o link show "$monitor" | grep -q '<[^>]*UP'; then
    echo "hwsim monitor must be down before the regression" >&2
    exit 1
fi
[ -r "$pidfile" ]
medium_pid=$(cat "$pidfile")
kill -0 "$medium_pid"

# Enabling the radiotap monitor makes hwsim construct ACK monitor frames.
# The old multichannel path dereferenced a NULL data->channel on the first
# successful ACK and oopsed the guest kernel.
ip link set "$monitor" up
lxc exec prpl-client-01 -- ping -q -c 3 -W 2 192.168.77.1 >/dev/null
sleep 1
dmesg | tail -n "+$((before_lines + 1))" > "$kernel_log"

if grep -Eq 'BUG: kernel NULL pointer|mac80211_hwsim_monitor_ack|Oops:' \
        "$kernel_log"; then
    echo "hwsim monitor ACK caused a kernel fault" >&2
    cat "$kernel_log" >&2
    exit 1
fi
kill -0 "$medium_pid"

# A fault in the generic-netlink receive path leaves later nl80211 callers
# blocked in genl_rcv_msg.  A bounded successful dump proves that did not
# happen, after the fault check above makes this safe on a broken build.
timeout -k 2 10 lxc exec prpl-controller -- \
    iw dev wlan0 station dump >/dev/null

echo 'PASS: multichannel hwsim monitor ACK preserves kernel and nl80211 health'
