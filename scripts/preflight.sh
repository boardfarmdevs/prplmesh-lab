#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=../manifests/lab.env
source "$ROOT/manifests/lab.env"

fail=0
check()
{
    if "$@" >/dev/null 2>&1; then
        printf 'PASS  %s\n' "$*"
    else
        printf 'FAIL  %s\n' "$*" >&2
        fail=1
    fi
}

. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 24.04 ] || {
    echo "FAIL  Ubuntu 24.04 is required" >&2
    fail=1
}
case "$(uname -r)" in
    7.0.*) echo "PASS  Linux $(uname -r)" ;;
    *) echo "FAIL  Linux 7.0 is required; running $(uname -r)" >&2; fail=1 ;;
esac

for command in git lxc iw jq make meson ninja python3 sha256sum; do
    check command -v "$command"
done
check test -d "/lib/modules/$(uname -r)/build"
check lxc info
check test -r "$ROOT/patches/hwsim/0001-mac80211_hwsim-allow-multichannel-wmediumd.patch"
check test -r "$ROOT/patches/wmediumd/0001-wmediumd-multichannel-per-freq-interference.patch"
check test -r "$ROOT/patches/prplmesh/0001-linux-map-third-radio-interface.patch"

if ! grep -Rqs '^Types:.*deb-src' /etc/apt/sources.list.d /etc/apt/sources.list 2>/dev/null; then
    echo 'FAIL  Ubuntu deb-src entries are required by build-hwsim.sh' >&2
    fail=1
else
    echo 'PASS  Ubuntu source repositories are enabled'
fi

exit "$fail"
