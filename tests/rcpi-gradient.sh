#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../scripts/lib/observer-status.sh
source "$ROOT/scripts/lib/observer-status.sh"
if [ -r /etc/default/prplmesh-lab ]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/default/prplmesh-lab
    set +a
fi
baseline=${PRPL_WMEDIUMD_CONFIG:-${PRPLMESH_APPLIANCE_WMEDIUMD_CONFIG:-$ROOT/manifests/wmediumd.conf}}
temporary=$(mktemp /tmp/prpl-wmediumd-gradient.XXXXXX.conf)
clients=${PRPL_CLIENT_COUNT:-${ACTIVE_CLIENT_COUNT:-${PROVISIONED_CLIENT_COUNT:-20}}}
runtime=${PRPL_WMEDIUMD_RUNTIME:-/run/prpl-wmediumd}
pidfile="$runtime/wmediumd.pid"
control="$runtime/control.sock"
metrics="$runtime/metrics.sock"
telemetry="$runtime/telemetry.sock"
traffic_target=${PRPL_TRAFFIC_TARGET:-192.168.77.1}

refresh_signals()
{
    local ordinal name pid
    local -a pids=()

    # hwsim updates the observed signal only when a frame crosses the link.
    # Generate one bounded frame stream from every client after a medium
    # change; otherwise a quiet scale profile can retain a valid but stale
    # associated RCPI for the complete test window.
    for ordinal in $(seq 1 "$clients"); do
        printf -v name 'prpl-client-%02d' "$ordinal"
        lxc exec "$name" -- ping -I wlan0 -q -c 1 -W 2 \
            "$traffic_target" >/dev/null 2>&1 &
        pids+=("$!")
        if [ "${#pids[@]}" -ge 10 ]; then
            for pid in "${pids[@]}"; do wait "$pid" || true; done
            pids=()
        fi
    done
    for pid in "${pids[@]}"; do wait "$pid" || true; done
}

start_medium()
{
    local config=$1 log=$2
    if [ -r "$pidfile" ]; then
        kill "$(cat "$pidfile")" 2>/dev/null || true
        for unused in $(seq 1 30); do
            kill -0 "$(cat "$pidfile")" 2>/dev/null || break
            sleep 0.1
        done
    fi
    mkdir -p "$runtime"
    rm -f "$pidfile" "$control" "$metrics" "$telemetry"
    "$ROOT/build/bin/wmediumd" -l 6 -c "$config" \
        -C "$control" -R "$metrics" -O "$telemetry" >"$log" 2>&1 &
    echo $! > "$pidfile"
    sleep 1
    kill -0 "$(cat "$pidfile")"
    [ -S "$control" ] && [ -S "$metrics" ] && [ -S "$telemetry" ]
}

restore()
{
    start_medium "$baseline" /tmp/prpl-wmediumd.log || true
    rm -f "$temporary"
}
trap restore EXIT

wait_signal()
{
    local expected=$1 attempt result observed matching
    for attempt in $(seq 1 18); do
        if [ "$attempt" -eq 1 ] || [ $((attempt % 6)) -eq 0 ]; then
            refresh_signals
        fi
        result=$(python3 - "$clients" "$expected" <<'PY'
import json,sys,urllib.request
clients=int(sys.argv[1]); expected=int(sys.argv[2])
with urllib.request.urlopen("http://127.0.0.1:8092/api/topology",timeout=20) as r:
    x=json.load(r)
signals=[c["signal_raw"] for d in x["devices"] for q in d["radios"]
         for b in q["bsses"] for c in b["clients"]
         if c["id"].startswith(("02:00:00:10:","02:00:00:20:"))]
print(f"{len(signals)} {sum(v == expected for v in signals)}")
PY
)
        read -r observed matching <<<"$result"
        printf 'RCPI convergence: expected=%s attempt=%s observed=%s matching=%s\n' \
            "$expected" "$attempt" "$observed" "$matching"
        if [ "$observed" -eq "$clients" ] && \
           [ "$matching" -eq "$clients" ]; then
            status_pass "All $clients clients now report RCPI $expected."
            return 0
        fi
        sleep 10
    done
    echo "RCPI did not converge: expected=$expected last='$result'" >&2
    return 1
}

sed 's/default_snr = 40/default_snr = 25/' "$baseline" > "$temporary"
grep -q 'default_snr = 25' "$temporary"

# With the hwsim noise floor used by this lab, SNR 40 reports -51 dBm/RCPI
# 118 and SNR 25 reports -66 dBm/RCPI 88.
status_section "Live RCPI gradient"
status_note "Changing the simulated medium for all $clients clients and observing NBAPI telemetry."
status_action "Reducing default SNR from 40 to 25 dB; expected RCPI becomes 88."
start_medium "$temporary" /tmp/prpl-wmediumd-gradient.log
wait_signal 88
status_pass "All $clients client metrics followed SNR 40 -> 25 (RCPI 118 -> 88)."

status_action "Restoring the original medium; expected RCPI returns to 118."
start_medium "$baseline" /tmp/prpl-wmediumd.log
wait_signal 118
trap - EXIT
rm -f "$temporary"
status_pass "All $clients client metrics returned to baseline without a container restart."
