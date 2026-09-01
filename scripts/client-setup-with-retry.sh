#!/bin/bash
set -euo pipefail

name=${1:?client container name}
ordinal=${2:?client cohort ordinal}
cohort=${3:?private or iot}
band=${4:?2.4, 5, or 6}
delay=${PRPLMESH_CLIENT_SETUP_RETRY_DELAY:-1}

case "$delay" in
    ''|*[!0-9]*) echo "retry delay must be a non-negative integer" >&2; exit 2 ;;
esac

for attempt in 1 2; do
    if lxc exec "$name" -- /mnt/project/scripts/container/setup-client.sh \
            "$ordinal" "$cohort" "$band"; then
        exit 0
    fi
    if [ "$attempt" -eq 1 ]; then
        echo "$name wireless setup failed; retrying full setup once" >&2
        sleep "$delay"
    fi
done

echo "$name wireless setup failed after 2 attempts" >&2
exit 1
