# Progress log

## 2026-08-27 — experiment created

- Created an independent local repository on rev140 at
  `/home/rev/prplmesh-lab/0827`.
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
isolated Ubuntu 24.04/Linux 7.0 radio VM on rev140 and use the reviewed hwsim
6 GHz and wmediumd multichannel changes without the control-plane extensions.
Attach tri-band radios to the agent and a dedicated radio to one client, then
require physical association and controller ownership to agree before
accepting M2.

The native Linux BPL currently maps only radio numbers 0 and 1 even though its
build configuration and platform database define `wlan4` as a third radio.
The first physical association will therefore use the existing two-radio path;
tri-band acceptance requires a small, separately reviewed native-platform fix
for radio number 2 rather than pretending the unused setting already works.
