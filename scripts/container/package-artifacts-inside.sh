#!/bin/bash
set -euo pipefail

: "${PRPL_RELEASE:?}"
: "${HOSTAP_COMMIT:?}"

install_dir="/opt/prpl-install-nl80211"
test -x "$install_dir/bin/beerocks_controller"
test -x /root/build-hostap-inside.sh

HOSTAP_COMMIT="$HOSTAP_COMMIT" /root/build-hostap-inside.sh
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
