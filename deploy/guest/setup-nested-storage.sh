#!/bin/bash
set -euo pipefail

pool=${PRPLMESH_NESTED_STORAGE_POOL:-prpl-lab}
driver=${PRPLMESH_NESTED_STORAGE_DRIVER:-btrfs}
size=${PRPLMESH_NESTED_STORAGE_SIZE:-120GiB}
[[ "$pool" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo 'Invalid nested pool name' >&2; exit 2; }
case "$driver" in btrfs|dir) ;; *) echo 'Nested storage must be btrfs or dir' >&2; exit 2 ;; esac
[[ "$size" =~ ^[1-9][0-9]*GiB$ ]] || { echo 'Nested pool size must be a positive integer GiB value' >&2; exit 2; }

profile=$(lxc query /1.0/profiles/default)
[[ $(jq '[.devices[] | select(.type == "disk" and .path == "/")] | length' <<<"$profile") -le 1 ]] || {
    echo 'Default profile has multiple root disks; refusing to modify it.' >&2
    exit 1
}
root=$(jq -r '[.devices | to_entries[] | select(.value.type == "disk" and .value.path == "/")] | if length == 1 then .[0].key else empty end' <<<"$profile")
current=$(jq -r --arg root "$root" '.devices[$root].pool // empty' <<<"$profile")
if [[ "$current" != "$pool" && $(lxc list --format json | jq length) != 0 ]]; then
    echo "Refusing to change nested storage with existing instances; use a fresh VM, not an in-place migration." >&2
    exit 1
fi
if lxc storage show "$pool" >/dev/null 2>&1; then
    actual=$(lxc query "/1.0/storage-pools/$pool" | jq -r .driver)
    [[ "$actual" == "$driver" ]] || {
        echo "Nested pool $pool already uses $actual, not $driver; it will not be reformatted." >&2
        exit 1
    }
else
    case "$driver" in
        btrfs)
            command -v btrfs >/dev/null
            modprobe btrfs
            lxc storage create "$pool" btrfs size="$size"
            ;;
        dir) lxc storage create "$pool" dir ;;
    esac
fi
if [[ -n "$root" ]]; then
    lxc profile device set default "$root" pool="$pool"
else
    lxc profile device add default root disk path=/ pool="$pool"
fi
printf 'Nested storage: pool=%s driver=%s; existing pools and instances retained\n' "$pool" "$driver"
