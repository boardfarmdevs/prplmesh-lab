#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
baseline="$ROOT/manifests/wmediumd.conf"
temporary=$(mktemp /tmp/prpl-wmediumd-gradient.XXXXXX.conf)
clients=${PRPL_CLIENT_COUNT:-20}
runtime=${PRPL_WMEDIUMD_RUNTIME:-/run/prpl-wmediumd}
pidfile="$runtime/wmediumd.pid"
control="$runtime/control.sock"
metrics="$runtime/metrics.sock"
telemetry="$runtime/telemetry.sock"

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
    local expected=$1 attempt result
    for attempt in $(seq 1 18); do
        result=$(python3 - "$clients" "$expected" <<'PY'
import json,sys,urllib.request
clients=int(sys.argv[1]); expected=int(sys.argv[2])
with urllib.request.urlopen("http://127.0.0.1:8090/api/topology",timeout=20) as r:
    x=json.load(r)
signals=[c["signal_raw"] for d in x["devices"] for q in d["radios"]
         for b in q["bsses"] for c in b["clients"]
         if c["id"].startswith(("02:00:00:10:","02:00:00:20:"))]
print(f"{len(signals)} {sum(v == expected for v in signals)}")
PY
)
        set -- $result
        if [ "$1" -eq "$clients" ] && [ "$2" -eq "$clients" ]; then
            return
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
start_medium "$temporary" /tmp/prpl-wmediumd-gradient.log
wait_signal 88
echo "PASS: all $clients client metrics followed SNR 40 -> 25 (RCPI 118 -> 88)"

start_medium "$baseline" /tmp/prpl-wmediumd.log
wait_signal 118
trap - EXIT
rm -f "$temporary"
echo "PASS: all $clients client metrics returned to baseline without container restart"
