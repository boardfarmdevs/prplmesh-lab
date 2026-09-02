#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"
RELEASE_ID=${PRPLMESH_RELEASE_ID:-0831}
case "$RELEASE_ID" in
    [0-9][0-9][0-9][0-9]) ;;
    *) echo "invalid PRPLMESH_RELEASE_ID: $RELEASE_ID" >&2; exit 2 ;;
esac
# shellcheck source=device-property.sh
source "$ROOT/deploy/lxd-vm/device-property.sh"
PROFILE=$(prplmesh_profile_name "${PRPLMESH_LAB_PROFILE:-20}")
CLIENTS=$(prplmesh_profile_clients "$PROFILE")
RADIOS=$(prplmesh_profile_radios "$PROFILE")
RELEASE_NAME=$(prplmesh_profile_release_name "$PROFILE")
NAME=${PRPLMESH_VM_NAME:-$RELEASE_NAME}
OUTPUT_DIR=${1:-$ROOT/release/$RELEASE_ID}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
BUNDLE="$OUTPUT_DIR/prplmesh-${RELEASE_ID}-thin"
OUTPUT="$BUNDLE/prplmesh-${RELEASE_ID}-${SHORT}-thin-lxd.tar.zst"
TRIM_REPORT="$BUNDLE/trim-report.txt"
BUILD_STORAGE_POOL=
RUNTIME_IMAGE=prpl-runtime-local
RUNTIME_BASE_COMMIT=${PRPLMESH_RUNTIME_BASE_COMMIT:-}
SOURCE_COMMIT=$(git -C "$ROOT" rev-parse HEAD)
SOURCE_STAGE=

cleanup()
{
    [ -z "$SOURCE_STAGE" ] || rm -rf -- "$SOURCE_STAGE"
}

trap cleanup EXIT

command -v jq >/dev/null 2>&1 || { echo 'jq is required for release metadata' >&2; exit 1; }
[ "${PRPLMESH_THIN_CONFIRM:-}" = "$NAME" ] || {
    echo "thin packaging removes the validated nested roster from $NAME" >&2
    echo "rerun with PRPLMESH_THIN_CONFIRM=$NAME" >&2
    exit 2
}
case "$RUNTIME_BASE_COMMIT" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]* ) ;;
    *) echo "PRPLMESH_RUNTIME_BASE_COMMIT must identify the accepted ready source" >&2; exit 2 ;;
esac
git -C "$ROOT" cat-file -e "$RUNTIME_BASE_COMMIT^{commit}"
git -C "$ROOT" merge-base --is-ancestor "$RUNTIME_BASE_COMMIT" HEAD || {
    echo "runtime base is not an ancestor of the thin release source" >&2
    exit 2
}
[ -z "$(git -C "$ROOT" status --porcelain)" ] || {
    echo "source checkout must be clean before packaging" >&2
    exit 1
}
SOURCE_STAGE=$(mktemp -d /tmp/prplmesh-thin-source.XXXXXX)
SOURCE_BUNDLE=$SOURCE_STAGE/prplmesh-lab.bundle
git -C "$ROOT" bundle create "$SOURCE_BUNDLE" HEAD
git bundle verify "$SOURCE_BUNDLE" >/dev/null
SOURCE_BUNDLE_SHA256=$(sha256sum "$SOURCE_BUNDLE" | awk '{print $1}')
rm -rf -- "$BUNDLE"
mkdir -p "$BUNDLE"
[ "$(lxc list "$NAME" -c t --format csv)" = VIRTUAL-MACHINE ] || {
    echo "not an LXD VM: $NAME" >&2
    exit 1
}
BUILD_STORAGE_POOL=$(lxc config device get "$NAME" root pool)
[ -n "$BUILD_STORAGE_POOL" ] || {
    echo "cannot determine $NAME root storage pool" >&2
    exit 1
}
if lxc config device show "$NAME" | awk '
    /^[^[:space:]].*:$/ {device=$1; sub(/:$/, "", device); type=""; source=""}
    /^[[:space:]]+type:/ {type=$2}
    /^[[:space:]]+source:/ {source=$2}
    type == "disk" && source ~ /^\// && device != "root" {found=1}
    END {exit !found}
'; then
    echo "$NAME has a host filesystem mount; it is not a portable appliance" >&2
    exit 1
fi

[ "$(lxc list "$NAME" -c s --format csv)" = RUNNING ] || lxc start "$NAME"
for unused in $(seq 1 120); do
    lxc exec "$NAME" -- true >/dev/null 2>&1 && break
    sleep 2
done
guest_commit=$(lxc exec "$NAME" -- git -C /opt/prplmesh-lab rev-parse HEAD)
prplmesh_thin_guest_source_allowed "$guest_commit" \
    "$RUNTIME_BASE_COMMIT" "$SOURCE_COMMIT" || {
    echo "guest source $guest_commit matches neither accepted runtime base $RUNTIME_BASE_COMMIT nor retry source $SOURCE_COMMIT" >&2
    exit 1
}
[ -z "$(lxc exec "$NAME" -- git -C /opt/prplmesh-lab status --porcelain)" ] || {
    echo "accepted guest source checkout is dirty" >&2
    exit 1
}
guest_clients=$(lxc exec "$NAME" -- bash -lc \
    '. /etc/default/prplmesh-lab; printf "%s" "$PROVISIONED_CLIENT_COUNT"')
[ "$guest_clients" = "$CLIENTS" ] || {
    echo "guest has $guest_clients clients; requested release profile has $CLIENTS" >&2
    exit 1
}

lxc exec "$NAME" -- systemctl stop prplmesh-lab.service
lxc file push "$SOURCE_BUNDLE" "$NAME/run/prplmesh-thin-source.bundle"
lxc exec "$NAME" -- env SOURCE_COMMIT="$SOURCE_COMMIT" bash -c '
    set -euo pipefail
    next=/opt/prplmesh-lab.thin-new
    previous=/opt/prplmesh-lab.ready-base
    swapped=0
    rollback()
    {
        rc=$?
        if [ "$swapped" -eq 1 ] && [ -d "$previous" ]; then
            failed=/opt/prplmesh-lab.failed-thin-source
            rm -rf -- "$failed"
            mv /opt/prplmesh-lab "$failed"
            mv "$previous" /opt/prplmesh-lab
            /opt/prplmesh-lab/deploy/guest/install-service.sh \
                /opt/prplmesh-lab >/dev/null 2>&1 || true
            rm -rf -- "$failed"
        fi
        exit "$rc"
    }
    trap rollback EXIT
    rm -rf -- "$next" "$previous"
    git clone /run/prplmesh-thin-source.bundle "$next"
    [ "$(git -C "$next" rev-parse HEAD)" = "$SOURCE_COMMIT" ]
    [ -z "$(git -C "$next" status --porcelain)" ]
    [ -d /opt/prplmesh-lab/build/wmediumd-source/.git ]
    [ -x /opt/prplmesh-lab/build/bin/wmediumd ]
    [ -r /opt/prplmesh-lab/build/bin/wmediumd.provenance.env ]
    [ -r /opt/prplmesh-lab/artifacts/SHA256SUMS ]
    (cd /opt/prplmesh-lab/artifacts && sha256sum -c SHA256SUMS)
    cp -a /opt/prplmesh-lab/build "$next/build"
    cp -a /opt/prplmesh-lab/artifacts/. "$next/artifacts/"
    (cd "$next/artifacts" && sha256sum -c SHA256SUMS)
    mv /opt/prplmesh-lab "$previous"
    if mv "$next" /opt/prplmesh-lab; then
        swapped=1
    else
        mv "$previous" /opt/prplmesh-lab
        exit 1
    fi
    /opt/prplmesh-lab/scripts/build-wmediumd.sh --offline
    (cd /opt/prplmesh-lab/artifacts && sha256sum -c SHA256SUMS)
    /opt/prplmesh-lab/deploy/guest/install-service.sh /opt/prplmesh-lab
    rm -rf -- "$previous"
    swapped=0
    trap - EXIT
'
lxc file delete "$NAME/run/prplmesh-thin-source.bundle"
[ "$(lxc exec "$NAME" -- git -C /opt/prplmesh-lab rev-parse HEAD)" = "$SOURCE_COMMIT" ]
[ -z "$(lxc exec "$NAME" -- git -C /opt/prplmesh-lab status --porcelain)" ]
lxc exec "$NAME" -- /opt/prplmesh-lab/scripts/radio-lab.sh stop
running_names=$(lxc exec "$NAME" -- lxc list --format csv -c ns |
    awk -F, '$2 == "RUNNING" {print $1}')
[ -z "$running_names" ] || {
    echo "nested instances remain running after staged-source drain:" >&2
    printf '%s\n' "$running_names" | sed 's/^/  /' >&2
    exit 1
}
lxc exec "$NAME" -- systemctl reset-failed prplmesh-lab.service
lxc exec "$NAME" -- systemctl start prplmesh-lab.service
PRPLMESH_VM_NAME="$NAME" "$ROOT/deploy/lxd-vm/build.sh" check
lxc exec "$NAME" -- env PRPLMESH_LAB_PROFILE="$PROFILE" \
    PRPLMESH_THIN_PROFILE_SELECTABLE=1 \
    /opt/prplmesh-lab/deploy/guest/prepare-thin-image.sh | tee "$TRIM_REPORT"
printf 'thin_source_bundle_sha256=%s\n' "$SOURCE_BUNDLE_SHA256" >> "$TRIM_REPORT"

nested_count=$(lxc exec "$NAME" -- lxc list --format csv -c n |
    awk 'NF {n++} END {print n+0}')
[ "$nested_count" -eq 0 ] || {
    echo "thin source still has $nested_count provisioned nested instances" >&2
    exit 1
}
lxc exec "$NAME" -- lxc image info "$RUNTIME_IMAGE" >/dev/null
lxc exec "$NAME" -- test -r /var/lib/prplmesh-lab/thin-firstboot.template.env
lxc exec "$NAME" -- test -r /var/lib/prplmesh-lab/thin-profile-selection.required
lxc exec "$NAME" -- test ! -e /var/lib/prplmesh-lab/thin-pending.env
printf 'nested_instances_before_export=%s\n' "$nested_count" >> "$TRIM_REPORT"

lxc file push "$ROOT/deploy/lxd-vm/package-cleanup.sh" \
    "$NAME/run/prplmesh-package-cleanup"
lxc exec "$NAME" -- chmod 0755 /run/prplmesh-package-cleanup
lxc exec "$NAME" -- env PRPLMESH_PRESERVE_IMAGE_ALIAS="$RUNTIME_IMAGE" \
    /bin/bash /run/prplmesh-package-cleanup | tee -a "$TRIM_REPORT"
lxc file delete "$NAME/run/prplmesh-package-cleanup"
lxc exec "$NAME" -- lxc image info "$RUNTIME_IMAGE" >/dev/null
[ "$(lxc exec "$NAME" -- lxc list --format csv -c n | awk 'NF {n++} END {print n+0}')" -eq 0 ]
lxd_set_device_property "$NAME" root size 160GiB
[ "$(lxc config device get "$NAME" root size)" = 160GiB ] || {
    echo "universal thin root disk did not expand to 160GiB" >&2
    exit 1
}
lxc stop "$NAME" --timeout 120

lxc export "$NAME" "$OUTPUT" --instance-only --compression zstd </dev/null
printf 'archive_bytes=%s\n' "$(stat -c %s "$OUTPUT")" >> "$TRIM_REPORT"
install -m 0755 "$ROOT/deploy/lxd-vm/import.sh" "$BUNDLE/import.sh"
install -m 0755 "$ROOT/deploy/lxd-vm/install-host.sh" "$BUNDLE/install-host.sh"
install -m 0755 "$ROOT/deploy/lxd-vm/package-release.sh" "$BUNDLE/package-release.sh"
sed "s/0831/${RELEASE_ID}/g" "$ROOT/deploy/lxd-vm/README.md" \
    > "$BUNDLE/README.md"
chmod 0644 "$BUNDLE/README.md"
install -m 0644 "$ROOT/docs/release-notes.md" "$BUNDLE/RELEASE-NOTES.md"
cat > "$BUNDLE/release.env" <<EOF
LAB_STACK=prplmesh
LAB_RELEASE_ID=$RELEASE_ID
LAB_FLAVOR=thin
LAB_PROFILE_SELECTABLE=true
LAB_SUPPORTED_PROFILES=20,50,100
LAB_DEFAULT_DISK=160GiB
LAB_BUILD_STORAGE_POOL=$BUILD_STORAGE_POOL
LAB_SOURCE_COMMIT=$(git -C "$ROOT" rev-parse HEAD)
LAB_RUNTIME_BASE_COMMIT=$RUNTIME_BASE_COMMIT
LAB_TRIMMED=true
LAB_FIRST_BOOT_PROVISION=true
EOF
jq -n \
    --arg stack prplmesh --arg flavor thin --arg release_id "$RELEASE_ID" \
    --arg source_commit "$(git -C "$ROOT" rev-parse HEAD)" \
    --arg runtime_base_commit "$RUNTIME_BASE_COMMIT" \
    --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg archive "$(basename "$OUTPUT")" --arg disk 160GiB \
    --arg build_storage_pool "$BUILD_STORAGE_POOL" \
    '{schema_version:2,stack:$stack,release_id:$release_id,flavor:$flavor,profile_selectable:true,
      supported_profiles:[20,50,100],source_commit:$source_commit,created_at:$created_at,
      runtime_base_commit:$runtime_base_commit,
      archive:$archive,
      profiles:{"20":{name:"small",instance:("prplmesh-20-"+$release_id),clients:20,hwsim_radios:40,cpus:6,memory:"8GiB"},
                "50":{name:"medium",instance:("prplmesh-50-"+$release_id),clients:50,hwsim_radios:72,cpus:8,memory:"12GiB"},
                "100":{name:"stress",instance:("prplmesh-100-"+$release_id),clients:100,hwsim_radios:120,cpus:12,memory:"20GiB"}},
      defaults:{disk:$disk},
      build:{storage_pool:$build_storage_pool},
      trim:{applied:true,report:"trim-report.txt"},
      first_boot:{provision:true,offline:true,initial_nested_instances:0},
      status:"candidate"}' > "$BUNDLE/release.json"
(
    cd "$BUNDLE"
    sha256sum "$(basename "$OUTPUT")" import.sh install-host.sh \
        package-release.sh README.md RELEASE-NOTES.md release.env release.json trim-report.txt \
        > SHA256SUMS
)
echo "$BUNDLE"
