#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTPUT_DIR=${1:-$ROOT/release/0828}
SHORT=$(git -C "$ROOT" rev-parse --short=7 HEAD)
NAME=prplmesh-lab-0828-${SHORT}
OUTPUT="$OUTPUT_DIR/${NAME}-source.tar.bz2"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ] || {
    echo 'tracked worktree changes must be committed before packaging' >&2
    exit 1
}
(cd "$ROOT/artifacts" && sha256sum -c SHA256SUMS)

mkdir -p "$OUTPUT_DIR" "$STAGE/$NAME"
git -C "$ROOT" archive HEAD | tar -C "$STAGE/$NAME" -xf -
mkdir -p "$STAGE/$NAME/artifacts"
cp "$ROOT"/artifacts/*.tar.gz "$ROOT/artifacts/SHA256SUMS" \
    "$STAGE/$NAME/artifacts/"
if [ -x "$ROOT/build/bin/wmediumd" ]; then
    mkdir -p "$STAGE/$NAME/build/bin"
    cp "$ROOT/build/bin/wmediumd" "$STAGE/$NAME/build/bin/"
fi
printf 'release=0828\ncommit=%s\ncreated=%s\n' \
    "$(git -C "$ROOT" rev-parse HEAD)" "$(date -u +%FT%TZ)" \
    > "$STAGE/$NAME/RELEASE"

rm -f "$OUTPUT" "$OUTPUT.sha256"
tar -C "$STAGE" -cjf "$OUTPUT" "$NAME"
(cd "$OUTPUT_DIR" && sha256sum "$(basename "$OUTPUT")" > "$(basename "$OUTPUT").sha256")
echo "$OUTPUT"
