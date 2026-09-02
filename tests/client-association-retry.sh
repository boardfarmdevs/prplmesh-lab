#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

cat > "$work/lxc" <<'SH'
#!/bin/bash
set -euo pipefail
count_file=${FAKE_LXC_COUNT:?}
mode=${FAKE_LXC_MODE:?}
count=0
[ ! -r "$count_file" ] || count=$(cat "$count_file")
count=$((count + 1))
printf '%s\n' "$count" > "$count_file"
printf '%s\n' "$*" >> "${count_file}.args"
case "$mode" in
    success) exit 0 ;;
    retry-success) [ "$count" -ge 2 ] ;;
    fail) exit 1 ;;
    *) exit 2 ;;
esac
SH
chmod 0755 "$work/lxc"

run_case()
{
    local mode=$1 expected_rc=$2 expected_count=$3
    local count_file="$work/$mode.count"
    local rc=0
    PATH="$work:$PATH" \
        FAKE_LXC_COUNT="$count_file" \
        FAKE_LXC_MODE="$mode" \
        PRPLMESH_CLIENT_SETUP_RETRY_DELAY=0 \
        "$ROOT/scripts/client-setup-with-retry.sh" \
            prpl-client-87 44 private 6 >/dev/null 2>&1 || rc=$?
    [ "$rc" -eq "$expected_rc" ] || {
        echo "$mode returned $rc, expected $expected_rc" >&2
        return 1
    }
    [ "$(cat "$count_file")" -eq "$expected_count" ] || {
        echo "$mode attempted $(cat "$count_file") times, expected $expected_count" >&2
        return 1
    }
    while IFS= read -r args; do
        [ "$args" = \
            'exec prpl-client-87 -- /mnt/project/scripts/container/setup-client.sh 44 private 6' ] || {
            echo "unexpected lxc arguments: $args" >&2
            return 1
        }
    done < "${count_file}.args"
}

run_case success 0 1
run_case retry-success 0 2
run_case fail 1 2

if PATH="$work:$PATH" \
    FAKE_LXC_COUNT="$work/invalid.count" \
    FAKE_LXC_MODE=success \
    PRPLMESH_CLIENT_SETUP_RETRY_DELAY=bad \
    "$ROOT/scripts/client-setup-with-retry.sh" \
        prpl-client-87 44 private 6 >/dev/null 2>&1; then
    echo 'invalid retry delay unexpectedly succeeded' >&2
    exit 1
fi

echo 'PASS: client setup retries exactly once and preserves terminal failure'
