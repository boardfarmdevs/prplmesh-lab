# Virtual-radio patch scope

## Signal-manager dependency

`amxp/0001-coalesce-signal-pipe-wakeups.patch` targets libamxp v2.0.0 from the
pinned Ambiorix v7.1.0 manifest. A 100-client model update can enqueue more
notifications than a pipe holds before the event loop gets another turn.
The original blocking write then prevents that same loop from draining it.
The patch keeps one nonblocking, level-triggered wakeup while queued work
exists; it does not discard or merge the actual notification payloads.
Suspension, resumption, deferred calls and cleanup update that readiness under
the existing queue mutex. Native dependency artifacts carry a checked
`amxp-provenance.env`; packaging and acceptance reject stale libraries.
`bash tests/amxp-signal-burst.sh` exercises 100,000-event bursts, concurrent
producers and complete delivery in the native build environment.

## Radio patches

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

The current ordered build series also includes scenario control,
frequency-qualified overrides, metrics and observer sockets. The build script
and patch directory are authoritative; the list above describes the initial
radio-correctness subset, not the complete current manifest.

The event-loop coordination patch initializes listener priorities, fairly
rotates continuously readable peers within each priority, and rejects stalled
control/observer readers without blocking radio processing. Higher-priority
timers retain precedence. `wmediumd -T` covers priority order, callback removal,
listener initialization and backpressure; it does not alter RF airtime/retries.

## prplMesh native-platform correction

`prplmesh/0018-controller-reconcile-conflicting-station-reports.patch` requests
one native Topology Response per conflicting associated-link report. A missed
association notification otherwise leaves the old owner in the controller
indefinitely, directing later BTM requests to an AP the client has left.
Only the authoritative Associated Clients response changes membership; signal
samples never do. Reports must belong to the sending Agent, and foreign-AL
traffic/TID updates cannot refresh the old owner's station data.
`tests/test_prpl_station_reconciliation.py` compiles the real link handler,
checks coalesced recovery and source ownership, and retains an unrepaired
negative control.

`hostap/0002-notify-successful-reauthorization.patch` fixes a stock-hostapd
nl80211 management-frame notification gap. A client can return to an AP whose
old authorized record survived its departure. Completing another association
and authorization updates the kernel and hostapd connection age, but the
unchanged authorization bit previously suppressed `AP-STA-CONNECTED`. The Agent
then retained the earlier association age and the controller correctly rejected
that apparently older ownership claim. An acknowledged successful association
now arms one notification for completed authorization; ordinary rekey callbacks
and repeated authorization calls remain deduplicated. No client is deauthorized
or declared connected before authorization. This patch covers hostapd's
software-managed association path used by nl80211, not driver-offloaded/FILS
callbacks. `tests/test_hostap_reauthorization.py` compiles the event guard and
checks initial joins, returning authorized clients, duplicate calls and failure
cleanup, including an unpatched negative control. Live room qualification is
required separately.

`prplmesh/0019-controller-order-associated-client-recovery.patch` qualifies
Associated Clients recovery against newer native association/departure events.
An old AP can retain an authorized station after the client roams; its older
Topology Response must not reclaim ownership or resurrect disconnected history.
Reported whole-second association ages are conservative bounds; saturated or
ambiguous ages cannot override a newer known event. Recovered joins run normal
native connection completion, including previous-AP cleanup, metrics reset and
steering/DHCP task notification. Empty reports remove only current ownership;
erased global stations detach from their BSS. Compiled regression tests in
`tests/test_prpl_topology_ownership.py` include negative controls for each guard.

`prplmesh/0017-controller-reconcile-recreated-agent-model.patch` repairs child
STA data-model paths when a native Agent is removed and recreated under a new
Device instance. Successful parent removal invalidates its old STA paths;
authoritative BSS publication repairs connected non-backhaul children still
owned by that BSS and registered as the current station object. Disconnected
history and orphaned BSS references cannot recreate ghost clients. Unchanged
paths preserve association timestamps, and stale old-AP membership cannot move
a client back. Missing operating-channel state
requests a real Operating Channel Report with an empty Channel Selection
Request, without changing channel preferences or inventing metrics.
`tests/test_prpl_model_recreation.py` covers recovery, exact path boundaries,
failed deletion, disconnected/orphan history and unchanged-path/roamed-client
cases, with negative controls for the missing guards. This fixes recovery,
not the cause of every possible Agent disappearance.

`prplmesh/0001-linux-map-third-radio-interface.patch` completes the native
Linux BPL mapping for radio number 2. Upstream release 6.0.0 already defines
`BEEROCKS_WLAN3_IFACE`, generates its hostapd and supplicant control paths,
and documents radio indices 0, 1 and 2, but the helper accepts only 0 and 1.
The patch is required to exercise the configured 6 GHz third radio; it does
not introduce a new controller feature.

`prplmesh/0002-nl80211-resolve-bssid-without-assoc-frame.patch`
preserves station ownership when vanilla hostapd reports a connection without
first providing prplMesh a raw association frame. The hostap control event is
already associated with a resolved VAP, so its BSSID is the correct fallback.
Capabilities still use the raw frame when one is available.

`prplmesh/0003-linux-separate-backhaul-sta-interfaces.patch` gives the
native Linux profile distinct `wlan1`, `wlan3`, and `wlan5` backhaul STA VIFs
next to the `wlan0`, `wlan2`, and `wlan4` AP VIFs. It also publishes the direct
station lookup aliases required by the backhaul HAL. The stock profile maps
both roles onto one netdev, which hostapd and wpa_supplicant cannot share.

`prplmesh/0004-nl80211-accept-unchanged-channel-with-stock-hostapd.patch`
keeps a selected backhaul radio's AP manager alive when stock hostapd rejects
the vendor `UPDATE` command but the requested channel and bandwidth already
match the live radio. Genuine channel changes still fail explicitly.

`prplmesh/0005-nl80211-apply-backhaul-credentials.patch` fixes the native
nl80211 station control reply API and stops M8 credential application from
treating the enrollee radio UID as a parent BSSID. An existing wireless parent
remains pinned while its credentials are refreshed; without an existing
association, `wpa_supplicant` may select a BSS advertising the backhaul SSID.
Networks created through the HAL are explicitly marked as Multi-AP backhaul
STA networks so a backhaul-only BSS accepts the replacement association.
## Wireless kernel namespace isolation

The hwsim builder also installs the namespace-safe cfg80211 companion module.
See [its build, restart and regression instructions](../scripts/cfg80211/README.md).
