#!/bin/bash
set -euo pipefail

CONTROLLER=prpl-controller

station_object()
{
    local mac=$1 object value instances
    instances=$(lxc exec "$CONTROLLER" -- ubus call \
        Device.WiFi.DataElements.Network _get_instances \
        '{"rel_path":"Device.*.Radio.*.BSS.*.STA.","depth":1}' | \
        sed -n 's/^[[:space:]]*"\([^"]*\.STA\.[0-9][0-9]*\)\.":.*/\1/p')
    while read -r object; do
        value=$(lxc exec "$CONTROLLER" -- ubus call "$object" _get \
            '{"rel_path":"","depth":0}' </dev/null 2>/dev/null || true)
        if printf '%s\n' "$value" | grep -q "\"MACAddress\": \"$mac\""; then
            printf '%s\n' "$object"
            return
        fi
    done <<< "$instances"
    return 1
}

model_bssid()
{
    local mac=$1 station bss value
    station=$(station_object "$mac") || return 1
    bss=${station%.STA.*}
    value=$(lxc exec "$CONTROLLER" -- ubus call "$bss" _get \
        '{"rel_path":"","depth":0}' 2>/dev/null || true)
    printf '%s\n' "$value" | sed -n \
        's/.*"BSSID": "\([^"]*\)".*/\1/p'
}

client_bssid()
{
    lxc exec "$1" -- wpa_cli -i wlan0 status 2>/dev/null | \
        sed -n 's/^bssid=//p'
}

wait_for_target()
{
    local client=$1 mac=$2 target=$3 attempt physical modeled
    for attempt in $(seq 1 45); do
        physical=$(client_bssid "$client" || true)
        modeled=$(model_bssid "$mac" || true)
        if [ "$physical" = "$target" ] && [ "$modeled" = "$target" ]; then
            return
        fi
        sleep 1
    done
    echo "steering convergence timeout: client=$client physical=${physical:-none} model=${modeled:-none} target=$target" >&2
    return 1
}

next_bssid()
{
    local source=$1 cohort=$2 octet radio local_radio source_node target_node node_count suffix
    octet=$(printf '%s\n' "$source" | cut -d: -f5)
    radio=$((16#$octet))
    local_radio=$((radio % 3))
    source_node=$((radio / 3))
    node_count=$((1 + $(lxc list '^prpl-agent-' -c s --format csv | grep -c '^RUNNING$')))
    [ "$node_count" -gt 1 ] || {
        echo "steering requires at least one running agent" >&2
        return 1
    }
    target_node=$(((source_node + 1) % node_count))
    [ "$cohort" = iot ] && suffix=01 || suffix=00
    printf '02:00:00:00:%02x:%s\n' "$((target_node * 3 + local_radio))" "$suffix"
}

source_node_and_radio()
{
    local source=$1 octet radio node local_radio
    octet=$(printf '%s\n' "$source" | cut -d: -f5)
    radio=$((16#$octet))
    node=$((radio / 3))
    local_radio=$((radio % 3))
    if [ "$node" -eq 0 ]; then
        SOURCE_NODE=prpl-controller
    else
        printf -v SOURCE_NODE 'prpl-agent-%02d' "$node"
    fi
    case "$local_radio" in
        0) SOURCE_RADIO=wlan0 ;;
        1) SOURCE_RADIO=wlan2 ;;
        2) SOURCE_RADIO=wlan4 ;;
        *) return 1 ;;
    esac
}

test_btm()
{
    local client=$1 mac=$2 cohort=$3 band=$4 source target object request
    source=$(client_bssid "$client")
    target=$(next_bssid "$source" "$cohort")
    object=$(station_object "$mac")
    source_node_and_radio "$source"

    request=$(printf \
        '{"DisassociationImminent":false,"DisassociationTimer":0,"BSSTerminationDuration":0,"ValidityInterval":10,"SteeringTimer":50,"TargetBSS":"%s"}' \
        "$target")
    echo "BTM ${band}GHz ${cohort}: $client $mac $source -> $target"
    lxc exec "$CONTROLLER" -- ubus call "${object}.MultiAPSTA" \
        BTMRequest "$request" >/dev/null
    wait_for_target "$client" "$mac" "$target"

    lxc exec "$SOURCE_NODE" -- grep -q \
        "BSS-TM-RESP $mac status_code=0.*target_bssid=$target" \
        "/tmp/beerocks/logs/beerocks_ap_manager_${SOURCE_RADIO}.log"
    echo "PASS ${band}GHz ${cohort}: physical association, NBAPI ownership and BTM response agree"
}

# Exercise both fronthaul SSIDs and two independent radio implementations.
test_btm prpl-client-03 02:00:00:10:02:00 private 5
test_btm prpl-client-08 02:00:00:20:04:00 iot 6
echo "PASS: two-SSID prplMesh NBAPI steering acceptance"
