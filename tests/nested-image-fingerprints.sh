#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-image-fingerprint.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
fingerprint=38bb5b45aaaa252ba0cc5f8598bdfafe4ccd69229d20eabd569d1c03fefd2f47

cat > "$work/lxc" <<SH
#!/bin/bash
set -euo pipefail
case "\$*" in
    'image list --format csv -c f') printf '%.12s\\n' '$fingerprint' ;;
    'image list --format json')
        printf '[{"fingerprint":"%s"}]\\n' '$fingerprint'
        ;;
    *) echo "unexpected fake lxc invocation: \$*" >&2; exit 2 ;;
esac
SH
chmod 755 "$work/lxc"

short=$("$work/lxc" image list --format csv -c f)
full=$("$work/lxc" image list --format json | jq -r '.[].fingerprint')
test "${#short}" -eq 12
test "${#full}" -eq 64
test "$short" != "$full"
test "$full" = "$fingerprint"

deleted=0
while IFS= read -r image; do
    [ "$image" = "$fingerprint" ] || deleted=$((deleted + 1))
done < <("$work/lxc" image list --format json | jq -r '.[].fingerprint')
test "$deleted" -eq 0

for script in \
    deploy/guest/prepare-thin-image.sh \
    deploy/lxd-vm/package-cleanup.sh; do
    grep -Fq "image list --format json" "$ROOT/$script"
    grep -Fq "jq -r '.[].fingerprint'" "$ROOT/$script"
    if grep -Fq 'image list --format csv -c f' "$ROOT/$script"; then
        echo "$script compares abbreviated image fingerprints" >&2
        exit 1
    fi
done

echo 'PASS: thin image retention compares full fingerprints'
