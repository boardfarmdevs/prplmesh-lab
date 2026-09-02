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
        "$work/release/import.sh" --profile 20 \
        "$work/release/appliance.tar.zst"
}

: > "$work/actions"
run_import 5 3 > "$work/delayed.out" 2> "$work/delayed.err"
test "$(cat "$work/query-count")" = 3
test -e "$work/profile-lock"
test -e "$work/proxy-added"
query_line=$(grep -nF 'exec prplmesh-20-0831 -- lxc query /1.0' \
    "$work/actions" | tail -n 1 | cut -d: -f1)
select_line=$(grep -nF 'select-thin-profile.sh 20' "$work/actions" |
    cut -d: -f1)
proxy_line=$(grep -nF 'config device add' "$work/actions" | head -n 1 |
    cut -d: -f1)
test "$query_line" -lt "$select_line"
test "$select_line" -lt "$proxy_line"

rm -f "$work/query-count" "$work/profile-lock" "$work/proxy-added"
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

echo 'PASS: thin import waits for nested LXD before profile publication'
