#!/usr/bin/env bash
# The optional LXD monitoring of a lab VM (inner LXD UI, Grafana, outer-VM metrics), from
# easymesh-medium's lxd-monitoring/ (the medium submodule), with this lab's ports for the VM:
#   deploy/lxd-vm/monitoring.sh enable VM HOST_IPV4 [LABEL]
#   deploy/lxd-vm/monitoring.sh disable VM
#   deploy/lxd-vm/monitoring.sh enable-outer-metrics VM HOST_IPV4 HOST_CERT_DNS_NAME LABEL
#   deploy/lxd-vm/monitoring.sh disable-outer-metrics VM
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
bundle=$here/../../medium/lxd-monitoring
action=${1:-}
case $action in
    enable|disable|enable-outer-metrics|disable-outer-metrics) shift ;;
    *) echo "usage: $0 enable|disable|enable-outer-metrics|disable-outer-metrics VM ..." >&2; exit 2 ;;
esac
vm=${1:?the lab VM}
[ -x "$bundle/$action.sh" ] || [ -f "$bundle/$action.sh" ] || {
    echo "no $bundle/$action.sh: git submodule update --init medium" >&2; exit 1; }
# shellcheck source=instance-config.sh
. "$here/instance-config.sh"
prplmesh_instance_config "$vm"    # this VM's LAB_LXD_UI_PORT, LAB_GRAFANA_PORT, LAB_OUTER_METRICS_PORT
export LAB_PORT_BASE=$PRPLMESH_PORT_BASE
exec bash "$bundle/$action.sh" "$@"
