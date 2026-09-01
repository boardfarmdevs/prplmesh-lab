#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/prplmesh-nested-stop.XXXXXX)
trap 'rm -rf -- "$work"' EXIT

cat > "$work/lxc" <<'SH'
#!/bin/bash
set -euo pipefail
root=${FAKE_LXC_ROOT:?}
action=${1:-}
name=${2:-}
case "$action" in
    list)
        printf 'list %s\n' "$name" >> "$root/actions"
        if [ "$name" = prpl-client-10 ]; then
            cat "$root/prpl-client-10.state" "$root/prpl-client-100.state"
            exit 0
        fi
        name=${name#^}
        name=${name%\$}
        cat "$root/$name.state"
        ;;
    stop)
        shift 2
        mode=graceful
        for arg in "$@"; do
            [ "$arg" != --force ] || mode=force
        done
        printf '%s %s\n' "$mode" "$name" >> "$root/actions"
        if [ "$mode" = graceful ] && grep -Fxq "$name" "$root/sticky"; then
            exit 1
        fi
        if [ "$mode" = force ] && grep -Fxq "$name" "$root/force-fail"; then
            exit 1
        fi
        printf 'STOPPED\n' > "$root/$name.state"
        ;;
    *) echo "unexpected fake lxc command: $*" >&2; exit 2 ;;
esac
SH
chmod 755 "$work/lxc"

run_helper()
{
    env PRPLMESH_LXC_BIN="$work/lxc" \
        PRPLMESH_STOP_GRACE_TIMEOUT=0 \
        PRPLMESH_STOP_WAIT_TIMEOUT=1 \
        PRPLMESH_STOP_POLL_INTERVAL=1 \
        FAKE_LXC_ROOT="$work" \
        "$ROOT/scripts/stop-nested-instances.sh" "$@"
}

printf 'RUNNING\n' > "$work/prpl-controller.state"
printf 'RUNNING\n' > "$work/prpl-client-10.state"
printf 'STOPPED\n' > "$work/prpl-client-100.state"
printf 'STOPPED\n' > "$work/prpl-agent-01.state"
printf 'prpl-client-10\n' > "$work/sticky"
: > "$work/force-fail"
: > "$work/actions"
test "$(FAKE_LXC_ROOT="$work" "$work/lxc" list prpl-client-10 -c s --format csv | wc -l)" -eq 2
: > "$work/actions"
run_helper prpl-controller prpl-client-10 prpl-agent-01
grep -Fxq 'STOPPED' "$work/prpl-controller.state"
grep -Fxq 'STOPPED' "$work/prpl-client-10.state"
grep -Fxq 'list ^prpl-client-10$' "$work/actions"
grep -Fxq 'graceful prpl-controller' "$work/actions"
grep -Fxq 'graceful prpl-client-10' "$work/actions"
grep -Fxq 'force prpl-client-10' "$work/actions"
if grep -Fxq 'list prpl-client-10' "$work/actions"; then
    echo 'ambiguous prefix state lookup was used' >&2
    exit 1
fi
if grep -Eq '^(graceful|force) prpl-agent-01$' "$work/actions"; then
    echo 'already-stopped instance was stopped again' >&2
    exit 1
fi

printf 'RUNNING\n' > "$work/prpl-client-10.state"
printf 'prpl-client-10\n' > "$work/force-fail"
: > "$work/actions"
if run_helper prpl-client-10 >"$work/fail.out" 2>"$work/fail.err"; then
    echo 'force-stop failure was accepted' >&2
    exit 1
fi
grep -Fxq 'nested instances did not stop: prpl-client-10' "$work/fail.err"

if env PRPLMESH_STOP_WAIT_TIMEOUT=bad \
    "$ROOT/scripts/stop-nested-instances.sh" prpl-client-10 \
    >"$work/invalid.out" 2>"$work/invalid.err"; then
    echo 'invalid timeout was accepted' >&2
    exit 1
fi
grep -Fq 'non-negative integers' "$work/invalid.err"

grep -Fq 'scripts/stop-nested-instances.sh' "$ROOT/scripts/radio-lab.sh"
grep -Fq 'scripts/stop-nested-instances.sh' \
    "$ROOT/deploy/guest/prepare-thin-image.sh"
test "$(grep -c 'instance_state' "$ROOT/scripts/radio-lab.sh")" -eq 8
! grep -Fq 'lxc list "$name" -c s' "$ROOT/scripts/radio-lab.sh"

echo 'PASS: nested shutdown anchors names, retries and reports leftovers'
