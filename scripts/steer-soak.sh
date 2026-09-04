#!/usr/bin/env bash
set -uo pipefail

# Drive the validated single-client NBAPI steering adapter from live topology.
# Client placement and compatible destinations are refreshed for every move.
exec </dev/null

usage()
{
    cat >&2 <<'EOF'
usage: scripts/steer-soak.sh [N]

Without N, consider every client connected when the run starts exactly once.
With N, issue N sequential valid steering attempts, cycling fairly through
that initial roster. Every destination is a different live device carrying
the client's current SSID on its current band.

Each move is delegated to scripts/steer-client.sh and must converge both at
the physical station and in the prplMesh NBAPI ownership model.

Environment:
  PRPL_TOPOLOGY_URL       normalized WebUI topology API
                          (default http://127.0.0.1:8091/api/v1/topology)
  PRPL_STEER_SOAK_SETTLE  seconds between moves (default 1)
  PRPL_STEER_SOAK_RESULTS result CSV path
  PRPLMESH_COLOR          auto, always or never
EOF
    exit "${1:-2}"
}

case ${1:-} in
    -h|--help) usage 0 ;;
esac
if (($# > 1)); then
    usage
fi
requested=${1:-}
if [[ -n $requested && ! $requested =~ ^[1-9][0-9]*$ ]]; then
    echo "steer-soak.sh: N must be a positive integer" >&2
    exit 2
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
topology_url=${PRPL_TOPOLOGY_URL:-http://127.0.0.1:8091/api/v1/topology}
settle_seconds=${PRPL_STEER_SOAK_SETTLE:-1}
results=${PRPL_STEER_SOAK_RESULTS:-$ROOT/artifacts/steer-soak-$(date -u +%Y%m%dT%H%M%SZ).csv}

if [[ ! $settle_seconds =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "steer-soak.sh: PRPL_STEER_SOAK_SETTLE must be a non-negative number" >&2
    exit 2
fi
for command in curl jq flock; do
    command -v "$command" >/dev/null || {
        echo "steer-soak.sh: required command is missing: $command" >&2
        exit 1
    }
done
if [[ ! -x $ROOT/scripts/steer-client.sh ]]; then
    echo "steer-soak.sh: single-steer adapter is unavailable: $ROOT/scripts/steer-client.sh" >&2
    exit 1
fi

lock_root=${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}
lock_file=${PRPL_STEER_SOAK_LOCK:-$lock_root/prplmesh-steer-soak-$UID.lock}
exec 9>"$lock_file" || {
    echo "steer-soak.sh: cannot open lock $lock_file" >&2
    exit 1
}
if ! flock -n 9; then
    echo "steer-soak.sh: another prplMesh steering soak is already running for this user" >&2
    exit 1
fi

read_topology()
{
    local document
    document=$(curl --connect-timeout 2 --max-time 10 -fsS "$topology_url") || return 1
    jq -e '.nodes | type == "array"' >/dev/null <<<"$document" || return 1
    printf '%s\n' "$document"
}

initial_topology=$(read_topology) || {
    echo "steer-soak.sh: cannot read a valid topology from $topology_url" >&2
    exit 1
}
mapfile -t clients < <(jq -r '
    [.nodes[].STAList[]?
      | select((.staMAC // "") | test("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"))
      | [(.name // .staMAC), (.staMAC | ascii_downcase)]]
    | unique_by(.[1]) | sort_by(.[0])[] | @tsv' <<<"$initial_topology")
if ((${#clients[@]} == 0)); then
    echo "steer-soak.sh: the live topology contains no connected clients" >&2
    exit 1
fi

if [[ -n $requested ]]; then
    target_attempts=$requested
    mode="requested count"
else
    target_attempts=${#clients[@]}
    mode="one pass over the initial roster"
fi
mkdir -p "$(dirname "$results")"
printf '%s\n' 'attempt,client,sta,source,target,ssid,band,duration_ms,result' >"$results"

status_section "Live prplMesh steering soak"
status_note "Initial topology has ${#clients[@]} clients; mode: $mode."
status_note "Will issue up to $target_attempts valid sequential steering attempts."
status_note "Results: $results"

issued=0
passed=0
failed=0
skipped=0
cursor=0
consecutive_skips=0

while ((issued < target_attempts)); do
    if [[ -z $requested && $cursor -ge ${#clients[@]} ]]; then
        break
    fi
    IFS=$'\t' read -r initial_name sta <<<"${clients[$((cursor % ${#clients[@]}))]}"
    cursor=$((cursor + 1))

    topology=$(read_topology) || {
        echo "steer-soak.sh: topology became unavailable; stopping safely" >&2
        failed=$((failed + 1))
        break
    }
    mapfile -t placements < <(jq -r --arg sta "$sta" '
        [.nodes[] as $node
          | $node.STAList[]?
          | select((.staMAC // "" | ascii_downcase) == $sta)
          | [(.name // $sta), $node.name, (.bssid // ""), (.ssid // ""), ((.band // -1) | tostring)]
          | @tsv]
        | unique[]' <<<"$topology")
    if ((${#placements[@]} != 1)); then
        status_note "Skipping $initial_name: $sta has ${#placements[@]} current placements (expected one)."
        skipped=$((skipped + 1))
        consecutive_skips=$((consecutive_skips + 1))
        if [[ -n $requested && $consecutive_skips -ge ${#clients[@]} ]]; then
            echo "steer-soak.sh: no client in the initial roster currently has a valid move" >&2
            failed=$((failed + 1))
            break
        fi
        continue
    fi
    IFS=$'\t' read -r client source source_bssid ssid band <<<"${placements[0]}"

    mapfile -t candidates < <(jq -r \
        --arg source "$source" --arg ssid "$ssid" --argjson band "$band" '
        [.nodes[]
          | select(.name != $source)
          | . as $node
          | [.haulTypes[]? as $haul
              | $haul.BSSList[]?
              | select(.Band == $band and (.ssid // $haul.ssid // "") == $ssid)
              | {name:$node.name, bssid:(.BSSID // "")}]
          | unique_by(.bssid | ascii_downcase)
          | select(length == 1)
          | .[0]
          | select(.bssid | test("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"))]
        | sort_by(.name)
        | .[] | [.name, .bssid] | @tsv' <<<"$topology")
    if ((${#candidates[@]} == 0)); then
        status_note "Skipping $client: no alternate device has exactly one $ssid BSS on $band."
        skipped=$((skipped + 1))
        consecutive_skips=$((consecutive_skips + 1))
        if [[ -n $requested && $consecutive_skips -ge ${#clients[@]} ]]; then
            echo "steer-soak.sh: no client in the initial roster currently has a valid move" >&2
            failed=$((failed + 1))
            break
        fi
        continue
    fi
    consecutive_skips=0
    candidate_index=$(( (issued + cursor - 1) % ${#candidates[@]} ))
    IFS=$'\t' read -r target target_bssid <<<"${candidates[$candidate_index]}"
    issued=$((issued + 1))

    status_section "Steer $issued/$target_attempts: $client"
    status_action "Moving $client from $source to $target on $ssid, $band."
    status_note "Live source BSSID: $source_bssid; selected target BSSID: $target_bssid."
    start_ms=$(date +%s%3N)
    # Pass MAC/BSSID to cover client labels above 09 without relying on label
    # parsing and to bind the operation to the exact compatible live BSS.
    if "$ROOT/scripts/steer-client.sh" "$sta" "$target_bssid"; then
        duration_ms=$(( $(date +%s%3N) - start_ms ))
        passed=$((passed + 1))
        result=PASS
        status_pass "$client reached $target in ${duration_ms}ms."
    else
        rc=$?
        duration_ms=$(( $(date +%s%3N) - start_ms ))
        failed=$((failed + 1))
        result=FAIL
        printf 'FAIL: %s -> %s returned rc=%d after %dms.\n' \
            "$client" "$target" "$rc" "$duration_ms" >&2
    fi
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$issued" "$client" "$sta" "$source" "$target" "$ssid" "$band" \
        "$duration_ms" "$result" >>"$results"

    if ((issued < target_attempts)) && [[ $settle_seconds != 0 ]]; then
        status_wait_seconds "$settle_seconds" "allowing NBAPI ownership to settle before the next live resolution"
    fi
done

status_section "Steering soak summary"
status_note "attempted=$issued passed=$passed failed=$failed skipped=$skipped"
status_note "results=$results"
if ((failed > 0)); then
    exit 1
fi
status_pass "All $passed issued steering attempts passed."
