#!/bin/sh
# The client image (prpl-client-local): Alpine, as the RDK lab's clients, with the lab's
# wpa_supplicant and wpa_cli built for it (artifacts/hostap-client-2.10-alpine.tar.gz,
# scripts/build-client-artifact.sh). Runs in the image's builder container.
set -eu

test -f /etc/alpine-release
apk add --no-cache bash ca-certificates curl iperf3 iproute2 iputils iw libnl3 libssl3 \
    procps psmisc python3 tcpdump >/dev/null
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
