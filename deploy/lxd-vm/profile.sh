#!/bin/bash

prplmesh_profile_name()
{
    case "${1:-20}" in
        20|small) printf 'small\n' ;;
        50|medium) printf 'medium\n' ;;
        100|stress) printf 'stress\n' ;;
        *) echo "invalid prplMesh profile: $1 (expected 20, 50 or 100)" >&2; return 2 ;;
    esac
}

prplmesh_profile_clients()
{
    case "$(prplmesh_profile_name "${1:-20}")" in
        small) printf '20\n' ;;
        medium) printf '50\n' ;;
        stress) printf '100\n' ;;
    esac
}

prplmesh_profile_release_name()
{
    printf 'prplmesh-%s-%s\n' \
        "$(prplmesh_profile_clients "${1:-20}")" \
        "${PRPLMESH_RELEASE_ID:-0908}"
}

prplmesh_thin_release_name()
{
    printf 'prplmesh-%s-thin\n' "${PRPLMESH_RELEASE_ID:-0908}"
}

prplmesh_profile_radios()
{
    # Five tri-band mesh nodes consume 15 radios. Keep a small spare pool
    # above the fixed client roster without exceeding the 128-radio patch.
    case "$(prplmesh_profile_name "${1:-20}")" in
        small) printf '40\n' ;;
        medium) printf '72\n' ;;
        stress) printf '120\n' ;;
    esac
}

prplmesh_profile_cpus()
{
    case "$(prplmesh_profile_name "${1:-20}")" in
        small) printf '6\n' ;;
        medium) printf '8\n' ;;
        stress) printf '12\n' ;;
    esac
}

prplmesh_profile_memory()
{
    case "$(prplmesh_profile_name "${1:-20}")" in
        small) printf '8GiB\n' ;;
        medium) printf '12GiB\n' ;;
        stress) printf '20GiB\n' ;;
    esac
}

prplmesh_profile_disk()
{
    case "$(prplmesh_profile_name "${1:-20}")" in
        small) printf '80GiB\n' ;;
        medium) printf '88GiB\n' ;;
        # A 104 GiB disk filled while creating client 80 in qualification.
        stress) printf '160GiB\n' ;;
    esac
}

prplmesh_profile_min_lxd_pool_free_bytes()
{
    # Sparse outer VM disks need the measured build working set plus headroom.
    case "$(prplmesh_profile_name "${1:-20}")" in
        small) printf '%s\n' $((24 * 1024 * 1024 * 1024)) ;;
        medium) printf '%s\n' $((48 * 1024 * 1024 * 1024)) ;;
        stress) printf '%s\n' $((80 * 1024 * 1024 * 1024)) ;;
    esac
}

prplmesh_thin_guest_source_allowed()
{
    local guest=$1 runtime_base=$2 source=$3

    [ "$guest" = "$runtime_base" ] || [ "$guest" = "$source" ]
}
