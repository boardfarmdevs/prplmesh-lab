#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-thin-firstboot.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
state=$work/instances
marker=$work/thin-pending.env
capacity=$work/capacity.json
printf '{"schema_version":3}\n' > "$capacity"
report=$work/firstboot-report.txt
mkdir -p "$work/root/deploy/guest"
cat > "$work/root/deploy/guest/thin-image-guard.py" <<'PY'
import sys

assert sys.argv[1] == 'firstboot-check'
assert sys.argv[sys.argv.index('--expected') + 1] == '105'
print('{"status": "PASS", "expected_instances": 105}')
PY

cat > "$work/lxc" <<'SH'
#!/bin/bash
set -euo pipefail
case "${1:-} ${2:-}" in
    "image info") printf 'Fingerprint: test-runtime-image\n' ;;
    "list --format") cat "$FAKE_LXC_STATE" ;;
    *) echo "unexpected fake lxc invocation: $*" >&2; exit 2 ;;
esac
SH
cat > "$work/radio-lab" <<'SH'
#!/bin/bash
set -euo pipefail
case "${1:-}" in
    radio-pool) ;;
    deploy)
        {
            echo prpl-controller
            for ordinal in $(seq 1 "$PROVISIONED_AGENT_COUNT"); do
                printf 'prpl-agent-%02d\n' "$ordinal"
            done
            for ordinal in $(seq 1 "$PROVISIONED_CLIENT_COUNT"); do
                printf 'prpl-client-%02d\n' "$ordinal"
            done
        } > "$FAKE_LXC_STATE"
        ;;
    *) echo "unexpected fake radio-lab action: $*" >&2; exit 2 ;;
esac
SH
chmod 755 "$work/lxc" "$work/radio-lab"

run_firstboot()
{
    local action=${1:-prepare}
    env PROVISIONED_AGENT_COUNT=4 PROVISIONED_CLIENT_COUNT=100 \
        PRPLMESH_ROOT="$work/root" \
        PRPLMESH_THIN_ALLOW_UNPRIVILEGED=1 \
        PRPLMESH_THIN_SKIP_SYNC=1 \
        PRPLMESH_THIN_MARKER="$marker" \
        PRPLMESH_THIN_REPORT="$report" \
        PRPLMESH_THIN_CAPACITY_STATE="$capacity" \
        PRPLMESH_LXC_BIN="$work/lxc" \
        PRPLMESH_RADIO_LAB="$work/radio-lab" \
        FAKE_LXC_STATE="$state" \
        "$ROOT/deploy/guest/prepare-thin-firstboot.sh" "$action"
}

: > "$state"
: > "$marker"
run_firstboot >/dev/null
test -e "$marker"
grep -Fxq 'nested_instances_before=0' "$report"
grep -Fxq 'nested_instances_after_provision=105' "$report"
test "$(wc -l < "$state")" -eq 105
run_firstboot finalize >/dev/null
test ! -e "$marker"
grep -Fxq 'nested_instances_final=105' "$report"
grep -Fxq 'thin_firstboot_status=PASS' "$report"

printf 'prpl-other\n' > "$state"
: > "$marker"
rm -f "$report"
if run_firstboot >"$work/unexpected.out" 2>"$work/unexpected.err"; then
    echo 'unexpected nested instance was accepted' >&2
    exit 1
fi
grep -q 'unexpected nested LXD instance' "$work/unexpected.err"
test -e "$marker"

printf 'prpl-controller\n' > "$state"
: > "$marker"
cat > "$report" <<'EOF'
thin_firstboot_started_at=test
nested_instances_before=0
expected_instances_after=105
profile_clients=100
EOF
run_firstboot >/dev/null
test -e "$marker"
grep -Fxq 'retry_instances_before=1' "$report"
grep -Fxq 'nested_instances_after_provision=105' "$report"
run_firstboot finalize >/dev/null
test ! -e "$marker"

echo 'PASS: offline thin first boot is empty, bounded and retryable'
