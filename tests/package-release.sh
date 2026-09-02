#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-package-release.XXXXXX)
trap 'find "$work" -depth -delete' EXIT
bundle="$work/prplmesh-test-lxd"
output="$work/prplmesh-test-lxd-bundle.tar"
mkdir -p "$bundle"
printf '{}\n' > "$bundle/release.json"
printf 'payload\n' > "$bundle/payload.txt"
(
    cd "$bundle"
    sha256sum release.json payload.txt > SHA256SUMS
)

"$ROOT/deploy/lxd-vm/package-release.sh" "$bundle" "$output" >/dev/null
(
    cd "$work"
    sha256sum -c "$(basename "$output").sha256"
)
test "$(awk '{print $2}' "$output.sha256")" = "$(basename "$output")"

mv "$bundle" "$work/prplmesh-0831-thin"
"$ROOT/deploy/lxd-vm/package-release.sh" "$work/prplmesh-0831-thin" >/dev/null
test -f "$work/prplmesh-0831-thin.tar"
test -f "$work/prplmesh-0831-thin.tar.sha256"
mv "$work/prplmesh-0831-thin" "$work/prplmesh-0901-thin"
"$ROOT/deploy/lxd-vm/package-release.sh" "$work/prplmesh-0901-thin" >/dev/null
test -f "$work/prplmesh-0901-thin.tar"
test -f "$work/prplmesh-0901-thin.tar.sha256"

echo 'PASS: outer bundle checksum is portable and basename-only'
