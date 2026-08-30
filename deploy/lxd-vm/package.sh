#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"
PROFILE=$(prplmesh_profile_name "${PRPLMESH_LAB_PROFILE:-20}")
CLIENTS=$(prplmesh_profile_clients "$PROFILE")
RADIOS=$(prplmesh_profile_radios "$PROFILE")
NAME=${PRPLMESH_VM_NAME:-prplmesh-${CLIENTS}-0829}
OUTPUT_DIR=${1:-$ROOT/release/0829}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
BUNDLE="$OUTPUT_DIR/prplmesh-${CLIENTS}-0829-${SHORT}-lxd"
OUTPUT="$BUNDLE/prplmesh-${CLIENTS}-0829-${SHORT}-lxd.tar.zst"
WAS_RUNNING=false

command -v jq >/dev/null 2>&1 || { echo 'jq is required for release metadata' >&2; exit 1; }

[ -z "$(git -C "$ROOT" status --porcelain)" ] || {
    echo "source checkout must be clean before packaging" >&2
    exit 1
}
rm -rf -- "$BUNDLE"
mkdir -p "$BUNDLE"
[ "$(lxc list "$NAME" -c t --format csv)" = VIRTUAL-MACHINE ] || {
    echo "not an LXD VM: $NAME" >&2
    exit 1
}
[ "$(lxc list "$NAME" -c s --format csv)" != RUNNING ] || WAS_RUNNING=true

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

if [ "$(lxc list "$NAME" -c s --format csv)" != RUNNING ]; then
    lxc start "$NAME"
fi
for unused in $(seq 1 120); do
    lxc exec "$NAME" -- true >/dev/null 2>&1 && break
    sleep 2
done
guest_commit=$(lxc exec "$NAME" -- git -C /opt/prplmesh-lab rev-parse HEAD)
[ "$guest_commit" = "$(git -C "$ROOT" rev-parse HEAD)" ] || {
    echo "guest source $guest_commit does not match release source" >&2
    exit 1
}
guest_clients=$(lxc exec "$NAME" -- bash -lc \
    '. /etc/default/prplmesh-lab; printf "%s" "$PROVISIONED_CLIENT_COUNT"')
[ "$guest_clients" = "$CLIENTS" ] || {
    echo "guest has $guest_clients clients; requested release profile has $CLIENTS" >&2
    exit 1
}
PRPLMESH_VM_NAME="$NAME" "$ROOT/deploy/lxd-vm/build.sh" check

if [ "$(lxc list "$NAME" -c s --format csv)" = RUNNING ]; then
    lxc exec "$NAME" -- systemctl stop prplmesh-lab.service 2>/dev/null || true
    lxc stop "$NAME" --timeout 120
fi
restart()
{
    [ "$WAS_RUNNING" = true ] && lxc start "$NAME" || true
}
trap restart EXIT

lxc export "$NAME" "$OUTPUT" --instance-only --compression zstd
install -m 0755 "$ROOT/deploy/lxd-vm/import.sh" "$BUNDLE/import.sh"
install -m 0755 "$ROOT/deploy/lxd-vm/install-host.sh" "$BUNDLE/install-host.sh"
install -m 0755 "$ROOT/deploy/lxd-vm/package-release.sh" "$BUNDLE/package-release.sh"
install -m 0644 "$ROOT/deploy/lxd-vm/README.md" "$BUNDLE/README.md"
cat > "$BUNDLE/release.env" <<EOF
LAB_STACK=prplmesh
LAB_PROFILE=$PROFILE
LAB_CLIENTS=$CLIENTS
LAB_HWSIM_RADIOS=$RADIOS
LAB_DEFAULT_NAME=$NAME
LAB_DEFAULT_CPUS=$(prplmesh_profile_cpus "$PROFILE")
LAB_DEFAULT_MEMORY=$(prplmesh_profile_memory "$PROFILE")
LAB_DEFAULT_DISK=$(prplmesh_profile_disk "$PROFILE")
LAB_SOURCE_COMMIT=$(git -C "$ROOT" rev-parse HEAD)
EOF
jq -n \
    --arg stack prplmesh --arg profile "$PROFILE" \
    --argjson clients "$CLIENTS" --argjson radios "$RADIOS" \
    --arg source_commit "$(git -C "$ROOT" rev-parse HEAD)" \
    --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg archive "$(basename "$OUTPUT")" --arg instance "$NAME" \
    --arg cpus "$(prplmesh_profile_cpus "$PROFILE")" \
    --arg memory "$(prplmesh_profile_memory "$PROFILE")" \
    --arg disk "$(prplmesh_profile_disk "$PROFILE")" \
    '{schema_version:1,stack:$stack,profile:$profile,clients:$clients,
      hwsim_radios:$radios,source_commit:$source_commit,created_at:$created_at,
      archive:$archive,defaults:{instance:$instance,cpus:$cpus,memory:$memory,disk:$disk},
      status:"candidate"}' > "$BUNDLE/release.json"
(
    cd "$BUNDLE"
    sha256sum "$(basename "$OUTPUT")" import.sh install-host.sh \
        package-release.sh README.md release.env release.json \
        > SHA256SUMS
)
echo "$BUNDLE"
