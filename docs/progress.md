# Progress log

## 2026-08-27 — experiment created

- Created an independent local repository for the prplMesh experiment.
- Added the official prplMesh repository as a submodule and pinned release
  `6.0.0`, commit `2e153c7e00cbcab6b8ee35082f494a364e23f018`.
- Confirmed upstream still provides a native Linux target, DUMMY and NL80211
  BWL choices, controller/agent executables, and hwsim-oriented Linux
  documentation.
- Chose separate LXD names, network, radios, medium files, and evidence paths so
  this experiment cannot mutate the RDK lab.

Next: create a clean Ubuntu x86 build container, install only declared build
dependencies, compile release 6.0.0 first with the supported Linux/DUMMY path,
then determine the smallest verified change needed for NL80211/hwsim runtime.

## 2026-08-28 — native build and control-plane onboarding

- Created isolated LXD networks `prplbr0` (management) and `prplbh0`
  (IEEE 1905/backhaul), with no RDK containers, bridges, or processes reused.
- Reproduced the upstream native build dependencies in Ubuntu 22.04 and built
  release 6.0.0 for x86 with the DUMMY BWL and NBAPI enabled.
- Started a colocated controller/agent and one separate agent in independent
  LXD containers. Each received deterministic, non-overlapping AL-MAC, radio,
  and BSSID identities.
- Observed AP Autoconfiguration Search, WSC M1/M2 configuration of both agent
  radios, topology exchange, and the separate agent reaching `OPERATIONAL`.
  The controller connection map reports both the colocated agent and the
  separate agent with their two radios. This accepts milestone M1 for the
  control-plane backend.
- Added scripts that capture the pinned build and the provisional DUMMY
  lifecycle. These are experiment scripts, not yet the final hwsim operator
  interface.

Known upstream build findings:

- GCC 11 turns a warning in the bundled older GoogleTest into an error when
  tests are enabled; a scoped `-Wno-error=maybe-uninitialized` permits those
  tests to compile.
- The Debug/test link has undefined static timing constants in service
  prioritization and traffic separation. Eight of nine produced test binaries
  pass; the build stops before `db_unit_tests` links. The release build used by
  the experiment completes.
- DUMMY monitor events cannot prove WLAN association, RSSI, traffic, or
  steering. Its client-event file is useful only as a control-path simulator.

Next: complete the NL80211 build against pinned hostap 2.10 headers. Build an
isolated Ubuntu 24.04/Linux 7.0 radio host and use the reviewed hwsim
6 GHz and wmediumd multichannel changes without the control-plane extensions.
Attach tri-band radios to the agent and a dedicated radio to one client, then
require physical association and controller ownership to agree before
accepting M2.

The native Linux BPL currently maps only radio numbers 0 and 1 even though its
build configuration and platform database define `wlan4` as a third radio.
The first physical association will therefore use the existing two-radio path;
tri-band acceptance requires a small, separately reviewed native-platform fix
for radio number 2 rather than pretending the unused setting already works.

## 2026-08-28 — NL80211 tri-band and steering accepted

- Built the native NL80211 backend and a WNM/802.11v, 802.11ax and SAE-capable
  hostap 2.10 runtime.
- Created the isolated Ubuntu 24.04/Linux 7.0 radio VM, loaded 12 hwsim radios
  with three channel contexts, and registered all radios with the dedicated
  patched wmediumd.
- Onboarded the colocated agent and one external agent. BML reports three
  radios per device at 2437, 5180 and 5975 MHz.
- Fixed native Linux radio-index 2 mapping so prplMesh starts `wlan4` as its
  third radio.
- Found that upstream hostapd can deliver `AP-STA-CONNECTED` without the raw
  association frame expected by prplMesh. The zero BSSID prevented the
  controller from creating a STA. The NL80211 fallback now resolves BSSID from
  the event's authoritative VAP.
- Associated clients on 2.4 GHz/WPA2, 5 GHz/WPA2 and 6 GHz/SAE. Physical
  wpa_supplicant state, hostapd state, BML and NBAPI ownership agree.
- Vanilla hostapd also leaves the station's 11v capability unknown because the
  raw association frame is absent. The lab clients are explicitly built with
  WNM, so the existing `send_btm_to_non_11v_sta=1` compatibility setting is
  applied in this controlled environment.
- Proved pure NBAPI `BTMRequest` steering on both 5 and 6 GHz. In each case the
  source hostapd reported `BSS-TM-RESP status_code=0`, wpa_supplicant moved to
  the requested BSSID, and the DataElements object moved to the destination
  agent. The repeatable gate is `scripts/test-steering.sh`.
- Added a separate read-only topology visualizer. It discovers dynamic model
  instances through `_get_instances`, reads parameters through `_get`, and
  renders devices, tri-band radios, backhaul and clients without modifying
  prplMesh.

At this checkpoint, data-plane addressing, wireless backhaul/multihop, and
stock-hostapd compatibility remained open. The following phase resolved the
backhaul and scale work; data traffic and upstream cleanup remain.

## 2026-08-28 — wireless multihop and scale accepted

- Fixed the NL80211 supplicant helper's `ADD_NETWORK` output-buffer check,
  preserved the currently selected parent instead of treating the WSC enrollee
  RUID as a BSSID, and added `multi_ap_backhaul_sta=1` to dynamically delivered
  credentials. External agents now remain associated after M8 configuration.
- Replaced host `wlanN` LXD parents with names derived from permanent hwsim
  MAC identity. Controller/agent PHY exchange no longer occurs across stop,
  radio-pool reconstruction or topology changes.
- Provisioned 40 radios, four external tri-band agents and 20 clients. Every
  external agent uses a wireless 5 GHz backhaul; star, branch and a four-hop
  chain pass physical and NBAPI parent validation.
- Added `private_ssid` and `iot_ssid` to every radio. Each cohort has 2.4, 5
  and 6 GHz clients; the total profile is 10 private, 10 IoT and 4/10/6 clients
  by band.
- Replaced the blocking BML connection-map readiness gate with bounded NBAPI
  instance queries. `bml_conn_map` remains useful at small scale but can wait
  indefinitely with wireless backhaul and many clients.
- Removed snapd and unattended upgrades from the runtime image after they
  activated independently in every node and saturated the VM. The image fell
  from 744 MiB to 357 MiB and the 20-client admission run completed in about
  69 seconds at normal load.
- Validated 20/20 associated-client metrics. A live wmediumd SNR step changed
  all clients from RCPI 118 to 88 and back to 118 without restarting a
  container.
- Passed a 30-cell matrix: private and IoT clients on 2.4, 5 and 6 GHz moved
  across controller plus all four agents. Physical BSSID and NBAPI owner agreed
  after every BTM request.
- Stopped the leaf agent in the four-hop chain. Its client reassociated without
  a manual WLAN reset, the inactive agent aged from NBAPI within 10 seconds,
  and the same AL-MAC/RUID/backhaul identity rejoined successfully.
- Repeated the leaf restart/steering cycle three times while checking the full
  topology, process cardinality, permanent-radio inventory hash and wmediumd
  PID on every iteration. All remained stable.
- Added a read-only visualizer normalization fix so backhaul STAs appear only
  as topology edges rather than being mislabeled and counted as WLAN clients.
- Added a deterministic isolated data network on `192.168.77.0/24`. All 20
  clients reach the controller bridge, and an IoT client on agent 4's 6 GHz
  fronthaul passed 10/10 packets through the complete wireless chain. The
  normal acceptance gate now checks this path after every run.

Current gaps are sustained and mixed traffic profiles, unassociated or
candidate-link metrics, optimizer/configurator adapter integration, long soak,
and cleanup of the stock-hostapd raw-frame/channel diagnostics.
