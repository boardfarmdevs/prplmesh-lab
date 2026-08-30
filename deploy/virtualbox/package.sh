#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUTPUT_DIR=${1:-$ROOT/release/0829}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
OUTPUT="$OUTPUT_DIR/prplmesh-lab-0829-${SHORT}-virtualbox.box"

mkdir -p "$OUTPUT_DIR"
vagrant halt
rm -f "$OUTPUT" "$OUTPUT.sha256"
vagrant package --output "$OUTPUT"
(cd "$OUTPUT_DIR" && sha256sum "$(basename "$OUTPUT")" > "$(basename "$OUTPUT").sha256")
echo "$OUTPUT"
