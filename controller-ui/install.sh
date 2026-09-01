#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SERVICE_USER=${PRPL_UI_USER:-${SUDO_USER:-$USER}}
UNIT=/etc/systemd/system/prplmesh-controller-ui.service

cd "$ROOT/controller-ui"
mkdir -p bin
go test -buildvcs=false ./...
# Appliance source archives intentionally omit .git. Disable VCS stamping so
# the same installer works from a checkout, a mounted canonical tree, or the
# self-contained /opt copy embedded in an image.
go build -buildvcs=false -o bin/easymesh-controller ./cmd/easymesh-controller

sed \
    -e "s#@PROJECT_ROOT@#$ROOT#g" \
    -e "s#@SERVICE_USER@#$SERVICE_USER#g" \
    systemd/prplmesh-controller-ui.service | sudo tee "$UNIT" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now prplmesh-controller-ui.service
# A stopped controller makes this endpoint return 503 by design. Installation
# only requires the systemd service to stay active and the HTTP listener to
# answer. Runtime acceptance later requires the fully healthy response after
# the mesh is online. Starting a Type=simple unit does not guarantee that its
# listener has bound yet, so do not race the first connect after enable --now.
ready_response=
for unused in $(seq 1 "${PRPL_UI_READY_ATTEMPTS:-30}"); do
    if sudo systemctl is-active --quiet prplmesh-controller-ui.service; then
        if ready_response=$(curl -sS --max-time 2 \
                http://127.0.0.1:8091/health 2>/dev/null); then
            printf '%s\n' "$ready_response"
            exit 0
        fi
    fi
    sleep 1
done

echo 'prplMesh controller UI did not become ready within the bounded install window' >&2
sudo systemctl status --no-pager prplmesh-controller-ui.service >&2 || true
exit 1
