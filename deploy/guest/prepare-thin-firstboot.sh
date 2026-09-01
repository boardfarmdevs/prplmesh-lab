#!/bin/bash
set -euo pipefail

ROOT=${PRPLMESH_ROOT:-/opt/prplmesh-lab}
MARKER=${PRPLMESH_THIN_MARKER:-/var/lib/prplmesh-lab/thin-pending.env}
REPORT=${PRPLMESH_THIN_REPORT:-/var/lib/prplmesh-lab/thin-firstboot-report.txt}
LXC_BIN=${PRPLMESH_LXC_BIN:-lxc}
RADIO_LAB=${PRPLMESH_RADIO_LAB:-$ROOT/scripts/radio-lab.sh}
RUNTIME_IMAGE=${PRPLMESH_RUNTIME_IMAGE:-prpl-runtime-local}
ACTION=${1:-prepare}

case "$ACTION" in
    prepare|finalize) ;;
    *) echo "usage: $0 {prepare|finalize}" >&2; exit 2 ;;
esac

if [ "$(id -u)" -ne 0 ] && [ "${PRPLMESH_THIN_ALLOW_UNPRIVILEGED:-0}" != 1 ]; then
    echo "thin first-boot provisioning must run as root" >&2
    exit 1
fi
[ -r "$MARKER" ] || exit 0
if [ -r /etc/default/prplmesh-lab ]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/default/prplmesh-lab
    set +a
fi

agents=${PROVISIONED_AGENT_COUNT:-4}
clients=${PROVISIONED_CLIENT_COUNT:-20}
expected=$((1 + agents + clients))

case "$agents:$clients" in
    *[!0-9:]*|0:*|*:0) echo "invalid thin profile cardinality: $agents agents, $clients clients" >&2; exit 2 ;;
esac

instance_names()
{
    "$LXC_BIN" list --format csv -c n
}

validate_instances()
{
    local name ordinal
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        case "$name" in
            prpl-controller) ;;
            prpl-agent-[0-9][0-9])
                ordinal=$((10#${name##*-}))
                [ "$ordinal" -ge 1 ] && [ "$ordinal" -le "$agents" ] || return 1
                ;;
            prpl-client-[0-9][0-9]|prpl-client-[0-9][0-9][0-9])
                ordinal=$((10#${name##*-}))
                [ "$ordinal" -ge 1 ] && [ "$ordinal" -le "$clients" ] || return 1
                ;;
            *) return 1 ;;
        esac
    done < <(instance_names)
}

"$LXC_BIN" image info "$RUNTIME_IMAGE" >/dev/null
before=$(instance_names | awk 'NF {n++} END {print n+0}')
validate_instances || {
    echo "thin first boot found an unexpected nested LXD instance" >&2
    exit 1
}

if [ "$ACTION" = finalize ]; then
    [ -r "$REPORT" ] || {
        echo "thin first-boot report is missing" >&2
        exit 1
    }
    [ "$before" -eq "$expected" ] || {
        echo "thin acceptance completed with $before instances; expected $expected" >&2
        exit 1
    }
    report_tmp=${REPORT}.tmp
    cp -- "$REPORT" "$report_tmp"
    {
        printf 'nested_instances_final=%s\n' "$before"
        printf 'thin_firstboot_status=PASS\n'
        printf 'thin_firstboot_finished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$report_tmp"
    mv -f -- "$report_tmp" "$REPORT"
    rm -f -- "$MARKER"
    [ "${PRPLMESH_THIN_SKIP_SYNC:-0}" = 1 ] || sync
    echo "thin first-boot acceptance finalized: $before nested instances"
    exit 0
fi

if [ ! -e "$REPORT" ]; then
    [ "$before" -eq 0 ] || {
        echo "thin appliance did not start from an empty nested inventory: $before" >&2
        exit 1
    }
    install -d -m 0755 "$(dirname "$REPORT")"
    {
        printf 'thin_firstboot_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'nested_instances_before=%s\n' "$before"
        printf 'expected_instances_after=%s\n' "$expected"
        printf 'profile_clients=%s\n' "$clients"
    } > "$REPORT"
else
    printf 'retry_instances_before=%s\n' "$before" >> "$REPORT"
fi

env PRPL_AGENT_COUNT="$agents" PRPL_CLIENT_COUNT="$clients" \
    PROVISIONED_AGENT_COUNT="$agents" PROVISIONED_CLIENT_COUNT="$clients" \
    "$RADIO_LAB" radio-pool
env PRPL_AGENT_COUNT="$agents" PRPL_CLIENT_COUNT="$clients" \
    PROVISIONED_AGENT_COUNT="$agents" PROVISIONED_CLIENT_COUNT="$clients" \
    "$RADIO_LAB" deploy

after=$(instance_names | awk 'NF {n++} END {print n+0}')
validate_instances
[ "$after" -eq "$expected" ] || {
    echo "thin first boot provisioned $after nested instances; expected $expected" >&2
    exit 1
}

printf 'nested_instances_after_provision=%s\n' "$after" >> "$REPORT"
echo "thin first-boot provisioning complete; acceptance pending: $after nested instances"
