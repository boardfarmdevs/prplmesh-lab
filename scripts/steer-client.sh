#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
source "$ROOT/scripts/lib/nbapi-btm.sh"
CONTROLLER=prpl-controller
request_only=0
if [[ ${1:-} == --request-only ]]; then
    request_only=1
    shift
fi
client_name=${1:?client: sta-NN, iot-NN or STA MAC}
target_name=${2:?target: controller, agent-N, extender-N or BSSID}
steering_ui=${PRPL_STEERING_UI:-http://127.0.0.1:8091/api/v1/steering-event}
preview_seconds=${PRPL_STEERING_PREVIEW_SECONDS:-${EASYMESH_STEERING_PREVIEW_SECONDS:-0}}

if [[ "$client_name" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
    mac=${client_name,,}
    prefix=$(printf '%s\n' "$mac" | cut -d: -f4)
    cohort_ordinal=$((16#$(printf '%s\n' "$mac" | cut -d: -f5)))
    case "$prefix" in
        10) cohort=private; ordinal=$((cohort_ordinal * 2 - 1)); printf -v client_name 'sta-%02x' "$cohort_ordinal" ;;
        20) cohort=iot; ordinal=$((cohort_ordinal * 2)); printf -v client_name 'iot-%02x' "$cohort_ordinal" ;;
        *) echo "unsupported prplMesh STA identity: $mac" >&2; exit 2 ;;
    esac
else
    case "$client_name" in
        sta-*) cohort=private; prefix=10; cohort_ordinal=$((10#${client_name#sta-})); ordinal=$((cohort_ordinal * 2 - 1)) ;;
        iot-*) cohort=iot; prefix=20; cohort_ordinal=$((10#${client_name#iot-})); ordinal=$((cohort_ordinal * 2)) ;;
        *) echo "client must be sta-NN, iot-NN or a prplMesh STA MAC" >&2; exit 2 ;;
    esac
    printf -v mac '02:00:00:%s:%02x:00' "$prefix" "$cohort_ordinal"
fi
target_override=
if [[ "$target_name" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
    target_override=${target_name,,}
    radio_octet=$(printf '%s\n' "$target_override" | cut -d: -f5)
    target_node=$((16#$radio_octet / 3))
    if [ "$target_node" -eq 0 ]; then
        target_name=controller
    else
        target_name=agent-$target_node
    fi
else
    case "$target_name" in
        controller) target_node=0 ;;
        agent-*) target_node=$((10#${target_name#agent-})) ;;
        extender-*) target_node=$((10#${target_name#extender-})); target_name=agent-$target_node ;;
        *) echo "target must be controller, agent-N, extender-N or a BSSID" >&2; exit 2 ;;
    esac
fi
printf -v container 'prpl-client-%02d' "$ordinal"

station_object()
{
    lxc exec --mode non-interactive "$CONTROLLER" -- timeout -k 1 8 ubus -t 5 call \
        Device.WiFi.DataElements.Network _get \
        '{"rel_path":"Device.*.Radio.*.BSS.*.STA.","depth":0}' </dev/null |
        python3 "$ROOT/scripts/lib/nbapi-station.py" "$mac"
}

model_bssid()
{
    local station bss value
    station=$(station_object) || return 1
    bss=${station%.STA.*}
    value=$(lxc exec --mode non-interactive "$CONTROLLER" -- timeout -k 1 8 ubus -t 5 call \
        Device.WiFi.DataElements.Network _get \
        "{\"rel_path\":\"${bss#Device.WiFi.DataElements.Network.}.\",\"depth\":0}" </dev/null) || return
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
if [ -n "$target_override" ]; then
    target=$target_override
else
    printf -v target '02:00:00:00:%02x:%s' "$((target_node * 3 + local_radio))" "$bss_suffix"
fi

if [ "$source" != "$target" ]; then
    object=$(station_object)
    request=$(printf \
        '{"DisassociationImminent":false,"DisassociationTimer":0,"BSSTerminationDuration":0,"ValidityInterval":10,"SteeringTimer":50,"TargetBSS":"%s"}' \
        "$target")
    status_section "prplMesh steering: $client_name to $target_name"
    status_note "Station $mac currently uses $source; target BSSID is $target."
    announce_steering planned
    status_wait_seconds "$preview_seconds" "highlighting $client_name in the topology before it moves"
    announce_steering moving
    status_action "Sending the NBAPI BTM request for $mac to $target."
    nbapi_btm_request "$object" "$request"
    if ((request_only)); then
        status_pass "The prplMesh NBAPI accepted the BTM request; verification is delegated to the caller."
        echo "PASS: BTM request submitted for $client_name to $target"
        exit 0
    fi
else
    status_pass "$client_name is already on $target_name ($target)."
fi

status_wait "Waiting up to 45s for physical association and NBAPI ownership to agree."
for attempt in $(seq 1 45); do
    physical=$(physical_bssid || true)
    modeled=$(model_bssid || true)
    if [ "$physical" = "$target" ] && [ "$modeled" = "$target" ]; then
        announce_steering completed
        status_pass "$client_name converged physically and in NBAPI on $target_name."
        echo "PASS: $client_name converged physically and in NBAPI on $target_name"
        exit 0
    fi
    sleep 1
done
announce_steering failed
echo "steering timeout: physical=${physical:-none} modeled=${modeled:-none} target=$target" >&2
exit 1
