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
# only requires the HTTP service to answer; runtime acceptance later requires
# the fully healthy response after the mesh is online.
curl -sS http://127.0.0.1:8091/health
