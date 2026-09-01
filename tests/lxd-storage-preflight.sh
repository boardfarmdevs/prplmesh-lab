#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d /tmp/prpl-lxd-storage-test.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/lxc" <<'SH'
#!/bin/bash
set -euo pipefail
case "${1:-} ${2:-} ${3:-} ${4:-} ${5:-}" in
    "profile device get default root") printf '%s\n' "${FAKE_POOL:-test-pool}" ;;
    query*)
        printf '{"space":{"total":%s,"used":%s}}\n' "$FAKE_TOTAL" "$FAKE_USED"
        ;;
    *) echo "unexpected fake lxc invocation: $*" >&2; exit 2 ;;
esac
SH
chmod 755 "$tmp/lxc"

gib=$((1024 * 1024 * 1024))
run_preflight()
{
    env PATH="$tmp:$PATH" FAKE_TOTAL="$1" FAKE_USED="$2" \
        "$ROOT/deploy/lxd-vm/storage-preflight.sh" "$3" "${4:-}"
}

output=$(run_preflight "$((100 * gib))" "$((70 * gib))" 20)
grep -q 'pool=test-pool profile=small' <<<"$output"
grep -q 'free=30.00GiB required_free=24.00GiB' <<<"$output"

if run_preflight "$((100 * gib))" "$((53 * gib))" 50 \
    >"$tmp/fail.out" 2>"$tmp/fail.err"; then
    echo "medium preflight unexpectedly accepted 47 GiB free" >&2
    exit 1
fi
grep -q 'free=47.00GiB required_free=48.00GiB' "$tmp/fail.out"
grep -q 'insufficient free space' "$tmp/fail.err"

output=$(run_preflight "$((150 * gib))" "$((70 * gib))" 100 named-pool)
grep -q 'pool=named-pool profile=stress' <<<"$output"
grep -q 'free=80.00GiB required_free=80.00GiB' <<<"$output"

output=$(env PATH="$tmp:$PATH" FAKE_TOTAL="$((100 * gib))" \
    FAKE_USED="$((70 * gib))" PRPLMESH_LXD_STORAGE=selected-pool \
    "$ROOT/deploy/lxd-vm/storage-preflight.sh" 20)
grep -q 'pool=selected-pool profile=small' <<<"$output"
grep -Fq 'PRPLMESH_LXD_STORAGE=' "$ROOT/deploy/lxd-vm/build.sh"
grep -Fq 'import_args+=(--storage "$STORAGE")' "$ROOT/deploy/lxd-vm/import.sh"

echo "PASS: profile-aware LXD storage preflight"
