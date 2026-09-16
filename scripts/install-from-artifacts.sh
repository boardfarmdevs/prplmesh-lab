#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE_ALIAS=${PRPL_BASE_IMAGE_ALIAS:-prpl-ubuntu-22.04-base}
MODE=${1:-}
case "$MODE" in
    ''|--prepare-only) [ "$#" -le 1 ] || exit 2 ;;
    *) echo "usage: $0 [--prepare-only]" >&2; exit 2 ;;
esac

"$ROOT/scripts/preflight.sh"
(cd "$ROOT/artifacts" && sha256sum -c SHA256SUMS)

if ! lxc image info "$BASE_ALIAS" >/dev/null 2>&1; then
    # Ubuntu release images remain available from Canonical's `ubuntu:`
    # remote even when the general-purpose `images:` catalog has retired an
    # older distribution entry.  Pin the architecture so a clean nested-LXD
    # appliance build resolves the same container image on every x86 host.
    lxc image copy ubuntu:22.04/amd64 local: --alias "$BASE_ALIAS"
fi

if [ ! -x "$ROOT/build/bin/wmediumd" ]; then
    "$ROOT/scripts/build-wmediumd.sh"
fi
SOURCE_IMAGE=$BASE_ALIAS "$ROOT/scripts/build-runtime-image.sh"

sudo env INSTALL_MODULE=1 "$ROOT/scripts/build-hwsim.sh"
sudo depmod -a "$(uname -r)"
if [ "$MODE" = --prepare-only ]; then
    echo 'Runtime image and radio modules installed; reboot before provisioning the radio pool.'
    exit 0
fi
sudo "$ROOT/scripts/radio-lab.sh" radio-pool
sudo "$ROOT/scripts/radio-lab.sh" deploy

echo 'Runtime artifacts installed and the fixed inventory is provisioned.'
echo 'Start it with deploy/guest/prplmesh-lab-start start.'
