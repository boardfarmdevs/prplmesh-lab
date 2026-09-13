#!/bin/bash
set -euo pipefail

: "${PRPL_RELEASE:?}"
: "${PRPL_COMMIT:?}"
: "${HOSTAP_COMMIT:?}"
: "${BWL_TYPE:?}"

export DEBIAN_FRONTEND=noninteractive

retry()
{
    local attempt
    for attempt in 1 2 3; do
        if "$@"; then
            return 0
        fi
        if [ "$attempt" -eq 3 ]; then
            return 1
        fi
        echo "network operation failed; retrying ($attempt/3): $*" >&2
        sleep $((attempt * 5))
    done
}

clone_retry()
{
    local url=$1 directory=$2 attempt
    shift 2

    if [ -d "$directory/.git" ] &&
       git -C "$directory" rev-parse --verify HEAD >/dev/null 2>&1 &&
       git -C "$directory" fsck --connectivity-only >/dev/null 2>&1; then
        return 0
    fi

    for attempt in 1 2 3; do
        rm -rf "$directory"
        if git clone "$@" "$url" "$directory"; then
            return 0
        fi
        if [ "$attempt" -eq 3 ]; then
            return 1
        fi
        echo "clone failed; retrying ($attempt/3): $url" >&2
        sleep $((attempt * 5))
    done
}

apt-get update
apt-get install -y \
    bison bridge-utils build-essential ca-certificates clang-format cmake curl \
    ebtables fakeroot flex g++ gcc gdb git gpg iperf3 iproute2 \
    iputils-ping libcap-ng-dev libevent-dev libjson-c-dev liblua5.1-0-dev \
    libncurses-dev libnl-3-dev libnl-genl-3-dev libnl-route-3-dev libssl-dev \
    liburiparser-dev libxml2-dev libxslt1-dev libyajl-dev lua5.1 \
    net-tools ninja-build pkg-config psmisc python3 python3-pytest \
    python3-yaml uuid-runtime wget

if [ ! -x /usr/local/bin/repo ]; then
    curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo \
        -o /usr/local/bin/repo
    chmod 0755 /usr/local/bin/repo
fi

clone_retry https://gitlab.com/prpl-foundation/prplmesh/prplMesh.git /opt/prplMesh
retry git -C /opt/prplMesh fetch --tags origin
git -C /opt/prplMesh checkout --detach "$PRPL_COMMIT"
git -C /opt/prplMesh reset --hard "$PRPL_COMMIT"
test "$(git -C /opt/prplMesh rev-parse HEAD)" = "$PRPL_COMMIT"
for patch_file in /root/prplmesh-patches/*.patch; do
    git -C /opt/prplMesh apply --check "$patch_file"
    git -C /opt/prplMesh apply "$patch_file"
done

mkdir -p /opt/prpl-deps
clone_retry https://git.openwrt.org/project/libubox.git /opt/prpl-deps/libubox
git -C /opt/prpl-deps/libubox checkout 9e52171d70def760a6949676800d0b73f85ee22d
cmake -S /opt/prpl-deps/libubox -B /opt/prpl-deps/libubox/build \
    -DCMAKE_INSTALL_PREFIX=/usr
cmake --build /opt/prpl-deps/libubox/build --parallel
cmake --install /opt/prpl-deps/libubox/build

clone_retry https://git.openwrt.org/project/ubus.git /opt/prpl-deps/ubus
git -C /opt/prpl-deps/ubus reset --hard 13a4438b4ebdf85d301999e0a615640ac4c9b0a8
if ! git -C /opt/prpl-deps/ubus apply --check \
    /opt/prplMesh/tools/docker/builder/ubuntu/bionic/ubus/0001-ubusd-convert-tx_queue-to-linked-list.patch 2>/dev/null
then
    echo "ubus patch does not apply cleanly" >&2
    exit 1
fi
git -C /opt/prpl-deps/ubus apply \
    /opt/prplMesh/tools/docker/builder/ubuntu/bionic/ubus/0001-ubusd-convert-tx_queue-to-linked-list.patch
for patch_file in /root/ubus-patches/*.patch; do
    git -C /opt/prpl-deps/ubus apply --check "$patch_file"
    git -C /opt/prpl-deps/ubus apply "$patch_file"
done
cmake -S /opt/prpl-deps/ubus -B /opt/prpl-deps/ubus/build \
    -DCMAKE_INSTALL_PREFIX=/usr
cmake --build /opt/prpl-deps/ubus/build --parallel
cmake --install /opt/prpl-deps/ubus/build
install -d -m 0755 /usr/share/prplmesh-lab
ubus_patchset=$(
    cd /root
    sha256sum ubus-patches/*.patch | sed 's#  ubus-patches/#  patches/ubus/#' | sha256sum | awk '{print $1}'
)
printf '%s\n' \
    "UBUS_COMMIT=$(git -C /opt/prpl-deps/ubus rev-parse HEAD)" \
    "UBUS_PATCHSET_SHA256=$ubus_patchset" \
    "UBUS_LIBRARY_SHA256=$(sha256sum /usr/lib/libubus.so | awk '{print $1}')" \
    > /usr/share/prplmesh-lab/ubus-provenance.env
ldconfig

if [ ! -d /opt/prpl-deps/ambiorix/.repo ]; then
    mkdir -p /opt/prpl-deps/ambiorix
    cd /opt/prpl-deps/ambiorix
    retry repo init -u https://gitlab.com/prpl-foundation/components/ambiorix/ambiorix.git \
        -b refs/tags/v7.1.0 </dev/null
fi
cd /opt/prpl-deps/ambiorix
retry repo sync
for component in \
    libraries/libamxc libraries/libamxp libraries/libamxd libraries/libamxb \
    libraries/libamxs libraries/libamxo libraries/libamxj libraries/libamxrt \
    applications/amxb-inspect applications/amxo-cg applications/amxo-xml-to \
    bus_adaptors/amxb_ubus
do
    make -C "$component"
    make install -C "$component"
done

clone_retry \
    https://gitlab.com/prpl-foundation/components/core/modules/mod-dmext.git \
    /opt/prpl-deps/mod-dmext --branch v0.11.12
make -C /opt/prpl-deps/mod-dmext
make install -C /opt/prpl-deps/mod-dmext
ldconfig

if [ "$BWL_TYPE" = NL80211 ] && \
   [ ! -d /opt/prpl-deps/hostapd-src/hostapd-2.10/.git ]; then
    mkdir -p /opt/prpl-deps/hostapd-src
    clone_retry https://w1.fi/hostap.git \
        /opt/prpl-deps/hostapd-src/hostapd-2.10 || \
    clone_retry https://chromium.googlesource.com/external/w1.fi/cgit/hostap/ \
        /opt/prpl-deps/hostapd-src/hostapd-2.10
fi
if [ "$BWL_TYPE" = NL80211 ]; then
    retry git -C /opt/prpl-deps/hostapd-src/hostapd-2.10 \
        fetch origin "$HOSTAP_COMMIT"
    git -C /opt/prpl-deps/hostapd-src/hostapd-2.10 checkout --detach "$HOSTAP_COMMIT"
    test "$(git -C /opt/prpl-deps/hostapd-src/hostapd-2.10 rev-parse HEAD)" = \
        "$HOSTAP_COMMIT"
fi

lower=$(printf '%s' "$BWL_TYPE" | tr '[:upper:]' '[:lower:]')
build="/opt/prpl-build-$lower"
install="/opt/prpl-install-$lower"
rm -rf "$build" "$install"
cmake -S /opt/prplMesh -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_INSTALL_PREFIX="$install" \
    -DBUILD_TESTS=OFF -DENABLE_NBAPI=ON -DUSE_PRPLMESH_WHM=OFF \
    -DBWL_TYPE="$BWL_TYPE" -DPLATFORM_BUILD_DIR=/opt/prpl-deps
cmake --build "$build" --parallel
cmake --install "$build"
echo "Built prplMesh $PRPL_RELEASE ($PRPL_COMMIT), BWL=$BWL_TYPE at $install"
