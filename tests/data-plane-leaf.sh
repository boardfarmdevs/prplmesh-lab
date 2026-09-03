#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-data-plane-leaf.XXXXXX)
trap 'rm -rf -- "$work"' EXIT

cat > "$work/lxc" <<'SH'
#!/bin/bash
set -euo pipefail
[ "${1:-}" = exec ] || { echo "unexpected lxc action: $*" >&2; exit 2; }
container=$2
shift 3
printf '%s %s\n' "$container" "$*" >> "$FAKE_ACTIONS"
ordinal=${container##*-}
ordinal=$((10#$ordinal))
case "${1:-}" in
    ip)
        printf '7: wlan0    inet 192.168.77.%d/24 scope global wlan0\n' \
            "$((100 + ordinal))"
        ;;
    ping)
        printf '10 packets transmitted, 10 received, 0%% packet loss\n'
        printf 'rtt min/avg/max/mdev = 1.0/2.0/3.0/0.1 ms\n'
        ;;
    wpa_cli)
        if [ "${FAKE_STAR_FALLBACK:-0}" = 1 ]; then
            case "$ordinal" in
                1) bssid=02:00:00:00:04:00 ;;
                *) bssid=02:00:00:00:02:00 ;;
            esac
        elif [ "${FAKE_NO_LEAF:-0}" = 1 ]; then
            bssid=02:00:00:00:02:00
        else
            case "$ordinal" in
                1) bssid=02:00:00:00:02:00 ;;
                2) bssid=02:00:00:00:07:01 ;;
                3) bssid=02:00:00:00:0d:00 ;;
            esac
        fi
        printf 'bssid=%s\nwpa_state=COMPLETED\n' "$bssid"
        ;;
    *) echo "unexpected nested command: $*" >&2; exit 2 ;;
esac
SH
chmod 755 "$work/lxc"

: > "$work/actions"
env PATH="$work:$PATH" FAKE_ACTIONS="$work/actions" \
    PRPL_CLIENT_COUNT=3 PRPL_AGENT_COUNT=4 \
    "$ROOT/tests/data-plane.sh" >"$work/pass.out"
grep -Fq 'deepest data path: prpl-client-03 via agent-4 (02:00:00:00:0d:00)' \
    "$work/pass.out"
grep -Fq 'PASS: 3/3 clients reach the controller' "$work/pass.out"
grep -Fq 'prpl-client-03 ping -q -c 10' "$work/actions"
if grep -Fq 'steer-client' "$work/actions"; then
    echo 'data-plane test issued an unrelated steering request' >&2
    exit 1
fi

: > "$work/actions"
if env PATH="$work:$PATH" FAKE_ACTIONS="$work/actions" FAKE_NO_LEAF=1 \
    PRPL_CLIENT_COUNT=3 PRPL_AGENT_COUNT=4 \
    "$ROOT/tests/data-plane.sh" >"$work/fail.out" 2>"$work/fail.err"; then
    echo 'missing deepest-agent association was accepted' >&2
    exit 1
fi
grep -Fq 'no client is associated with a BSSID on a deepest chain agent' \
    "$work/fail.err"

: > "$work/actions"
env PATH="$work:$PATH" FAKE_ACTIONS="$work/actions" FAKE_STAR_FALLBACK=1 \
    PRPL_CLIENT_COUNT=3 PRPL_AGENT_COUNT=4 PRPL_TOPOLOGY=star \
    "$ROOT/tests/data-plane.sh" >"$work/star.out"
grep -Fq 'deepest data path: prpl-client-01 via agent-1 (02:00:00:00:04:00)' \
    "$work/star.out"

echo 'PASS: data-plane acceptance selects a populated deepest-topology agent'
