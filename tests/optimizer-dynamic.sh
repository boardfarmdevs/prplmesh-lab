#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
MODE=${1:-recommend}
CLIENT=${2:-prpl-client-07}
TARGET=${3:-prpl-agent-02}
MEDIUM_BACKEND=${PRPL_MEDIUM_BACKEND:-userspace}
case "$MODE" in
    recommend|act) ;;
    *) echo "usage: $0 [recommend|act] [prpl-client-NN] [prpl-agent-NN|prpl-controller]" >&2; exit 2 ;;
esac

inventory=$(mktemp /tmp/prpl-optimizer-inventory.XXXXXX.json)
plan=$(mktemp /tmp/prpl-optimizer-plan.XXXXXX.json)
journal=$(mktemp /tmp/prpl-optimizer-journal.XXXXXX.jsonl)
scenario_log=$(mktemp /tmp/prpl-optimizer-scenario.XXXXXX.log)
optimizer_log=$(mktemp /tmp/prpl-optimizer-output.XXXXXX.log)
scenario_pid=

cleanup()
{
    if [ -n "$scenario_pid" ] && kill -0 "$scenario_pid" 2>/dev/null; then
        kill -TERM "$scenario_pid" 2>/dev/null || true
        wait "$scenario_pid" 2>/dev/null || true
    fi
    rm -f "$inventory" "$plan"
}
trap cleanup EXIT

cd "$ROOT/wmediumd/configurator"
python3 -m wmdcfg.cli inventory -o "$inventory"
expected_clients=$(jq '[.radios[] | select(.kind == "station")] | length' "$inventory")
[ "$expected_clients" -gt 0 ] || {
    echo "optimizer inventory contains no station radios" >&2
    exit 1
}

if ! binding_output=$(python3 - "$inventory" "$CLIENT" "$TARGET" <<'PY'
import json
import sys

inventory = json.load(open(sys.argv[1], encoding="utf-8"))
client_name, target_name = sys.argv[2:]
by_name = {item["container"]: item for item in inventory["radios"]}
client = by_name.get(client_name)
target = by_name.get(target_name)
if not client or client.get("kind") != "station":
    raise SystemExit(f"unknown station container: {client_name}")
if not target or target.get("kind") != "mesh":
    raise SystemExit(f"unknown mesh target: {target_name}")
source_bssid = client.get("associated_bssid")
if not source_bssid:
    raise SystemExit(f"{client_name} is not associated")

def bss_owner(bssid):
    for item in inventory["radios"]:
        if item.get("kind") != "mesh":
            continue
        for iface in item.get("interfaces", []):
            if str(iface.get("mac", "")).lower() == bssid.lower():
                return item["container"]

source = bss_owner(source_bssid)
if not source:
    raise SystemExit(f"cannot map serving BSSID {source_bssid}")
if source == target_name:
    raise SystemExit(f"{client_name} is already served by {target_name}")
others = sorted(
    item["container"] for item in inventory["radios"]
    if item.get("kind") == "mesh" and item["container"] not in {source, target_name}
)
if len(others) != 3:
    raise SystemExit(f"five-node profile required; found {2 + len(others)} mesh nodes")
band = client.get("band")
ssid = client.get("ssid")
target_bssid = next(
    (iface.get("mac") for iface in target["band_radios"][band]["interfaces"]
     if iface.get("ssid") == ssid),
    None,
)
if not target_bssid:
    raise SystemExit(f"no {band} GHz {ssid} BSS on {target_name}")
for value in [source, target_name, target_bssid, client["station_mac"], *others]:
    print(value)
PY
); then
    exit 1
fi
readarray -t binding <<<"$binding_output"
[ "${#binding[@]}" -eq 7 ] || {
    echo "optimizer scenario binding returned ${#binding[@]} fields, expected 7" >&2
    exit 1
}
source=${binding[0]}
target=${binding[1]}
target_bssid=${binding[2]}
client_sta=${binding[3]}

python3 -m wmdcfg.cli compile scenarios/optimizer-five-ap-crossover.wmd \
    --inventory "$inventory" \
    --bind "client=$CLIENT" \
    --bind "source=$source" \
    --bind "target=$target" \
    --bind "alternate_1=${binding[4]}" \
    --bind "alternate_2=${binding[5]}" \
    --bind "alternate_3=${binding[6]}" \
    -o "$plan"

echo "optimizer stimulus: $CLIENT $source -> $target ($target_bssid)"
python3 -m wmdcfg.cli run --backend "$MEDIUM_BACKEND" "$plan" \
    >"$scenario_log" 2>&1 &
scenario_pid=$!
sleep 2

cd "$ROOT/optimizer"
args=(
    "$MODE" --backend prplmesh --base-url http://127.0.0.1:8090
    --candidate-provider controller --allow-simulated-candidates
    --policy configs/threshold-policy.yaml --journal "$journal"
    --expected-clients "$expected_clients"
    --count 30 --interval 1
)
if [ "$MODE" = act ]; then
    args+=(--yes-act --max-actions 1)
fi
if ! python3 -m optimizer.cli "${args[@]}" >"$optimizer_log"; then
    tail -n 40 "$optimizer_log" >&2
    exit 1
fi
wait "$scenario_pid"
scenario_pid=

if [ "$MODE" = recommend ]; then
    if ! jq -e --arg sta "$client_sta" --arg target "$target_bssid" '
        select(.kind == "evaluation")
        | .payload.decisions[]
        | select(
            .sta_mac == $sta
            and .action == "steer"
            and .target_bssid == $target
        )
    ' "$journal" >/dev/null; then
        echo "optimizer did not recommend $client_sta to expected target $target_bssid" >&2
        tail -n 40 "$optimizer_log" >&2
        exit 1
    fi
else
    jq -e 'select(.kind == "action" and .payload.success == true)' "$journal" >/dev/null
    jq -e 'select(.kind == "verification" and .payload.success == true)' "$journal" >/dev/null
fi

summary=$(tail -1 "$scenario_log")
jq -e '.outcome == "passed" and .restored == true' "$summary/summary.json" >/dev/null
echo "PASS: prplMesh dynamic $MODE used NBAPI candidate metrics; scenario restored"
echo "journal: $journal"
echo "scenario: $summary"
echo "optimizer output: $optimizer_log"
