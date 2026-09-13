#!/bin/bash

prplmesh_profile_name() {
    case "${1:-unified}" in
        100|unified) printf 'unified\n' ;;
        *) echo '0913 uses one appliance with capacity for 100 clients; select the active roster in the room viewer' >&2; return 2 ;;
    esac
}

prplmesh_profile_release_name() {
    printf 'prplmesh-%s\n' "${PRPLMESH_RELEASE_ID:-0913}"
}

prplmesh_thin_release_name() {
    printf 'prplmesh-%s-thin\n' "${PRPLMESH_RELEASE_ID:-0913}"
}

prplmesh_profile_clients() {
    prplmesh_profile_name "${1:-unified}" >/dev/null || return
    printf '100\n'
}

prplmesh_profile_radios() {
    prplmesh_profile_name "${1:-unified}" >/dev/null || return
    printf '120\n'
}

prplmesh_profile_cpus() {
    prplmesh_profile_name "${1:-unified}" >/dev/null || return
    printf '8\n'
}

prplmesh_profile_memory() {
    prplmesh_profile_name "${1:-unified}" >/dev/null || return
    printf '16GiB\n'
}

prplmesh_profile_disk() {
    prplmesh_profile_name "${1:-unified}" >/dev/null || return
    printf '160GiB\n'
}

prplmesh_profile_min_lxd_pool_free_bytes() {
    prplmesh_profile_name "${1:-unified}" >/dev/null || return
    printf '85899345920\n'
}

prplmesh_thin_guest_source_allowed() {
    local guest=$1 runtime_base=$2 source=$3
    [ "$guest" = "$runtime_base" ] || [ "$guest" = "$source" ]
}
