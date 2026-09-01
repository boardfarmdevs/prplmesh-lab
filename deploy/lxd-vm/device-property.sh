#!/bin/bash

lxd_set_device_property()
{
    local instance=$1 device=$2 key=$3 value=$4

    if lxc config device show "$instance" | awk -v device="$device" '
        $0 == device ":" { found=1 }
        END { exit !found }
    '; then
        lxc config device set "$instance" "$device" "$key" "$value"
    else
        lxc config device override "$instance" "$device" "$key=$value"
    fi
}
