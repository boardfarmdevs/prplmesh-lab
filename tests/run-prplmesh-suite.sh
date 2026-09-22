#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
source "$root/deploy/lxd-vm/instance-config.sh"
prplmesh_instance_config
exec python3 "$root/tests/run-prplmesh-suite.py" "$@"
