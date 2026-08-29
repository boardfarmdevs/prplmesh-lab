#!/bin/bash
set -euo pipefail

agents=${PRPL_AGENT_COUNT:-4}
clients=${PRPL_CLIENT_COUNT:-20}

check_count()
{
    local container=$1 process=$2 expected=$3 actual
    actual=$(lxc exec "$container" -- pgrep -cx "$process" 2>/dev/null || true)
    [ "${actual:-0}" -eq "$expected" ] || {
        echo "$container: expected $expected $process process(es), found ${actual:-0}" >&2
        return 1
    }
}

printf '%-18s %10s %10s\n' NODE RSS_KB PROCESSES
for node in prpl-controller $(printf 'prpl-agent-%02d ' $(seq 1 "$agents")); do
    rss=$(lxc exec "$node" -- sh -lc \
        "ps -eo rss,args | awk '/beerocks_|ieee1905_transport|hostapd|wpa_supplicant/ && !/awk/ {sum += \$1} END {print sum+0}'")
    processes=$(lxc exec "$node" -- sh -lc \
        "pgrep -c -f 'beerocks_|ieee1905_transport|hostapd|wpa_supplicant' || true")
    printf '%-18s %10s %10s\n' "$node" "$rss" "$processes"
    check_count "$node" beerocks_agent 1
    check_count "$node" beerocks_fronth 3
    check_count "$node" ieee1905_transp 1
    check_count "$node" hostapd 1
    if [ "$node" = prpl-controller ]; then
        check_count "$node" beerocks_contro 1
        check_count "$node" wpa_supplicant 0
    else
        check_count "$node" beerocks_contro 0
        check_count "$node" wpa_supplicant 1
    fi
    lxc exec "$node" -- sh -lc \
        '! pgrep -f "[/](snapd|unattended-upgrade)" >/dev/null'
done

for ordinal in $(seq 1 "$clients"); do
    printf -v node 'prpl-client-%02d' "$ordinal"
    check_count "$node" wpa_supplicant 1
    lxc exec "$node" -- sh -lc \
        '! pgrep -f "[/](snapd|unattended-upgrade)" >/dev/null'
done

medium_pid=$(cat /run/prpl-wmediumd/wmediumd.pid)
kill -0 "$medium_pid"
medium_rss=$(awk '/^VmRSS:/ {print $2}' "/proc/$medium_pid/status")
echo "wmediumd RSS_KB=$medium_rss pid=$medium_pid"
echo "PASS: process cardinality, background-service exclusion and runtime footprint"
