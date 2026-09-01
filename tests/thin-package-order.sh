#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
script=$ROOT/deploy/lxd-vm/package-thin.sh

first_line()
{
    local pattern=$1
    grep -nF "$pattern" "$script" | head -n 1 | cut -d: -f1
}

swap_line=$(first_line 'lxc file push "$SOURCE_BUNDLE"')
verify_line=$(first_line 'rev-parse HEAD)" = "$SOURCE_COMMIT"')
start_line=$(first_line 'systemctl start prplmesh-lab.service')
check_line=$(first_line '"$ROOT/deploy/lxd-vm/build.sh" check')
prepare_line=$(first_line 'prepare-thin-image.sh')

for value in "$swap_line" "$verify_line" "$start_line" "$check_line" \
    "$prepare_line"; do
    case "$value" in
        ''|*[!0-9]*) echo 'missing thin package ordering marker' >&2; exit 1 ;;
    esac
done

[ "$swap_line" -lt "$verify_line" ]
[ "$verify_line" -lt "$start_line" ]
[ "$start_line" -lt "$check_line" ]
[ "$check_line" -lt "$prepare_line" ]
test "$(grep -cF '"$ROOT/deploy/lxd-vm/build.sh" check' "$script")" -eq 1

python3 - "$script" <<'PY'
import sys

text = open(sys.argv[1], encoding="utf-8").read()
check = text.index('"$ROOT/deploy/lxd-vm/build.sh" check')
prepare = text.index('prepare-thin-image.sh')
swap = text.index('lxc file push "$SOURCE_BUNDLE"')
verify = text.index('rev-parse HEAD)" = "$SOURCE_COMMIT"')
assert swap < verify < check < prepare
assert 'systemctl start prplmesh-lab.service' in text[verify:check]
PY

echo 'PASS: thin packaging validates staged source before roster removal'
