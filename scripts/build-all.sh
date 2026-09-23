#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

"$ROOT/scripts/preflight.sh"
"$ROOT/scripts/create-build-container.sh"
"$ROOT/scripts/build-prplmesh.sh" nl80211
"$ROOT/scripts/package-build-artifacts.sh"
"$ROOT/scripts/build-wmediumd.sh"
IMAGE_ALIAS=${PRPLMESH_RUNTIME_IMAGE:-prpl-runtime-local} "$ROOT/scripts/build-runtime-image.sh"
IMAGE_ALIAS=${PRPLMESH_CLIENT_IMAGE:-prpl-client-local} "$ROOT/scripts/build-runtime-image.sh" client

sudo env INSTALL_MODULE=1 "$ROOT/scripts/build-hwsim.sh"
sudo depmod -a "$(uname -r)"
sudo "$ROOT/scripts/radio-lab.sh" radio-pool
sudo "$ROOT/scripts/radio-lab.sh" deploy

echo
echo 'Build and provisioning complete. Start the fixed 100-client baseline with:'
echo '  sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=100 PRPL_TOPOLOGY=star scripts/radio-lab.sh start'
echo '  sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=100 PRPL_TOPOLOGY=star scripts/radio-lab.sh clients'
echo 'The room service selects 20 online clients by default after baseline acceptance.'
