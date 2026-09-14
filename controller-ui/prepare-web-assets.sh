#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
sha256sum -c web-vendor.tar.gz.sha256
tar --no-same-owner -xzf web-vendor.tar.gz -C web/static
(cd web/static; sha256sum -c vendor/SHA256SUMS)
