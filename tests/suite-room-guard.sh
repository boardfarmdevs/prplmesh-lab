#!/usr/bin/env bash
set -euo pipefail

state=/run/prplmesh-suite-room-guard
dropin=/run/systemd/system/prplmesh-room-demo.service.d/90-suite-guard.conf

case ${1:-} in
acquire)
    mkdir -m 0700 "$state" || {
        echo "Another suite owns $state; restore that suite before retrying." >&2
        exit 75
    }
    if [ -e "$dropin" ]; then
        rmdir "$state"
        echo "Unexpected existing guard: $dropin" >&2
        exit 75
    fi
    trap 'status=$?; if ((status)); then rm -f "$dropin"; rmdir "$state"; systemctl daemon-reload; fi; exit "$status"' EXIT
    mkdir -p "$(dirname "$dropin")"
    printf '[Unit]\nConditionPathExists=!%s\n' "$state" > "$dropin"
    systemctl daemon-reload
    ;;
release)
    test -d "$state"
    rm -f "$dropin"
    systemctl daemon-reload
    rmdir "$state"
    ;;
*)
    echo 'usage: suite-room-guard.sh acquire|release (inside the VM, as root)' >&2
    exit 2
    ;;
esac
