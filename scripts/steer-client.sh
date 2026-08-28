#!/bin/bash
set -euo pipefail

CONTROLLER=prpl-controller
client_name=${1:?client name: sta-NN or iot-NN}
target_name=${2:?target: controller or agent-N}
steering_ui=${PRPL_STEERING_UI:-http://127.0.0.1:8091/api/v1/steering-event}
preview_seconds=${PRPL_STEERING_PREVIEW_SECONDS:-3}

case "$client_name" in
    sta-*) cohort=private; prefix=10; cohort_ordinal=$((10#${client_name#sta-})); ordinal=$((cohort_ordinal * 2 - 1)) ;;
    iot-*) cohort=iot; prefix=20; cohort_ordinal=$((10#${client_name#iot-})); ordinal=$((cohort_ordinal * 2)) ;;
    *) echo "client must be sta-NN or iot-NN" >&2; exit 2 ;;
esac
case "$target_name" in
    controller) target_node=0 ;;
    agent-*) target_node=$((10#${target_name#agent-})) ;;
    *) echo "target must be controller or agent-N" >&2; exit 2 ;;
esac
printf -v container 'prpl-client-%02d' "$ordinal"
printf -v mac '02:00:00:%s:%02x:00' "$prefix" "$cohort_ordinal"

station_object()
{
    local object value instances
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
    local station bss value
    station=$(station_object) || return 1
    bss=${station%.STA.*}
    value=$(lxc exec "$CONTROLLER" -- ubus call "$bss" _get \
        '{"rel_path":"","depth":0}' 2>/dev/null || true)
    printf '%s\n' "$value" | sed -n 's/.*"BSSID": "\([^"]*\)".*/\1/p'
}

physical_bssid()
{
    lxc exec "$container" -- wpa_cli -i wlan0 status 2>/dev/null | sed -n 's/^bssid=//p'
}

announce_steering()
{
    local phase=$1
    curl -fsS --max-time 2 -X POST -H 'Content-Type: application/json' \
        --data "{\"sta_mac\":\"$mac\",\"client_name\":\"$client_name\",\"target_name\":\"$target_name\",\"phase\":\"$phase\"}" \
        "$steering_ui" >/dev/null 2>&1 || true
}

source=$(physical_bssid)
radio_octet=$(printf '%s\n' "$source" | cut -d: -f5)
local_radio=$((16#$radio_octet % 3))
[ "$cohort" = iot ] && bss_suffix=01 || bss_suffix=00
printf -v target '02:00:00:00:%02x:%s' "$((target_node * 3 + local_radio))" "$bss_suffix"

if [ "$source" != "$target" ]; then
    object=$(station_object)
    request=$(printf \
        '{"DisassociationImminent":false,"DisassociationTimer":0,"BSSTerminationDuration":0,"ValidityInterval":10,"SteeringTimer":50,"TargetBSS":"%s"}' \
        "$target")
    echo "$client_name ($mac): $source -> $target ($target_name)"
    announce_steering planned
    sleep "$preview_seconds"
    announce_steering moving
    lxc exec "$CONTROLLER" -- ubus call "${object}.MultiAPSTA" \
        BTMRequest "$request" >/dev/null
else
    echo "$client_name ($mac) is already on $target_name ($target)"
fi

for attempt in $(seq 1 45); do
    physical=$(physical_bssid || true)
    modeled=$(model_bssid || true)
    if [ "$physical" = "$target" ] && [ "$modeled" = "$target" ]; then
        announce_steering completed
        echo "PASS: $client_name converged physically and in NBAPI on $target_name"
        exit 0
    fi
    sleep 1
done
announce_steering failed
echo "steering timeout: physical=${physical:-none} modeled=${modeled:-none} target=$target" >&2
exit 1
