#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

"$ROOT/scripts/preflight.sh"
"$ROOT/scripts/create-build-container.sh"
"$ROOT/scripts/build-prplmesh.sh" nl80211
"$ROOT/scripts/package-build-artifacts.sh"
"$ROOT/scripts/build-wmediumd.sh"
"$ROOT/scripts/build-runtime-image.sh"

sudo env INSTALL_MODULE=1 "$ROOT/scripts/build-hwsim.sh"
sudo depmod -a "$(uname -r)"
sudo "$ROOT/scripts/radio-lab.sh" radio-pool
sudo "$ROOT/scripts/radio-lab.sh" deploy

echo
echo 'Build and provisioning complete. Start the accepted profile with:'
echo '  sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain scripts/radio-lab.sh start'
echo '  sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain scripts/radio-lab.sh clients'
