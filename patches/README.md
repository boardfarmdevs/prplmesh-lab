# Virtual-radio patch scope

These patches are copied into this independent experiment so the prplMesh lab
does not build from or modify the RDK repository.

The source versions were reviewed at RDK lab commit
`c461c591afe8afef47d1b215fbcfbb09eb5abcb3`. They retain their original patch
metadata. The hwsim patch applies to the Ubuntu Linux 7.0 source; the older
Linux 6.8 strict-regdomain workaround is deliberately not imported because
Linux 7.0 `regtest=5` already supplies the validated 6 GHz regulatory profile.

The wmediumd subset contains only radio-medium correctness changes:

1. per-frequency interference state;
2. learned VIF ownership for delivery;
3. removal of per-frame diagnostic file I/O;
4. independent frequency scheduling;
5. Linux 7 HT/VHT rate flags;
6. multicast frequency filtering;
7. enlarged netlink receive buffer;
8. configured default SNR;
9. transmit-learning requirement for multicast;
10. classification of transient clone rejections.

The scenario-control, frequency-override, metrics and observer socket patches
are not included in this phase.

## prplMesh native-platform correction

`prplmesh/0001-linux-map-third-radio-interface.patch` completes the native
Linux BPL mapping for radio number 2. Upstream release 6.0.0 already defines
`BEEROCKS_WLAN3_IFACE`, generates its hostapd and supplicant control paths,
and documents radio indices 0, 1 and 2, but the helper accepts only 0 and 1.
The patch is required to exercise the configured 6 GHz third radio; it does
not introduce a new controller feature.
