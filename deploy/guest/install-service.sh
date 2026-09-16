#!/bin/bash
set -euo pipefail

SOURCE=${1:-/opt/prplmesh-lab}
TARGET=${PRPLMESH_ROOT:-/opt/prplmesh-lab}

[ "$(id -u)" -eq 0 ] || {
    echo "run as root: sudo $0 [repository]" >&2
    exit 1
}
[ -x "$SOURCE/scripts/radio-lab.sh" ] || {
    echo "not a prplMesh lab repository: $SOURCE" >&2
    exit 1
}

if [ "$SOURCE" != "$TARGET" ]; then
    install -d -m 0755 "$TARGET"
    tar -C "$SOURCE" --exclude=.git -cf - . | tar -C "$TARGET" -xf -
fi

install -m 0755 "$TARGET/deploy/guest/prplmesh-lab-start" \
    /usr/local/sbin/prplmesh-lab-start
install -m 0644 "$TARGET/deploy/guest/prplmesh-lab.service" \
    /etc/systemd/system/prplmesh-lab.service
install -m 0644 "$TARGET/deploy/guest/prplmesh-room-demo.service" \
    /etc/systemd/system/prplmesh-room-demo.service

PRPL_UI_USER=root "$TARGET/controller-ui/install.sh"
"$TARGET/wmediumd/observer/install-prplmesh.sh"
"$TARGET/wmediumd/install-survey-bridge.sh" /run/prpl-wmediumd/metrics.sock prplmesh-lab.service
bash "$TARGET/wmediumd/install-control-priority.sh" prplmesh
systemctl daemon-reload
systemctl enable prplmesh-lab.service
systemctl enable prplmesh-room-demo.service
echo 'Installed prplmesh-lab.service; it will start automatically on the next boot.'
