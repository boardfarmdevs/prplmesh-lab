#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SERVICE_USER=${PRPL_UI_USER:-${SUDO_USER:-$USER}}
UNIT=/etc/systemd/system/prplmesh-controller-ui.service

cd "$ROOT/controller-ui"
mkdir -p bin
go test ./...
go build -o bin/easymesh-controller ./cmd/easymesh-controller

sed \
    -e "s#@PROJECT_ROOT@#$ROOT#g" \
    -e "s#@SERVICE_USER@#$SERVICE_USER#g" \
    systemd/prplmesh-controller-ui.service | sudo tee "$UNIT" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now prplmesh-controller-ui.service
curl -fsS http://127.0.0.1:8091/health
