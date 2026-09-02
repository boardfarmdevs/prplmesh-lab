#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
client_container=${1:-prpl-client-01}
api_url=${PRPL_TOPOLOGY_API:-http://127.0.0.1:8092/api/topology}
output_root=${WMD_RUN_ROOT:-/tmp/wmdcfg-runs}
traffic_target=${WMD_TRAFFIC_TARGET:-192.168.77.1}
inventory_file=$(mktemp --suffix=.json /tmp/rcpi-monitor-inventory.XXXXXX)
plan_file=$(mktemp --suffix=.json /tmp/rcpi-monitor-plan.XXXXXX)
sample_file=$(mktemp --suffix=.tsv /tmp/rcpi-monitor-samples.XXXXXX)
sampler_pid=
traffic_pid=

cleanup() {
    if [[ -n "$sampler_pid" ]]; then
        kill "$sampler_pid" 2>/dev/null || true
        wait "$sampler_pid" 2>/dev/null || true
    fi
    if [[ -n "$traffic_pid" ]]; then
        kill "$traffic_pid" 2>/dev/null || true
        wait "$traffic_pid" 2>/dev/null || true
    fi
    rm -f -- "$inventory_file" "$plan_file" "$sample_file"
}
trap cleanup EXIT

for command in curl jq lxc python3 timeout; do
    command -v "$command" >/dev/null || {
        echo "required command not found: $command" >&2
        exit 2
    }
done

cd "$script_dir"
python3 -m wmdcfg.cli inventory -o "$inventory_file"

client_mac=$(jq -r --arg container "$client_container" '
    .radios[]
    | select(.kind == "station" and .container == $container)
    | .station_mac' "$inventory_file")
serving_bssid=$(jq -r --arg container "$client_container" '
    .radios[]
    | select(.kind == "station" and .container == $container)
    | .associated_bssid // empty' "$inventory_file")

if [[ -z "$client_mac" || -z "$serving_bssid" ]]; then
    echo "$client_container is absent or not associated" >&2
    exit 2
fi

serving_ap=$(jq -r --arg bssid "$serving_bssid" '
    [.radios[]
     | select(.kind == "mesh")
     | select(any(.interfaces[]?;
         ((.mac // "") | ascii_downcase) == ($bssid | ascii_downcase)))
     | .container]
    | if length == 1 then .[0] else empty end' "$inventory_file")

if [[ -z "$serving_ap" ]]; then
    echo "could not map serving BSSID $serving_bssid to exactly one mesh container" >&2
    exit 2
fi

python3 -m wmdcfg.cli compile scenarios/client-rcpi-monitor.wmd \
    --inventory "$inventory_file" \
    --bind "client=$client_container" \
    --bind "ap=$serving_ap" \
    -o "$plan_file"

# hwsim updates the observed signal when frames cross the RF link. Start a
# small traffic stream before checking RCPI so an otherwise idle client gets a
# fresh observation during the next reporting interval.
lxc exec "$client_container" -- ping -I wlan0 -c 1 -W 2 "$traffic_target" \
    >/dev/null
timeout 150 lxc exec "$client_container" -- \
    ping -I wlan0 -i 0.2 "$traffic_target" >/dev/null 2>&1 &
traffic_pid=$!
sleep 6

initial_rcpi=$(curl -fsS "$api_url" | jq -r --arg mac "$client_mac" '
    first(.devices[].radios[].bsses[].clients[]
      | select((.id | ascii_downcase) == ($mac | ascii_downcase))
      | .signal_raw) // 0')
if [[ "$initial_rcpi" -le 0 ]]; then
    echo "the clients API has no reported RCPI for $client_mac" >&2
    echo "enable metrics reporting and deploy the live-RCPI WebUI/API fix first" >&2
    exit 2
fi

echo "client=$client_container mac=$client_mac serving_ap=$serving_ap bssid=$serving_bssid"
echo "Open the prplMesh Network Topology; signal refreshes every two seconds."
printf 'time\tclient\tbssid\trcpi\trssi_dbm\n'

sample_api() {
    while true; do
        sample_time=$(date -u +%H:%M:%S)
        sample=$(curl -fsS "$api_url" | jq -r \
            --arg sample_time "$sample_time" --arg mac "$client_mac" '
            first(.devices[].radios[] as $radio
              | $radio.bsses[] as $bss
              | $bss.clients[]
              | select((.id | ascii_downcase) == ($mac | ascii_downcase))
              | {mac: .id, bssid: $bss.bssid, rcpi: .signal_raw,
                 rssi_dbm: .signal_dbm}) as $client
            | [$sample_time, $client.mac, $client.bssid,
               $client.rcpi, $client.rssi_dbm]
            | @tsv')
        printf '%s\n' "$sample" | tee -a "$sample_file"
        sleep 2
    done
}

sample_api &
sampler_pid=$!

python3 -m wmdcfg.cli run "$plan_file" --output-root "$output_root"

# Keep traffic and API sampling alive for one more five-second reporting period
# so the restored baseline is visible before the script exits.
sleep 6
kill "$sampler_pid" 2>/dev/null || true
wait "$sampler_pid" 2>/dev/null || true
sampler_pid=

read -r minimum_rcpi maximum_rcpi < <(
    awk -F '\t' '
        NF >= 4 && $4 ~ /^[0-9]+$/ {
            if (!seen || $4 < minimum) minimum=$4
            if (!seen || $4 > maximum) maximum=$4
            seen=1
        }
        END {
            if (!seen) exit 1
            print minimum, maximum
        }
    ' "$sample_file"
)

# 20 dB in the scenario is 40 RCPI units. Allow one 10-unit reporting-step
# margin while still requiring an unmistakable fall and recovery.
if (( maximum_rcpi - minimum_rcpi < 30 )); then
    echo "RCPI did not follow the dynamic medium: min=$minimum_rcpi max=$maximum_rcpi" >&2
    exit 1
fi
echo "PASS: associated RCPI followed the dynamic medium (min=$minimum_rcpi max=$maximum_rcpi)"
