#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../deploy/lxd-vm/profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"
work=$(mktemp -d /tmp/prplmesh-portable-profiles.XXXXXX)
trap 'find "$work" -type f -delete; rmdir "$work"' EXIT

check()
{
    local input=$1 name=$2 clients=$3 radios=$4 output
    test "$(prplmesh_profile_name "$input")" = "$name"
    test "$(prplmesh_profile_clients "$input")" = "$clients"
    test "$(prplmesh_profile_radios "$input")" = "$radios"
    output="$work/wmediumd-$clients.conf"
    "$ROOT/scripts/generate-wmediumd-config.py" \
        --radios "$radios" --output "$output"
    grep -Fq "count = $radios;" "$output"
    test "$(grep -Eo '42:00:00:00:[0-9a-f]{2}:00' "$output" | wc -l)" \
        -eq "$radios"
}

check 20 small 20 40
check small small 20 40
check 50 medium 50 72
check medium medium 50 72
check 100 stress 100 120
check stress stress 100 120
if prplmesh_profile_name 21 >/dev/null 2>&1; then
    echo 'invalid profile was accepted' >&2
    exit 1
fi

for script in \
    deploy/guest/prepare-thin-firstboot.sh \
    deploy/guest/prepare-thin-image.sh \
    deploy/lxd-vm/package-thin.sh; do
    bash -n "$ROOT/$script"
done
grep -Fq 'PRPLMESH_THIN_CONFIRM' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'initial_nested_instances:0' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'LAB_RUNTIME_BASE_COMMIT' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'bundle create "$SOURCE_BUNDLE" HEAD' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'thin_firstboot_status=PASS' "$ROOT/deploy/guest/prepare-thin-firstboot.sh"
grep -Fxq 'TimeoutStartSec=60min' "$ROOT/deploy/guest/prplmesh-lab.service"
grep -Fq 'PRPLMESH_PRESERVE_IMAGE_ALIAS' "$ROOT/deploy/lxd-vm/package-cleanup.sh"

echo 'PASS: prplMesh portable profiles and wmediumd rosters'
