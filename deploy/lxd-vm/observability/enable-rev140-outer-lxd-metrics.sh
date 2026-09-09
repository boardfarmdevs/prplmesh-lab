#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
[[ $(hostname -s) == rev140 ]] || { echo 'Run this preset on rev140' >&2; exit 1; }
exec bash "$source_dir/enable-outer-metrics.sh" \
    rdkeasymesh-20-0907 192.168.2.140 rev140 rev140-rdk-0907
