# Virtual RF assessment and implementation roadmap

[Radio reference](README.md) · [Neighbor-room design](../proposals/neighbor-rooms/design.md)

**Status: assessment complete; the enhancements below are proposed, not implemented.**
This is the shared RF assessment for the RDK EasyMesh and prplMesh labs on
`codex/0908-clean`. It is mirrored in each repository's radio reference so
either repository remains independently useful. Maintain the common text
together; do not create a second backlog for the same RF work.

The evidence baseline is 2026-09-10 Pacific / 2026-09-11 UTC. Inspection was
read-only: source, running configuration, module identity, survey queries and
existing logs. No room, radio, reporting policy or medium was changed; no
congestion, throughput, capture or soak experiment was run for this assessment.

## Navigation

- [Conclusions](#1-conclusions)
- [Evidence and deployed architecture](#2-evidence-and-deployed-architecture)
- [Available RF attributes](#3-available-rf-attributes)
- [Important implementation gaps](#4-important-implementation-gaps)
- [Required measurement contract](#5-required-measurement-contract)
- [Common implementation work](#6-common-implementation-work)
- [RDK implementation work](#7-rdk-implementation-work)
- [prpl implementation work](#8-prpl-implementation-work)
- [Optimizer and viewer integration](#9-optimizer-and-viewer-integration)
- [Phased delivery](#10-phased-delivery)
- [Correctness and performance qualification](#11-correctness-and-performance-qualification)
- [Reproducing the audit and maintaining this document](#12-reproducing-the-audit-and-maintaining-this-document)

## 1. Conclusions

The labs are useful **frame-level, signal-driven protocol test environments**.
They run real AP, station, security, association and EasyMesh software. Their
medium changes affect actual frame delivery and native stack behavior, not
just the pictures in the room viewer.

They are **not yet calibrated RF-capacity or congestion simulators**. In
particular, a successful steering demonstration does not establish valid
channel utilization, realistic airtime sharing, accurate PHY throughput or
real-world measurement availability.

The highest-value findings are:

1. Directed, frequency-qualified SNR control already exists in both systems.
   It affects delivery, reported signal and loss. It is not necessary to
   invent this capability again.
2. hwsim survey records are scan-oriented dummy data, not continuously
   measured operating-channel occupancy. RDK additionally has successful
   no-op HAL survey functions; prpl's existing survey consumer lacks useful input.
3. Candidate RCPI is deliberately synthesized from the configured link matrix
   at the HAL boundary. That is useful for controlled experiments, but it is
   not proof that a radio actually heard an unassociated station.
4. The userspace scheduler serializes equal/higher-priority queue tails across
   all radios on the same frequency, without testing mutual audibility.
   It cannot establish realistic spatial reuse merely by placing nodes far apart.
5. HT/VHT rates are approximated using legacy rate curves, including for
   airtime; RX injection supplies a fixed rate index. Rate fields and modeled
   service capacity can therefore disagree.
6. ACK selection is primarily a forward-link success model, not a separately
   simulated reverse-link exchange. Kernel injection and receiver acceptance
   are also not the same event.
7. Current shared optimizer snapshots are RCPI/band/association oriented.
   Adding load to an AP report alone would not make that optimizer load-aware.

**Recommendation:** preserve the working signal baseline, fix truthful
availability/reporting first, then add bounded per-radio/channel airtime
accounting and qualify one 20 MHz contention domain. Integrate both native
stacks before adding load-aware policy. Visibility-aware contention, reverse
ACK modeling and calibrated PHY service time are the next fidelity gates,
not optional details when claiming realistic capacity or hidden-node behavior.

## 2. Evidence and deployed architecture

### 2.1 Inspected baseline

| Item | RDK on rev140 | prpl on rev150 |
| --- | --- | --- |
| Running VM | `rdkeasymesh-20-0908` | `prplmesh-20-0908` |
| Canonical repository | `/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe` | `/home/rev/git/prplmesh-lab` |
| Repository revision before this assessment | `a272288680d798d8d9567e93709dd95a0a744a7d` | `61e01d207c7d225af8db8aaff47b92e2aa0667d3` |
| Guest kernel | `7.0.0-30-generic` | `7.0.0-30-generic` |
| Loaded/on-disk hwsim srcversion | `1D5C2CF6D5C83BD61935792`, matching | Same, matching |
| Configured radio pool / channel contexts | 32 / 3 | 40 / 3 |
| Mesh radio ownership | One wiphy per mesh container, concurrent band-specific VAPs | Three wiphys per mesh container |
| Default active radio requirement | 5 mesh + 20 client = 25 | 15 mesh + 20 client = 35 |
| Logical mesh roles | Controller plus colocated Agent-1 and four extenders | Same logical arrangement |
| Selected medium | Userspace wmediumd; `kernel_medium=N` | Userspace wmediumd; `kernel_medium=N` |
| Startup signal model | `snr`, default SNR 40 dB | Same |
| Radio regulatory test setting | `regtest=5` | Same |

The pool totals are not counts of independent RF channels. Nor are six
logical mesh roles six physical mesh containers. Recheck spare radio ownership
before adding foreign APs; do not reload hwsim during a room transition.

Both build scripts pin wmediumd to
`717e5d7fcc23eecbc8e32bd897a8fd4b1e3ba640`. The hwsim patch sets are identical
in the inspected repositories. wmediumd patch numbering differs after the
shared initial series, and prpl includes an additional learned-VIF control
identity patch. Compare content and capabilities, not patch numbers alone.

RDK's canonical Yocto source trees identify Wi-Fi HAL
`ce3170c9c8710a44b4627248e1443c31a9f7ad43`, OneWifi/libwebconfig
`6281b770f10654644c23e6f474c556cf913e41b4`, and Unified Wi-Fi Mesh
`1ef3cfd3014296defd2c5b575584e5f1d8195e0f`, plus the lab patches.
prpl's manifest pins release 6.0.0 at
`2e153c7e00cbcab6b8ee35082f494a364e23f018`, plus its lab patches.
Source inspection is not a new reproducible-build comparison of every installed
native binary; deployment provenance should remain part of later qualification.

### 2.2 Evidence register

**Live** means observed in the running VM. **Source** means an inspected
implementation or patch. **Documented** means an existing limitation not
remeasured here. **Proposed** always means future work.

| ID | Evidence | Finding |
| --- | --- | --- |
| E01 | Live, both module parameters and srcversion | Userspace backend active; matching installed/loaded hwsim identity |
| E02 | Live, RDK `iw dev wifi1 info` and `survey dump` | Operating at 5180 MHz; survey returned 5955 MHz, noise -92 dBm, active 120 ms, busy 15 ms |
| E03 | Live, prpl controller survey queries | No survey rows returned for its queried interfaces |
| E04 | Live, prpl hostapd configuration and monitor logs | No periodic BSS-load settings in generated configs; repeated current utilization 0 in monitor log |
| E05 | Source, deployed prpl `build/hwsim-source/mac80211_hwsim.c` | `mac80211_hwsim_get_survey()` uses scan records and `time_busy = time / 8` |
| E06 | Source, RDK canonical HAL | `wifi_getRadioChannelStats()` and `wifi_drv_get_survey()` return success without populating measurements |
| E07 | Source, shared wmediumd patches and deployed prpl source | Frequency overrides, rate approximation, fixed RX-rate index, same-frequency queue-tail scheduling, bounded telemetry |
| E08 | Source, each lab's candidate-provider patches | HAL reads directed frequency-qualified matrix values through a read-only socket |
| E09 | Source, pinned prpl BWL and scan task | Survey consumer exists; radio noise/SNR/ESP gaps; zero scan utilization rewritten to 10 |
| E10 | Source, shared optimizer model/policy and room integration | RCPI, band, freshness and association gates; no channel-load field in the shared policy snapshot |
| E11 | Documented RDK metrics limitations | Some rate values/storage are unreliable; no new rate-overflow reproduction performed |
| E12 | Source and loaded module identity | Monitor-ACK channel-context fix is present; raw monitor capture still needs bounded, explicit qualification |

E02 is not evidence of 12.5% utilization on the current 5 GHz AP. E04 is
not proof that every monitor cycle made a successful survey request. An empty
survey, default zero, stale scan and measured idle channel are different states.

### 2.3 Three separate planes

```text
Room geometry/events
    -> configurator/compiler -> atomic medium state generation
                                  |
AP/STA applications               v
    -> hostapd/OneWifi/supplicant -> mac80211/hwsim
                                  <-> wmediumd frame scheduler/PER
    <- received frames + signal + modeled TX status

Native measurement/reporting:
    driver or hwsim HAL provider -> RDK OneWifi/EasyMesh or prpl Agent
    -> IEEE 1905 reports -> native controller -> read-only APIs
    -> selected optimizer -> native steering/channel action

Independent observation:
    medium counters + kernel/stack events + traffic + browser timestamps
    -> diagnostic evidence, not a replacement controller database
```

Linux hwsim is a mac80211 hardware substitute, not an RF waveform solver.
The Wi-Fi state machines above it remain real software.
[Linux hwsim documentation](https://wireless.docs.kernel.org/en/latest/en/users/drivers/mac80211_hwsim.html)

The control socket changes the medium. The HAL metrics socket is read-only.
The separate Console telemetry socket exposes diagnostics. Keep these
privileges and roles separate when adding counters.

RDK requires measurement keys containing the actual radio/channel context:
a wiphy-only key would merge 2.4, 5 and 6 GHz. prpl has separate mesh wiphys,
but several BSSs share each band radio. In both labs, distinguish permanent
radio identity, learned transmitting VIF, BSSID, STA address and namespace.

## 3. Available RF attributes

### 3.1 Current support and usefulness

“Available” below does not imply hardware-calibrated accuracy.

| Attribute | Current source or manipulation | Native/optimizer value and limitation |
| --- | --- | --- |
| Radio/BSS/STA identity | hwsim inventory, VIF ownership learning, native associations | Essential and implemented; identities are not interchangeable |
| Band, operating class, frequency | Native configuration and hwsim frame frequency; delivery eligibility checks | Available; validate operating class and current context, especially 6 GHz |
| Channel width | Native advertised/configured capability | Not a qualified wide-channel interference or service-time model |
| Directed link SNR | Radio-pair defaults plus exact-frequency overrides, atomic generations | Working scenario control; not a measurement of physical noise |
| RSSI on received frames | Medium signal derived from SNR with fixed -91 dBm noise reference | Drives kernel/native associated signal; new samples depend on received traffic |
| RCPI | HAL/controller conversion of signal; candidate provider conversion | Useful for signal steering; retain conversion, source and observation time |
| Candidate signal | HAL reads matrix for requested direction/frequency | Idealized synthetic availability, not reception-backed scanning |
| Noise floor | Fixed medium reference; hwsim dummy survey -92 dBm; native placeholders | No trustworthy independently varied/measured noise floor today |
| Distance and walls | World compiler's logarithmic loss, wall-crossing loss, per-band reference | Repeatable geometry-to-SNR abstraction, not ray tracing |
| Transmit gain/power | World `tx_gain_db_by_band`; native power configuration also exists | Scenario gain affects SNR; native power changes are not proven to update that matrix |
| Shadowing/fading | Seeded world shadow term; upstream medium fading option | World term is repeatable but not temporally correlated fading; medium fading not enabled in baseline |
| Packet error probability | Legacy PER curves use SNR, length and approximated rate | Real delivery consequences; absolute curves are not modern-PHY calibration |
| Retries and TX success/failure | Medium retry series and TX status; kernel station counters | Available diagnostics, subject to ACK/delivery limitations |
| TX/RX bytes and packets | Real software traffic and native station/interface statistics | Useful demand/goodput inputs after units, wrap and ownership validation |
| TX/RX PHY-rate fields | Kernel rate control and HAL parsing | TX model approximated; RX-rate injection fixed; do not treat as measured capacity |
| Airtime/service delay | Medium scheduler calculates durations and queue completion | Internal model exists, but no trustworthy per-observer busy survey |
| Channel utilization | Dummy/empty hwsim survey and incomplete adapters | Not qualified in either lab |
| BSS station count | hostapd/native association tables | Available independently of channel load; filter stale and AP/VLAN duplicates |
| Beacon/probe BSS Load | hostapd feature and scan parsers | Reporting support exists; dynamic measured advertisement is not established |
| Estimated Service Parameters | EasyMesh structures; prpl nl80211 setter is a no-op | Do not use as qualified service-capacity input |
| Neighbor BSS discovery | Real beacons/probes and native scan mechanisms | Available protocol substrate; fresh off-channel end-to-end coverage still needs qualification |
| CCA / carrier sensing | Coarse receive cutoff and queue/interference approximations | Not a per-radio, visibility-aware CCA/NAV model |
| Co-channel interference | Optional same-frequency accounting, disabled in startup baseline | Not qualified; source contains additional modeling concerns |
| Hidden/exposed nodes and spatial reuse | Directed matrix can describe asymmetry | Scheduler/ACK behavior prevents a claim of realistic hidden-node performance |
| Adjacent-channel overlap | Exact-frequency isolation | No partial-overlap/spectral-mask model |
| Non-Wi-Fi interference | No supported room primitive | Proposed noise/energy occupancy model, distinct from foreign Wi-Fi traffic |
| QoS/access categories | Four medium queues, management priority, retry timing | Not complete TXOP, aggregation, OFDMA or MU scheduling |
| RTT, loss and application throughput | Real traffic through the simulated datapath | Observable outcome, includes host/software delay as well as modeled RF effects |
| DFS/CAC, regulatory flags, power limits | Kernel capabilities and native control protocols | Protocol testing possible; no qualified radar/AFC/physical-spectrum simulation |
| HE/EHT, MIMO, beamforming, MLO | Some capabilities/protocol paths exist | No calibrated modern-PHY spatial, RU or multi-link capacity model |
| Raw management capture | Global hwsim monitor, or daemon capture support | TX-side evidence, not receiver-local occupancy or proof of decoding |

### 3.2 How the room changes the medium

The world compiler calculates a directed value approximately as:

```text
SNR(band) =
    reference_SNR(band)
    - 10 * path_loss_exponent * log10(max(distance, reference_distance) / reference_distance)
    - sum(crossed_wall_losses)
    + source_gain(band)
    + seeded_shadow_term
```

The result is rounded and clamped; absent roles receive the configured minimum.
The shadow term is seeded by time, pair and band; reciprocal pairs share its
draw, while source gains can introduce asymmetry. A seed stabilizes the world
plan, not all scheduling, rate-control and random frame-loss outcomes.

The compiler can project one band onto a radio-pair matrix or compile
frequency-qualified updates for multiple bands. Exact-frequency overrides
take precedence over pair defaults. Older descriptions saying only one
cross-band matrix value is possible are incomplete.

A channel change needs a deliberate rebinding strategy: an override for
5180 MHz does not automatically become one for 5220 MHz. Recompile/apply the
geometry for the new channel with an epoch boundary, rather than accidentally
falling back to a strong startup default.

Changing RF conditions does not itself associate a client, remove a topology
node, alter an SSID or select a parent. Native software and the explicitly
selected external policy perform those actions. Protected startup backhaul,
adaptive backhaul and stimulus-only operation are distinct experiment modes.

## 4. Important implementation gaps

### 4.1 Survey counters are not traffic counters

E05 retains hwsim's scan-oriented dummy survey implementation: the busy time
is one eighth of the recorded channel time, with fixed noise. It does not
integrate transmissions sensed by each operating radio. Empty output is also
possible when no survey record exists. The upstream implementation documents
the values as dummy data.
[Upstream hwsim survey implementation](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/441c63ff42c4e666304cdd32d23b5fc6bc1ea3cc/drivers/net/wireless/virtual/mac80211_hwsim.c)

Neither packet counts nor sums of bytes are substitutes. Airtime depends on
rate, preamble, retransmissions and other transmitters. A receiver can sense
busy medium without successfully decoding a packet. Overlapping energy must
not be counted twice in total busy time.

### 4.2 RDK has successful no-op reporting interfaces

At E06, `platform/banana-pi/platform.c` implements
`wifi_getRadioChannelStats()` as success without output. In
`src/wifi_hal_nl80211.c`, `wifi_drv_get_survey()` does the same.
Zero-initialized callers can consequently publish zero without a measurement.
[Baseline Banana Pi HAL source](https://github.com/rdkcentral/rdk-wifi-hal/blob/ce3170c9c8710a44b4627248e1443c31a9f7ad43/platform/banana-pi/platform.c)

The hostapd integration conditionally sets `bss_load_update_period=360000`
under `CONFIG_BSS_LOAD`, with a driver-update assumption. That source setting
does not prove that the deployed build advertises fresh load; audit the build
flag, callback and actual beacon together. Changing only the period cannot
repair a no-op survey callback.

OneWifi already has channel-statistics collection, encoding and translation
paths. Complete those paths rather than inserting invented values into the
EasyMesh controller.

### 4.3 prpl has native consumers but additional placeholders

The pinned nl80211 `get_channel_utilization()` requests a survey and converts
it, returning failure when usable data is absent. The data source is therefore
the first missing dependency, not the topology adapter.
[prpl survey consumer](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/raw/2e153c7e00cbcab6b8ee35082f494a364e23f018/common/beerocks/bwl/nl80211/base_wlan_hal_nl80211.cpp)

Additional source findings:

- `update_radio_stats()` assigns noise zero.
- Associated station SNR is not supplied by this backend.
- `set_estimated_service_parameters()` returns success without implementation.
- The scan task supports optional neighbor BSS Load, but separately rewrites a
  zero local scan-utilization byte to `10`, citing an old certification-script
  workaround. This is present in the pinned source, not just an older proposal.
  Its execution on the current lab was not exercised in this audit.

The last item can turn an idle/placeholder value into misleading nonzero data.
Do not “correct” it by subtracting 10 in the viewer. Review/remove the native
workaround under a regression test and applicable test-plan review.
[prpl monitor HAL](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/raw/2e153c7e00cbcab6b8ee35082f494a364e23f018/common/beerocks/bwl/nl80211/mon_wlan_hal_nl80211.cpp),
[prpl scan report construction](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/raw/2e153c7e00cbcab6b8ee35082f494a364e23f018/agent/src/beerocks/slave/tasks/channel_scan_task.cpp)

### 4.4 Synthetic candidate metrics bypass physical availability

RDK patch `0024-hwsim-read-candidate-rcpi-from-wmediumd.patch` and prpl patch
`0006-nl80211-read-hwsim-candidate-metrics.patch` deliberately read link
configuration at the HAL boundary. RDK converts SNR to bounded RCPI; prpl
supplies RSSI to its normal agent reporting path.

These reports still traverse native software and IEEE 1905, which is valuable.
However, matrix access can produce a fresh answer without hearing the STA,
performing an off-channel dwell or suffering a failed measurement exchange.
A newly stamped response is not necessarily a new RF observation.

Retain this explicit **idealized candidate-provider** mode for policy tests.
Add a separate reception-backed mode with sample count, age, frequency and
receiver eligibility. Do not silently switch semantics or compare timing
between modes as if the underlying measurement work were equivalent.

prpl's patched controller reconstructs measurement time but serializes it at
whole-second resolution. Existing freshness handling compensates for that
ambiguity. A higher-resolution native sequence/timestamp is preferable to
pretending acquisition was instantaneous.

### 4.5 Airtime and PHY-rate fidelity are coupled

The Linux-7 rate patch maps HT/VHT MCS/NSS combinations to nearby legacy OFDM
rates. The same mapped rate drives both PER and `pkt_duration()`; the
available OFDM curves top out at 54 Mbit/s. Thus a higher native PHY rate does
not imply matching modeled service time.

The inspected `send_cloned_frame_msg()` also writes
`HWSIM_ATTR_RX_RATE=1`, despite accepting a rate argument. RX metadata is
therefore not a faithful description of the selected transmission mode.

Fixing airtime reporting without addressing or explicitly restricting this
model can make a wrong capacity calculation more visible, not more correct.
Initially qualify a supported 20 MHz legacy-rate case. Later separate airtime
calculation from PER-curve selection and preserve the actual supported RX mode.

RDK's associated parser consumes 32-bit byte counters and a limited bitrate
attribute path. Audit 64-bit preference, wrap and legacy bitrate fallback.
The existing signed-rate/storage warning is E11, not a newly reproduced
overflow in this assessment.

### 4.6 Contention is broader than the RF visibility graph

In E07, `queue_frame()` advances a frame behind equal/higher-priority queue
tails from every station on the same frequency. It does not require those
transmitters to hear one another. The model is closer to a coarse shared
collision domain than independent local contention domains.

Consequences:

- Two RF-isolated same-channel pairs may still delay each other.
- A distant foreign AP can impose scheduler delay inconsistent with locally
  observed busy time.
- Hidden/exposed-node and spatial-reuse experiments cannot be qualified just
  by changing SNR values.

The optional interference path is not an automatic fix. Its power arithmetic
also deserves a focused unit test: the inspected routine sums values expressed
in milliwatts, then returns no offset when the sum is at most 1.0. Ordinary
negative-dBm interferers are below that level. Verify linear-power addition,
noise reference and SINR degradation before enabling this path for experiments.
This is a source concern in a disabled path, not a measured production fault.

### 4.7 Modeled ACK and receiver delivery are different

Unicast PER/retry success is selected using the forward-link model before
delivery. There is no independent reverse-link ACK PER trial in that path.
Some receiver eligibility is learned from transmitted VIFs and checked again
at delivery, rather than obtained as authoritative current kernel state.

A frame can be selected as ACKed before a later off-channel/injection failure.
The delivery path does not provide a general receiver-acceptance handshake
that proves successful MAC decoding. `rx_injected` records submission, not
application reception; asynchronous netlink rejections are separate counters.

Required improvements are explicit context/lifecycle state, outcome
classification, and reverse-ACK modeling where bidirectional fidelity is
claimed. Do not add a blocking userspace round trip for every frame merely to
hide this distinction.

### 4.8 Signal, noise, interference and CCA must be separate

The active medium uses `signal = SNR - 91`; its coarse CCA cutoff is -90 dBm.
These are model constants, not calibrated receiver characteristics. Lowering
SNR currently lowers reported signal, which is not equivalent to increasing
noise at unchanged received power.

A better model separates received power, background noise, interfering energy,
decode probability and carrier sensing. Native transmit-power changes must
either feed that model or be reported as unsupported RF actuation. Avoid
applying the same power change in both geometry and the medium.

Likewise, wall loss is currently a scalar sum; changing antenna orientation,
material response by band, moving reflectors or fading correlation requires
explicit new model parameters.

### 4.9 Optional kernel medium is not an occupancy shortcut

The opt-in kernel patches provide directed link state, cutoff/loss, optional
rate/PER and bounded delay/jitter, plus per-band airtime/overlap diagnostics.
Those are not complete per-channel, per-observer CCA surveys. Band-wide overlap
and receive-fanout accounting cannot simply be relabeled channel utilization.

Userspace remains the baseline. Share the measurement schema and conformance
tests with kernel mode, but qualify each backend independently. Identical
socket shapes do not establish equal model fidelity.

### 4.10 Capture and host delay are observation limits

`hwsim0` is the global transmitter-side monitor for one VM's virtual radios.
It is useful for beacon fields; it is not a local spectrum analyzer or proof
that every intended receiver accepted a frame. Modeled retries/ACKs also need
their own interpretation rather than assuming a hardware-equivalent trace.

The current patch set contains the multichannel monitor-ACK fix. Older blanket
warnings that dynamic capture is always unsafe do not describe that fix.
Nevertheless, verify the loaded module, preserve monitor state, bound capture
duration and record drops. The room trace helper's normal management filter
excludes beacons/probes, so use a deliberately chosen beacon capture for BSS Load.

CPU contention, netlink backlog, container scheduling, polling, candidate
admission and browser rendering add real latency. They are not RF congestion.
Fast emulation requires measuring and bounding these costs, not claiming zero
cost or interpreting a loaded host as a busy wireless channel.

## 5. Required measurement contract

### 5.1 Keep three kinds of information distinct

| Class | Examples | Who may consume it |
| --- | --- | --- |
| Scenario/model state | Intended SNR, noise setting, traffic schedule, geometry generation | Stimulus engine and independent test oracle |
| Native observations | Received RSSI, operating-channel survey, reported neighbor BSS Load | Native controller and selected optimizer |
| Decisions/outcomes | Steering request, actual association, channel change, verified goodput | Observer, operator and evaluation |

An idealized HAL sample is an explicit model-derived observation, not an
unlabeled passive measurement. Diagnostic access to scenario truth must not
silently become an optimizer input.

### 5.2 Proposed radio/channel record

The following is a design contract, not an existing API:

| Group | Required fields |
| --- | --- |
| Identity | Medium instance/boot ID, stable radio ID, logical radio/context ID, frequency, width, context epoch |
| Window | Monotonic start/end, sequence, publication time, measurement source and fidelity profile |
| Cumulative counters | Active, sensed-busy, own TX, RX; separately supported in-BSS RX, decoded foreign RX, undecodable energy |
| Quality | Valid-field mask; unsupported, missing, warming-up, partial, stale, invalid or valid state |
| Correlation | Applied RF generation, capture/receipt timestamps where available, reset reason |
| Derived values | Utilization percentage and protocol encoding, each with explicit unit and averaging window |
| Health | Transport loss, scheduler lateness, observation gaps and counter-overflow indicators |

Use 64-bit internal time counters, preferably microseconds or finer where
needed. Export Linux survey units correctly; do not round every short frame
independently to milliseconds. Keep fractional/remainder accounting until
snapshot conversion. Avoid per-frame allocations merely to retain history.

An AP that is up and tuned accumulates observation time even when idle.
A disabled context does not accumulate fresh on-channel time. Retune, restart,
radio reuse and daemon replacement establish explicit epochs. Multiple BSSs on
one context reference the same channel record rather than duplicating airtime.

### 5.3 Definitions and invariants

```text
utilization_percent = 100 * delta_busy / delta_active
BSS_Load_utilization_byte = round(255 * delta_busy / delta_active)
SNR_dB = received_power_dBm - noise_power_dBm
RCPI = clamp(round(2 * (RSSI_dBm + 110)), 0, 220)
```

The RCPI expression covers valid representable signal values; preserve
unavailable/reserved encodings separately. A zero denominator is unavailable,
not idle. Preserve the raw BSS-load byte alongside normalized percentages.

Busy time is the union of sensed occupied intervals intersected with the
observer's valid on-channel window. Specify whether own TX is included in
total busy and keep this consistent with the chosen driver/export semantics.
Idle backoff, userspace queue waiting and scheduler lateness are not
transmitted RF energy. ACK airtime is occupied; an ACK timeout without energy
is not equivalent to an ACK transmission.

Require nonnegative deltas and `busy <= active`. Do not assume all diagnostic
subcounters are mutually exclusive; collision energy and decoded RX may overlap.
Validate context identity before differencing counters.

Linux defines active/busy/TX/RX survey fields with explicit support flags.
Use that interface where possible rather than inventing a controller-only
busy metric. [Linux survey contract](https://cdn.kernel.org/doc/html/latest/driver-api/80211/cfg80211.html)

### 5.4 BSS Load is not three independent capacity measurements

The element contains station count, channel utilization and available admission
capacity. Station count belongs to a BSS; utilization describes the channel as
observed by its radio. Admission capacity is not simply `100 - utilization`,
CPU headroom or spare Internet bandwidth.

Our AP's sensed utilization and a neighbor's advertised utilization are
different observations. An unseen interferer at the neighbor can make them
differ legitimately. Multiple private/IoT BSS advertisements from one radio
must not be summed as independent loads.

Hostapd supports periodic BSS Load and fixed test values, subject to build
support. A fixed advertisement is appropriate for parser tests only.
[Hostapd BSS-load settings](https://chromium.googlesource.com/external/w1.fi/cgit/hostap/+/9c6b0a941672eb54e5a5e11f4d6a699f2aba1709/hostapd/hostapd.conf)

Where an IEEE 1905 TLV has no general unknown encoding, use its specified
failure/omission behavior where applicable and retain availability in local
diagnostics. Do not invent reserved wire values or break required messages.
Audit required fields individually; native APIs and UI must not reinterpret an
uninitialized placeholder as a valid measurement.

## 6. Common implementation work

### 6.1 Recommended architecture

Keep one medium event loop and bounded counter tables. Add explicit radio/VIF
context registration and lifecycle notifications from hwsim, rather than
relying exclusively on TX learning for quiet radios and scan transitions.

Accumulate per-observer interval counters from the actual modeled transmission
timeline. Separate PHY occupancy from service/queue duration. A low-overhead
bounded snapshot export feeds a driver-side cache; nl80211 survey queries read
that cache without synchronously asking userspace to process traffic.

A possible implementation is a versioned, privileged hwsim netlink batch
message for completed counter snapshots, plus context/epoch events in the
opposite direction. This is a proposal requiring kernel API review, not an
existing hwsim facility. Accept updates only from the registered medium,
validate lengths/identities/epochs, and expire them on daemon loss. Never block
the TX path behind an observer or control client.

Start with an explicit 20 MHz, single-contending-domain profile. Its measured
occupancy must reflect its actual model. Do not claim spatial reuse until the
scheduler uses a visibility graph consistent with local sensing.

### 6.2 Driver-first versus HAL-first

| Approach | Advantage | Cost / limitation | Recommendation |
| --- | --- | --- | --- |
| Common hwsim survey provider | Native Linux consumers and hostapd share one source; reusable across stacks | New kernel/provider contract, context lifecycle and ABI validation | Preferred durable solution |
| Common counter snapshot with thin HAL adapters | Can validate native reporting before the driver export is ready | Both adapters plus hostapd integration; no automatic `iw survey` parity | Acceptable bounded intermediate step |
| UI/controller database injection | Fast-looking demonstration | Bypasses real collection, freshness and protocol behavior | Do not use for qualification |
| Global PCAP-derived utilization | No driver change | Misses observer sensing and reliable airtime/acceptance semantics | Diagnostic comparison only |
| Replace the complete lab with another simulator | Potentially richer PHY | Major integration/calibration cost and new behavior differences | Not a prerequisite |

HAL-first must consume the same counter contract and remain removable. Do not
grow two independent utilization models. No Redis, Kafka, separate database or
per-container packet collector is needed.

### 6.3 Common work packages

| ID | Work and implementation points | Acceptance |
| --- | --- | --- |
| C01 | Capability/provenance manifest; common unit and availability rules in configurator, medium, observers and adapters | Unsupported fields never appear as valid zero; backend/version mismatch fails clearly |
| C02 | Radio/context lifecycle in hwsim and wmediumd; current frequency, scan dwell, up/down, VIF ownership and epochs | Quiet/retuning radios have correct eligibility without needing a learning transmission |
| C03 | Refactor scheduler duration into transmission/ACK occupancy versus waiting; bounded per-observer counters | Hand-calculated interval fixtures, no double counting, no busy inflation from CPU delay |
| C04 | Versioned snapshot export and survey cache, or bounded HAL-first adapter | Concurrent readers get coherent epochs; daemon failure becomes stale; readers cannot mutate RF |
| C05 | Truthful RX-rate metadata and supported PHY airtime; separate PER calibration | Known-rate airtime fixtures agree; unsupported modes are explicit, not plausible invented throughput |
| C06 | Visibility-aware same-channel contention and independent reverse ACK outcome | RF-isolated pairs can reuse airtime; asymmetric reverse-link test fails/retries appropriately |
| C07 | Receiver-side received-power/noise/CCA/interference model; fix disabled interference arithmetic before use | Correct sub-milliwatt power addition, noise-only degradation and CCA/decode distinction |
| C08 | Reception-backed candidate sample cache alongside explicit idealized mode | Silent/off-channel/undecodable STA does not gain a fake fresh sample |
| C09 | Bounded traffic actor and F1 BSS-load injection profiles | Advertised load and actual offered load are independently controllable and visibly labeled |
| C10 | Deterministic impairment streams, generation correlation and latency/drop accounting | Same plan reproducible at model level; transport/host failures never counted as RF policy failures |

Update both wmediumd patch series by semantic content. Keep old APIs compatible
where possible, negotiate new capabilities, and add unsupported responses
rather than making old HAL clients parse a changed packet layout.

Frequency override capacity is bounded in the current implementation. A
channel-switch stress test must check reclamation and capacity explicitly;
do not accumulate overrides for every historical channel indefinitely.

## 7. RDK implementation work

Repository paths below are relative to the RDK repository root.

| ID | Location / responsibility | Required work |
| --- | --- | --- |
| R01 | `recipes-ccsp/hal/rdk-wifi-hal/`; Banana Pi `wifi_getRadioChannelStats()` | Replace success/no-output with real common survey conversion; validate requested channel, pool membership, units and availability |
| R02 | Same HAL; `wifi_drv_get_survey()` and `wifi_hal_hostapd.c` | Supply hostapd survey results through its callback/event contract; audit BSS-load build flag, period and beacon generation |
| R03 | `recipes-ccsp/ccsp/ccsp-one-wifi/` and libwebconfig; `source/stats/wifi_stats_radio_channel.c`, radio diagnostics and translators | Trace valid data into AP/radio metrics; share one context sample, preserve collection time, check idle-radio reports |
| R04 | `recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/` | Verify query/periodic/threshold-crossing AP reports and native model persistence; fix demonstrated field/age/encoding errors |
| R05 | HAL associated/candidate providers and native rate storage | Audit 64-bit counters, 16/32-bit bitrate fallback, units and signed range; add reception-backed candidate mode without leaking matrix truth |
| R06 | Native scan/channel-control paths | Preserve neighbor load presence and local scan utilization separately; verify actual channel change, VAP sharing and backhaul continuity |
| R07 | `gen/optimizer/`, `gen/demo/room_demo/`, native web UI | Version load-aware snapshots only after R01-R06 gates; expose validity and decision reasons |
| R08 | `gen/hwsim/`, `gen/wmediumd/`, `gen/vm/` packaging | Pin rebuilt module/daemon/HAL compatibility; include conformance tests and safe rollback in future artifacts |

A standard survey response may identify a channel on a shared wiphy but not
all logical RDK radio semantics by itself. Map frequency/context back to the
correct RDK radio index and VAP group. Do not aggregate all three bands into
one `radio_ChannelUtilization` value.

Collection and publication are separate. Prove the value through the HAL,
OneWifi provider, translation, Agent CMDU, controller model and API rather
than concluding success from a populated `iw` counter alone. Exercise
threshold crossings upward and downward, periodic reporting, policy changes,
agent restart and an AP with no associated client traffic.

Existing source includes metrics transport and scan infrastructure; this is
integration/completion work, not a reason to replace OneWifi or EasyMesh.
No native load-balancing decision should be changed merely to make a new
demonstration appear to converge.

## 8. prpl implementation work

Repository paths below are relative to the prpl lab repository root.

| ID | Location / responsibility | Required work |
| --- | --- | --- |
| P01 | `patches/prplmesh/`; BWL `base_wlan_hal_nl80211::get_channel_utilization()` and underlying survey client | Consume a valid current-channel survey; preserve failure/empty/stale state through monitor and NBAPI |
| P02 | BWL `mon_wlan_hal_nl80211.cpp` | Replace radio-noise placeholder where a valid source exists; qualify associated SNR, counters and rates; audit no-op ESP setter |
| P03 | Agent `channel_scan_task.cpp` | Remove or explicitly test-gate the zero-to-10 workaround; preserve BSS-load presence and raw byte separately from local utilization |
| P04 | `manifests/hostapd-wlan*.conf`, `scripts/container/setup-nl80211-node.sh`, hostap build | Enable measured BSS-load updates once surveys work; explicit synthetic-test setting only in F1 mode; no uncontrolled restarts |
| P05 | Agent metrics tasks, controller link-metrics handling and NBAPI | Query/periodic/threshold reports, high-resolution time/sequence, empty-result semantics and restart recovery |
| P06 | `topology-adapter/server.py`, `optimizer/`, `demo/room_demo/` | Adapter currently passes `Radio.Utilization`; add availability/source/window, not a fabricated replacement value |
| P07 | Native scan/channel selection and backhaul handling | Verify actual enabled policy/capabilities; channel request acceptance is not proof of radio convergence |
| P08 | `patches/hwsim/`, `patches/wmediumd/`, `scripts/build-*`, `deploy/lxd-vm/` | Package the same common contracts and tests with independently reproducible prpl artifacts |

prpl's radio-per-band structure simplifies ownership but does not remove
BSS sharing, scan-state, retune or stale-result problems. Check all three band
workers and all four extenders, not just the colocated Agent.

The nl80211 backend is the assessed backend. Results must not be generalized
to other prpl hardware/HAL backends or to an independently certified device.
A certification-related workaround in source is not evidence that fabricated
RF values are suitable for optimizer profiling.

## 9. Optimizer and viewer integration

### 9.1 Desirable inputs in priority order

| Priority | Input | Useful decision | Guard against |
| --- | --- | --- | --- |
| First | Valid current/candidate RSSI/RCPI, direction, age and sample count | Link viability and steering eligibility | Comparing idealized candidates with stale associated samples |
| First | Local utilization, own TX/RX share, observation window | Congestion detection, AP/channel comparison | Equating foreign advertised load with local sensing |
| First | Client demand/goodput, retry/failure deltas | Distinguish a weak link from a busy AP | Byte counters mistaken for airtime; transport drops mistaken for RF |
| First | Backhaul signal, utilization, traffic and topology | Avoid moving a client behind an overloaded path | Treating strongest fronthaul as best end-to-end service |
| Next | Neighbor BSSID/channel/width/RSSI and optional BSS Load | Discover alternatives and corroborate congestion | Counting multiple BSSs on one physical radio as separate occupancy |
| Next | Per-AC queue/service delay and defensible ESP estimates | QoS-aware admission and steering | Filling ESP from an arbitrary scalar “free capacity” |
| Next | Independent noise/interference, CCA and channel preference constraints | Noise diagnosis and channel selection | Choosing an illegal, unavailable or backhaul-breaking channel |
| Later | Qualified width/NSS/PHY service capacity, MLO/link-specific metrics | Modern-radio capacity policy | Inferring physical performance from advertised capabilities |

Maximum SNR is not the optimization objective once real load is available.
A slightly weaker AP with spare airtime and a healthy backhaul can be better.
Conversely, an AP with few clients can be saturated by one slow/high-demand
station. For multihop paths, account for shared-channel airtime consumed by
multiple hops; taking only the smallest nominal link rate is insufficient.

Begin with explainable gates rather than an elaborate new scoring formula:
reject stale/ineligible candidates, require a viable target link/backhaul,
identify sustained overload, estimate whether moving the demand helps, then
apply hold/dwell/cooldown and verify the native outcome. Freeze policy settings
when comparing RF implementations.

### 9.2 Versioned observations and explicit policy ownership

Extend the shared snapshot model with radio/channel observations and BSS
references, rather than copying load into every client record. Backward
compatibility should retain the existing signal-only policy when load is
unsupported. Adding a field must not silently change all existing rooms.

Record one decision owner per run:

- Native optimizer profiling: room supplies stimulus; external steering and
  backhaul selection are disabled.
- External optimizer profiling: named policy consumes native observations and
  sends native requests; conflicting native automation is controlled explicitly.
- Field-handling test: synthetic values are allowed and labeled; performance
  conclusions are not.
- Manual demonstration: operator actions are recorded separately from policy.

The room's strongest-simulated-link overlay remains an oracle visualization.
It is not evidence that the optimizer received that candidate measurement.
Do not call a load-aware topology incorrect merely because a client is not
attached to its highest-SNR AP.

### 9.3 Presentation and latency attribution

Show signal and utilization as separate quantities. Reuse the established
signal colors for signal; do not make high channel utilization look like a
good green link. Show load numerically with its window, source and freshness.
Keep optimizer explanations stable enough to read.

For each change, retain timestamps for stimulus request, medium application,
sample window/end, HAL availability, Agent report, controller ingestion,
policy decision, native action, observed association/channel and rendered
frame. Track acquisition delay separately from policy delay and UI delay.
Monotonic clocks inside one VM are suitable for local durations; record clock
mapping/uncertainty when correlating hosts or packet captures.

Normal protocol timers, physical observation windows and intentional policy
holds are legitimate. Unbounded queues, artificial replay waits and accidental
serialization are not. “Instant” should mean bounded measured overhead,
not removal of every meaningful timing mechanism.

## 10. Phased delivery

Effort labels are relative: **S** is bounded adapter/configuration work,
**M** crosses components, **L** changes core model behavior. They are not
calendar commitments. Every phase ends with a working baseline and explicit
unsupported capabilities, not a partly enabled production experiment.

| Phase | Scope and dependencies | Owners | Effort | Exit gate |
| --- | --- | --- | --- | --- |
| 0: Truthfulness | Capability/validity contract, reproducible survey audit, failing unit fixtures for stubs/placeholders/rates; no RF behavior change | C01, R01 audit, P01-P03 audit | S-M | Zero/unknown/stale distinguishable; pinned evidence and baseline tests |
| 1: Reporting-only | Explicit fixed BSS Load test; native beacon/scan/report round-trip; availability and unit fixes | C09, R02-R04, P03-P06 | S-M | F1 field tests pass on both stacks; no congestion claim |
| 2: Measured airtime | C02-C04; fixed supported 20 MHz PHY, occupancy/wait separation, both HAL paths | Common plus R01-R04/P01-P05 | M-L | Idle/load/channel controls pass within one declared contention domain |
| 3: Credible contention | Visibility-aware scheduling, reverse ACK/receiver outcomes, interference power tests, truthful PHY metadata/service time | C05-C07, R05/P02 | L | Same-channel spatial reuse and asymmetric-link tests pass; no transport-error masking |
| 4: Load-aware policy | Native observations, client demand/backhaul costs, optional neighbor actors, reason reporting | C08-C10, R06-R07/P05-P07 | M-L | Both policies evaluated separately with traceable improvement and no oscillation |
| 5: Advanced RF | Calibrated HT/VHT/HE/EHT models, correlated fading, width/overlap, non-Wi-Fi energy; kernel-backend parity as separately justified | Common/platform specialists | L | Per-feature conformance and physical-reference comparison |

Phases 1 and the common development portion of phase 2 can proceed in parallel
after phase 0. Do not gate every small reporting fix on a complete PHY rewrite.
Conversely, passing phase 1 must never be described as passing phase 3.

**Smallest useful implementation:** phase 0, a fixed-value BSS-load round-trip,
then one AP/client load experiment with real common counters through each
native stack. Keep the default 20 clients and mesh roles. Reuse existing
traffic endpoints first; add one foreign AP/STA pair only when required.
No extra VM, full neighbor-room UI or long soak is necessary for this milestone.

A shared scenario and independent RDK/prpl runs are preferable to forcing both
systems to share a medium process. Run in parallel only after reserving enough
host CPU and memory. Host capacity is its own fixable issue, not a reason to
weaken RF or measurement correctness.

## 11. Correctness and performance qualification

### 11.1 Short test catalog

These are **proposed tests, not results from this assessment**. Start with
30-60 second observation phases after warm-up and a few repeat runs. Use
longer tests only when a specific timing/variance question requires them.

| Test | Stimulus | Required evidence |
| --- | --- | --- |
| RF01 Identity/context | Same BSSID lifecycle, multiple VAPs, separate bands, disabled/recreated radio | No cross-radio/channel contamination; epoch/reset correct |
| RF02 Idle and unknown | Quiet enabled AP; no provider; provider restart | Idle may include beacons; missing/stale never becomes measured 0 |
| RF03 SNR step | Fixed-rate traffic with low/high SNR and exact restoration | Applied generation precedes new samples; loss/signal respond consistently |
| RF04 Directed asymmetry | Strong forward data, weak reverse ACK, then swap | Retries/success follow both directions in the qualified ACK profile |
| RF05 Unit boundaries | Utilization 0/mid/full, valid/invalid RCPI, negative dBm, counter wrap | Native and displayed encodings correct; no reserved-value invention |
| RF06 Fixed BSS Load | Controlled advertisement with negligible application load | Beacon, scan and controller preserve fields; clearly F1, not measured congestion |
| RF07 Load ramp | Paced UDP low/high/off on a supported fixed PHY | Busy/demand/goodput trend consistently; window and service time match fixtures |
| RF08 Shared BSS | Private and IoT clients on one channel | One airtime budget; accurate distinct station counts; no double counting |
| RF09 Co-channel visible | Two mutually audible transmitter/receiver pairs | Appropriate contention, bounded busy and measurable service impact |
| RF10 RF-isolated co-channel | Same frequency, pairs unable to sense/interfere with each other | Spatial reuse; known current scheduler limitation until C06 |
| RF11 Different channel | Move second pair to nonoverlapping supported channel | No modeled cross-channel interference or queue serialization |
| RF12 Noise-only / hidden node | Constant desired power, raised noise; then hidden interferer | Distinguish RSSI/SNR/CCA/PER; conditional on C06-C07 |
| RF13 Scan and retune | Native off-channel scan and native channel change under light traffic | Valid dwell-only survey, no inherited old-channel load; service impact recorded |
| RF14 Reporting policy | Query, periodic interval, upward/downward threshold crossing | Correlated native CMDUs and timestamps; behavior survives agent restart |
| RF15 Candidate availability | Silent, transmitting, off-channel and RF-isolated STA | Idealized/reception-backed modes distinct; no false fresh passive sample |
| RF16 Overload/failure | Slow observer, saturated export queue, medium loss, netlink rejection | Fail closed; classify transport versus RF loss; bounded memory and recovery |
| RF17 Policy outcome | Busy strong AP versus viable quieter AP; overloaded backhaul; no better target | Explainable decision/no-action, traffic benefit where expected, no ping-pong |
| RF18 Existing rooms | Load each existing room, static then short movement, both backends' native topology views | Roster, steering, backhaul mode, signal and restoration regressions absent |

RF10 is deliberately a discriminator: it may expose the current coarse model,
not a controller bug. RF12 and advanced PHY cases are skipped as unsupported
until their dependencies pass, never silently marked successful.

### 11.2 Quantitative gates

Freeze traffic size/rate, PHY profile, channel width, RF matrix, CPU allocation,
observer settings and decision mode before measuring. Report offered and
achieved load; the host must be able to generate the requested traffic.

Proposed initial engineering targets, to be calibrated rather than represented
as achieved:

- Zero incorrect identity/epoch joins, unexplained counter resets, or accepted
  invalid samples; zero unclassified netlink/transport failures.
- Exact accounting against deterministic interval fixtures before statistical
  traffic tests. Specify the permitted time/encoding quantization error.
- Counter snapshot publication every 100-250 ms under the small supported
  profile, without a per-frame synchronous IPC exchange.
- No extra full-second polling delay in a newly implemented local adapter;
  report its p50/p95/p99 separately from the native reporting interval.
- Less than 5% throughput impact from the added observation path versus the
  identical RF model with observation disabled, when run variance is below
  that threshold. Otherwise report the comparison as inconclusive.
- Record medium scheduling lateness and export age at 25 RDK / 35 prpl active
  radios, with one and multiple readers. Fail the performance claim when
  host throttling/backlog prevents faithful timekeeping.

Do not demand equality between a short driver window and a longer beacon or
controller averaging window. Compare aligned intervals and account for byte
encoding and timestamp resolution. Reporting policy must still satisfy the
applicable EasyMesh version; measurement and reporting periods are not the
same knob.

Physical calibration is required before absolute “real-world capacity” claims:
use one supported hardware AP/STA setup at known conditions, compare RSSI
steps, rate selection, loss, service time and saturation, and document the
range where the model agrees. Without it, publish comparative results within
the declared virtual profile.

### 11.3 Completion evidence and release gates

For every work package retain compact machine-readable run artifacts outside
the reference tree: revisions, binary/module hashes, topology/roles, scenario
hash, seed, policy, raw/normalized samples, event timing, traffic and restoration.
The reference keeps conclusions and reusable acceptance rules, not raw logs.

Run existing configurator/model, medium self-test, HAL/provider,
optimizer/freshness, topology and room regression tests before packaging.
Rebuild hwsim/daemon/HAL only as required by the phase. Verify old/new ABI
rejection and a rollback to the signal-only baseline.

This assessment does not certify either lab. Protocol/reporting compliance,
measurement fidelity and optimizer quality require separate evidence. A
certified hardware product does not confer certification on a replacement
hwsim/HAL deployment.

## 12. Reproducing the audit and maintaining this document

### 12.1 Safe read-only checks

Run inside the outer lab VM; `lxc` there targets the inner AP containers.
These commands do not start a scan, change a channel, enable a monitor,
generate traffic or reconfigure policy.

```sh
uname -r
cat /sys/module/mac80211_hwsim/srcversion
modinfo -F srcversion mac80211_hwsim
cat /sys/module/mac80211_hwsim/parameters/kernel_medium
cat /sys/module/mac80211_hwsim/parameters/channels
```

RDK:

```sh
lxc exec bpibroadband -- iw dev wifi1 info
lxc exec bpibroadband -- iw dev wifi1 survey dump
```

prpl:

```sh
lxc exec prpl-controller -- iw dev wlan2 info
lxc exec prpl-controller -- iw dev wlan2 survey dump
lxc exec prpl-controller -- sh -c \
  'grep -nE "^(bss_load_update_period|chan_util_avg_period|bss_load_test)=" /etc/hostapd/wlan*.conf || true'
```

Empty survey output is not a zero-utilization observation. Match the returned
frequency to the operating context. Do not provoke a scan merely to populate
dummy records. Hostapd configuration inspection does not replace beacon
verification during phase 1.

### 12.2 Source map for future changes

| Component | RDK repository | prpl repository |
| --- | --- | --- |
| hwsim patches/build | `gen/hwsim/patches/`, `gen/hwsim/build-hwsim.sh` | `patches/hwsim/`, `scripts/build-hwsim.sh` |
| Medium patches/build | `gen/wmediumd/patches/`, `gen/wmediumd/build-wmediumd.sh` | `patches/wmediumd/`, `scripts/build-wmediumd.sh` |
| Geometry, compilation, actuation | `gen/wmediumd/configurator/wmdcfg/` | `wmediumd/configurator/wmdcfg/` |
| Console/protocol diagnostics | `gen/wmediumd/observer/` | `wmediumd/observer/` |
| Native HAL/reporting changes | `recipes-ccsp/hal/`, `recipes-ccsp/ccsp/`, `recipes-ccsp/unified-wifi-mesh/` | `patches/prplmesh/`, `scripts/container/`, `manifests/` |
| External optimizer | `gen/optimizer/optimizer/` | `optimizer/optimizer/` |
| Room orchestration | `gen/demo/room_demo/` | `demo/room_demo/` |
| Documentation validation | `gen/tests/test_documentation.py` | `tests/test_documentation.py` |

For E07 inspect the assembled patched source, especially
`wmediumd.c:queue_frame`, `send_cloned_frame_msg`,
`wmediumd_deliver_frame`, `model_rate_idx`, `per.c`,
`control.c` and `control.h`. Upstream source alone omits lab changes.
For E05 inspect `mac80211_hwsim_get_survey`, scan record writers and the
optional kernel-medium counter updates.

Keep this page as the capability/gap assessment. The
[neighbor-room proposal](../proposals/neighbor-rooms/design.md) owns foreign-AP
scenarios and discovery/contention fidelity levels; it does not replace the
lower-layer measurement work here. Treat old proposal observations as
historical unless rechecked against the pinned implementation.

When a phase lands, replace the relevant proposed item with its implemented
contract, source pointer and compact validation summary. Remove superseded
claims rather than appending another dated report. Update both mirrored copies
and both radio indexes; preserve independent release/build instructions.
