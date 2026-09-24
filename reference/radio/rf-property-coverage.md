# RF property demonstration coverage

[Radio reference](README.md) · [Room catalog](../rooms/catalog.md) ·
[Field guide](console-rf-properties.md)

This is the maintained shared property-to-room contract, not a declaration that
every room or daemon mode is live-qualified. The complete property inventory
is `PROPERTIES` in [rf_observations.py](../../optimizer/optimizer/rf_observations.py).
[rf_coverage.py](../../optimizer/optimizer/rf_coverage.py) adds named
rooms, machine-readable check categories and expectations to both generated
catalogs and the room catalog API. Coverage tests require exact property-set
equality, signed existing rooms and this document. A catalog entry neither
activates a policy nor provides a measurement.

## Evidence and policy contract

Default signal policy is unchanged. It consumes fresh serving/candidate RCPI,
eligibility, identity, dwell, gain, hold, cooldown and observed ownership.
RDK ordinary same-band candidate RCPI currently comes through native reporting
from the HAL's configured-matrix lookup; it is not independent reception.
Received-scan profiles instead require fresh AP→client passive reception.
Geometry, intended APs, room names, traffic schedules and modeled busy time
never select a target. Presence can remove eligibility; it cannot manufacture
native ownership or a successful association.

The RF inspector separately reports whether load policy and the native counter
guard are configured. Configuration does not prove decision use: weak-signal
rescue bypasses load balancing. Individual decision evidence and native counter
shadow checks distinguish these cases.

Native load remains explicitly enabled by a policy file. Verified inventory,
provider epoch, BSSID/device/radio/channel context, ownership floors and
bounded counter windows remain required. Missing or stale is unavailable,
never idle. Native AP report timestamps identify receipt, not a known
measurement window. A report visible with unverified inventory is inspection
only; it cannot become a typed policy load sample. Retunes, reassociation,
provider replacement, counter resets and implausible deltas invalidate the
affected windows. Existing native path validation rejects unknown parents,
cycles and conflicting topology; room geometry never fills a missing hop.

The new optional [counter-guard policy](../../optimizer/configs/load-counter-guard-policy.yaml)
requires `load_aware_enabled` and `load_counter_guard_enabled`. For an otherwise
overloaded strong serving link it checks three native AP counter rates:
retries ≤100/s, TX failures ≤10/s and RX drops ≤10/s by default. These are
configurable conservative experiment limits, not calibrated RF thresholds.
All three counters must exist; zero and equality with the limit are valid.
Activity must match the current load transport, owner and provider epoch,
remain within five seconds and satisfy the configured report skew. The
guard adds `counter_checks` and actual sample values/times to decision
evidence. Bytes/s remains observational. It never divides retries by combined
TX/RX packets, adds TX and RX errors into a loss fraction, estimates capacity,
or claims that a quieter target fixes reverse-link impairment.

| Condition | Expected decision/check |
| --- | --- |
| Missing, stale, future, wrong-owner or wrong-epoch activity | `native_load_activity_unavailable`; no balancing |
| Activity transport or report skew mismatch | `native_load_activity_context_mismatch`; no balancing |
| Any retry/TX-failure/RX-drop rate unavailable | `native_load_counter_evidence_unavailable`; no balancing |
| Any measured rate exceeds its configured limit | `native_load_counter_pressure`; no balancing, reset hold |
| Current utilization below threshold | `native_load_current_acceptable`; no balancing; counters need not be queried |
| Idle client | `native_load_client_idle`; no balancing |
| Same radio/channel, busy/weak target, extra/unknown wireless hops, stale/skewed/foreign-epoch target | Excluded with individual reasons in `candidate_assessments` |
| Safe target and good counters persist | Normal load hold; both AP reports and the counter report must advance past its start |
| All load gates and sustained hold pass | `native_load_margin_hold_satisfied`; one client per batch, then settling and native verification |
| Weak serving link | Existing signal rescue and its guards; high counters do not suppress rescue |

Selecting a room alone does not enable this policy. The checked-in
[native-counter-guard-room-profile manifest](../../demo/manifests/native-counter-guard-room-profile.json)
selects `rf-asymmetric-ack`, its real client binding and the opt-in policy.
Stop the room service before operating it; never start a second actuator:

```sh
demo/room-demo interactive --mode recommend --profiling \
  --manifest demo/manifests/native-counter-guard-room-profile.json
```

On exit, restart the unchanged room service for default signal-only operation.
Received-band profiles retain their existing
received-signal policy with load and counter guards disabled. Counter pressure
and unavailable evidence cannot mark the load fleet converged. A live
positive load move still requires a separately prepared different-channel
target; these rooms never retune a radio.

## Property inventory

Every row specifies a named stimulus, expected optimizer behavior or explicit
observation/abstention check, and the evidence boundary. Check categories are
metadata for these contracts, not a claim of automatic live qualification.

| Property | Stimulus and named rooms | Inputs and expected decision/no-action check | Observe and limitation |
| --- | --- | --- | --- |
| `rcpi` | `received-same-band-roam`, `home-a-border-hover`: movement and sustained/marginal gain | Fresh eligible received/current RCPI, gain and hold; missing/stale samples abstain; small gains hold | Native BSSID plus decision source/time; receiving direction and synthetic HAL candidates remain distinct |
| `configured_snr` | `rf-asymmetric-ack`: station transmit-gain offset | Diagnostic only; read back both directions at the exact frequency and same daemon generation; never use room target truth | Room RF inspector / Console RF matrix; pair fallback and exact-frequency override differ |
| `received_signal` | `rf-asymmetric-ack`, `received-same-band-roam`: directional reception | Last medium signal is observation only; received-profile policy requires its own fresh native scan | Console Traffic dBm/SNR and scan source/time; last packet may predate current matrix |
| `noise_reference` | `home-a-stationary`: baseline model | Observe compiled −91 dBm profile; no noise/power action | Console Services; fixed reference, not independently measured noise |
| `cca_threshold` | `received-discovery-recovery`: fronthaul visibility loss/return | Observe compiled −90 dBm threshold and classified CCA drops; no threshold steering/control | Services and selected Traffic; no adjustable or calibrated CCA model |
| `noise` | `home-a-stationary`: negative control | Explicit `unsupported`; never infer noise by subtracting SNR from signal | Catalog/field-state contract; no independent noise observation or noise generator |
| `native_utilization` | `traffic-low-high-off`, `traffic-quieter-ap`: bounded offered UDP | Opt-in native utilization byte, activity, signal and path gates; same-channel targets abstain | RF Native observations and decision evidence; offered bitrate does not guarantee overload |
| `station_count` | `home-a-flash-crowd`: 10→20→10 clients | Observe native per-BSS count after ownership settles; count never substitutes for load or chooses AP | AP Metrics and topology; pool size differs from associated population; do not sum radio utilization per BSS |
| `beacon_utilization` | `rf-packet-size-counters`: two real UDP phases | Observation only: require fresh received BSS Load IE, exact source/receiver/frequency and successful receive evidence; absent IE stays unavailable | Selected Console Load/Traffic; AP Metrics alone does not prove a beacon IE or reception |
| `modeled_busy` | `traffic-low-high-off`: low/high/off | Observe nonnegative identified active/busy windows; no direct ranking or capacity inference | Console global channel and radio-local survey; distinct scopes, background frames persist when experiment is off |
| `packets_per_second` | `rf-packet-size-counters`: equal offered bitrate, different payload sizes | Native owner/epoch-matched bounded delta window gates activity in load policy; reset/stale/idle abstain | Native rate/window and traffic results; aggregate AP TX+RX events are not attempts or offered packets |
| `bytes_per_second` | `rf-packet-size-counters`: 256 vs 1200-byte datagrams | Observation only, with native byte-unit conversion and same window/owner safeguards | Native deltas and independent sender/receiver results; not application goodput or capacity |
| `retries_per_second` | `rf-asymmetric-ack`, `rf-packet-size-counters`: directional impairment and control | Optional counter guard checks absolute native AP retry rate; missing abstains, excess vetoes balancing | Native counters and medium ACK/no-ACK separately; retransmissions not guaranteed, no invented retry fraction |
| `tx_errors_per_second` | `rf-asymmetric-ack`: same stimulus | Optional counter guard checks native AP TX failure rate; zero valid, unavailable abstains | Native counter windows; different boundary from medium receiver drops |
| `rx_errors_per_second` | `rf-asymmetric-ack`: same stimulus | Optional counter guard checks native AP RX drops; never substitute zero for unavailable | Native counters; dropped received packets do not count all unseen over-the-air frames |
| `backhaul_hops` | `backhaul-branch-formation`, `backhaul-isolation-recovery`, `traffic-quieter-ap`: parent opportunity/outage/load comparison | Native valid path required; load rejects unknown/additional wireless hops, no geometry-based parent assignment | Shared backhaul explanation, actual uplink BSSID and traffic; repeated frequency is contention risk, not additive capacity |
| `receive_context` | `received-discovery-recovery`: lost and rediscovered beacons | Fresh exact-frequency receive evidence qualifies candidates; not-received/stale abstains, no modeled fallback | Passive scan ID, age, source and rejected BSSID; maintained context may be historical activity |
| `room_presence` | `home-a-disappear-reappear`, `received-discovery-recovery`: offline clients/fronthaul | Exclude absent roles; returning presence requires fresh native evidence before use | Room identity/epoch, disconnect status, topology and BSSID; exclusion neither destroys radios nor guarantees silence |
| `frequency` | `band-upgrade-24-5`, `band-upgrade-5-6`, `traffic-quieter-ap` | Native band/channel and capability eligibility; retune floors discard old context; same-channel load targets excluded | Actual frequency/BSSID, AP context and directed override; AP name alone cannot prove a band change |
| `channel_width` | `rf-packet-size-counters`: unchanged configured contexts | Observe configured native width; survey qualification is legacy 20 MHz; unsupported widths stay unavailable | Console Load/profile; wider configured channels do not prove calibrated bonded PHY behavior |
| `packet_types` | `rf-asymmetric-ack`, `received-discovery-recovery`: ICMP/ACK, beacon and discovery frames | Observation only: bounded selected header/subtype counters; no policy from frame class | Selected Traffic management/data/control, EAPOL and fan-out; receiver candidates differ from injections, header history starts at selection |
| `frame_loss` | `rf-asymmetric-ack`: strong forward/weak reverse opportunity | Observation only: distinguish PER, CCA, off-channel, no-receiver and ACK outcomes; no loss-truth target selection | Console Traffic and independent echo replies; last PER is not interval loss; counters have different boundaries |
| `queue_delay` | `rf-packet-size-counters`: differing offered datagram rates | Diagnostic queue/deadline/netlink observation only; host scheduling delay never becomes low RCPI | Console Summary/Services; host cost is not calibrated physical latency or EDCA |
| `active_rf_modes` | `home-a-stationary`, `rf-packet-size-counters`: idle/activity baseline | Read actual daemon mode flags; disabled fading/interference/visibility/priority means that mode is not exercised | Services/profile; compiled capability alone does not prove activation or qualification |
| `physical_capacity` | `rf-packet-size-counters`: explicit negative control | `unsupported`; no policy capacity score and no throughput claim from a band/rate label | Separate offered, sender actual and receiver goodput; modern PHY capacity unqualified |

## Source properties beyond the catalog

The field guide and daemon contain sub-properties grouped by the catalog.
These must also retain named observation checks, including disabled modes.

| Sub-property/source | Room stimulus and expected check | Boundary and regression coverage |
| --- | --- | --- |
| Distance, path-loss exponent, per-band reference, walls, seeded shadowing; world compiler and geometry model | `home-a-one-client-handover`, `home-a-asymmetric-link`, `home-a-stationary`: verify signed deterministic matrices and wall/direction changes; policy uses reports, never coordinates | Not ray tracing, multipath or Doppler; configurator world/geometry tests |
| Per-node transmit gain | `rf-asymmetric-ack`: only station→AP links change by −45 dB, clipped at the model floor; reverse remains unchanged | Scenario SNR offset, not HAL TX-power control; new exact directional compiler contract |
| Pair fallback, per-frequency overrides, generation, VIF aliases/ownership | `band-upgrade-24-5`, `received-discovery-recovery`: exact-context readback and real ownership; stale/wrong context abstains | Frequency-control, VIF and observer tests; no inference from MAC aliases alone |
| Legacy rate, frame length, PER, forward delivery and independent reverse ACK | `rf-packet-size-counters`, `rf-asymmetric-ack`: selected length/rate/PER and ACK/injection observations | Medium patches 0021/0022; selected detail tests; no modern PHY rate or guaranteed failure-rate claim |
| Optional fading coefficient, per-frequency interference, SNR/error-probability/path-loss daemon modes | `home-a-stationary`, `rf-asymmetric-ack`: record actual profile; zero/disabled is the negative control, enabled outcomes require separate evidence | Patch 0033 profile; Console tests; rooms do not enable daemon modes or model thermal noise/spectral leakage |
| Global occupancy, radio-local active/busy, survey provider/epoch, synthetic utilization fixture | `traffic-low-high-off`, `traffic-quieter-ap`: distinguish actual modeled-airtime provenance from `synthetic-field-test`; fixture load cannot qualify policy | Survey/provenance tests; fixture tests field encoding only, not congestion |
| Visibility reservation/spatial reuse (`-F`) | `traffic-quieter-ap`: observe actual enabled flag and local/global survey scopes; disabled mode is observation-only | Patches 0023/0025 and RF spatial tests; no receiver-local collision/capture physics |
| Access category/priority admission (`-Q`), queue heads, scheduler deadlines/netlink rejection | `rf-packet-size-counters`: differing packet-rate stimulus; inspect enabled flag, category, queue and infrastructure counters | Patches 0026–0031 and scheduler/latency tests; no WMM admission, calibrated EDCA or guaranteed latency |
| Multicast fan-out, management/control/data, EAPOL, selected-window lease and ring overwrites | `received-discovery-recovery`, `rf-asymmetric-ack`: observe discovery/echo traffic within selected-window budget; missing history remains missing | Patch 0032 and Console detail tests; no payload capture or assumption that every modeled ACK is captured |
| Beacon station count, utilization, available admission capacity | `rf-packet-size-counters`, `home-a-flash-crowd`: fresh received IE and exact context; capacity stays diagnostic in 32 µs/s units | Console BSS Load parsing tests; AP Metrics is not beacon proof; no ESP/free-bandwidth inference |

Source anchors are the [world compiler](../../wmediumd/configurator/wmdcfg/world.py),
[native load provider](../../optimizer/optimizer/load_observer.py),
[load policy](../../optimizer/optimizer/load_policy.py),
[medium patches](../../patches/wmediumd/) and
[field guide](console-rf-properties.md). Independent TX power, noise and CCA
controls, adjacent-channel spectra, receiver collision/capture, MIMO,
OFDMA/MLO and calibrated HT/VHT/HE/EHT capacity remain unsupported. Named
negative controls make these omissions visible; they do not simulate them.

## New room procedure

Both new rooms retain five APs, ten already-bound clients, fixed protected
backhaul, unchanged channels and a 30-second script. The compact golden files
need only start/end geometry frames; playback still advances each second and
runs the intermediate traffic phases. Start paused and let ownership/metrics
settle. Select `sta_static_03` in the RF inspector, then play at 1×.

- `rf-packet-size-counters`: 1 offered UDP Mbps, 256-byte payloads at 5–13 s,
  off at 13–15 s, 1200-byte payloads at 15–23 s, then off. Compare actual
  sender/receiver records and native packet/byte windows. Smaller payloads
  request more datagrams; setup, background traffic and report windows prevent
  an exact ratio requirement. Off stops experimental traffic, not beacons.
- `rf-asymmetric-ack`: a −45 dB station transmit-gain offset across all bands;
  30 ICMP echoes/s, 1200-byte payloads at 5–23 s. Verify forward/reverse applied
  SNR, then correlate real ACK/no-ACK, AP counters and replies. The exact retry
  rate is stochastic; zero is a valid observation. Missing native counters
  cannot qualify the counter guard. Ending playback does not remove the gain;
  loading Default restores the original RF.

## Native counter pressure qualification

The initial asymmetric room produced partial echo delivery but zero AP
retries/TX failures/RX drops. This is not a Banana Pi HAL mapping stub:
`rdk-wifi-hal/platform/banana-pi/platform.c:1179` maps
`NL80211_STA_INFO_TX_FAILED`, `RX_DROP_MISC` and `TX_RETRIES` to
`cli_ErrorsSent`, `cli_RxErrors` and `cli_RetransCount` respectively.
OneWifi `source/apps/em/wifi_em.c:363` copies these into STA traffic stats;
`source/webconfig/wifi_easymesh_translator.c:1966` exports errors/retransmissions.
`optimizer/load_capture.py` decodes native TLV `0xA2`; `load_observer.py`
derives bounded deltas, not medium counters. Paths/lines identify the inspected
RDK 6.1 build sources; the wifi-emulator platform is not this active HAL.

The medium's `0022-wmediumd-independent-reverse-ack.patch` uses rate index zero
and a ten-byte reverse ACK. The room's approximately 5 dB near-AP reverse SNR
can still carry that robust ACK while long uplink data is lost. Frames never
injected into the AP need not increment kernel RX drops. Held reverse-loss
mode remains unsupported/unqualified; this experiment adds no native
counter-mapping patch.

The bounded [native counter acceptance](../../tests/native-retry-counter-acceptance.py)
adds stronger supported *pulsed* downlink/ACK impairment on the currently
associated Default client, independent of room geometry. It compares kernel
and native deltas, confirms ownership before/after each trial, restores exact
frequency overrides and restarts the unchanged room service:

```sh
PYTHONPATH=optimizer:wmediumd/configurator python3 tests/native-retry-counter-acceptance.py \
  --stack prpl --yes-change-lab --seconds 8 \
  --shadow-counter-policy optimizer/configs/load-counter-guard-policy.yaml \
  --output /tmp/native-counter-shadow-new
```

Shadow checks replay consecutive actual native reports at receipt time through
the **same** counter evaluator used by load policy. They retain message IDs,
monotonic windows, raw deltas, transport, actual medium instance and association.
No utilization, RCPI, hop count or target is invented. `clear` means only
counter eligibility; `pressure` vetoes load balancing. This is not a complete
load-steer qualification or proof that a quieter AP repairs the impairment.

The helper records counter qualification, RF/association/service restoration
and final room health separately. Its bounded read-only health check must
recover the initial expected client count; starting a service alone is not
proof of healthy ownership. The tested association is checked before resuming
the room optimizer, which may legitimately steer afterward.

RDK demo-a follow-up (not prpl qualification) observed kernel-matched ACK-loss deltas of 1,229 retries
and 63 TX failures; a native 157/s retry window exceeded the unchanged 100/s
limit. Data-loss also produced pressure; baseline/recovery checks were clear.
RX drops remained zero; its positive-pressure case is unit-only. TX failures
were nonzero but below the configured 10/s veto. Raw evidence is retained in
`test-results/rdk-rf-counter-followup/native-2.json` in the RDK checkout.
The prpl backport passes focused offline contracts and five GET-only RF access
checks. Both new rooms also pass playback, all seven required fresh native
properties, traffic phases and Default restoration in the bounded rerun.
Initial startup/preflight and a first 10-client settle failed their unchanged
deadlines; those failures remain recorded. The native model subsequently
recovered without forced associations or another controller restart. This is
not a diagnosed fix for that intermittent convergence delay.

Separate prpl qualification now passes four eight-second trials through its
native broker/HAL. ACK impairment produced 1,042 retries and 57 TX failures,
exactly matching kernel deltas. Native retry rates reached 145/s, exceeding
the unchanged 100/s guard; data loss also produced pressure, while baseline
and recovery remained clear. All 2,517 actual ACK-trial datagrams arrived.
RF overrides, association and healthy paused Default-20 were restored.
Evidence: `test-results/rf-backport/prpl-counter-shadow-1.json`.
Prpl RX drops stayed zero and TX failure rates remained below their veto:
those positive-pressure cases are not live-qualified.

## Native ownership reporting repair

A later Default preflight correctly failed at 18/20. Both missing clients were
physically associated to Ext-4's 5 GHz BSSs. The native station database also
marked them connected to those BSSs, but their NBAPI paths were empty.
The old recovery gate required infrastructure loss, which a successful
association clears; an older association-age snapshot could not repair the path.

Native patch 0029 republishes only an already-connected, same-owner station
from a fresh matched topology query newer than its association event. It
retains the departure barrier and never uses room geometry, forces a roam,
or resets the native association event/counters. Matching-owner metrics
explicitly request reconciliation for a missing path; otherwise a stable
station can wait indefinitely for an unrelated topology query. The request
is batched once per metrics message and is not itself ownership evidence.
Compiled positive and
original-code negative controls cover stale/unmatched queries, wrong owners,
missing BSSs, departure and failure. This is separate from memory patches
0026–0028. Initial failures remain evidence, not retroactive passes.

## Native load action qualification

The `rf-actions` suite section runs three separate bounded cases on healthy
paused Default-20: guarded load balancing, retry-pressure suppression with an
otherwise eligible quieter target, and weak-signal rescue despite pressure.
Use `tests/load-policy-acceptance.py --help` for direct diagnostics.
The optional `--policy` selects the checked-in counter-guard policy;
`--counter-case clear|pressure|rescue` selects the case.

Only the target private 2.4 GHz radio changes channel. Real UDP demand and
read-back-verified pulsed downlink loss provide stimuli, never fabricated
native utilization/counters. Thresholds and hold times remain unchanged.
The driver requires fresh native evidence, captured source/target-specific
BTM transitions, native ownership and receiver data after verified steering.
Pressure must veto an otherwise safe target. A non-actuating shadow evaluates
the identical native snapshots with only the counter guard disabled; it must
complete the unchanged ten-second load hold and propose that same target while
the real policy vetoes for fresh counter pressure. The shadow never submits
commands or advances an unexecuted proposal to pending. Intermittent pressure
resets the real policy's hold; continuous pressure for ten seconds is not a
policy requirement. Missing evidence or insufficient load cannot pass.
The subject must remain on the source AP throughout the negative window;
disappearance or an uncommanded roam fails rather than counting as a veto.

The action deadline and the following twenty-second settling observation are
separate bounded windows. Cleanup restores channel, exact RF overrides,
client frequency lists/associations, owned traffic/routing and room service;
fresh Default-20 and unchanged native process identities are required.
Stopping the room restores the full provisioned pool: saved setup snapshots
contain 100 native clients, not twenty. Only two generate the explicit unicast
workloads. New reports expose `native_clients_at_workload_setup`; this is not
an isolated two-station RF environment.
Detailed JSON/JSONL remains in guest `test-results/rf-actions-*` when run by
the suite. Earlier failed runs remain separate evidence.

### Current action evidence and remaining gates

The original full prpl suite failed pressure and did not attempt rescue; its
report remains unchanged. Bounded repeats are under
`test-results/qualification-repeat/`. The earlier 512-byte pressure fixture
does not repeat reliably: one fresh veto is followed by clear counters and a
legitimate load-steer proposal. The harness refuses that proposal before
actuation; this is insufficient stimulus, not a demonstrated policy failure.
Two consecutive 1400-byte pressure repeats pass with 14/15 causal witnesses,
no BTM, unchanged source ownership, 20.02/20.00-second settling and 5,179/5,127
delivered downlink datagrams. The suite now uses 1400-byte CS6 downlink packets
for pressure only; rescue retains 512 bytes and passes again, with a 5.041-second
signal hold and 2.033-second native target verification.
Both retain two offered 12-Mbps, 1200-byte uplinks, 300 offered source-AP
broadcasts/s and 250-ms alternating 2-dB/healthy RF. Actual throughput is recorded
and can be substantially lower than offered demand; requested rates are not
measurement evidence. Rescue uses a usable 32-dB serving link.
Read-only AQM/Console NG samples confirm TID7/voice traffic; PHY retry-rate
chains were not captured. No native counter, utilization, policy threshold or
PHY-rate mask is injected. Both cases restore Default-20, fresh metrics and
unchanged native identities. This is bounded qualification, not a new suite pass.

These bounded diagnostics preserve production policy thresholds and are not
clean-source release acceptance. Clear-case suite traffic uses
two real 12 Mbps senders with 1,400-byte payloads; actual native occupancy,
not requested traffic, determines eligibility.

| Case | RDK | prpl |
| --- | --- | --- |
| Clear counters, quieter different-channel target | Latest bounded run passes using actual source-AP broadcast traffic: utilization 213 versus target 9, unchanged ten-second hold, clear counters, captured BTM, 3.419 s native verification, post-steer traffic and fresh Default restoration. Earlier native HTTP 504 failures remain retained. | Pass: utilization 213→16, RCPI 148→144, matching BTM, 0.681 s native verification, 74 positive post-verification receiver intervals and 20.68 s settling. |
| Retry-pressure veto | Earlier pass: utilization 241/11, 182 retries/s, three causal vetoes, no BTM and 21.99 s settling. Latest two-hop repeat fails stimulus qualification; see below. | Two 1400-byte repeats pass: first qualified source/target loads 215/13 and 210/14, retries 128/s and 132/s; 14/15 causal vetoes after the unchanged shadow hold, no BTM and twenty-second settling. The 512-byte repeat fails stimulus qualification. |
| Weak-signal rescue during pressure | Latest repeat passes: RCPI 102→144, 7.849 s observed hold against the unchanged five-second minimum, matching BTM, 3.489 s target verification and 20.25 s settling. | Repeat passes: RCPI 102→144, unchanged 5.041 s signal hold, matching native BTM, 2.033 s target verification and 20.56 s settling. |

All action runs restored RF, channels, associations and Default-20 without
native process changes. prpl's subsequent 90-second traffic/memory check,
after 20 seconds warm-up, measured zero controller or fronthaul RSS growth:
controller 43.07 MiB, fifteen fronthauls at most 14.36 MiB. This check had
20 active clients, not a new 100-client qualification.

Earlier raw evidence is under `test-results/guarded-load-followup/` in each checkout.
`rdk-clear-2-read-only-audit.json` replays the saved decisions and hashes the
original evidence; it is not a fresh rerun. Initial passes are under
`test-results/qualification-followup/`; their repeats are under
`test-results/qualification-repeat/`. No threshold is lowered, no load is
fabricated, and an uncommanded roam cannot pass. Bounded passes do not
constitute an all-green regression suite.

RDK's new `qualification-repeat/qualification-repeat-pressure-2/` fails
stimulus qualification: load peaks at 204/255 but never yields a fully held
unguarded opportunity. Its source now has two native backhaul hops rather
than one in the passing trial, with a one-hop target. No BTM is submitted;
Default-20, RF and native identities restore correctly. This is not proof of
a policy regression or a controlled latency comparison; host contention and
path differences remain confounders, not established causes.

RDK rescue first verifies native reassociation in 2.717 seconds, then fails
immediately on a post-steer admission refusal. The common action driver now
uses the room's one-second bounded retry for explicitly unsubmitted RDK
`Error_Not_Ready`/`Error_Prev_Cmd_In_Progress` requests and records that budget.
Generic 503s, partial completion and 504s remain failures; policy and observation
gates are unchanged. The next RDK repeat passes at 3.489-second verification
and 20.25-second settling, with complete fresh evidence first sampled after
16.856 seconds. Its 49 queries encounter no busy response, so live recovery
through that retry branch remains unproven despite passing unit coverage.
prpl's provider and workload timing are unchanged by this RDK-specific option.

## Room catalog qualification and open failures

The latest bounded room campaign checks **24 ordinary rooms plus three
geometry/backhaul rooms** on each stack. Ordinary rooms exercise load, initial
policy convergence, Play, native associations/traffic and the two browser views.
Passing the configured steering policy does not mean every client must be on
the mathematically strongest AP: hysteresis, eligibility and dwell still apply.

| Gate | RDK | prpl |
| --- | --- | --- |
| Ordinary catalog | September 23: 22/24 passed. `received-discovery-recovery` retained an association in an outage sample; `rf-packet-size-counters` rejected a one-datagram receiver/sender byte discrepancy despite zero receiver loss. Both rooms passed initial/final convergence. The accounting discrepancy needs investigation, not an assumption of packet loss. | September 23: 19/24 passed initially. All five loading failures pass a targeted load/Play/final-convergence rerun after the client executable-path fix, with unchanged native identities and healthy Default restoration. This is combined evidence, not one clean full-catalog pass. |
| `backhaul-branch-formation` | Feature checks and native branch/return recovery passed. | Passed. |
| `backhaul-parent-handover` | Feature checks and native parent changes/return recovery passed. | Passed. |
| `backhaul-isolation-recovery` | Upstream outage was observed, but midpoint convergence failed; Default recovery was not verified within the unchanged 60-second gate. Native identities remained unchanged. Later suite world-switch/restoration and full-scale health checks passed. | Passed, including the geometry campaign's recovery check. |

The newer RDK `targeted-suite-repair/geometry-hal-warm/report.json` passes
all three geometry rooms together after enabling the beacon-preserving HAL,
including Default restoration and unchanged native identities. Its earlier
cold attempt still failed initial candidate coverage. These targeted passes
supersede the isolation diagnosis, not the original failed suite result.
`targeted-suite-repair/rf-rooms/report.json` also passes both failed ordinary
RF rooms through load, Play, checkpoints, native/view convergence and Default
restoration, with unchanged native identities. This is not a full-catalog rerun.

Newer RDK `cold-metrics-followup/` repeats remain red: the branch run reaches
initial convergence, then loses all four backhaul station links during Play
while APs remain operating. Isolation and parent-handover stop before Play at
9/10 and 8/10 candidate-complete clients; both restore Default successfully.
Native identities remain unchanged. Native admission 503s and transport 504s
are recorded separately. This does not invalidate the earlier warm passes,
but prevents claiming repeatable three-room acceptance; no native threshold,
RF geometry or convergence deadline is weakened to pass the rerun.

The prpl ordinary-room loading failures affect `band-ap-counter-roam`,
`band-upgrade-24-5`, `band-upgrade-5-6`,
`received-discovery-recovery` and `received-same-band-roam`.
The lean client image installs its patched `wpa_cli` in `/usr/local/bin`, but
the namespace helper's fixed PATH omitted that directory. The corrected fixed
PATH searches trusted local-system directories before distribution binaries;
it never inherits the host PATH. Namespace identity, PID/start-time and
mount/net/PID/root/working-directory checks remain. The five rooms load in
4.1–9.5 seconds in the bounded rerun; that is load completion, not total
scenario or steering latency.

Both browser drivers now await completed fullscreen entry/exit. This prevents
selecting the hidden Play button or toggling fullscreen back on during cleanup.
The original prpl catalog also failed restoration through that harness race;
a separate restoration receipt and targeted rerun record recovery. Original
reports are not rewritten as passes.

Latest evidence under each checkout's `test-results/`:

- RDK: `20260923T210503Z-demo-a/` — 81 passed, six failed, one skipped.
  Full-scale VM check, health, both steering cohorts and world switching pass.
  Other failures are steering-cue expiry, counter-manifest echo delivery,
  guarded-load source/target preconditions and the soak's candidate-RCPI
  preflight. That soak ran zero churn workloads; its missing diagnostics are
  fixed. An explicit 100-client preflight repeated after the native query fix
  passes in 154.755 seconds: both full health gates, traffic, RCPI and process
  identities, without claiming a soak pass. Default-20 returns converged.
  Browser cue expiry now passes ten offline repetitions per stack: immediate
  removal plus one animation-frame relayout replaces repeated synchronous
  layouts. The six-second lifetime and eight-second assertion are unchanged.
- prpl: `20260923T204713Z-demo-prpl-cow/` — 91 passed, two failed. The new
  report accounting will additionally expose the unrun rescue as blocked.
- prpl room rerun: `prpl-suite-repair-band-20260923/report.json` — five passed,
  Default restored, native identities unchanged. This uses a working-tree
  runtime fix and is not clean-source release acceptance.
- prpl `targeted-suite-repair/pressure-neighbor/report.json`: independent
  co-channel traffic peaks at 173/255, below the unchanged 192 threshold;
  that attempt did not qualify pressure or rerun rescue. Channels, RF,
  ownership, fresh twenty-client metrics and native identities restore correctly.
- RDK `targeted-suite-repair/`: counter-manifest and guarded clear pass.
  Independent pressure workload peaks at 124/255; it does not qualify a veto.

Older failed evidence stays under `guarded-load-followup/`; newer passes do
not rewrite those reports. The previous prpl post-isolation inventory failure
did not recur in the new VM's full geometry campaign.

### Next build and test gates

1. Commit and synchronize matching test/runtime sources before clean-suite
   qualification. The prpl executable-path fix does not require new native
   artifacts or a VM rebuild; do not bypass the suite's source-match gate.
2. Recheck the affected ordinary rooms after synchronization. The current
   full-scale baselines already pass; no repeated full build or soak is needed
   merely to investigate these bounded failures.
3. Recheck RDK cold candidate completeness; its new terminal-response contract
   reports partial results promptly but does not create missing measurements.
   Browser-expiry and full-roster
   preflight now pass bounded checks, not a new catalog or soak campaign.
4. Keep the repeat-qualified prpl pressure fixture (1400-byte voice, 300 offered
   broadcasts/s) separate from rescue (512 bytes); both retain native evidence
   and unchanged policy gates. Recheck RDK pressure/rescue repeatability.
   RDK pressure uses 1400-byte voice packets and 1000 broadcasts/s; its rescue
   uses 512-byte voice packets and 500 broadcasts/s. Production policy is
   unchanged; different native stacks need not share one traffic stimulus.
5. Only after those gates, qualify optional medium visibility `-F` and priority
   `-Q` modes separately. Both deployed binaries passed their isolated `-T`
   selftests, but those do not enable or live-qualify either mode.

The new checkpoint and optional remote-access tooling do not fix these remaining
native/fixture issues. Full-suite failures remain visible; no known-failure
exemptions, longer convergence windows or relaxed assertions are added here.

## Cold room initialization

The first-switch failure was separate from native memory and model-path bugs.
Initializing 3,060 frequency overrides used a cubic free-slot search inside
wmediumd's single event loop. Console telemetry recorded a 2,669,387 µs
control handler. Clients lost beacons before room switching; APs retained
old authorized peers after the clients had already disconnected. A later
`wpa_cli disconnect` cannot notify an AP the client has already lost.
Startup and Default reload generate identical RF values; intended geometry
was not the cause, and filtering native topology would hide the failure.

Shared medium patches (prpl 0035 / RDK 0034) reserve free slots using one
monotonic cursor. Validation still precedes every mutation, preserves active
slots and rejects invalid or duplicate updates atomically. No RF values,
native steering policy, AP inactivity limits or test deadlines change.
Duplicate-key validation and existing-key lookup retain their previous bounds;
the linear claim applies specifically to free-slot reservation.

On prpl, the first immediate post-startup two-room check now passes, including
both 30-second plays, all seven required native properties, real traffic and
healthy Default restoration. The first ten-client roster settles in 5.12 s
within the unchanged 60-second gate. Maximum control-handler time in that
fresh daemon window is 7,339 µs, versus the earlier 2.67-second maximum.
Raw evidence: `test-results/rf-backport/slot-first-rooms.json` and
`slot-services.json`. Earlier failed runs and the transmitter-side management
capture remain in `first-switch-audit/` and `first-switch-pcap/`.

A second cold room-service start also passes both rooms and Default restoration
(`slot-repeat-audit/rooms.json`); its first roster settles in 8.19 s. The same
patch passes RDK's immediate post-startup pair of rooms and Default restoration
(`test-results/rdk-rf-counter-followup/slot-first-rooms.json` in the RDK checkout),
with 9.32 s for the first ten-client roster. Each check retains the 60-second
gate; these timings describe native roster readiness, not optimal-AP proof.

## Validation and live limits

### Test accounting and diagnostics

Room reports include named failure reasons and native per-node outage state.
RF action cases after a failed case remain individually blocked in the suite
scorecard, not silently omitted or credited as passes.

UDP room checks retain raw endpoint counters. One exact datagram of excess
receiver bytes is accepted and explicitly labeled only when packet counts
agree, receiver loss is zero, receiver bytes equal packets times payload and
sender bytes equal one fewer payload. Larger or inconsistent discrepancies
fail; no counter is rewritten. Byte and sequence accounting are distinct in
the [iperf statistics implementation](https://github.com/esnet/iperf/blob/3.9/src/iperf_api.c).

Guarded-load fixtures select native extender radios with verified hop counts
and no extra target backhaul hop, retaining the original target when suitable.
They do not force backhaul parents or change native policy thresholds.

Load-action reports also retain production thresholds, evaluated and missing
subject cycle counts, decision-reason counts, peak decision-evidence utilization
and the last subject decision. Failures print these diagnostics: an unmet load
precondition must not be confused with a failed native steering request. These
observations never change the pass/fail gates.

The load fixture optionally adds real non-IP broadcast frames using
`--background-packets-per-second 200` (bounded to 1000/s, 1400-byte payloads,
105 seconds). Frames traverse an existing AP's wireless interface; no metric
value or PHY-rate mask is written. The source AP is the default. Experimental
`--background-ap gateway` uses a separate co-channel AP and a recorded,
restorable 35 dB gateway/source radio link at 2437 MHz, without changing
backhaul or target-channel RF. Optional `--pressure-snr`, `--rescue-snr`,
`--pressure-payload-bytes`, `--pressure-access-category` and `--pressure-pattern`
control only the real workload/RF stimulus, never policy thresholds. Periodic
endpoint progress survives failed runs without claiming completed traffic.
Workload failure, missing pressure and native-policy failure remain distinct.

### Direct prpl diagnostic checks

The recommend-only counter-manifest helper explicitly associates its traffic
subject with the room's nearby Ext-1 before Play, using the bound AP's native
SSID/frequency/BSSID. It verifies physical and controller ownership and restores
the original association after RF recovery. This is fixture setup, **not** an
optimizer action or a steering qualification. Without it, an inherited distant
owner can make the deliberately asymmetric uplink completely unusable.

On an authorized dirty diagnostic runtime, do not bypass the suite's clean
source gate. Use these direct helpers after the memory/full-roster work has
finished, the room service is active and Default is healthy/paused at zero,
with no lease, recording or external suite guard. Obtain `ROOM_URL` from the
selected VM's proxy configuration. On the outer host:

```sh
python3 tests/rf-property-rooms-smoke.py --yes-act --host local \
  --vm "$PRPLMESH_VM_NAME" --room-url "$ROOM_URL" --output /tmp/prpl-rf-rooms-new.json
lxc exec "$PRPLMESH_VM_NAME" -- python3 /opt/prplmesh-lab/tests/counter-guard-room-smoke.py \
  --stack prpl --yes-change-lab --output /var/lib/prplmesh-lab/test-results/counter-manifest-new
lxc exec "$PRPLMESH_VM_NAME" -- env PYTHONPATH=/opt/prplmesh-lab/optimizer:/opt/prplmesh-lab/wmediumd/configurator \
  python3 /opt/prplmesh-lab/tests/native-retry-counter-acceptance.py \
  --stack prpl --yes-change-lab --seconds 8 \
  --shadow-counter-policy /opt/prplmesh-lab/optimizer/configs/load-counter-guard-policy.yaml \
  --output /var/lib/prplmesh-lab/test-results/counter-shadow-new
```

Run sequentially; stop on any failure. The latter two temporarily replace the
room process, never run a second optimizer, and restore its unchanged service.
prpl traffic counters arrive via the native 1905 broker with 1024-byte units;
the same delta/context checks apply. Held impairment and RX-drop pressure
remain unqualified. Never infer pressure from the room name or traffic loss.

`bash tests/run-prplmesh-suite.sh rf --yes-act` runs the focused contracts,
viewer coverage, documentation, the bounded two-room live check, named-manifest
recommend-only operation and native counter shadow acceptance. The
existing static section also discovers the new pytest tests. The rooms
section includes the new rooms in its broader catalog tests;
use `rf` alone for this work, not a full catalog/soak.

The standalone [live runner](../../tests/rf-property-rooms-smoke.py)
uses the normal lease/revision protocol, refuses a held lease or suite room
guard, saves timestamped samples and traffic phase results, and restores the
paused Default in `finally`. It never starts another optimizer, retunes radios
or changes daemon modes. A timeout, missing native activity, failed traffic
phase or failed restoration is a failure, not a skipped pass. All raw samples
and failures belong under `test-results/`, outside this documentation tree.

Focused regression covers counter thresholds, zero/missing distinctions,
transport/skew/age/owner/epoch exclusions, hold reset and advancing counter
reports, default signal rescue, band-profile separation, provider ownership
and reset handling, reproducible room compilation, asymmetric direction,
traffic phase scheduling, generated catalog equality, viewer coverage and
documentation navigation. Existing RF contract/survey, native capture,
backhaul and Console tests cover the other observation boundaries.

Live qualification is deliberately narrower than this inventory: room load,
playback, native observations, bounded traffic and restoration. Positive
different-channel balancing with the counter guard, all selected Console
diagnostics, optional fading/interference/`-F`/`-Q` modes and every catalog room
still require their own live evidence. Unit fixtures prove policy behavior,
not congestion or live steering. No all-properties-live-qualified claim is
made here; consult each saved check's per-room failures and observations.
