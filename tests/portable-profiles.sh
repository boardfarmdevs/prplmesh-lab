#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../deploy/lxd-vm/profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"
work=$(mktemp -d /tmp/prplmesh-portable-profiles.XXXXXX)
trap 'rm -rf -- "$work"' EXIT

check()
{
    local input=$1 name=$2 clients=$3 radios=$4 release_name=$5 output
    test "$(prplmesh_profile_name "$input")" = "$name"
    test "$(prplmesh_profile_clients "$input")" = "$clients"
    test "$(prplmesh_profile_radios "$input")" = "$radios"
    test "$(prplmesh_profile_release_name "$input")" = "$release_name"
    output="$work/wmediumd-$clients.conf"
    "$ROOT/scripts/generate-wmediumd-config.py" \
        --radios "$radios" --output "$output"
    grep -Fq "count = $radios;" "$output"
    test "$(grep -Eo '42:00:00:00:[0-9a-f]{2}:00' "$output" | wc -l)" \
        -eq "$radios"
}

check 20 small 20 40 prplmesh-20-0831
check small small 20 40 prplmesh-20-0831
check 50 medium 50 72 prplmesh-50-0831
check medium medium 50 72 prplmesh-50-0831
check 100 stress 100 120 prplmesh-100-0831
check stress stress 100 120 prplmesh-100-0831
test "$(prplmesh_thin_release_name)" = prplmesh-0831-thin
if prplmesh_profile_name 21 >/dev/null 2>&1; then
    echo 'invalid profile was accepted' >&2
    exit 1
fi

for script in \
    controller-ui/install.sh \
    scripts/build-wmediumd.sh \
    deploy/guest/prepare-thin-firstboot.sh \
    deploy/guest/prepare-thin-image.sh \
    deploy/guest/select-thin-profile.sh \
    deploy/lxd-vm/package-thin.sh; do
    bash -n "$ROOT/$script"
done

for clients in 20 50 100; do
    case "$clients" in
        20) expected_profile=small; expected_radios=40 ;;
        50) expected_profile=medium; expected_radios=72 ;;
        100) expected_profile=stress; expected_radios=120 ;;
    esac
    state=$work/state-$clients
    defaults=$work/defaults-$clients
    config=$work/wmediumd-selected-$clients.conf
    mkdir "$state"
    printf 'THIN_RELEASE_FLAVOR=thin\n' > "$state/thin-firstboot.template.env"
    : > "$state/thin-profile-selection.required"
    PRPLMESH_PROFILE_STATE_DIR="$state" \
    PRPLMESH_PROFILE_DEFAULTS="$defaults" \
    PRPLMESH_PROFILE_WMEDIUMD_CONFIG="$config" \
    PRPLMESH_PROFILE_TEST_MODE=true \
        "$ROOT/deploy/guest/select-thin-profile.sh" "$clients" >/dev/null
    grep -Fxq "PRPLMESH_LAB_PROFILE=$expected_profile" "$defaults"
    grep -Fxq "PROVISIONED_CLIENT_COUNT=$clients" "$defaults"
    grep -Fxq "HWSIM_RADIOS=$expected_radios" "$defaults"
    grep -Fxq "PROVISIONED_CLIENT_COUNT=$clients" \
        "$state/thin-profile.lock.env"
    grep -Fxq "THIN_CLIENTS=$clients" "$state/thin-pending.env"
    grep -Fq "count = $expected_radios" "$config"
    test ! -e "$state/thin-profile-selection.required"

    PRPLMESH_PROFILE_STATE_DIR="$state" \
    PRPLMESH_PROFILE_DEFAULTS="$defaults" \
    PRPLMESH_PROFILE_WMEDIUMD_CONFIG="$config" \
    PRPLMESH_PROFILE_TEST_MODE=true \
        "$ROOT/deploy/guest/select-thin-profile.sh" "$clients" >/dev/null
    different=20
    [ "$clients" != 20 ] || different=50
    if PRPLMESH_PROFILE_STATE_DIR="$state" \
        PRPLMESH_PROFILE_DEFAULTS="$defaults" \
        PRPLMESH_PROFILE_WMEDIUMD_CONFIG="$config" \
        PRPLMESH_PROFILE_TEST_MODE=true \
        "$ROOT/deploy/guest/select-thin-profile.sh" "$different" \
            >/dev/null 2>&1; then
        echo "locked $clients-client profile changed to $different" >&2
        exit 1
    fi
done

universal=$work/universal-import
mkdir "$universal"
install -m 0755 "$ROOT/deploy/lxd-vm/import.sh" "$universal/import.sh"
printf 'LAB_PROFILE_SELECTABLE=true\nLAB_SUPPORTED_PROFILES=20,50,100\n' \
    > "$universal/release.env"
if "$universal/import.sh" >"$work/missing-profile.out" 2>&1; then
    echo 'universal import accepted a missing profile' >&2
    exit 1
fi
grep -Fq 'requires --profile 20, 50 or 100' "$work/missing-profile.out"
if "$universal/import.sh" --profile 21 >"$work/invalid-profile.out" 2>&1; then
    echo 'universal import accepted an invalid profile' >&2
    exit 1
fi
grep -Fq 'requires --profile 20, 50 or 100' "$work/invalid-profile.out"
grep -Fq 'PRPLMESH_THIN_CONFIRM' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'initial_nested_instances:0' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'LAB_RUNTIME_BASE_COMMIT' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'bundle create "$SOURCE_BUNDLE" HEAD' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'thin_firstboot_status=PASS' "$ROOT/deploy/guest/prepare-thin-firstboot.sh"
grep -Fxq 'TimeoutStartSec=60min' "$ROOT/deploy/guest/prplmesh-lab.service"
grep -Fq 'PRPLMESH_PRESERVE_IMAGE_ALIAS' "$ROOT/deploy/lxd-vm/package-cleanup.sh"
grep -Fq 'systemctl is-active --quiet prplmesh-controller-ui.service' \
    "$ROOT/controller-ui/install.sh"
grep -Fq 'PRPL_UI_READY_ATTEMPTS:-30' "$ROOT/controller-ui/install.sh"
grep -Fq 'curl -sS --max-time 2' "$ROOT/controller-ui/install.sh"
grep -Fq 'build-wmediumd.sh --offline' "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'cp -a /opt/prplmesh-lab/build "$next/build"' \
    "$ROOT/deploy/lxd-vm/package-thin.sh"
grep -Fq 'cp -a /opt/prplmesh-lab/artifacts/. "$next/artifacts/"' \
    "$ROOT/deploy/lxd-vm/package-thin.sh"
test "$(grep -c 'sha256sum -c SHA256SUMS' \
    "$ROOT/deploy/lxd-vm/package-thin.sh")" -ge 3

"$ROOT/tests/wmediumd-offline-build.sh"
"$ROOT/tests/nested-stop.sh"
"$ROOT/tests/nested-image-fingerprints.sh"
"$ROOT/tests/data-plane-leaf.sh"
"$ROOT/tests/thin-package-order.sh"
"$ROOT/tests/thin-import-nested-ready.sh"

echo 'PASS: prplMesh portable profiles and wmediumd rosters'
