#!/bin/bash
set -euo pipefail
source=${1:?patched prplMesh source directory required}
build=${2:?prplMesh build directory required}
here=$(cd "$(dirname "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
read -r -a netlink_flags <<< "$(pkg-config --cflags --libs libnl-genl-3.0 libnl-3.0)"
g++ -std=c++17 -Wall -Wextra -Werror -Wno-unused-parameter \
    -pthread -DELPP_THREAD_SAFE -DELPP_FORCE_USE_STD_THREAD -DELPP_NO_DEFAULT_LOG_FILE \
    -DELPP_LOG_UNORDERED_MAP -DELPP_LOG_UNORDERED_SET -DELPP_STL_LOGGING -DELPP_SYSLOG \
    -I"$source/common/beerocks/bwl/shared" \
    -I"$source/framework/external/easylogging" \
    "$here/prpl-netlink-recovery.cpp" "$source/common/beerocks/bwl/shared/netlink_socket.cpp" \
    -L"$build/out/lib" -Wl,-rpath,"$build/out/lib" -lelpp \
    -Wl,--wrap=nl_recvmsgs -Wl,--wrap=nl_send_auto_complete \
    "${netlink_flags[@]}" -o "$temporary/netlink-recovery"
"$temporary/netlink-recovery"
