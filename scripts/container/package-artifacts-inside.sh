#!/bin/bash
set -euo pipefail

: "${PRPL_RELEASE:?}"
: "${PRPL_COMMIT:?}"
: "${PRPL_PATCHSET_SHA256:?}"
: "${UBUS_PATCHSET_SHA256:?}"
: "${AMXP_PATCHSET_SHA256:?}"
: "${HOSTAP_COMMIT:?}"

install_dir="/opt/prpl-install-nl80211"
test -x "$install_dir/bin/beerocks_controller"
test -x /root/build-hostap-inside.sh
ubus_provenance=/usr/share/prplmesh-lab/ubus-provenance.env
grep -Fxq "UBUS_COMMIT=13a4438b4ebdf85d301999e0a615640ac4c9b0a8" "$ubus_provenance"
grep -Fxq "UBUS_PATCHSET_SHA256=$UBUS_PATCHSET_SHA256" "$ubus_provenance"
grep -Fxq "UBUS_LIBRARY_SHA256=$(sha256sum /usr/lib/libubus.so | awk '{print $1}')" "$ubus_provenance"
amxp_provenance=/usr/share/prplmesh-lab/amxp-provenance.env
grep -Fxq "AMXP_COMMIT=873b53069855414d35b821fcb46ed0f8ae108b3e" "$amxp_provenance"
grep -Fxq "AMXP_PATCHSET_SHA256=$AMXP_PATCHSET_SHA256" "$amxp_provenance"
grep -Fxq "AMXP_LIBRARY_SHA256=$(sha256sum /usr/lib/x86_64-linux-gnu/libamxp.so.2.0.0 | awk '{print $1}')" "$amxp_provenance"

HOSTAP_COMMIT="$HOSTAP_COMMIT" /root/build-hostap-inside.sh
install -d -m 0755 "$install_dir/share/prplmesh-lab"
printf '%s\n' \
    "PRPL_RELEASE=$PRPL_RELEASE" \
    "PRPL_COMMIT=$PRPL_COMMIT" \
    "PRPL_PATCHSET_SHA256=$PRPL_PATCHSET_SHA256" \
    > "$install_dir/share/prplmesh-lab/provenance.env"
tar -C /opt -czf "/tmp/prpl-install-nl80211-${PRPL_RELEASE}.tar.gz" \
    prpl-install-nl80211

mapfile -t runtime_files < <(
    find /usr/lib/x86_64-linux-gnu -maxdepth 1 \
        \( -name 'libamx*.so*' \) -printf '%P\n' | \
        sed 's#^#usr/lib/x86_64-linux-gnu/#'
    find /usr/lib -maxdepth 1 \
        \( -name 'libubox.so*' -o -name 'libubus.so*' \
           -o -name 'libblobmsg_json.so*' \) -printf '%P\n' | \
        sed 's#^#usr/lib/#'
    printf '%s\n' \
        usr/lib/amx/modules/mod-dmext.so \
        usr/bin/mods/amxb/mod-amxb-ubus.so \
        usr/bin/amxb-inspect \
        usr/bin/ubus \
        usr/sbin/ubusd \
        etc/acl/admin/prplmesh.json
    printf '%s\n' usr/share/prplmesh-lab/ubus-provenance.env
    printf '%s\n' usr/share/prplmesh-lab/amxp-provenance.env
)

for path in "${runtime_files[@]}"; do
    test -e "/$path" || {
        echo "missing runtime artifact: /$path" >&2
        exit 1
    }
done
tar -C / -czf "/tmp/prpl-runtime-deps-${PRPL_RELEASE}.tar.gz" \
    "${runtime_files[@]}"

sha256sum \
    /tmp/hostap-runtime-2.10.tar.gz \
    "/tmp/prpl-install-nl80211-${PRPL_RELEASE}.tar.gz" \
    "/tmp/prpl-runtime-deps-${PRPL_RELEASE}.tar.gz"
