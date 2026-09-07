#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-thin-import-ready.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/bin" "$work/release"

cat > "$work/bin/lxc" <<'SH'
#!/bin/bash
set -euo pipefail
root=${FAKE_LXC_ROOT:?}
printf '%s\n' "$*" >> "$root/actions"

case "${1:-} ${2:-}" in
    'network show') exit 0 ;;
    'network get') printf '10.99.0.1/24\n'; exit 0 ;;
    'network list-leases') exit 0 ;;
    'info '*) exit 1 ;;
    'import '*) exit 0 ;;
    'start '*) exit 0 ;;
    'config unset'|'config set') exit 0 ;;
    'config device')
        case "${3:-}" in
            show)
                printf 'eth0:\n  type: nic\n'
                ;;
            add)
                : > "$root/proxy-added"
                ;;
        esac
        exit 0
        ;;
    'exec '*)
        shift 2
        [ "${1:-}" = -- ] && shift
        case "${1:-} ${2:-} ${3:-}" in
            'true  ')
                exit 0
                ;;
            'ip -4 -o')
                count=0
                [ ! -r "$root/address-count" ] || count=$(cat "$root/address-count")
                count=$((count + 1))
                printf '%s\n' "$count" > "$root/address-count"
                ready_after=${FAKE_ADDRESS_READY_AFTER:-1}
                [ "$count" -ge "$ready_after" ] || exit 2
                printf '1.1.1.1 via 10.99.0.1 dev enp5s0 src 10.99.0.42 uid 0\n'
                exit 0
                ;;
            'lxc query /1.0')
                count=0
                [ ! -r "$root/query-count" ] || count=$(cat "$root/query-count")
                count=$((count + 1))
                printf '%s\n' "$count" > "$root/query-count"
                ready_after=${FAKE_NESTED_READY_AFTER:-0}
                [ "$ready_after" -gt 0 ] && [ "$count" -ge "$ready_after" ]
                exit
                ;;
            '/opt/prplmesh-lab/deploy/guest/select-thin-profile.sh '*)
                : > "$root/profile-lock"
                exit 0
                ;;
            'grep -Fx PROVISIONED_CLIENT_COUNT=20')
                test -e "$root/profile-lock"
                exit
                ;;
            'systemctl reset-failed prplmesh-lab.service'|\
            'systemctl --no-block start')
                exit 0
                ;;
        esac
        echo "unexpected fake lxc exec: $*" >&2
        exit 2
        ;;
esac

echo "unexpected fake lxc command: $*" >&2
exit 2
SH
chmod 0755 "$work/bin/lxc"

install -m 0755 "$ROOT/deploy/lxd-vm/import.sh" "$work/release/import.sh"
printf 'LAB_PROFILE_SELECTABLE=true\nLAB_SUPPORTED_PROFILES=20,50,100\n' \
    > "$work/release/release.env"
: > "$work/release/appliance.tar.zst"

run_import()
{
    env PATH="$work/bin:$PATH" \
        FAKE_LXC_ROOT="$work" \
        PRPLMESH_UI_HOST_IP=127.0.0.1 \
        PRPLMESH_NESTED_LXD_READY_ATTEMPTS="$1" \
        PRPLMESH_NESTED_LXD_READY_INTERVAL=0 \
        FAKE_NESTED_READY_AFTER="$2" \
        FAKE_ADDRESS_READY_AFTER=3 \
        "$work/release/import.sh" --profile 20 \
        "$work/release/appliance.tar.zst"
}

: > "$work/actions"
run_import 5 3 > "$work/delayed.out" 2> "$work/delayed.err"
test "$(cat "$work/address-count")" = 3
test "$(cat "$work/query-count")" = 3
test -e "$work/profile-lock"
test -e "$work/proxy-added"
query_line=$(grep -nF 'exec prplmesh-20-0904 -- lxc query /1.0' \
    "$work/actions" | tail -n 1 | cut -d: -f1)
select_line=$(grep -nF 'select-thin-profile.sh 20' "$work/actions" |
    cut -d: -f1)
proxy_line=$(grep -nF 'config device add' "$work/actions" | head -n 1 |
    cut -d: -f1)
import_line=$(grep -nF \
    'import '"$work"'/release/appliance.tar.zst prplmesh-20-0904' \
    "$work/actions" | cut -d: -f1)
grep -F 'eth0,network=lxdbr0' "$work/actions" | grep -F \
    'eth0,ipv4.address=10.99.0.250' >/dev/null
! sed -n "${import_line}p" "$work/actions" | grep -Eq \
    'wmediumd-console|controller-ui|topology-ui|room-demo-viewer'
grep -F 'config device add prplmesh-20-0904 wmediumd-console proxy' \
    "$work/actions" | grep -F 'connect=tcp:10.99.0.42:8090' >/dev/null
grep -F 'config device add prplmesh-20-0904 controller-ui proxy' \
    "$work/actions" | grep -F 'connect=tcp:10.99.0.42:8091' >/dev/null
grep -F 'config device add prplmesh-20-0904 room-demo-viewer proxy' \
    "$work/actions" | grep -F 'listen=tcp:127.0.0.1:18891' | \
    grep -F 'connect=tcp:10.99.0.42:8891' >/dev/null
grep -Fq \
    'config device set prplmesh-20-0904 eth0 ipv4.address 10.99.0.42' \
    "$work/actions"
test "$import_line" -lt "$query_line"
test "$query_line" -lt "$select_line"
test "$select_line" -lt "$proxy_line"

rm -f "$work/address-count" "$work/query-count" "$work/profile-lock" \
    "$work/proxy-added"
: > "$work/actions"
if run_import 2 0 > "$work/timeout.out" 2> "$work/timeout.err"; then
    echo 'unready nested LXD was accepted' >&2
    exit 1
fi
test "$(cat "$work/query-count")" = 2
grep -Fq 'nested LXD did not become ready after 2 attempts' \
    "$work/timeout.err"
test ! -e "$work/profile-lock"
test ! -e "$work/proxy-added"
! grep -Fq 'select-thin-profile.sh' "$work/actions"
! grep -Fq 'config device add' "$work/actions"

mkdir -p "$work/release/observability"
cat > "$work/release/observability/enable.sh" <<'SH'
#!/usr/bin/env bash
printf 'monitoring-enabled %s\n' "$*" >> "${FAKE_LXC_ROOT:?}/actions"
SH
: > "$work/actions"
env PATH="$work/bin:$PATH" FAKE_LXC_ROOT="$work" \
    PRPLMESH_UI_HOST_IP=127.0.0.1 PRPLMESH_NESTED_LXD_READY_INTERVAL=0 \
    FAKE_NESTED_READY_AFTER=1 FAKE_ADDRESS_READY_AFTER=1 \
    "$work/release/import.sh" --profile 20 --monitoring \
    "$work/release/appliance.tar.zst" > "$work/monitoring.out"
monitoring_line=$(grep -nF 'monitoring-enabled prplmesh-20-0904 127.0.0.1' "$work/actions" | cut -d: -f1)
start_line=$(grep -nF 'exec prplmesh-20-0904 -- systemctl --no-block start prplmesh-lab.service' "$work/actions" | cut -d: -f1)
test "$monitoring_line" -lt "$start_line"

echo 'PASS: thin import waits for nested LXD and enables optional monitoring before lab startup'
