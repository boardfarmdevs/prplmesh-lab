#!/bin/bash

# Human-readable progress output for demonstrations and acceptance scenarios.
# Messages go to stderr so command substitutions and machine-readable stdout
# remain stable. ANSI colour is used only for an interactive terminal.

if [ -t 2 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != dumb ]; then
    _OBS_ACTION='\033[1;96m'
    _OBS_WAIT='\033[1;93m'
    _OBS_PASS='\033[1;92m'
    _OBS_INFO='\033[1;94m'
    _OBS_RESET='\033[0m'
else
    _OBS_ACTION=
    _OBS_WAIT=
    _OBS_PASS=
    _OBS_INFO=
    _OBS_RESET=
fi

status_section() { printf '\n%b=== %s ===%b\n' "$_OBS_INFO" "$*" "$_OBS_RESET" >&2; }
status_action()  { printf '%b==> %s%b\n' "$_OBS_ACTION" "$*" "$_OBS_RESET" >&2; }
status_wait()    { printf '%b... %s%b\n' "$_OBS_WAIT" "$*" "$_OBS_RESET" >&2; }
status_pass()    { printf '%bOK: %s%b\n' "$_OBS_PASS" "$*" "$_OBS_RESET" >&2; }
status_note()    { printf '%b    %s%b\n' "$_OBS_INFO" "$*" "$_OBS_RESET" >&2; }

status_wait_seconds()
{
    local seconds=$1 reason=${2:-waiting for the system to converge}
    status_wait "Waiting ${seconds}s: $reason"
    sleep "$seconds"
}
