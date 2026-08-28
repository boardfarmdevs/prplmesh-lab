#!/bin/bash
set -euo pipefail

: "${PRPL_RELEASE:?}"
: "${PRPL_COMMIT:?}"
: "${BWL_TYPE:?}"

export DEBIAN_FRONTEND=noninteractive
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

if [ ! -d /opt/prplMesh/.git ]; then
    git clone https://gitlab.com/prpl-foundation/prplmesh/prplMesh.git /opt/prplMesh
fi
git -C /opt/prplMesh fetch --tags origin
git -C /opt/prplMesh checkout --detach "$PRPL_COMMIT"
git -C /opt/prplMesh reset --hard "$PRPL_COMMIT"
test "$(git -C /opt/prplMesh rev-parse HEAD)" = "$PRPL_COMMIT"
for patch_file in /root/prplmesh-patches/*.patch; do
    git -C /opt/prplMesh apply --check "$patch_file"
    git -C /opt/prplMesh apply "$patch_file"
done

mkdir -p /opt/prpl-deps
if [ ! -d /opt/prpl-deps/libubox/.git ]; then
    git clone https://git.openwrt.org/project/libubox.git /opt/prpl-deps/libubox
fi
git -C /opt/prpl-deps/libubox checkout 9e52171d70def760a6949676800d0b73f85ee22d
cmake -S /opt/prpl-deps/libubox -B /opt/prpl-deps/libubox/build \
    -DCMAKE_INSTALL_PREFIX=/usr
cmake --build /opt/prpl-deps/libubox/build --parallel
cmake --install /opt/prpl-deps/libubox/build

if [ ! -d /opt/prpl-deps/ubus/.git ]; then
    git clone https://git.openwrt.org/project/ubus.git /opt/prpl-deps/ubus
fi
git -C /opt/prpl-deps/ubus reset --hard 13a4438b4ebdf85d301999e0a615640ac4c9b0a8
if ! git -C /opt/prpl-deps/ubus apply --check \
    /opt/prplMesh/tools/docker/builder/ubuntu/bionic/ubus/0001-ubusd-convert-tx_queue-to-linked-list.patch 2>/dev/null
then
    echo "ubus patch does not apply cleanly" >&2
    exit 1
fi
git -C /opt/prpl-deps/ubus apply \
    /opt/prplMesh/tools/docker/builder/ubuntu/bionic/ubus/0001-ubusd-convert-tx_queue-to-linked-list.patch
cmake -S /opt/prpl-deps/ubus -B /opt/prpl-deps/ubus/build \
    -DCMAKE_INSTALL_PREFIX=/usr
cmake --build /opt/prpl-deps/ubus/build --parallel
cmake --install /opt/prpl-deps/ubus/build
ldconfig

if [ ! -d /opt/prpl-deps/ambiorix/.repo ]; then
    mkdir -p /opt/prpl-deps/ambiorix
    cd /opt/prpl-deps/ambiorix
    repo init -u https://gitlab.com/prpl-foundation/components/ambiorix/ambiorix.git \
        -b refs/tags/v7.1.0 </dev/null
    repo sync
fi
cd /opt/prpl-deps/ambiorix
for component in \
    libraries/libamxc libraries/libamxp libraries/libamxd libraries/libamxb \
    libraries/libamxs libraries/libamxo libraries/libamxj libraries/libamxrt \
    applications/amxb-inspect applications/amxo-cg applications/amxo-xml-to \
    bus_adaptors/amxb_ubus
do
    make -C "$component"
    make install -C "$component"
done

if [ ! -d /opt/prpl-deps/mod-dmext/.git ]; then
    git clone --branch v0.11.12 \
        https://gitlab.com/prpl-foundation/components/core/modules/mod-dmext.git \
        /opt/prpl-deps/mod-dmext
fi
make -C /opt/prpl-deps/mod-dmext
make install -C /opt/prpl-deps/mod-dmext
ldconfig

if [ "$BWL_TYPE" = NL80211 ] && \
   [ ! -d /opt/prpl-deps/hostapd-src/hostapd-2.10/.git ]; then
    mkdir -p /opt/prpl-deps/hostapd-src
    git clone --branch hostap_2_10 --depth 1 https://git.w1.fi/hostap.git \
        /opt/prpl-deps/hostapd-src/hostapd-2.10
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
