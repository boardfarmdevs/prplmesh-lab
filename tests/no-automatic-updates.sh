#!/usr/bin/env bash
# The VM build's first guest step switches automatic updates off, before any apt-get.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
script=$root/deploy/lxd-vm/build.sh
eval "$(sed -n '/^no_automatic_updates()/,/^}/p' "$script")"

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
export APT_CONF_DIR=$tmp
echo 2 > "$tmp/runs-left"    # an upgrade in flight for two polls (a file: the stub runs in a pipeline)
systemctl() {
    echo "systemctl $*" >> "$tmp/calls"
    if [ "$1" = show ]; then
        local runs_left
        runs_left=$(cat "$tmp/runs-left")
        if [ "$runs_left" -gt 0 ]; then
            echo $((runs_left - 1)) > "$tmp/runs-left"
            printf '%s\n\n%s\n' inactive activating
        else
            printf '%s\n\n%s\n' inactive inactive
        fi
    fi
}
snap() { echo "snap $*" >> "$tmp/calls"; }
sleep() { echo "sleep $*" >> "$tmp/calls"; }

no_automatic_updates

mapfile -t calls < "$tmp/calls"
test "${calls[0]}" = 'systemctl mask --now apt-daily.timer apt-daily-upgrade.timer'
test "$(grep -c '^sleep 2$' "$tmp/calls")" = 2    # it waited for the run in flight
last_wait=$(grep -n '^sleep' "$tmp/calls" | tail -1 | cut -d: -f1)
masked=$(grep -n -Fx 'systemctl mask apt-daily.service apt-daily-upgrade.service' "$tmp/calls" | cut -d: -f1)
test "$masked" -gt "$last_wait"
grep -Fxq 'systemctl disable --now unattended-upgrades.service' "$tmp/calls"
grep -Fxq 'snap wait system seed.loaded' "$tmp/calls"
test "${calls[-1]}" = 'snap refresh --hold'
grep -Fxq 'APT::Periodic::Update-Package-Lists "0";' "$tmp/99-lab-no-automatic-updates"
grep -Fxq 'APT::Periodic::Unattended-Upgrade "0";' "$tmp/99-lab-no-automatic-updates"

# in the build: sent to the guest, and before its first apt-get
call=$(grep -n 'declare -f no_automatic_updates); no_automatic_updates' "$script" | head -1 | cut -d: -f1)
first_apt=$(grep -n '^ *apt-get ' "$script" | head -1 | cut -d: -f1)
test -n "$call" && test "$call" -lt "$first_apt"
echo 'PASS: the lab VM takes no automatic updates, switched off before the first apt-get'
