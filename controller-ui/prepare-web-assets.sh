#!/bin/bash
# The topology page this UI embeds (web/static, not tracked): easymesh-medium's
# topology-ui assembled for prplMesh, from the medium this lab pins.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf web/static
../medium/topology-ui/assemble.sh prplmesh web/static
