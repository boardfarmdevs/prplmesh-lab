#!/usr/bin/env bash
set -euo pipefail

# Submit independent prplMesh NBAPI steering operations concurrently.
exec </dev/null

usage()
{
    cat >&2 <<'EOF'
usage:
  scripts/steer-batch.sh STA TARGET [STA TARGET ...]
  scripts/steer-batch.sh --count N

Examples:
  scripts/steer-batch.sh sta-01 agent-1 sta-02 agent-2 iot-03 controller
  scripts/steer-batch.sh --count 5

Explicit moves use the same names as scripts/steer-client.sh. --count selects
N distinct connected clients and compatible live destinations. Requests run in
bounded parallel groups and every move must converge physically and in NBAPI.

Environment:
  PRPL_TOPOLOGY_URL          normalized topology API
  PRPL_STEER_BATCH_PARALLEL  maximum simultaneous operations (default 8)
  PRPL_STEER_BATCH_RESULTS   result CSV path
  PRPLMESH_COLOR             auto, always or never
EOF
    exit "${1:-2}"
}

case ${1:-} in
    -h|--help) usage 0 ;;
esac
if (($# == 0)); then usage; fi

count=
if [[ ${1:-} == --count ]]; then
    (($# == 2)) || usage
    count=$2
    [[ $count =~ ^[1-9][0-9]*$ ]] || {
        echo "steer-batch.sh: --count requires a positive integer" >&2
        exit 2
    }
elif (($# % 2 != 0)); then
    usage
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
topology_url=${PRPL_TOPOLOGY_URL:-http://127.0.0.1:8091/api/v1/topology}
parallel=${PRPL_STEER_BATCH_PARALLEL:-8}
results=${PRPL_STEER_BATCH_RESULTS:-$ROOT/artifacts/steer-batch-$(date -u +%Y%m%dT%H%M%SZ).csv}
[[ $parallel =~ ^[1-9][0-9]*$ ]] || {
    echo "steer-batch.sh: PRPL_STEER_BATCH_PARALLEL must be a positive integer" >&2
    exit 2
}
for command in curl jq flock; do
    command -v "$command" >/dev/null || {
        echo "steer-batch.sh: required command is missing: $command" >&2
        exit 1
    }
done
[[ -x $ROOT/scripts/steer-client.sh ]] || {
    echo "steer-batch.sh: single-client adapter is unavailable" >&2
    exit 1
}

lock_root=${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}
lock_file=${PRPL_STEERING_LOCK:-$lock_root/prplmesh-steering-$UID.lock}
exec 9>"$lock_file"
if ! flock -n 9; then
    echo "steer-batch.sh: another batch steering transaction is active" >&2
    exit 1
fi

work=$(mktemp -d /tmp/prplmesh-steer-batch.XXXXXX)
moves=$work/moves.tsv
: >"$moves"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT INT TERM

topology=$(curl --connect-timeout 2 --max-time 10 -fsS "$topology_url") || {
    echo "steer-batch.sh: cannot read $topology_url" >&2
    exit 1
}
jq -e '.nodes | type == "array"' >/dev/null <<<"$topology" || {
    echo "steer-batch.sh: topology response has no nodes array" >&2
    exit 1
}

current_rows()
{
    local input=${1,,}
    if [[ $input =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
        jq -r --arg input "$input" '
            [.nodes[] as $node | $node.STAList[]?
              | select((.staMAC // "" | ascii_downcase) == $input)
              | [(.name // .staMAC), (.staMAC | ascii_downcase), $node.name,
                 (.bssid // ""), (.ssid // ""), ((.band // -1) | tostring)]
              | @tsv] | unique[]' <<<"$topology"
    else
        jq -r --arg input "$input" '
            [.nodes[] as $node | $node.STAList[]?
              | select((.name // "" | ascii_downcase) == $input)
              | [(.name // .staMAC), (.staMAC | ascii_downcase), $node.name,
                 (.bssid // ""), (.ssid // ""), ((.band // -1) | tostring)]
              | @tsv] | unique[]' <<<"$topology"
    fi
}

canonical_target_name()
{
    local input=${1,,}
    case "$input" in
        controller) printf 'controller\n' ;;
        agent-*) printf 'extender-%d\n' "$((10#${input#agent-}))" ;;
        extender-*) printf 'extender-%d\n' "$((10#${input#extender-}))" ;;
        *) printf '%s\n' "$input" ;;
    esac
}

compatible_targets()
{
    local target_input=$1 source=$2 ssid=$3 band=$4 canonical
    if [[ ${target_input,,} =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
        jq -r --arg target "${target_input,,}" --arg source "$source" \
            --arg ssid "$ssid" --argjson band "$band" '
            [.nodes[] | select(.name != $source) | . as $node
              | .haulTypes[]? as $haul | $haul.BSSList[]?
              | select((.BSSID // "" | ascii_downcase) == $target
                       and .Band == $band
                       and (.ssid // $haul.ssid // "") == $ssid)
              | [$node.name, .BSSID] | @tsv] | unique[]' <<<"$topology"
    else
        canonical=$(canonical_target_name "$target_input")
        jq -r --arg target "$canonical" --arg source "$source" \
            --arg ssid "$ssid" --argjson band "$band" '
            [.nodes[]
              | select(.name != $source and (.name // "" | ascii_downcase) == $target)
              | . as $node | .haulTypes[]? as $haul | $haul.BSSList[]?
              | select(.Band == $band and (.ssid // $haul.ssid // "") == $ssid)
              | [$node.name, .BSSID] | @tsv] | unique[]' <<<"$topology"
    fi
}

append_explicit()
{
    local input=$1 target_input=$2 label sta source source_bssid ssid band target target_bssid
    mapfile -t current < <(current_rows "$input")
    ((${#current[@]} == 1)) || {
        echo "steer-batch.sh: '$input' has ${#current[@]} live placements (expected one)" >&2
        return 1
    }
    IFS=$'\t' read -r label sta source source_bssid ssid band <<<"${current[0]}"
    mapfile -t targets < <(compatible_targets "$target_input" "$source" "$ssid" "$band")
    ((${#targets[@]} == 1)) || {
        echo "steer-batch.sh: '$target_input' has ${#targets[@]} compatible BSSes for $label" >&2
        return 1
    }
    IFS=$'\t' read -r target target_bssid <<<"${targets[0]}"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$label" "$sta" "$source" "$source_bssid" "$ssid" "$band" \
        "$target" "$target_bssid" >>"$moves"
}

if [[ -n $count ]]; then
    mapfile -t clients < <(jq -r '
        [.nodes[].STAList[]?
          | select((.staMAC // "") | test("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"))
          | [(.name // .staMAC), (.staMAC | ascii_downcase)]]
        | unique_by(.[1]) | sort_by(.[0])[] | @tsv' <<<"$topology")
    if ((count > ${#clients[@]})); then
        echo "steer-batch.sh: requested $count moves but only ${#clients[@]} clients are connected" >&2
        exit 2
    fi
    for ((index=0; index<count; index++)); do
        IFS=$'\t' read -r label sta <<<"${clients[$index]}"
        mapfile -t current < <(current_rows "$sta")
        ((${#current[@]} == 1)) || exit 1
        IFS=$'\t' read -r label sta source source_bssid ssid band <<<"${current[0]}"
        mapfile -t candidates < <(jq -r --arg source "$source" --arg ssid "$ssid" \
            --argjson band "$band" '
            [.nodes[] | select(.name != $source) | . as $node
              | .haulTypes[]? as $haul | $haul.BSSList[]?
              | select(.Band == $band and (.ssid // $haul.ssid // "") == $ssid)
              | [$node.name, .BSSID] | @tsv] | unique | sort[]' <<<"$topology")
        ((${#candidates[@]} > 0)) || {
            echo "steer-batch.sh: no compatible destination for $label" >&2
            exit 1
        }
        IFS=$'\t' read -r target target_bssid \
            <<<"${candidates[$((index % ${#candidates[@]}))]}"
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$label" "$sta" "$source" "$source_bssid" "$ssid" "$band" \
            "$target" "$target_bssid" >>"$moves"
    done
else
    while (($#)); do
        append_explicit "$1" "$2"
        shift 2
    done
fi

duplicate=$(cut -f2 "$moves" | sort | uniq -d | head -1)
[[ -z $duplicate ]] || {
    echo "steer-batch.sh: station $duplicate occurs more than once" >&2
    exit 2
}

move_count=$(wc -l <"$moves")
mkdir -p "$(dirname "$results")"
printf '%s\n' 'client,sta,source,target,ssid,band,target_bssid,duration_ms,rc,result' >"$results"
status_section "prplMesh batch steering"
status_note "Prepared $move_count distinct moves; up to $parallel execute concurrently."
while IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid; do
    status_note "$label: $source -> $target on $ssid/band $band ($target_bssid)."
done <"$moves"

run_move()
{
    local index=$1 label=$2 sta=$3 source=$4 target=$5 ssid=$6 band=$7 target_bssid=$8
    local start duration rc result
    start=$(date +%s%3N)
    set +e
    "$ROOT/scripts/steer-client.sh" "$sta" "$target_bssid" 2>&1 \
        | sed -u "s/^/[$label] /" | tee "$work/move-$index.log"
    rc=${PIPESTATUS[0]}
    set -e
    duration=$(( $(date +%s%3N) - start ))
    if ((rc == 0)); then result=PASS; else result=FAIL; fi
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$label" "$sta" "$source" "$target" "$ssid" "$band" "$target_bssid" \
        "$duration" "$rc" "$result" >"$work/result-$index.csv"
    return "$rc"
}

failures=0
index=0
mapfile -t move_rows <"$moves"
for ((start=0; start<move_count; start+=parallel)); do
    end=$((start + parallel))
    ((end > move_count)) && end=$move_count
    status_action "Launching moves $((start+1))-$end of $move_count concurrently."
    pids=()
    for ((index=start; index<end; index++)); do
        IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid \
            <<<"${move_rows[$index]}"
        run_move "$index" "$label" "$sta" "$source" "$target" "$ssid" "$band" \
            "$target_bssid" &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || failures=$((failures + 1))
    done
done

for ((index=0; index<move_count; index++)); do
    cat "$work/result-$index.csv" >>"$results"
done
status_section "Batch steering summary"
status_note "moves=$move_count passed=$((move_count-failures)) failed=$failures"
status_note "results=$results"
if ((failures > 0)); then exit 1; fi
status_pass "All $move_count concurrent NBAPI steering operations passed."
