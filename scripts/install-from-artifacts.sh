#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE_ALIAS=${PRPL_BASE_IMAGE_ALIAS:-prpl-ubuntu-22.04-base}

"$ROOT/scripts/preflight.sh"
(cd "$ROOT/artifacts" && sha256sum -c SHA256SUMS)

if ! lxc image info "$BASE_ALIAS" >/dev/null 2>&1; then
    lxc image copy images:ubuntu/22.04 local: --alias "$BASE_ALIAS"
fi

if [ ! -x "$ROOT/build/bin/wmediumd" ]; then
    "$ROOT/scripts/build-wmediumd.sh"
fi
SOURCE_IMAGE=$BASE_ALIAS "$ROOT/scripts/build-runtime-image.sh"

sudo env INSTALL_MODULE=1 "$ROOT/scripts/build-hwsim.sh"
sudo depmod -a "$(uname -r)"
sudo "$ROOT/scripts/radio-lab.sh" radio-pool
sudo "$ROOT/scripts/radio-lab.sh" deploy

echo 'Runtime artifacts installed and the fixed inventory is provisioned.'
echo 'Start it with deploy/guest/prplmesh-lab-start start.'
