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

# Ubuntu's on-demand LXD installer is masked too, and an install it started finishes first
eval "$(sed -n '/^no_on_demand_lxd()/,/^}/p' "$script")"
: > "$tmp/calls"
echo 1 > "$tmp/runs-left"
snap() {
    echo "snap $*" >> "$tmp/calls"
    [ "$1" = changes ] || return 0
    local runs_left
    runs_left=$(cat "$tmp/runs-left")
    if [ "$runs_left" -gt 0 ]; then
        echo $((runs_left - 1)) > "$tmp/runs-left"
        echo '5    Doing   today at 20:37 UTC  -                   Install "lxd" snap from "5.21/stable/ubuntu-24.04" channel'
    else
        echo '5    Done    today at 20:37 UTC  today at 20:37 UTC  Install "lxd" snap from "5.21/stable/ubuntu-24.04" channel'
    fi
}
no_on_demand_lxd
test "$(head -1 "$tmp/calls")" = 'systemctl mask --now lxd-installer.socket'
test "$(grep -c '^sleep 2$' "$tmp/calls")" = 1

# in the build: both sent to the guest and run before base_host, which holds its apt-get
call=$(grep -n 'declare -f no_automatic_updates no_on_demand_lxd base_host); no_automatic_updates; no_on_demand_lxd; base_host"' "$script" \
    | head -1 | cut -d: -f1)
test -n "$call"
base_start=$(grep -n '^base_host()' "$script" | cut -d: -f1)
base_end=$(awk -v start="$base_start" 'NR > start && /^}/ {print NR; exit}' "$script")
first_apt=$(grep -n '^ *apt-get ' "$script" | head -1 | cut -d: -f1)
last_apt=$(grep -n '^ *apt-get ' "$script" | tail -1 | cut -d: -f1)
test "$first_apt" -gt "$base_start" && test "$last_apt" -lt "$base_end"
echo 'PASS: the lab VM takes no automatic updates and no on-demand LXD, both before the first apt-get'
