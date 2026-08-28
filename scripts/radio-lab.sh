#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../../manifests/lab.env
source "$ROOT/manifests/lab.env"

ACTION=${1:-status}
RUNTIME_IMAGE=prpl-runtime-local
CONTROLLER=$CONTROLLER_CONTAINER
ACTIVE_AGENTS=${PRPL_AGENT_COUNT:-$ACTIVE_AGENT_COUNT}
ACTIVE_CLIENTS=${PRPL_CLIENT_COUNT:-$ACTIVE_CLIENT_COUNT}
TOPOLOGY=${PRPL_TOPOLOGY:-$DEFAULT_TOPOLOGY}

require_count()
{
    local value=$1 maximum=$2 label=$3
    case "$value" in
        ''|*[!0-9]*|0) echo "$label must be a positive integer" >&2; exit 2 ;;
    esac
    [ "$value" -le "$maximum" ] || {
        echo "$label $value exceeds provisioned maximum $maximum" >&2
        exit 2
    }
}

require_count "$ACTIVE_AGENTS" "$PROVISIONED_AGENT_COUNT" PRPL_AGENT_COUNT
require_count "$ACTIVE_CLIENTS" "$PROVISIONED_CLIENT_COUNT" PRPL_CLIENT_COUNT
case "$TOPOLOGY" in
    star|branch|chain) ;;
    *) echo "PRPL_TOPOLOGY must be star, branch or chain" >&2; exit 2 ;;
esac

agent_name()
{
    printf 'prpl-agent-%02d' "$1"
}

client_name()
{
    printf 'prpl-client-%02d' "$1"
}

radio_host_name()
{
    # Never use wlanN as an LXD device identity. The same names are also used
    # inside mesh containers, and physical-NIC attachment can consequently
    # exchange radios while resolving target-name collisions. A host-only
    # name derived from the permanent hwsim radio ordinal is unambiguous.
    printf 'prpl-r%02d' "$1"
}

name_radio_pool()
{
    local ordinal expected iface stable count=0

    for ordinal in $(seq 0 $((HWSIM_RADIOS - 1))); do
        printf -v expected '02:00:00:00:%02x:00' "$ordinal"
        iface=
        for address_file in /sys/class/net/*/address; do
            [ "$(cat "$address_file")" = "$expected" ] || continue
            iface=${address_file%/address}
            iface=${iface##*/}
            break
        done
        [ -n "$iface" ] || {
            echo "hwsim radio $ordinal ($expected) is missing from the host" >&2
            return 1
        }
        stable=$(radio_host_name "$ordinal")
        if [ "$iface" != "$stable" ]; then
            ip link set "$iface" name "$stable"
        fi
        count=$((count + 1))
    done

    [ "$count" -eq "$HWSIM_RADIOS" ]
}

agent_al()
{
    printf '02:00:00:27:%02x:01' "$(( $1 + 1 ))"
}

ensure_network()
{
    lxc network show "$BACKHAUL_NETWORK" >/dev/null 2>&1 ||
        lxc network create "$BACKHAUL_NETWORK" ipv4.address=10.88.28.1/24 \
            ipv4.nat=false ipv6.address=none
}

ensure_project_mount()
{
    local name=$1
    if ! lxc config device show "$name" | grep -q '^project:'; then
        lxc config device add "$name" project disk source="$ROOT" path=/mnt/project
    fi
}

ensure_radio_device()
{
    local name=$1 device=$2 parent=$3 inside=$4
    if lxc config device show "$name" | grep -q "^${device}:"; then
        lxc config device set "$name" "$device" parent "$parent"
        lxc config device set "$name" "$device" name "$inside"
    else
        lxc config device add "$name" "$device" nic nictype=physical \
            parent="$parent" name="$inside"
    fi
}

ensure_wired_backhaul()
{
    local name=$1
    if ! lxc config device show "$name" | grep -q '^backhaul:'; then
        lxc config device add "$name" backhaul nic \
            network="$BACKHAUL_NETWORK" name=eth1
    fi
}

remove_wired_backhaul()
{
    local name=$1
    if lxc config device show "$name" | grep -q '^backhaul:'; then
        lxc config device remove "$name" backhaul
    fi
}

create_node()
{
    local name=$1 first_radio=$2 backhaul=$3
    if ! lxc info "$name" >/dev/null 2>&1; then
        lxc init "$RUNTIME_IMAGE" "$name" -c security.privileged=true
    fi
    [ "$(lxc list "$name" -c s --format csv)" != RUNNING ] || {
        echo "$name must be stopped before provisioning" >&2
        return 1
    }
    ensure_project_mount "$name"
    ensure_radio_device "$name" radio0 "$(radio_host_name "$first_radio")" wlan0
    ensure_radio_device "$name" radio1 "$(radio_host_name "$((first_radio + 1))")" wlan2
    ensure_radio_device "$name" radio2 "$(radio_host_name "$((first_radio + 2))")" wlan4
    if [ "$backhaul" = wired ]; then
        ensure_wired_backhaul "$name"
    else
        remove_wired_backhaul "$name"
    fi
    lxc config set "$name" boot.autostart false
}

create_client()
{
    local name=$1 radio=$2
    if ! lxc info "$name" >/dev/null 2>&1; then
        lxc init "$RUNTIME_IMAGE" "$name" -c security.privileged=true
    fi
    [ "$(lxc list "$name" -c s --format csv)" != RUNNING ] || {
        echo "$name must be stopped before provisioning" >&2
        return 1
    }
    ensure_project_mount "$name"
    ensure_radio_device "$name" radio "$(radio_host_name "$radio")" wlan0
    lxc config set "$name" boot.autostart false
}

stop_medium()
{
    if [ -r /run/prpl-wmediumd.pid ]; then
        kill "$(cat /run/prpl-wmediumd.pid)" 2>/dev/null || true
        rm -f /run/prpl-wmediumd.pid
    fi
    pkill -x wmediumd 2>/dev/null || true
}

start_medium()
{
    if [ -r /run/prpl-wmediumd.pid ] &&
       kill -0 "$(cat /run/prpl-wmediumd.pid)" 2>/dev/null; then
        return
    fi
    "$ROOT/build/bin/wmediumd" -l 6 -c "$ROOT/manifests/wmediumd.conf" \
        > /tmp/prpl-wmediumd.log 2>&1 &
    echo $! > /run/prpl-wmediumd.pid
    sleep 1
    kill -0 "$(cat /run/prpl-wmediumd.pid)"
}

start_container()
{
    local name=$1
    if [ "$(lxc list "$name" -c s --format csv)" != RUNNING ]; then
        lxc start "$name"
    fi
}

controller_cli()
{
    local command="$*"
    lxc exec "$CONTROLLER" -- /opt/prpl-install-nl80211/bin/beerocks_cli \
        -c "$command"
}

controller_model_contains()
{
    local pattern=$1
    # bml_conn_map is a presentation command, not a reliable state API: with
    # a Wi-Fi backhaul plus several fronthaul STAs the 6.0.0 CLI can wait
    # indefinitely for its asynchronous map callback. Query bounded Device or
    # STA instances from the authoritative NBAPI tree instead.
    lxc exec "$CONTROLLER" -- \
        /mnt/project/scripts/container/nbapi-contains.sh "$pattern"
}

wait_for_model()
{
    local pattern=$1 label=$2 attempts=${3:-120} attempt
    for attempt in $(seq 1 "$attempts"); do
        if controller_model_contains "$pattern"; then
            return
        fi
        sleep 1
    done
    echo "timed out waiting for controller model: $label" >&2
    return 1
}

wait_for_agent_controller()
{
    local name=$1 ordinal=$2 attempt
    for attempt in $(seq 1 90); do
        if lxc exec "$name" -- grep -q \
            'Link to the controller is established' \
            /tmp/beerocks/logs/beerocks_agent.log 2>/dev/null; then
            return
        fi
        sleep 1
    done
    echo "timed out waiting for agent $ordinal controller-connectivity gate" >&2
    return 1
}

set_device_credentials()
{
    local al=$1
    controller_cli bml_clear_wifi_credentials "$al" >/dev/null
    controller_cli bml_set_wifi_credentials "$al" "$PRIVATE_SSID" \
        "$WIFI_PASSPHRASE" 24g-5g fronthaul 0 >/dev/null
    controller_cli bml_set_wifi_credentials "$al" "$PRIVATE_SSID" \
        "$WIFI_PASSPHRASE" 6g fronthaul 1 >/dev/null
    controller_cli bml_set_wifi_credentials "$al" "$IOT_SSID" \
        "$WIFI_PASSPHRASE" 24g-5g fronthaul 0 >/dev/null
    controller_cli bml_set_wifi_credentials "$al" "$IOT_SSID" \
        "$WIFI_PASSPHRASE" 6g fronthaul 1 >/dev/null
    controller_cli bml_set_wifi_credentials "$al" "$BACKHAUL_SSID" \
        "$WIFI_PASSPHRASE" 24g-5g backhaul 0 >/dev/null
    controller_cli bml_set_wifi_credentials "$al" "$BACKHAUL_SSID" \
        "$WIFI_PASSPHRASE" 6g backhaul 1 >/dev/null
}

configure_credentials()
{
    local attempt ordinal ready=0
    for attempt in $(seq 1 30); do
        if controller_cli bml_ping >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 1
    done
    [ "$ready" = 1 ] || {
        echo "controller BML did not become ready" >&2
        return 1
    }

    set_device_credentials "$CONTROLLER_AL_MAC"
    for ordinal in $(seq 1 "$ACTIVE_AGENTS"); do
        set_device_credentials "$(agent_al "$ordinal")"
    done
    controller_cli bml_update_wifi_credentials >/dev/null
}

client_cohort()
{
    if [ $(( $1 % 2 )) -eq 1 ]; then echo private; else echo iot; fi
}

client_ordinal()
{
    echo $(( ($1 + 1) / 2 ))
}

client_band()
{
    local cohort_ordinal=$((($1 + 1) / 2))
    case $(((cohort_ordinal - 1) % 10)) in
        0|6) echo 2.4 ;;
        1|2|4|7|8) echo 5 ;;
        3|5|9) echo 6 ;;
    esac
}

client_mac()
{
    local cohort=$1 ordinal=$2 prefix
    [ "$cohort" = private ] && prefix=10 || prefix=20
    printf '02:00:00:%s:%02x:00' "$prefix" "$ordinal"
}

parent_backhaul_bssid()
{
    local ordinal=$1 parent_node parent_radio
    case "$TOPOLOGY" in
        star)
            parent_node=0
            ;;
        branch)
            if [ "$ordinal" -eq 1 ]; then parent_node=0; else parent_node=1; fi
            ;;
        chain)
            parent_node=$((ordinal - 1))
            ;;
    esac
    parent_radio=$((parent_node * RADIOS_PER_MESH_NODE + 1))
    printf '02:00:00:00:%02x:02\n' "$parent_radio"
}

start_agent()
{
    local ordinal=$1 name parent_bssid
    require_count "$ordinal" "$PROVISIONED_AGENT_COUNT" agent
    name=$(agent_name "$ordinal")
    parent_bssid=$(parent_backhaul_bssid "$ordinal")
    start_container "$name"
    echo "$name: $TOPOLOGY backhaul -> $parent_bssid"
    lxc exec "$name" -- \
        /mnt/project/scripts/container/setup-nl80211-node.sh \
        agent "$ordinal" wireless "$parent_bssid"
    wait_for_model "$(agent_al "$ordinal")" \
        "external agent $(agent_al "$ordinal")"
    wait_for_agent_controller "$name" "$ordinal"
}

stop_agent()
{
    local ordinal=$1 name
    require_count "$ordinal" "$PROVISIONED_AGENT_COUNT" agent
    name=$(agent_name "$ordinal")
    [ "$(lxc list "$name" -c s --format csv)" = RUNNING ] || return 0
    lxc exec "$name" -- \
        /mnt/project/scripts/container/cleanup-nl80211-node.sh >/dev/null
    lxc stop "$name" --timeout 5 >/dev/null 2>&1 || \
        lxc stop "$name" --force >/dev/null
}

stop_all()
{
    local ordinal name pid
    local -a names=() pids=()
    for ordinal in $(seq 1 "$PROVISIONED_CLIENT_COUNT"); do
        name=$(client_name "$ordinal")
        lxc info "$name" >/dev/null 2>&1 || continue
        names+=("$name")
    done
    for ordinal in $(seq 1 "$PROVISIONED_AGENT_COUNT"); do
        name=$(agent_name "$ordinal")
        lxc info "$name" >/dev/null 2>&1 || continue
        names+=("$name")
    done
    lxc info "$CONTROLLER" >/dev/null 2>&1 && names+=("$CONTROLLER")

    # Tear down dynamic hostapd and bSTA VIFs before LXD returns the PHYs to
    # the host. Otherwise a radio can return under a transient VIF name and
    # invalidate another container's wlanN assignment on the next start.
    for name in "${names[@]}"; do
        case "$name" in
            "$CONTROLLER"|prpl-agent-*) ;;
            *) continue ;;
        esac
        [ "$(lxc list "$name" -c s --format csv)" = RUNNING ] || continue
        lxc exec "$name" -- \
            /mnt/project/scripts/container/cleanup-nl80211-node.sh \
            >/dev/null 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    pids=()

    # Container shutdown is independent. Waiting serially for the LXD timeout
    # makes a scaled lab take count * timeout seconds to stop. Give all nodes a
    # short graceful window concurrently, then force only the non-responsive
    # remainder down.
    for name in "${names[@]}"; do
        [ "$(lxc list "$name" -c s --format csv)" = RUNNING ] || continue
        lxc stop "$name" --timeout 5 >/dev/null 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    pids=()
    for name in "${names[@]}"; do
        [ "$(lxc list "$name" -c s --format csv)" = RUNNING ] || continue
        lxc stop "$name" --force >/dev/null 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    stop_medium
}

case "$ACTION" in
    radio-pool)
        stop_all
        modprobe -r mac80211_hwsim
        modprobe mac80211_hwsim radios="$HWSIM_RADIOS" \
            channels="$HWSIM_CHANNELS" regtest=5
        name_radio_pool
        count=$(iw dev | awk '$1 == "Interface" { count++ } END { print count+0 }')
        [ "$count" -eq "$HWSIM_RADIOS" ] || {
            echo "expected $HWSIM_RADIOS base hwsim interfaces, found $count" >&2
            exit 1
        }
        ;;
    deploy)
        ensure_network
        create_node "$CONTROLLER" 0 wired
        for ordinal in $(seq 1 "$PROVISIONED_AGENT_COUNT"); do
            name=$(agent_name "$ordinal")
            first_radio=$((ordinal * RADIOS_PER_MESH_NODE))
            create_node "$name" "$first_radio" wireless
        done
        first_client_radio=$(( (PROVISIONED_AGENT_COUNT + 1) * RADIOS_PER_MESH_NODE ))
        for ordinal in $(seq 1 "$PROVISIONED_CLIENT_COUNT"); do
            create_client "$(client_name "$ordinal")" \
                "$((first_client_radio + ordinal - 1))"
        done
        ;;
    start)
        start_medium
        start_container "$CONTROLLER"
        lxc exec "$CONTROLLER" -- \
            /mnt/project/scripts/container/setup-nl80211-node.sh controller 0 wired
        configure_credentials
        sleep 5
        for ordinal in $(seq 1 "$ACTIVE_AGENTS"); do
            start_agent "$ordinal"
        done
        ;;
    clients)
        for ordinal in $(seq 1 "$ACTIVE_CLIENTS"); do
            name=$(client_name "$ordinal")
            cohort=$(client_cohort "$ordinal")
            cohort_ordinal=$(client_ordinal "$ordinal")
            band=$(client_band "$ordinal")
            start_container "$name"
            lxc exec "$name" -- /mnt/project/scripts/container/setup-client.sh \
                "$cohort_ordinal" "$cohort" "$band"
            station_mac=$(client_mac "$cohort" "$cohort_ordinal")
            if ! wait_for_model "$station_mac" "$name station $station_mac" 30; then
                # A physical association can race a transient agent/controller
                # reconnect. Re-emit the association once, then require both
                # the client and controller model to converge.
                echo "$name associated but is absent from the model; reassociating once" >&2
                lxc exec "$name" -- wpa_cli -i wlan0 disconnect >/dev/null
                sleep 1
                lxc exec "$name" -- wpa_cli -i wlan0 reconnect >/dev/null
                wait_for_model "$station_mac" "$name station $station_mac" 90
            fi
        done
        ;;
    steering-test)
        "$ROOT/scripts/test-steering.sh"
        ;;
    start-agent)
        start_agent "${2:?agent ordinal required}"
        ;;
    stop-agent)
        stop_agent "${2:?agent ordinal required}"
        ;;
    restart-agent)
        stop_agent "${2:?agent ordinal required}"
        start_agent "$2"
        ;;
    stop)
        stop_all
        ;;
    status)
        lxc list '^prpl-(controller$|agent-|client-)' -c ns4
        if [ "$(lxc list "$CONTROLLER" -c s --format csv)" = RUNNING ]; then
            timeout 15 lxc exec "$CONTROLLER" -- \
                /opt/prpl-install-nl80211/bin/beerocks_cli \
                -c bml_conn_map || \
                echo "bml_conn_map did not complete; use the NBAPI visualizer/status tests" >&2
        fi
        for ordinal in $(seq 1 "$PROVISIONED_CLIENT_COUNT"); do
            name=$(client_name "$ordinal")
            [ "$(lxc list "$name" -c s --format csv)" = RUNNING ] || continue
            echo "[$name]"
            lxc exec "$name" -- wpa_cli -i wlan0 status | \
                grep -E '^(bssid|ssid|freq|wpa_state)=' || true
        done
        ;;
    *)
        echo "usage: $0 {radio-pool|deploy|start|clients|steering-test|start-agent N|stop-agent N|restart-agent N|stop|status}" >&2
        exit 2
        ;;
esac
