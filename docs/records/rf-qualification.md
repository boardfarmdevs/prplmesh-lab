# RF qualification on prplMesh

[Documents](../README.md)

How the RF properties qualify on this lab's native prplMesh stack: the counter guard, ownership
reporting, load actions, the room catalog and its open failures, cold initialization and the
lab's diagnostics. The property-to-room contract itself, the same for both labs, is the RF
property coverage (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)).

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

The bounded [native counter acceptance](../../optimizer/acceptance/native-retry-counter-acceptance.py)
adds stronger supported *pulsed* downlink/ACK impairment on the currently
associated Default client, independent of room geometry. It compares kernel
and native deltas, confirms ownership before/after each trial, restores exact
frequency overrides and restarts the unchanged room service:

```sh
PYTHONPATH=optimizer:medium/configurator python3 optimizer/acceptance/native-retry-counter-acceptance.py \
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
Use `optimizer/acceptance/load-policy-acceptance.py --help` for direct diagnostics.
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

1. Runtime sources are synchronized to prplMesh's and RDK's of 24 September;
   previous guest edits are preserved in named stashes. The additional fixture
   and diagnostic changes still need a committed checkpoint before clean-suite
   acceptance; do not bypass source-match gates.
2. The synchronized prpl run passes all three geometry rooms, pressure and
   rescue, with native identities unchanged during each check. RDK's native
   recovery and reporting qualification remains separate. No full build or
   soak is required merely to investigate these bounded failures.
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

## Test accounting and diagnostics

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

Pressure-only qualification now prefers the shallowest available source path,
then equal-depth pairs, before historical AP preferences. Reports record
`pair_selection` and both actual hop counts. This controls an avoidable
backhaul bottleneck without requiring a star or manufacturing overload; a
deeper-only lab still has to meet every original stimulus and policy gate.
Clear/rescue selection is unchanged. The synchronized prpl pressure repeat in
`test-results/synchronized-rf/pressure/` passes with 22 causal veto witnesses,
no steering, healthy Default-20 restoration and unchanged native identities.
Its first qualified native sample has source/target utilization 213/15 and
113 retries/s, using the existing 1400-byte voice/300 offered broadcasts/s
fixture. The accompanying `geometry/` run passes all three geometry rooms,
their return checkpoints and Default restoration. The `rescue/` repeat passes
with a native BTM, 2.166 s verification and 23.742 s observed settling, using
the separate 512-byte fixture. Original channels, RF, associations, fresh
twenty-client metrics and native identities restore. These are bounded
hot-runtime checks, not fresh-build or soak acceptance.
The synchronized `rf-rooms.json` also passes both 30-second RF-property rooms,
all seven native observations, traffic and healthy Default restoration.

Geometry reports retain browser/lab identities and a bounded host
CPU/load/temperature/process trace. Run the browser on a separate test machine
with `--host` and reachable room/topology URLs to avoid measuring its software
rendering load as lab work. Keep `host-monitor.jsonl` with the report; sampling
errors fail the diagnostic gate, without changing convergence assertions.
The prpl geometry trace records host CPU busy averaging 25.15%, but CPU
temperature reaches 100 °C and package throttle count increases by 7,363.
These functional passes are not unconstrained performance measurements;
address host cooling before comparing latency. No power settings or unrelated
workloads were changed for this run.

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

## Direct prpl diagnostic checks

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
python3 optimizer/acceptance/rf-property-rooms-smoke.py --yes-act --host local \
  --vm "$PRPLMESH_VM_NAME" --room-url "$ROOM_URL" --output /tmp/prpl-rf-rooms-new.json
lxc exec "$PRPLMESH_VM_NAME" -- python3 /opt/prplmesh-lab/optimizer/acceptance/counter-guard-room-smoke.py \
  --stack prpl --yes-change-lab --output /var/lib/prplmesh-lab/test-results/counter-manifest-new
lxc exec "$PRPLMESH_VM_NAME" -- env PYTHONPATH=/opt/prplmesh-lab/optimizer:/opt/prplmesh-lab/medium/configurator \
  python3 /opt/prplmesh-lab/optimizer/acceptance/native-retry-counter-acceptance.py \
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

The standalone [live runner](../../optimizer/acceptance/rf-property-rooms-smoke.py)
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
