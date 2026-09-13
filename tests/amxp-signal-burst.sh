#!/bin/bash
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
binary=$(mktemp /tmp/amxp-signal-burst.XXXXXX)
trap 'rm -f "$binary"' EXIT
gcc -std=c11 -Wall -Wextra -Werror "$source_dir/amxp-signal-burst.c" \
    -lamxp -lamxc -pthread -o "$binary"
timeout 15 "$binary"
