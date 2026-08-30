#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/manifests/lab.env"
upstream_dns=${PRPL_DNS_SERVERS:-1.1.1.1,1.0.0.1}

if ! lxc network show "$MANAGEMENT_NETWORK" >/dev/null 2>&1; then
    lxc network create "$MANAGEMENT_NETWORK" \
        ipv4.address="$MANAGEMENT_IPV4" ipv4.nat=true ipv6.address=none
fi

# Avoid chaining nested dnsmasq through a host-local systemd-resolved stub.
# Keep public defaults for the portable lab while allowing restricted
# environments to provide their own resolvers.
dnsmasq_servers=$(printf '%s' "$upstream_dns" | tr ',' '\n' | sed 's/^/server=/')
lxc network set "$MANAGEMENT_NETWORK" raw.dnsmasq "$dnsmasq_servers"

if ! lxc network show "$BACKHAUL_NETWORK" >/dev/null 2>&1; then
    lxc network create "$BACKHAUL_NETWORK" \
        ipv4.address="$BACKHAUL_IPV4" ipv4.nat=false ipv6.address=none
fi

if ! lxc info "$BUILD_CONTAINER" >/dev/null 2>&1; then
    lxc launch ubuntu:22.04/amd64 "$BUILD_CONTAINER" \
        --network "$MANAGEMENT_NETWORK"
fi

lxc config set "$BUILD_CONTAINER" boot.autostart false
lxc start "$BUILD_CONTAINER" 2>/dev/null || true
printf 'Build container: %s\n' "$BUILD_CONTAINER"
