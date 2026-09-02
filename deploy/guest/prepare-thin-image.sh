#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
MARKER=${PRPLMESH_THIN_MARKER:-/var/lib/prplmesh-lab/thin-pending.env}
TEMPLATE=${PRPLMESH_THIN_TEMPLATE:-/var/lib/prplmesh-lab/thin-firstboot.template.env}
SELECTION_REQUIRED=${PRPLMESH_THIN_SELECTION_REQUIRED:-/var/lib/prplmesh-lab/thin-profile-selection.required}
REPORT=${PRPLMESH_THIN_REPORT:-/var/lib/prplmesh-lab/thin-firstboot-report.txt}
RUNTIME_IMAGE=${PRPLMESH_RUNTIME_IMAGE:-prpl-runtime-local}
CANDIDATE_ALIAS=prpl-runtime-thin-candidate

[ "$(id -u)" -eq 0 ] || { echo "thin image preparation must run as root" >&2; exit 1; }
# shellcheck disable=SC1091
source /etc/default/prplmesh-lab
agents=${PROVISIONED_AGENT_COUNT:?}
clients=${PROVISIONED_CLIENT_COUNT:?}
expected=$((1 + agents + clients))

systemctl stop prplmesh-lab.service
expected_instances=(prpl-controller)
for ordinal in $(seq 1 "$agents"); do
    printf -v name 'prpl-agent-%02d' "$ordinal"
    expected_instances+=("$name")
done
for ordinal in $(seq 1 "$clients"); do
    printf -v name 'prpl-client-%02d' "$ordinal"
    expected_instances+=("$name")
done
mapfile -t expected_instances < <(printf '%s\n' "${expected_instances[@]}" | sort)
mapfile -t instances < <(lxc list --format csv -c n | sort)
[ "${#instances[@]}" -eq "$expected" ] || {
    echo "thin preparation found ${#instances[@]} instances; expected $expected" >&2
    exit 1
}
for index in "${!instances[@]}"; do
    [ "${instances[$index]}" = "${expected_instances[$index]}" ] || {
        echo "refusing unexpected nested roster entry: ${instances[$index]}" >&2
        exit 1
    }
done
"$ROOT/scripts/stop-nested-instances.sh" "${instances[@]}"

if lxc image alias list --format csv | cut -d, -f1 | grep -Fxq "$CANDIDATE_ALIAS"; then
    lxc image alias delete "$CANDIDATE_ALIAS"
fi
lxc publish prpl-controller --alias "$CANDIDATE_ALIAS"
fingerprint=$(lxc image info "$CANDIDATE_ALIAS" | sed -n 's/^Fingerprint: //p')
[ -n "$fingerprint" ]
if lxc image alias list --format csv | cut -d, -f1 | grep -Fxq "$RUNTIME_IMAGE"; then
    lxc image alias delete "$RUNTIME_IMAGE"
fi
lxc image alias create "$RUNTIME_IMAGE" "$fingerprint"
lxc image alias delete "$CANDIDATE_ALIAS"

for name in "${instances[@]}"; do
    lxc delete "$name"
done
[ "$(lxc list --format csv -c n | awk 'NF {n++} END {print n+0}')" -eq 0 ]

while IFS= read -r image; do
    [ -n "$image" ] || continue
    [ "$image" = "$fingerprint" ] || lxc image delete "$image"
done < <(lxc image list --format json | jq -r '.[].fingerprint')
lxc image info "$RUNTIME_IMAGE" >/dev/null

install -d -m 0755 "$(dirname "$MARKER")"
rm -f -- "$REPORT" "$MARKER" "$TEMPLATE" "$SELECTION_REQUIRED" \
    /var/lib/prplmesh-lab/thin-profile.lock.env
marker_tmp=${TEMPLATE}.tmp
{
    printf 'THIN_RELEASE_FLAVOR=thin\n'
    printf 'THIN_RUNTIME_IMAGE=%s\n' "$RUNTIME_IMAGE"
    printf 'THIN_PREPARED_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$marker_tmp"
if [ "${PRPLMESH_THIN_PROFILE_SELECTABLE:-0}" = 1 ]; then
    mv -f -- "$marker_tmp" "$TEMPLATE"
    : > "$SELECTION_REQUIRED"
    chmod 0444 "$SELECTION_REQUIRED"
    rm -f /etc/default/prplmesh-lab
else
    {
        printf 'THIN_PROFILE=%s\n' "${PRPLMESH_LAB_PROFILE:-unknown}"
        printf 'THIN_CLIENTS=%s\n' "$clients"
    } >> "$marker_tmp"
    mv -f -- "$marker_tmp" "$MARKER"
fi
sync

printf 'thin_nested_instances=0\n'
printf 'thin_runtime_image=%s\n' "$RUNTIME_IMAGE"
printf 'thin_runtime_fingerprint=%s\n' "$fingerprint"
