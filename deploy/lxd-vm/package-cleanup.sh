#!/bin/bash
set -euo pipefail

# Prepare an accepted appliance for a compact block-volume export. Everything
# removed here is reconstructible cache or transient diagnostic data; the
# provisioned containers, identities, lab configuration and source remain.
[ "$(id -u)" -eq 0 ] || {
    echo "package cleanup must run as root" >&2
    exit 1
}

root_used()
{
    df -B1 --output=used / | awk 'NR == 2 {print $1}'
}

nested_images()
{
    command -v lxc >/dev/null 2>&1 || return 0
    lxc image list --format json 2>/dev/null | jq -r '.[].fingerprint' || true
}

PRESERVE_IMAGE_ALIAS=${PRPLMESH_PRESERVE_IMAGE_ALIAS:-}
PRESERVE_CLIENT_ALIAS=${PRPLMESH_PRESERVE_CLIENT_ALIAS:-}
preserve_fingerprints=()
for alias in "$PRESERVE_IMAGE_ALIAS" "$PRESERVE_CLIENT_ALIAS"; do
    [[ -n "$alias" ]] || continue
    fingerprint=$(lxc image info "$alias" 2>/dev/null |
        sed -n 's/^Fingerprint: //p')
    [ -n "$fingerprint" ] || {
        echo "nested image alias is missing: $alias" >&2
        exit 1
    }
    preserve_fingerprints+=("$fingerprint")
done

printf 'trim_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'root_used_bytes_before=%s\n' "$(root_used)"
printf 'nested_images_before=%s\n' "$(nested_images | awk 'NF {n++} END {print n+0}')"

systemctl stop prplmesh-lab.service 2>/dev/null || true

# Provisioned containers have independent root filesystems. Their source
# image cache is not needed to start, stop, restart or validate the appliance.
while IFS= read -r fingerprint; do
    [ -n "$fingerprint" ] || continue
    if printf '%s\n' "${preserve_fingerprints[@]}" | grep -Fxq "$fingerprint"; then continue; fi
    lxc image delete "$fingerprint" >/dev/null
done < <(nested_images)

if command -v docker >/dev/null 2>&1; then
    docker builder prune -af >/dev/null 2>&1 || true
    docker image prune -af >/dev/null 2>&1 || true
fi

apt-get clean
find /var/lib/apt/lists -xdev -mindepth 1 -maxdepth 1 -delete
journalctl --rotate >/dev/null 2>&1 || true
journalctl --vacuum-size=16M >/dev/null 2>&1 || true
find /tmp /var/tmp -xdev -mindepth 1 -maxdepth 1 -delete 2>/dev/null || true
find /var/log -xdev -type f \
    \( -name '*.gz' -o -name '*.old' -o -name '*.[0-9]' \) -delete

sync
printf 'fstrim_output_begin\n'
pool=$(lxc profile device get default root pool)
if [[ $(lxc query "/1.0/storage-pools/$pool" | jq -r .driver) == btrfs ]]; then
    python3 "${PRPLMESH_ROOT:-/opt/prplmesh-lab}/deploy/guest/thin-image-guard.py" trim-pool
fi
fstrim -av
printf 'fstrim_output_end\n'
sync

printf 'nested_images_after=%s\n' "$(nested_images | awk 'NF {n++} END {print n+0}')"
for fingerprint in "${preserve_fingerprints[@]}"; do printf 'preserved_nested_image=%s\n' "$fingerprint"; done
printf 'root_used_bytes_after=%s\n' "$(root_used)"
printf 'trim_finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
