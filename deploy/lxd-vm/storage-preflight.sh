#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=profile.sh
source "$ROOT/deploy/lxd-vm/profile.sh"

profile=$(prplmesh_profile_name "${1:-${PRPLMESH_LAB_PROFILE:-20}}")
pool=${2:-${PRPLMESH_LXD_STORAGE:-${PRPLMESH_LXD_STORAGE_POOL:-}}}
if [ -z "$pool" ]; then
    pool=$(lxc profile device get default root pool)
fi
[ -n "$pool" ] || {
    echo "cannot determine the LXD storage pool from the default profile" >&2
    exit 2
}

encoded_pool=$(python3 - "$pool" <<'PY'
from urllib.parse import quote
import sys
print(quote(sys.argv[1], safe=""))
PY
)
resources=$(lxc query "/1.0/storage-pools/$encoded_pool/resources")
read -r total used free < <(python3 -c '
import json
import sys
value = json.load(sys.stdin)["space"]
total, used = int(value["total"]), int(value["used"])
if total <= 0 or used < 0 or used > total:
    raise SystemExit("LXD returned invalid storage resource values")
print(total, used, total - used)
' <<<"$resources")
required=$(prplmesh_profile_min_lxd_pool_free_bytes "$profile")

format_bytes()
{
    python3 - "$1" <<'PY'
import sys
print(f"{int(sys.argv[1]) / (1024 ** 3):.2f}GiB")
PY
}

printf 'LXD pool preflight: pool=%s profile=%s capacity=%s used=%s free=%s required_free=%s\n' \
    "$pool" "$profile" "$(format_bytes "$total")" "$(format_bytes "$used")" \
    "$(format_bytes "$free")" "$(format_bytes "$required")"
if [ "$free" -lt "$required" ]; then
    echo "insufficient free space in LXD pool $pool for the $profile profile" >&2
    exit 1
fi
