#!/usr/bin/env bash

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    echo 'Use: source deploy/lxd-vm/lab-config.sh [VM-name]' >&2
    exit 2
fi
source "$(dirname "${BASH_SOURCE[0]}")/instance-config.sh"
if [[ -n ${_PRPL_LAB_NAME:-} && ${1:-$_PRPL_LAB_NAME} != "$_PRPL_LAB_NAME" ]]; then
    for _prpl_variable in "${!_PRPL_DERIVED[@]}"; do
        if [[ ${!_prpl_variable:-} == "${_PRPL_DERIVED[$_prpl_variable]}" ]]; then
            unset "$_prpl_variable"
        fi
    done
fi
prplmesh_instance_config "${1:-${PRPLMESH_VM_NAME:-prplmesh}}" || return
declare -gA _PRPL_DERIVED=()
for _prpl_variable in PRPLMESH_LXD_STORAGE PRPLMESH_PORT_BASE PRPLMESH_UI_HOST_PORT PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT PRPLMESH_ROOM_DEMO_HOST_PORT LAB_LXD_UI_PORT LAB_GRAFANA_PORT LAB_OUTER_METRICS_PORT; do
    _PRPL_DERIVED[$_prpl_variable]=${!_prpl_variable}
done
_PRPL_LAB_NAME=$PRPLMESH_VM_NAME
unset _prpl_variable
printf 'vm=%s pool=%s topology=%s console=%s room=%s\n' "$PRPLMESH_VM_NAME" "$PRPLMESH_LXD_STORAGE" "$PRPLMESH_UI_HOST_PORT" "$PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT" "$PRPLMESH_ROOM_DEMO_HOST_PORT"
