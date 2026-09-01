#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-lxd-device.XXXXXX)
trap 'find "$work" -depth -delete' EXIT

cat > "$work/lxc" <<'EOF'
#!/bin/bash
set -euo pipefail
if [ "$*" = "config device show test-vm" ]; then
    [ "${MOCK_LOCAL_DEVICE:-}" = yes ] && printf 'root:\n  path: /\n  type: disk\n'
    exit 0
fi
printf '%s\n' "$*" >> "$MOCK_LXC_LOG"
EOF
chmod +x "$work/lxc"

export PATH="$work:$PATH"
export MOCK_LXC_LOG="$work/lxc.log"
# shellcheck source=../deploy/lxd-vm/device-property.sh
source "$ROOT/deploy/lxd-vm/device-property.sh"

MOCK_LOCAL_DEVICE=yes lxd_set_device_property test-vm root size 80GiB
grep -Fxq 'config device set test-vm root size 80GiB' "$MOCK_LXC_LOG"

: > "$MOCK_LXC_LOG"
MOCK_LOCAL_DEVICE=no lxd_set_device_property test-vm eth0 network lxdbr0
grep -Fxq 'config device override test-vm eth0 network=lxdbr0' "$MOCK_LXC_LOG"

echo 'PASS: LXD local and inherited devices use the correct mutation command'
