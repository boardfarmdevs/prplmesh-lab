#!/bin/bash
set -euo pipefail

LXC=${PRPLMESH_LXC_BIN:-lxc}
GRACE_TIMEOUT=${PRPLMESH_STOP_GRACE_TIMEOUT:-5}
WAIT_TIMEOUT=${PRPLMESH_STOP_WAIT_TIMEOUT:-15}
POLL_INTERVAL=${PRPLMESH_STOP_POLL_INTERVAL:-1}

for value in "$GRACE_TIMEOUT" "$WAIT_TIMEOUT" "$POLL_INTERVAL"; do
    case "$value" in
        ''|*[!0-9]*)
            echo "nested stop timeouts must be non-negative integers" >&2
            exit 2
            ;;
    esac
done
[ "$#" -gt 0 ] || exit 0

declare -a pending=()

collect_pending()
{
    local name state
    pending=()
    for name in "$@"; do
        state=$("$LXC" list "^${name}$" -c s --format csv) || {
            echo "cannot read nested instance state: $name" >&2
            exit 1
        }
        [ -n "$state" ] || {
            echo "nested instance is missing: $name" >&2
            exit 1
        }
        [ "$state" = STOPPED ] || pending+=("$name")
    done
}

stop_batch()
{
    local mode=$1 name pid
    shift
    local -a pids=()
    for name in "$@"; do
        case "$mode" in
            graceful)
                "$LXC" stop "$name" --timeout "$GRACE_TIMEOUT" \
                    >/dev/null 2>&1 &
                ;;
            force)
                "$LXC" stop "$name" --force >/dev/null 2>&1 &
                ;;
            *) echo "invalid nested stop mode: $mode" >&2; exit 2 ;;
        esac
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

collect_pending "$@"
if [ "${#pending[@]}" -gt 0 ]; then
    stop_batch graceful "${pending[@]}"
fi
collect_pending "$@"
if [ "${#pending[@]}" -gt 0 ]; then
    stop_batch force "${pending[@]}"
fi

deadline=$((SECONDS + WAIT_TIMEOUT))
while :; do
    collect_pending "$@"
    [ "${#pending[@]}" -gt 0 ] || exit 0
    [ "$SECONDS" -lt "$deadline" ] || break
    sleep "$POLL_INTERVAL"
done

printf 'nested instances did not stop:' >&2
printf ' %s' "${pending[@]}" >&2
printf '\n' >&2
exit 1
