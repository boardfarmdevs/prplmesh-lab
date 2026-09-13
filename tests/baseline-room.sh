#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
eval "$(sed -n '/^check_vm() (/,/^)/p' "$ROOT/deploy/lxd-vm/build.sh")"
CLIENTS=100
RADIOS=120
start_vm() { return 0; }
run() {
    printf '%s\n' "$*" >> "$work/calls"
    case "$*" in
        'systemctl show prplmesh-room-demo.service -p ActiveState --value') echo "$room_state" ;;
        'systemctl stop prplmesh-room-demo.service') return "$stop_status" ;;
        'systemctl start prplmesh-room-demo.service') return 0 ;;
        *'/tests/run-acceptance.sh') return "$audit_status" ;;
        'bash -c '*) echo 'client target' ;;
        *'/tests/optimizer-dynamic.sh recommend client target') return 0 ;;
        *) return 99 ;;
    esac
}
stop_status=0
for room_state in active activating inactive; do
    for audit_status in 0 19; do
        : > "$work/calls"
        result=0
        check_vm || result=$?
        test "$result" = "$audit_status"
        grep -Fq 'systemctl stop prplmesh-room-demo.service' "$work/calls"
        if [ "$room_state" != inactive ]; then
            test "$(tail -1 "$work/calls")" = 'systemctl start prplmesh-room-demo.service'
        else
            ! grep -Fq 'systemctl start prplmesh-room-demo.service' "$work/calls"
        fi
        if [ "$audit_status" != 0 ]; then
            ! grep -Fq '/tests/optimizer-dynamic.sh' "$work/calls"
        fi
    done
done
room_state=active
stop_status=7
audit_status=0
: > "$work/calls"
result=0
check_vm || result=$?
test "$result" = 7
! grep -Fq '/tests/run-acceptance.sh' "$work/calls"
echo 'PASS: baseline audits suspend room RF ownership and restore it on success/failure'
