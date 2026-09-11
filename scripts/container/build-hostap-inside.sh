#!/bin/bash
set -euo pipefail

source_dir=/opt/prpl-deps/hostapd-src/hostapd-2.10
test -d "$source_dir/.git"
: "${HOSTAP_COMMIT:?}"

git -C "$source_dir" clean -fdx
git -C "$source_dir" reset --hard "$HOSTAP_COMMIT"
git -C "$source_dir" checkout --detach "$HOSTAP_COMMIT"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$HOSTAP_COMMIT"
for patch_file in /root/hostap-patches/*.patch; do
    git -C "$source_dir" apply --check "$patch_file"
    git -C "$source_dir" apply "$patch_file"
done

cp "$source_dir/hostapd/defconfig" "$source_dir/hostapd/.config"
sed -i \
    -e 's/^#CONFIG_WNM=y/CONFIG_WNM=y/' \
    -e 's/^#CONFIG_IEEE80211AC=y/CONFIG_IEEE80211AC=y/' \
    -e 's/^#CONFIG_IEEE80211AX=y/CONFIG_IEEE80211AX=y/' \
    -e 's/^#CONFIG_SAE=y/CONFIG_SAE=y/' \
    -e 's/^#CONFIG_MBO=y/CONFIG_MBO=y/' \
    "$source_dir/hostapd/.config"
grep -qx 'CONFIG_SAE=y' "$source_dir/hostapd/.config" ||
    echo 'CONFIG_SAE=y' >> "$source_dir/hostapd/.config"
make -C "$source_dir/hostapd" -j"$(nproc)"

cp "$source_dir/wpa_supplicant/defconfig" "$source_dir/wpa_supplicant/.config"
sed -i \
    -e 's/^#CONFIG_WNM=y/CONFIG_WNM=y/' \
    -e 's/^#CONFIG_MBO=y/CONFIG_MBO=y/' \
    -e 's/^CONFIG_CTRL_IFACE_DBUS_NEW=y/#CONFIG_CTRL_IFACE_DBUS_NEW=y/' \
    -e 's/^CONFIG_CTRL_IFACE_DBUS_INTRO=y/#CONFIG_CTRL_IFACE_DBUS_INTRO=y/' \
    "$source_dir/wpa_supplicant/.config"
make -C "$source_dir/wpa_supplicant" -j"$(nproc)"

staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
install -D -m 0755 "$source_dir/hostapd/hostapd" "$staging/sbin/hostapd"
install -D -m 0755 "$source_dir/hostapd/hostapd_cli" "$staging/bin/hostapd_cli"
install -D -m 0755 "$source_dir/wpa_supplicant/wpa_supplicant" \
    "$staging/sbin/wpa_supplicant"
install -D -m 0755 "$source_dir/wpa_supplicant/wpa_cli" "$staging/bin/wpa_cli"
tar -C "$staging" -czf /tmp/hostap-runtime-2.10.tar.gz .
