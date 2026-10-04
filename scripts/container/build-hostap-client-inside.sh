#!/bin/sh
# The clients' wpa_supplicant and wpa_cli: hostap at the lab's pinned commit with its patch
# series, configured as build-hostap-inside.sh configures them, built in an Alpine container
# for the Alpine client image (musl). Runs inside that container.
set -eu

: "${HOSTAP_COMMIT:?}"
apk add --no-cache bash build-base git libnl3-dev linux-headers openssl-dev >/dev/null
source_dir=/root/hostap
if [ ! -d "$source_dir/.git" ]; then
    git clone -q https://w1.fi/hostap.git "$source_dir" ||
        git clone -q https://chromium.googlesource.com/external/w1.fi/cgit/hostap/ "$source_dir"
fi
git -C "$source_dir" clean -q -fdx
git -C "$source_dir" checkout -q --detach "$HOSTAP_COMMIT"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$HOSTAP_COMMIT"
for patch_file in /root/hostap-patches/*.patch; do
    git -C "$source_dir" apply --check "$patch_file"
    git -C "$source_dir" apply "$patch_file"
done

cp "$source_dir/wpa_supplicant/defconfig" "$source_dir/wpa_supplicant/.config"
sed -i \
    -e 's/^#CONFIG_WNM=y/CONFIG_WNM=y/' \
    -e 's/^#CONFIG_MBO=y/CONFIG_MBO=y/' \
    -e 's/^CONFIG_CTRL_IFACE_DBUS_NEW=y/#CONFIG_CTRL_IFACE_DBUS_NEW=y/' \
    -e 's/^CONFIG_CTRL_IFACE_DBUS_INTRO=y/#CONFIG_CTRL_IFACE_DBUS_INTRO=y/' \
    "$source_dir/wpa_supplicant/.config"
make -s -C "$source_dir/wpa_supplicant" -j"$(nproc)" wpa_supplicant wpa_cli

staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
install -D -m 0755 "$source_dir/wpa_supplicant/wpa_supplicant" "$staging/sbin/wpa_supplicant"
install -D -m 0755 "$source_dir/wpa_supplicant/wpa_cli" "$staging/bin/wpa_cli"
{
    printf 'HOSTAP_COMMIT=%s\n' "$HOSTAP_COMMIT"
    printf 'HOSTAP_PATCHSET_SHA256=%s\n' "$(cat /root/hostap-patches/*.patch | sha256sum | cut -d' ' -f1)"
    printf 'ALPINE=%s\n' "$(cat /etc/alpine-release)"
    printf 'BUILT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$staging/hostap-client.provenance.env"
"$staging/sbin/wpa_supplicant" -v | head -1
tar -C "$staging" -czf /tmp/hostap-client-2.10-alpine.tar.gz .
