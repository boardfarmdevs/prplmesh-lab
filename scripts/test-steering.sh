#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/scripts/lib/nbapi-btm.sh"
CONTROLLER=prpl-controller

station_object()
{
    local mac=$1 values
    values=$(lxc exec --mode non-interactive "$CONTROLLER" -- timeout -k 1 8 \
        ubus call Device.WiFi.DataElements.Network _get \
        '{"rel_path":"Device.*.Radio.*.BSS.*.STA.","depth":0}' </dev/null) || return
    printf '%s\n' "$values" | jq -ers --arg mac "$mac" '
        if any(.[]; (."amxd-error-code" // 0) != 0) then
            error("native station query failed")
        else
            [ .[] | to_entries[] | select(.value | type == "object")
              | select(.value.MACAddress == $mac)
              | .key | select(test("^Device[.]WiFi[.]DataElements[.]Network[.]Device[.][0-9]+[.]Radio[.][0-9]+[.]BSS[.][0-9]+[.]STA[.][0-9]+[.]$"))
              | rtrimstr(".") ]
            | if length == 1 then .[0] else error("station ownership missing or ambiguous") end
        end'
}

model_bssid()
{
    local mac=$1 station bss value
    station=$(station_object "$mac") || return 1
    bss=${station%.STA.*}
    value=$(lxc exec --mode non-interactive "$CONTROLLER" -- timeout -k 1 8 \
        ubus call Device.WiFi.DataElements.Network _get \
        "{\"rel_path\":\"${bss#Device.WiFi.DataElements.Network.}.\",\"depth\":0}" </dev/null) || return
    printf '%s\n' "$value" | jq -ers --arg object "$bss." '
        if any(.[]; (."amxd-error-code" // 0) != 0) then
            error("native BSS query failed")
        else
            [ .[] | .[$object].BSSID | select(type == "string" and length > 0) ]
            | if length == 1 then .[0] else error("native BSSID missing or ambiguous") end
        end'
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

btm_response_count()
{
    local node=$1 radio=$2 mac=$3 target=$4
    lxc exec "$node" -- sh -c '
        radio=$1
        sta=$2
        target=$3
        for file in /tmp/beerocks/logs/beerocks_ap_manager_"$radio"*.log; do
            [ -f "$file" ] || continue
            grep -h -F "BSS-TM-RESP $sta " "$file" 2>/dev/null || true
        done | awk -v status="status_code=0" -v destination="target_bssid=$target" '\''
            index($0, status) && index($0, destination) { count++ }
            END { print count + 0 }
        '\''
    ' sh "$radio" "$mac" "$target"
}

wait_for_btm_response()
{
    local node=$1 radio=$2 mac=$3 target=$4 before=$5 attempt current
    for attempt in $(seq 1 10); do
        current=$(btm_response_count "$node" "$radio" "$mac" "$target")
        if [ "$current" -gt "$before" ]; then
            return
        fi
        sleep 1
    done
    echo "BTM response missing: node=$node radio=$radio sta=$mac target=$target before=$before current=$current" >&2
    return 1
}

test_btm()
{
    local client=$1 mac=$2 cohort=$3 band=$4 source target object request responses_before
    source=$(client_bssid "$client")
    target=$(next_bssid "$source" "$cohort")
    object=$(station_object "$mac")
    source_node_and_radio "$source"
    responses_before=$(btm_response_count \
        "$SOURCE_NODE" "$SOURCE_RADIO" "$mac" "$target")

    request=$(printf \
        '{"DisassociationImminent":false,"DisassociationTimer":0,"BSSTerminationDuration":0,"ValidityInterval":10,"SteeringTimer":50,"TargetBSS":"%s"}' \
        "$target")
    echo "BTM ${band}GHz ${cohort}: $client $mac $source -> $target"
    nbapi_btm_request "$object" "$request"
    wait_for_target "$client" "$mac" "$target"
    wait_for_btm_response \
        "$SOURCE_NODE" "$SOURCE_RADIO" "$mac" "$target" "$responses_before"
    echo "PASS ${band}GHz ${cohort}: physical association, NBAPI ownership and BTM response agree"
}

# Exercise both fronthaul SSIDs and two independent radio implementations.
test_btm prpl-client-03 02:00:00:10:02:00 private 5
test_btm prpl-client-08 02:00:00:20:04:00 iot 6
echo "PASS: two-SSID prplMesh NBAPI steering acceptance"
