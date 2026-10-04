#!/bin/sh
# The client image (prpl-client-local): Alpine, as the RDK lab's clients, with the lab's
# wpa_supplicant and wpa_cli built for it (artifacts/hostap-client-2.10-alpine.tar.gz,
# scripts/build-client-artifact.sh). Runs in the image's builder container.
set -eu

test -f /etc/alpine-release
# The builder runs this as soon as its container starts: its network may not be up yet
# (prpl-fast-a, 4 Oct: apk's first fetch failed).
for attempt in $(seq 1 60); do
    ip -4 route | grep -q '^default' && break
    [ "$attempt" -lt 60 ] || { echo 'the client builder has no network' >&2; exit 1; }
    sleep 1
done
for attempt in 1 2 3 4 5; do
    apk add --no-cache bash ca-certificates curl iperf3 iproute2 iputils iw libnl3 libssl3 \
        procps psmisc python3 tcpdump >/dev/null && break
    [ "$attempt" -lt 5 ] || exit 1
    sleep 5
done
tar -C /usr/local -xzf /mnt/project/artifacts/hostap-client-2.10-alpine.tar.gz \
    ./sbin/wpa_supplicant ./bin/wpa_cli
for binary in /usr/local/sbin/wpa_supplicant /usr/local/bin/wpa_cli; do
    if ldd "$binary" 2>&1 | grep -q 'Error\|not found'; then
        ldd "$binary" >&2
        exit 1
    fi
done
for binary in bash wpa_supplicant wpa_cli iw ip ping iperf3 tcpdump python3 pkill pgrep; do
    command -v "$binary" >/dev/null
done
/usr/local/sbin/wpa_supplicant -v | head -1
test ! -e /opt/prpl-install-nl80211
test ! -e /usr/local/sbin/hostapd
mkdir -p /var/run/wpa_supplicant
rm -rf /var/cache/apk/*
