#!/bin/bash
set -euo pipefail

STATE_DIR=${PRPLMESH_PROFILE_STATE_DIR:-/var/lib/prplmesh-lab}
TEMPLATE=$STATE_DIR/thin-firstboot.template.env
REQUIRED=$STATE_DIR/thin-profile-selection.required
PENDING=$STATE_DIR/thin-pending.env
LOCK=$STATE_DIR/thin-profile.lock.env
DEFAULTS=${PRPLMESH_PROFILE_DEFAULTS:-/etc/default/prplmesh-lab}
CONFIG=${PRPLMESH_PROFILE_WMEDIUMD_CONFIG:-/var/lib/prplmesh-lab/wmediumd.conf}
ROOT=${PRPLMESH_ROOT:-/opt/prplmesh-lab}
TEST_MODE=${PRPLMESH_PROFILE_TEST_MODE:-false}

usage()
{
    echo "usage: $0 [100] (fixed appliance capacity)" >&2
}

case "${1:-100}" in
    100) PROFILE=unified; CLIENTS=100; RADIOS=120 ;;
    *) usage; exit 2 ;;
esac

install -d -m 0755 "$STATE_DIR" "$(dirname "$DEFAULTS")" \
    "$(dirname "$CONFIG")"
if [ -r "$LOCK" ]; then
    # shellcheck disable=SC1090
    source "$LOCK"
    if [ "${PROVISIONED_CLIENT_COUNT:-}" = "$CLIENTS" ]; then
        echo "thin profile already locked: $CLIENTS clients ($PROFILE)"
        exit 0
    fi
    echo "thin profile is already locked to ${PROVISIONED_CLIENT_COUNT:-unknown} clients" >&2
    exit 1
fi
[ -r "$TEMPLATE" ] || { echo "thin first-boot template is missing" >&2; exit 1; }
[ -r "$REQUIRED" ] || { echo "appliance is not awaiting profile selection" >&2; exit 1; }
[ ! -e "$PENDING" ] || { echo "thin provisioning was already selected" >&2; exit 1; }

if [ "$TEST_MODE" != true ]; then
    count=$(lxc list --format csv -c n | awk 'NF {n++} END {print n+0}')
    [ "$count" -eq 0 ] || {
        echo "refusing profile selection with $count nested instances" >&2
        exit 1
    }
    systemctl stop prplmesh-lab.service 2>/dev/null || true
    # The package may have been produced from any ready profile. No nested
    # radio owner exists now, so discard its idle pool; normal start recreates
    # exactly the selected count and stable names.
    modprobe -r mac80211_hwsim 2>/dev/null || true
fi

DEFAULTS_TMP=$DEFAULTS.tmp.$$
CONFIG_TMP=$CONFIG.tmp.$$
PENDING_TMP=$PENDING.tmp.$$
LOCK_TMP=$LOCK.tmp.$$
trap 'rm -f -- "$DEFAULTS_TMP" "$CONFIG_TMP" "$PENDING_TMP" "$LOCK_TMP"' EXIT

cat > "$DEFAULTS_TMP" <<EOF
PRPLMESH_LAB_PROFILE=$PROFILE
PROVISIONED_AGENT_COUNT=4
PROVISIONED_CLIENT_COUNT=$CLIENTS
ACTIVE_AGENT_COUNT=4
ACTIVE_CLIENT_COUNT=$CLIENTS
DEFAULT_TOPOLOGY=star
HWSIM_RADIOS=$RADIOS
HWSIM_CHANNELS=3
PRPLMESH_APPLIANCE_WMEDIUMD_CONFIG=$CONFIG
EOF
chmod 0644 "$DEFAULTS_TMP"
mv -f "$DEFAULTS_TMP" "$DEFAULTS"

if [ "$TEST_MODE" = true ]; then
    printf 'ifaces = { count = %s; };\n' "$RADIOS" > "$CONFIG_TMP"
else
    python3 "$ROOT/scripts/generate-wmediumd-config.py" \
        --radios "$RADIOS" --output "$CONFIG_TMP"
fi
chmod 0644 "$CONFIG_TMP"
mv -f "$CONFIG_TMP" "$CONFIG"

cat "$TEMPLATE" > "$PENDING_TMP"
cat >> "$PENDING_TMP" <<EOF
THIN_PROFILE=$PROFILE
THIN_CLIENTS=$CLIENTS
HWSIM_RADIOS=$RADIOS
EOF
chmod 0600 "$PENDING_TMP"
cat > "$LOCK_TMP" <<EOF
PRPLMESH_LAB_PROFILE=$PROFILE
PROVISIONED_CLIENT_COUNT=$CLIENTS
HWSIM_RADIOS=$RADIOS
EOF
chmod 0444 "$LOCK_TMP"

mv -f "$LOCK_TMP" "$LOCK"
mv -f "$PENDING_TMP" "$PENDING"
rm -f "$REQUIRED"
trap - EXIT
echo "thin profile locked: $CLIENTS clients ($PROFILE), $RADIOS hwsim radios"
