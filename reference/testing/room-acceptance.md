# Room correctness and convergence acceptance

[Testing reference](README.md) · [Expected room features](../rooms/catalog.md)

Run every advertised room sequentially within each lab; independent RDK and
prpl runs may overlap across hosts. This is bounded feature testing, not a soak
or intrinsic stack-speed ranking. A targeted `--world` run is not full coverage.

## Preparation

1. Reserve the lab. Save initial room/service configuration, native/container/
   medium identities and source revisions. No other operator lease or RF writer
   may be active. Do not alter native policy, metrics intervals or VM resources.
2. Copy the **deployed guest's** `gen/wmediumd/configurator/worlds/golden/*.world.json`
   to the observer evidence directory. Match hashes to the loaded world.
3. Copy `gen/tests/room-feature-guest-audit.py` and
   `gen/tests/room-feature-rf-audit.py` into the guest's `/tmp/`, keeping names.
4. Use an installed Playwright/Chromium and preferably a separate observer.
   If colocated, restrict only owned browser GPU threads with `--observer-cpus`,
   using valid CPU IDs. The harness owns an SSH host sampler, requires two
   samples before lab mutation and retains it through restoration. Samples
   include CPU/pressure, RAM, temperature and available throttle counters.
   Its stdin closes on shutdown; sampler failure invalidates host coverage.
5. The room's default 100-action cap is session-wide. A complete catalog may
   exceed it. Save the unit and, if needed, create a **named temporary runtime**
   drop-in under `/run/systemd/system/` that copies the original `ExecStart`
   with only `--max-actions 2000` changed. Clear the old ExecStart in the
   drop-in, daemon-reload and restart **only the room**, outside measurement.
   Verify twenty-client readiness and the chosen cap. Remove only this drop-in
   and restore the original configuration after testing.

Do not discard an RF journal or restart native services to make a case pass.
Keep failures and incomplete runs in separate evidence directories.

## Gates

| Phase | Required observation |
| --- | --- |
| Load | Browser selection auto-applies correct world/epoch, resets overrides and commits verified RF |
| Initial settling | Within 60 s after readiness: exact roster, no duplicate MACs, six mesh roles, matching physical/native/rendered ownership |
| Freshness | Current-epoch complete candidate coverage; evaluation and serving metrics at most 30 s old |
| Policy convergence | Complete fresh evaluation satisfies the configured steering margins; this is the pass gate |
| Strongest AP diagnostic | Report stronger same-band candidates and RCPI gaps separately; do not force margin-only roams |
| Stable gate | All required checks hold continuously for five seconds |
| Play | Real browser Play at 1×; monotonic clock, golden positions/presence, actual SVG nodes/parents |
| During motion | Record transient divergence; flag sustained view mismatch over five seconds only with adequate samples |
| Checkpoints | Allow 45 s per explicit pause, then resume on pass or timeout so later segments still run |
| End | Allow 90 s after completion for the same stable gate |
| Integrity | Native/container/medium identities unchanged; no hidden RF assistance, faults, SSE gaps or browser errors |
| Cleanup | Default twenty-client world, paused, no lease/fault; original service/action cap restored |

A continuously moving target need not be strictly converged every instant.
Record one-second target sampling cadence and actual gaps; screenshots can
slow sampling. Do not infer continuous failure across unobserved intervals.

For presence worlds, inspect exact MAC sets in both views and kernel links at
settled boundaries. During fronthaul loss require no clients on the disabled
role after five seconds while backhaul remains connected. Check directional
RF gains against the asymmetric golden via the read-only midpoint audit;
reject samples crossing epochs. Protected startup backhaul need only match
the connected actual tree, not form geometric branches.

## Execute

New reports identify `convergenceCriterion=configured-steering-policy`.
`policyConverged` includes roster, ownership, freshness and completeness checks;
`optimizerPolicySatisfied` is only the policy's raw verdict. The separate
`strongestApConverged` and `strongerClientGaps` preserve the stricter diagnostic.
Missing metrics, incomplete decision coverage or an RF fault cannot pass either
qualified verdict. Older reports retain their original strongest-AP criterion.

From this repository on an observer able to SSH to the physical host:

```sh
node gen/tests/test-room-feature-acceptance.js
node --check gen/tests/room-feature-acceptance.js
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright-core
export CHROMIUM_PATH=/absolute/path/to/chromium/chrome
node gen/tests/room-feature-acceptance.js --yes-act --flavor rdk \
  --host rev140 --vm rdkeasymesh-20-0908 \
  --room-url http://192.168.2.140:48891/ \
  --topology-url http://192.168.2.140:48889/ \
  --worlds /absolute/path/to/deployed-goldens \
  --output /absolute/path/to/new-results --native-audits 1 \
  --initial-timeout 60 --checkpoint-timeout 45 --final-timeout 90
node gen/tests/room-feature-report.js /absolute/path/to/new-results \
  /absolute/path/to/deployed-goldens > audited-summary.json
```

Replace deployment arguments as needed. Add `--observer-cpus CPU_LIST` when
sharing a lab host. Repeat `--world WORLD_ID` only for explicitly targeted
runs; omit it to enumerate the live catalog. Use independent output directories,
browsers and host samplers for simultaneous backends. Inspect the harness's
nonzero exit and report; completing playback alone is not acceptance.

## Evidence and restoration

Retain per-room JSON, sampled JSONL, SSE, world hashes, screenshots and a compact
matrix: loaded/final/checkpoint convergence, presence/RF/visual correctness,
verified/failed/unmatched actions, p50/p95/max timing and native identities.
Distinguish collection, submission, verification and rendering intervals.
Absent timestamps are unavailable, not zero; timeouts are censored failures,
not omitted successful samples.

Always remove the named temporary service override, daemon-reload, restore the
original room and verify the default roster, paused time zero, no held lease,
no fault and the original action cap. Stop only owned browsers/host samplers.
For a separate opt-in crash-recovery test, use
`gen/tests/room-recovery-smoke.py --help`; it deliberately kills only the room
process and must be scheduled, not silently included in a normal room pass.

## Opt-in load-policy qualification

Run separately from the default catalog, as root **inside the lab VM** with
the default twenty-client room paused at zero and unleased:

```sh
ROOT=/opt/prplmesh-lab
PYTHONPATH="$ROOT/optimizer:$ROOT/wmediumd/configurator" \
  python3 "$ROOT/tests/load-policy-acceptance.py" --stack prpl \
  --root "$ROOT" --output /tmp/load-policy-new --yes-change-lab
```

For RDK set `ROOT=/home/easymesh/git/meta-cmf-bananapi-vcpe/gen` and `--stack rdk`.
The driver stops only the room, prepares two existing private clients and
two different 2.4-GHz channels, then offers two bounded 12-Mbit/s UDP flows.
Native load/activity and explicitly labeled hwsim candidate reports drive
one load-only BTM to a slightly weaker AP. Require native association
verification, no additional move during settling and positive receiver data.
BTM admission alone is not success; no forced roam repairs a measured failure.

Setup retries, decisions, client control events and receiver intervals are
retained. Cleanup restores RF overrides, channels, client frequency capability,
logging, owned traffic/capture processes and the original service, then checks
fresh twenty-client native metrics. RDK retunes use a single-radio South
subdoc, not global radio Apply or an agent refresh. The driver refuses
mismatched configured/live channels and verifies all three bands and the
unchanged agent PID after each change. Restore the lab before default-room
qualification if preparation or cleanup fails.
Separate preparation/cleanup from timed steering.
Receiver queue draining is not calibrated physical capacity.

## Current qualification

The current catalog includes three dedicated band-steering rooms in addition
to the fourteen original scenarios. See [band-steering qualification](../optimizer/band-steering.md#results)
for the current seventeen-room results, native receive-channel requirements,
verified band transitions and preparation limitations. The table below is the
earlier RF baseline, not coverage of the three added rooms.

### Pre-band RF baseline

September 13, 2026 UTC, `codex/0908-clean`: the pre-band independent catalogs pass
**14/14 on each stack**, including the unchanged five-second extender-loss
departure gate. Every available room loads and plays at 1×, with initial,
checkpoint and final policy convergence, fullscreen room/topology inspection,
presence, directional RF and physical/native/rendered ownership.
Native/container/medium identities remain unchanged within each final catalog;
neither has browser errors or SSE gaps. Failed earlier attempts remain separate.

The **60/45/90-second bounds and five-second stable hold** are unchanged.
Native cadence, steering margins and VM resources are unchanged. Only the
temporary test action cap rises to 2000, then returns to 100. prpl dependency
repair/restarts occur before its final window, never to rescue a measured room.
These are bounded feature tests, not a soak or intrinsic stack-speed ranking.

### Catalog performance

| Observation | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| UTC window | 03:35:19–04:02:21 | 05:06:14–05:29:21 |
| Verified / submitted actions | 150 / 150 | 153 / 154 |
| Failed / discarded / unmatched verifications | 0 / 0 / 0 | 0 / 1 / 0 |
| Request → verification p50 / p95 / max, s | 1.674 / 5.722 / 7.145 | 0.981 / 1.149 / 1.224 |
| Submission p50 / p95 / max, s | 0.061 / 0.076 / 0.105 | 0.473 / 0.531 / 0.559 |
| RF application p50 / p95 / max, ms | 9.452 / 30.474 / 494.133 | 8.873 / 30.999 / 671.827 |
| Candidate publication wait p50 / p95 / max, ms | 84.674 / 132.167 / 458.078 | 36.793 / 71.481 / 513.321 |
| Unavailable collections / native HTTP 504s / busy rejections | 0 / 0 / 0 | 0 / 0 / 0 |
| Superseded collections, separate cancellations | 13 | 10 |

RDK candidate transactions p50/p95/max: **268.956 / 392.675 / 7740.489 ms**.
prpl NBAPI operations: **147.582 / 178.927 / 270.810 ms**;
complete collections: **943.476 / 992.680 / 1641.982 ms**.
prpl's timestamp-resolution guard remains **490/515 ms p50/p95**;
removing it without native request correlation would weaken freshness validity.
These are different boundaries, not interchangeable stack execution times.
Superseded collections are cancellations, not unavailable measurements or
verified steers. No clean repeat establishes the cause of an uncaptured failure.
One prpl verification is discarded after the next world commits a new epoch;
it is counted separately, not as a successful or failed native steer.

RDK includes agent **0185/0186**, OneWifi **0027/0028**, wmediumd **0026**
and hwsim **0010**. prpl includes coherent adapter membership, HAL **0015**,
wmediumd **0027**, hwsim **0010** and the ubus backport documented below.
The common viewer applies playback clock/positions atomically. Native
controllers, default steering policy and reporting intervals are unchanged.
prpl cold candidate registration now uses at most four independent workers;
warm cached registrations add no RPCs or worker pool.

### Per-room convergence

Initial/final **first policy convergence**, seconds from each settling gate,
not the first movement. Near-zero final values mean already converged;
the five-second continuous hold is additional.

| Room: initial / final, s | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| `home-a-stationary` | 0.03 / 0.01 | 0.02 / 0.01 |
| `home-a-one-client-handover` | 13.15 / 7.13 | 8.08 / 0.01 |
| `large-room-extender-evacuation` | 18.23 / 15.18 | 6.07 / 0.01 |
| `large-room-perimeter-counter-roam` | 25.17 / 5.07 | 8.08 / 0.01 |
| `home-a-asymmetric-link` | 33.39 / 2.03 | 11.15 / 0.01 |
| `home-a-band-walk-small` | 17.18 / 11.19 | 8.08 / 4.04 |
| `home-a-border-hover` | 22.24 / 17.25 | 5.07 / 0.01 |
| `home-a-disappear-reappear` | 13.16 / 0.01 | 4.13 / 0.01 |
| `home-a-extender-loss-recovery` | 9.10 / 0.01 | 4.10 / 0.01 |
| `home-a-fast-transit` | 12.12 / 18.20 | 4.04 / 7.07 |
| `home-a-flash-crowd` | 9.11 / 0.01 | 2.03 / 0.01 |
| `home-a-private-client-room-walk` | 13.17 / 0.02 | 5.05 / 0.01 |
| `home-a-slow-walk-ten` | 14.41 / 8.11 | 3.04 / 0.02 |
| `home-b-slow-walk-ten` | 22.32 / 9.13 | 19.23 / 1.03 |

- prpl: `home-a-asymmetric-link` retains 1 stronger same-band candidate(s) below the configured steering margin.
- prpl: `home-a-slow-walk-ten` retains 1 stronger same-band candidate(s) below the configured steering margin.

Absolute-strongest diagnostics remain separate from policy convergence.
A policy pass does not claim every moving client always selects the absolute
strongest AP. `room-final-readiness.py` uses the same fresh, complete policy
gate and five-second hold; `--require-absolute-best` adds the stricter check.
No target is forced to make acceptance pass.

### Native metrics → browser presentation

Use the catalog's Playwright/Chromium environment and a new output directory
during scheduled movement. The tool only observes; the catalog or an operator
owns playback. On RDK:

```sh
node gen/tests/controller-render-latency.js \
  --scope metrics --url http://192.168.2.140:48889/ \
  --output /tmp/native-metrics-new --seconds 100 \
  --native-stack rdk --host rev140 --vm rdkeasymesh-20-0908
```

On prpl omit `gen/`, use URL `http://192.168.2.150:8091/`,
`--native-stack prpl --host rev150 --vm prplmesh-20-0908`.
The guest requires root Python/BCC and the exact qualified native binary hash;
the browser profile is **Chromium 139.0.7258.5**. Unknown native builds fail
closed; changed or missing browser trace identities cannot qualify a frame.
Captures own their receiver/browser, last at most 150 seconds with native
tracing, and restore the normal API wrapper before draining pending records.
There is no always-on observer, extra RF query, policy change or RF write.

`--scope associations` retains association-model timing; `--scope metrics`
adds **ordinary serving-link RCPI**, not association events masquerading as
signal updates. RDK probes the instruction following the accepted RCPI store
at file offset `0x89b90`; prpl uses `0x2737c1`. Both read the actual STA and
BSSID from the owning model. prpl's qualified Station/BSS layouts are pinned
by the controller digest. Requalify instruction boundaries and layouts after
native rebuilds; never disable the digest guard.

The metric path joins the native RCPI transition to `/clients` response
decode, checks the same owner/raw RCPI and all ten actual SVG segment fills,
then finds a covering Paint. Changes within one meter level still require
the correct SVG data, but **do not require a nonexistent visual change**.
Repeated equal native reports cannot reset the transition clock. Ambiguous
recurrences, ownership changes predating the HTTP request, stale metrics, supersession,
timeouts and incomplete traces fail rather than receiving guessed timings.
An ownership/metric change proven to occur **after request start but before
decode** is tagged as an in-flight snapshot race, not mistaken for a bad
native join. The old-owner metric's own commit must still match uniquely;
clock-overlapping request boundaries remain unqualified.

Presentation is no longer inferred from two animation callbacks. A covering
Paint must belong to the exact renderer/thread's main-frame→commit flow;
that frame's hexadecimal trace identity must match Chrome's presentation
feedback. Zero-frame feedback and missing/duplicate joins are unqualified.
The source is Chromium's
[presentation callback](https://chromium.googlesource.com/chromium/src/+/139.0.7258.5/third_party/blink/renderer/core/frame/animation_frame_timing_monitor.cc)
and [main-frame pipeline](https://chromium.googlesource.com/chromium/src/+/139.0.7258.5/cc/trees/proxy_main.cc).
Trace categories are `devtools.timeline,blink.user_timing,benchmark`; avoiding
the entire `cc` category retains the required commit flows without its
unrelated scheduler events. Recording is capped at 128 MiB, with loss rejected;
JSON export has a 512 MiB limit and a separate 30-second completion deadline.
Export/offline analysis are outside latency and CPU measurement windows and
use additional memory, not the recording buffer's budget.

The following topology figures are retained September 12 baselines, not new
timings of the post-backport prpl dependency. The room profiles below are from
the final September 13 deployment.

| Qualified fullscreen topology baseline | RDK | prpl |
| --- | --- | --- |
| Ordinary RCPI → decoded response joins | 87/87 | 22/22 |
| Changed-meter → frame presentation joins | 49/49 | 7/7 |
| RCPI → presentation p95 interval | 457.11–458.51 ms | 347.20–348.11 ms |
| Maximum presentation upper bound | 499.56 ms | 348.11 ms |
| Maximum RCPI clock uncertainty | 3.27 ms | 2.94 ms |
| Association → presentation joins | 25/25 | 27/27 |
| Association → presentation p95 interval | 305.91–308.61 ms | 206.77–209.02 ms |

RCPI captures use RDK's `home-b-slow-walk-ten` and prpl's
`home-a-private-client-room-walk`; association captures cover evacuation.
Different movement cohorts and small prpl visual counts are **not an intrinsic
stack-speed comparison**. A separate RDK band-walk capture has 79/79 native
metric joins and 44/44 changed-meter frames. Earlier raw captures are retained;
`precision-audit.json` reapplies the conservative timer allowance to recorded
Chromium timestamps without modifying the original reports.

Monotonic clock brackets refresh every ten seconds and include 100 ppm drift
and [0.1 ms browser timer coarsening](https://developer.chrome.com/blog/cross-origin-isolated-hr-timers/)
at both calibration and event endpoints;
latency qualification requires ≤5 ms maximum uncertainty.
Native/perf loss, missing joins, API failures and trace errors fail.
Retain raw native events, clock samples and Chrome traces outside the repo.

#### Observer overhead

On a paused, unleased default twenty-client lab, run the same command with
`--scope overhead --seconds 30 --room-url http://192.168.2.140:48891/` and
a new output directory. For prpl use room URL `http://192.168.2.150:18891/`.
This is a **separate qualification**, not a latency pass with zero samples.
After initializing Chrome's otherwise lazily created tracing service, it
records 20 seconds before tracing, 30 traced, and 20 after; unchanged
room epoch/roles/playback, process identities, no RCPI or association changes,
native metric events and no trace loss are required.

Budgets are fixed before measurement: observer callbacks p95 ≤2 ms and total
≤1% of wall time, including a conservative 0.2 ms per-callback timer allowance;
incremental controller CPU ≤5 and browser CPU ≤10 percentage
points of **one core**. The upper envelope subtracts the lower of the two
baseline windows, including ±2 native scheduler ticks. It is an observed
stationary envelope, not a universal or statistical confidence bound.

Final controlled runs pass both stacks: controller upper increments
**1.45 / 0.00 percentage points**, browser **0.58 / 0.48**, and callback
upper bounds **0.115% / 0.100%** of elapsed time (RDK/prpl). The zero prpl increment means
no detectable increase within this envelope, **not zero probe cost**. Moving
room CPU windows are retained separately and are not controlled A/B evidence.
The controlled comparison keeps the same topology page open in all windows;
it bounds instrumentation cost, not the cost of opening a viewer. Catalog
captures add an observed topology page, so they are not uncontended runs.

Scope is **native association/RCPI model store to topology presentation feedback**
in a headless compositor. This does not qualify physical display scanout,
layout-animation completion, the room's WebGL presentation, every native
counter or an exact server-publication timestamp. Request/decode brackets
include publication, polling and transport; no zero-external-delay claim is
made. Profiling cannot turn a failed room convergence gate into a pass.

### prpl snapshot coherence and candidate diagnosis

The September 13 follow-up reproduces a **different** reporting bug while
playing the perimeter room: `sta-04` appears at its old and new AP in one
topology sample (13 visible clients instead of 12). The room gate correctly
fails despite all 11 steering requests completing. The adapter had merged
independently timed, per-device STA snapshots across the roam.

The fix retains concurrent device metadata reads but obtains all STA
membership in one bounded NBAPI read. It does not guess the winning owner,
deduplicate by RSSI, cache a previous roster, or loosen the duplicate gate.
The focused repaired perimeter run passes, with **11/11** steers verified.
The prpl repository's `reference/observability/topology-adapter.md` documents
the read boundaries.

The preceding **30.36-second candidate gap remains unattributed**. Three
bounded diagnostic perimeter plays show no incomplete collections; the
retained duplicate-view failure is not counted as a room pass. Native packet
captures cover **8,460** unambiguous query/response pairs across the four
extenders, with no missing replies and a maximum observed turnaround of
**21.46 ms**. Pairing uses agent/opclass/station set with exactly one pending
request, not an assumed matching response MID. These observations cannot
explain an earlier uncaptured failure.

The full follow-up catalog does reproduce an availability failure while
loading `home-b-slow-walk-ten`, at **01:50:24 UTC**:

- Agent `prpl-agent-02` receives an operating-class-115 query containing ten
  stations. Its response follows **2.754 ms** later but contains only nine;
  `02:00:00:20:05:00` is missing. The controller-side capture confirms the same
  omission; all five capture interfaces report zero kernel drops.
- The native HAL logs `No wmediumd candidate metric` for that first station.
  The remaining nine reported RSSIs have the preceding station's values:
  the signal-to-client mapping is shifted, not just late.
- The new timeout diagnostic retains RCPI 78 and timestamp
  `2026-09-13T01:50:23Z` unchanged through the last NBAPI read at 01:50:54.140.
  Freshness correctly refuses that stale entry. The next measurement round
  recovers, and the room initially converges in **40.49 seconds**, inside the
  unchanged 60-second bound. The incomplete collection remains a failure.

The previous laboratory HAL's `read_snr` used one `send`/`recv` pair, continued
on a failed receive, and checked frequency but not the echoed source/destination.
An offline fault-injection harness using that exact function reproduces a
missing first metric and misassigned subsequent RSSI when the first `recv`
returns `EINTR`. This proves a transport-handling weakness, **not which errno
occurred live**: that HAL did not log it. Packet turnaround rules out
a 30-second bridge/1905 delivery delay for this particular response, not all
possible native delays or the earlier six-entry failure.

**HAL repair 0015:** interrupted sends/receives retry the same operation within
one shared one-second monotonic exchange deadline. An interrupted receive never
resends its request. Validate response length, protocol, status, frequency and
both echoed MACs; abandon the entire candidate batch on failure, closing its
socket instead of assigning another client's signal. Failed exchanges now log
the requested station, interface, response length and errno. HELLO uses the
same bounded exchange. No freshness interval or optimizer timeout is relaxed.

`tests/candidate-transport-test.py SOURCE` compiles the assembled native reader
and exchange, not a Python reimplementation. Fourteen scenarios cover send and
receive interruption, wrong source/destination/frequency/opcode/status, short
messages, late replies and a bounded signal storm. Real Unix `SOCK_SEQPACKET`
tests include a targeted `SIGUSR1` interruption and a real receive timeout;
successful transactions preserve the two distinct station values. Both the
repository regression and the actual canonical build source pass.

The rev150 deployment replaces only installed `libbwl.so.6.0.0` and refreshes
the internal runtime payload/provenance used by normal lab startup. Its digest
is `f50f5834b65c287cf1513aed583adc48545cb422f83aefbcb5543091eba0a971`.
Controller/agent/fronthaul binaries, qualified RF-load support and reporting
cadence remain unchanged. This is not a new thin release or box.

**Incremental build prerequisite:** check `CMAKE_HOME_DIRECTORY` and the full
patch set, including ABI-changing RF patch 0014, before reusing a build tree.
This host's matching tree is `/opt/prpl-build-0908` with source
`/opt/prplMesh-0908`; the older `/opt/prpl-build-nl80211` is not equivalent.
An initial mismatched-library deployment crashed fronthauls at HAL attachment;
the correctly patched build resolves it. The raw build library also has build
directory RUNPATHs: deploy the CMake-installed library, not `out/lib` directly.
Dependency resolution alone does not prove C++ ABI compatibility. Failed setup
logs remain separate from room qualification. Do not reuse those binaries.

A real stalled/failed exchange can still make native measurement collection
unavailable; fail-closed behavior is intentional. Neither passing tests nor a
later clean catalog proves the cause of the original uncaptured 30.36-second gap.

Candidate timeout transactions now retain the missing entries' baseline and
last parsed signal/timestamp, plus the last-read time, without extra NBAPI calls
or changed timeouts. In a prpl lab VM, as root, capture native evidence with:

```sh
python3 /opt/prplmesh-lab/tests/prpl-candidate-capture.py \
  /tmp/prpl-candidates-new --seconds 180
```

The opt-in collector owns five bridge pcaps and filtered native logs, stops
its processes, and leaves radio/link state untouched. Bounds are 5–2400
seconds and 256 MiB; touching the output directory's `stop` file ends it early.
Require exit zero; inspect packet-drop counts in `*.pcap.stderr` and cleanup in `capture.json`.
Preserve native packets alongside room `events.jsonl`; do not turn a recovered
timeout into a successful collection.

### prpl cold candidate registration

The first passing post-HAL/ubus catalog exposes a separate startup delay:
24 independent `AddUnassociatedStation` calls run serially in the first
stationary-room collection. Their wall span is **3629 ms**, summed RPC time
**3628 ms**, and complete collection **4079 ms**. Native bridge responses are
not responsible for that registration span.

Registration now uses at most **four workers**, only for uncached targets.
Successful registrations are cached on the collecting thread; on failure,
queued work is cancelled and running calls are drained before raising the
error. Only actual successes survive for retry. Generation checks still occur
before each native RPC; no timeout, timestamp guard or policy is relaxed.
Warm rounds create no registration pool and send no registration calls.
Regression tests require concurrent progress, enforce the four-worker limit,
check successful-only caching/retry and reject superseded generations.

In the repeat, a 24-call preflight batch spans **1314 ms**, with four observed
concurrent RPCs and **4912 ms** summed RPC time; its complete collection is
**1896 ms**. These equal-count batches have different room phases and targets,
so this is an observed reduction in serialization, not a controlled end-to-end
speedup claim. The first stationary-room batch now has eight calls rather than
24; its **425 ms** registration span must not be compared as equal work.
The full final catalog, not just this faster cold batch, must pass unchanged.
Raw events and `registration-audit.json` retain counts and timestamp boundaries.

Parallel registration also overlaps identical native query rosters. Responses
do not echo query MIDs, so these bursts cannot support exact per-request latency
joins. `packet-group-audit.json` instead reconciles **17,798 queries and 17,798
responses** by exact agent/opclass/roster, with no outstanding groups or orphan
responses. **331 queries in 140 concurrent groups** are excluded from individual
timing claims; their maximum group-drain span is **40.92 ms**. All five capture
interfaces report zero kernel drops. The older single-pending auditor's
ambiguities and leftover responses are retained, not silently treated as exact
matches. Group counts do not prove request identity within concurrent bursts.

### Playback reply ordering

The first HAL-repaired prpl catalog remains **13/14**, not a pass. All steers
and convergence gates succeed, but one `home-a-slow-walk-ten` frame shows the
zero-second clock with ten clients' one-second positions. Native playback
events are coherent: revision 534 starts at zero, and revision 535 advances
clock and roles together 33 ms later. The viewer's Play HTTP callback could
then apply the older reply's clock alone after the newer SSE event.

The common viewer now applies playback replies, events and interaction
snapshots as revision-ordered clock/role updates. Older revisions and backwards
time within one revision are rejected together; a newer revision can rewind.
A committed world establishes a new revision boundary. Active drags and
acknowledged preview cleanup remain intact. No polling, native restart, delay
or acceptance-tolerance change is added.

`tests/viewer-playback-order-test.js` executes the actual viewer functions with
a deliberately delayed Play response. The previous source reproduces the
0-versus-1000-ms clock failure; repaired source passes, including stale full
snapshots, same-revision clock regression, rewinds, world reset and dragging.
The focused slow-walk room then passes on both labs with **19/19** verified
steers each. The final full catalogs qualify the common viewer on both hosts;
the first failed prpl catalog and before/after regression logs remain retained.

### prpl libubus reentrancy

A subsequent catalog stops qualifying when the native controller crashes in
`libubus:ubus_cmp_id` at approximately **03:35:56 UTC on September 13**. Its
NULL AVL key is recorded by the guest kernel; topology becomes unavailable,
not falsely converged. The run is retained as failed. The existing unseen
Apport report prevented a new core, so the exact live call chain is unavailable.

The lab pins ubus at `13a4438b4ebdf85d301999e0a615640ac4c9b0a8` (2020).
Inspection finds a demonstrable recursive-dispatch defect: a callback can
drain the pending list while its outer iterator retains the next entry.
Object callbacks can also be reentered before returning. The narrow dependency
backport incorporates upstream
[safe pending iteration](https://github.com/openwrt/ubus/commit/2099bb3ad997),
[outer-handler draining](https://github.com/openwrt/ubus/commit/ef038488edc3),
and [nested-object deferral](https://github.com/openwrt/ubus/commit/a72457b61df0).
Queued work drains without waiting for another socket-read event; there is no
new mutex, poll interval, optimizer delay or EasyMesh policy change.

`tests/ubus-reentrancy-test.py UBUS_SOURCE` compiles the actual dispatch
functions with controlled callback/socket boundaries. Five cases check
recursive queue consumption, nested dispatch, an empty socket, an active
outer request and disconnect handling. The old source processes a retired
message twice; repaired source passes all five. The repository fixture is
extracted from the pinned source, and the regression includes that negative
control. This proves the source defect, **not the exact cause of the uncored
live crash**; retain the crash evidence if it recurs.

`patches/ubus/0001-libubus-guard-reentrant-message-dispatch.patch` is applied
by normal builds. Packaging checks the installed dependency's source,
patch-set and library digests against build-time provenance. Normal node
startup refreshes dependencies from the internal payload after stopping native
processes, unlinking old library files before extraction so existing mappings
are not truncated. Existing containers therefore do not retain an older base
image's library. The deployed library digest is
`0506ee044dce344af3325fe04a4277e0d1fd2d7d67ae0f187112165878963214`.
The dependency archive changes only this library and adds its provenance;
controller, agent, fronthaul, hostapd and libubox remain unchanged.
A bounded live probe observes **22,807 object additions / 22,892 removals**
over 180 seconds, with no nonzero returns or lost events; the controller stays
alive. This exercises the dependency path, not every possible crash condition.

### Room WebGL presentation

The common opt-in profiler also covers decoded room network snapshots to
**client gauge materials and association-line geometry, actual WebGL draws,
canvas mailbox preparation, and exact Chrome frame presentation feedback**:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright-core \
CHROMIUM_PATH=/path/to/chromium-139.0.7258.5/chrome \
node gen/tests/room-render-latency.js --url http://192.168.2.140:48891/ \
  --output /tmp/rdk-room-render-new --seconds 65 \
  --native-stack rdk --host rev140 --vm rdkeasymesh-20-0908
```

For prpl omit `gen/`, use `http://192.168.2.150:18891/`, and select
`--native-stack prpl --host rev150 --vm prplmesh-20-0908`.
Omit the native arguments for decoded-snapshot-only profiling. Run passively while
a separately controlled room is playing. The tool enters full screen, enables
`?profile=1` on its own page, and removes its observer before export. The
default viewer has no observer. No extra RF/API queries, pixel readback or
synchronous GPU wait is introduced. The profile pins Chromium and SwiftShader,
with the owned GPU process restricted to CPUs 0–1 and nice 19.

The join requires one canvas, correct material colors/line endpoints, actual
draw calls, an exact renderer/thread/main-frame identity and one
[`DrawingBuffer::prepareMailbox`](https://chromium.googlesource.com/chromium/src/+/139.0.7258.5/third_party/blink/renderer/platform/graphics/gpu/drawing_buffer.cc)
before its commit. Missing or duplicate joins, lost traces, SSE gaps, context
loss and API failures fail qualification. A collapsed asynchronous frame in
Chrome's JSON export is accepted only with its exact begin-frame ID, unique
explicit render interval and matching recorded duration; no nearest-frame
guess is used. Marker start times include observer work rather than subtracting
it from reported latency. Browser timer precision contributes ±0.2 ms.

Native mode additionally joins serving-RCPI stores at the digest-qualified
controller boundary to observed room RCPI transitions and their exact WebGL
frame. Match station, BSSID and RCPI; reject ambiguous/repeated transitions,
fallback sources, stale metrics, mismatched RSSI conversion and clock
uncertainty over five milliseconds. Equal repeated native values do not create
new transitions. Missing native events or an empty join cannot pass. Native
capture stops before Chrome export, and its process/clock evidence is retained.
The bounded search spans thirty seconds, not an assumed event/presentation
identity. These joins describe observed value publication, not every native
sample: SSE can coalesce intervening values, and unchanged signal bars may
represent distinct RCPI values within the same color level.

| Qualified fullscreen band-walk profile | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| Checked and presented network frames | 259/259 | 259/259 |
| Frames with changed client state | 42 | 54 |
| SSE decode → presentation p95 upper | 323.72 ms | 225.30 ms |
| Maximum decode → presentation upper | 413.19 ms | 318.31 ms |
| Observer callback p95 upper | 0.40 ms | 0.50 ms |
| Observer callback wall-time upper fraction | 0.134% | 0.170% |
| Qualified native RCPI joins | 90/90 | 53/53 |
| Joins changing signal-bar level | 58 | 40 |
| Native RCPI → SSE decode p95 upper | 471.36 ms | 461.21 ms |
| Native RCPI → presentation p95 lower–upper | 758.22–761.26 ms | 634.95–637.48 ms |
| Native RCPI → presentation maximum upper | 781.59 ms | 647.74 ms |
| Maximum joined clock uncertainty | 3.12 ms | 3.05 ms |
| Native events captured / lost | 185 / 0 | 965 / 0 |

The unchanged callback budgets are p95 ≤2 ms and ≤1% of elapsed wall time.
An initial profiler used layout-forcing canvas bounds reads; removing those
reduces its measured callback p95 upper from 4.10 ms to the values above.
Earlier failed/empty captures are retained, not counted as passes.
Different hosts, native reporting cadence and software GPU scheduling preclude
an intrinsic stack-speed comparison. These 65-second profiles run alongside
the respective full catalogs, without changing their gates. Capture receiver CPU is **0.116 / 0.353 s**
over approximately 67 seconds for RDK/prpl. Native and Chrome traces have no
lost events. Receiver resource evidence remains in each profile report.
RDK's retained raw capture also passes the stricter RSSI/RCPI-conversion reaudit.

This is native **controller RCPI-store → room presentation**, not RF generation
or reception → controller timing, physical scanout, pixel-exact framebuffer
validation, completed animations, or qualification of every mesh/wall effect.
Do not call it the entire virtual-RF pipeline or zero outside-stack delay.
The topology native-RCPI profile remains separate.

### Opt-in policy outcome

Three RDK warm-retune repetitions and the broker-enabled prpl qualification pass with
the production twenty-client pool intact. Native AP metrics/activity drive one gentle BTM to a slightly
weaker, quieter AP on another 2.4-GHz channel. Signal-only remains the default.
Both live-room recommend-mode smoke tests also pass, including owned receiver
shutdown and restoration; these smoke tests authorize no steering.

| Observation | RDK | prpl |
| --- | --- | --- |
| Source → target RCPI | 148 → 144 | 148 → 144 |
| Native utilization, octet 0–255 | 234 → 11 | 234 → 17 |
| Sustained condition before action | 10.053–11.560 s | 5.032 s |
| Request → native verified association | 1.207–1.440 s | 0.719 s |
| Verifier-only interval | 1.157–1.390 s | 0.288 s |
| Additional actions during ≥20 s settling | 0 | 0 |

RDK uses five-second report skew/freshness and a ten-second hold because its
independent native periodic reports arrive staggered. prpl uses one-second
skew/five-second hold. Both AP reports must advance; default room gates and
native reporting intervals do not change. Unknown/stale load never means idle.

Two 12-Mbit/s UDP senders deliver approximately **13.59 → 26.15 Mbit/s RDK**
in receiver windows 5–15 s and 65–75 s. The separate prpl repeat delivers
**12.60 → 24.63 Mbit/s** in the same windows. Later windows include queued
traffic draining and can exceed the 24-Mbit/s offered rate; these are receiver
delivery observations, **not calibrated capacity or steady-state gains**.
Packet activity is not offered demand; wireless hops are not backhaul capacity.

Client control events confirm native BTM reception, scan and association.
Setup scans/roams and retunes occur before timed
steering; cleanup restores them and verifies fresh twenty-client metrics.
The RDK target starts and ends at **6/36/37** (2.4/5/6 GHz); only its
2.4-GHz channel changes. This is not arbitrary radio-configuration qualification.
No forced roam repairs a measured failure; earlier failures remain evidence
in the timeout investigation below.

### Native-load coverage

`tests/native-load-acceptance.py` is a read-only, twenty-second check of the
default lab. It requires all thirty private/IoT BSS loads, native station
counts matching controller associations, all twenty client activity records,
advancing report timestamps and unavailable observations after receiver
shutdown. RDK prefixes the path with `gen/`.

Run inside the VM with a new output directory:

```sh
PYTHONPATH=optimizer python3 tests/native-load-acceptance.py \
  --stack prpl --output /tmp/native-load-new
```

For RDK use `PYTHONPATH=gen/optimizer`,
`gen/tests/native-load-acceptance.py` and `--stack rdk`.
No retunes, traffic injection, steering or native restarts occur.

Both pass on September 12. Complete load/activity coverage first appears in
**2.155 s prpl / 10.333 s RDK**; the activity calculation needs two native
counter reports. prpl covers one colocated and four remote APs through one
owned `uds_broker` subscription to AP Metrics Response CMDUs. RDK retains its
Ethernet receiver. Snapshot/decision transport provenance distinguishes
`prpl-local-broker`, `prpl-1905-broker` and `ieee1905-ethernet`.

The prpl v6 x86_64 little-endian broker envelope is checked against the pinned
source and live transport layout. Its native publication timestamp has
**one-second resolution**: retain that conservative timestamp, not the time a
queued record or cached NBAPI object is read. Reports older than five seconds,
future timestamps, unsupported envelopes and disconnected receivers fail
closed. Duplicate/older timestamps cannot refresh observations or activity.
No extra native requests, agents, services or public ports are introduced.
The default signal-only room starts no load collector.

The prpl recommend-mode room also exposes local-AP evidence and cleans up its
receiver on return to default. Both post-change UDP/native-BTM checks pass,
with no further move during twenty seconds of settling. Evidence is under
`/home/rev/work/steering-local-ap-0912/`: `*native-load*/`,
`steering-local-ap-prpl-load-1/`, `rdk-load-3/` and
`steering-local-ap-prpl-room-load/`.

### RDK steering-timeout investigation

Retained failures are specifically:

- **15.178 s:** September 12 17:05:21 UTC, STA `02:00:00:00:03:00`,
  `02:00:00:88:ae:ac` → `02:00:00:da:2e:b2`, channel 1.
- **40.088 s:** 17:10:24 UTC, evacuation STA `02:00:00:00:0d:00`,
  `02:00:00:da:2e:b2` → `02:00:00:c7:08:e5`, channel 6.

Both requests received successful native-helper acknowledgements in about
50 ms, but controller association verification stayed at the source.
The evacuation collector remained fresh and both views agreed; it was not a
forty-second browser repaint delay. The retained records lack synchronized
BTM/client/native-commit evidence for those exact failures. They cannot
distinguish an untransmitted request, client refusal or lost native reporting.
Their root cause therefore remains **unproven**, not fixed by inference.

Three bounded load repeats and two warm evacuation load/play runs now verify
**39/39 steers**, without native resets or relaxed gates. The first two loaded
moves take **1.207 / 1.440 s** from request to verification; transmitted BTM,
token-matched acceptance, target association and native commit are joined.
The previously failing evacuation tuple verifies in **1.490 / 0.886 s**.
Full BTM/acceptance/association/native-commit packet joins cover **37/39**;
two 6-GHz moves have protected action frames without a decoded BTM join.
All native uprobe traces close with matching event counts and zero lost events;
packet captures report zero kernel drops. The shared native-commit tracer now
opens its consumer before attaching probes, closing a startup observability
race without changing native behavior.

Keep the old failures. On recurrence capture all four boundaries before any
reset; API admission is not proof of transmitted BTM. The bounded drivers,
pcaps, client events, native commits and explicit ambiguous joins are in
`/home/rev/work/steering-local-ap-0912/rdk-*` and `rdk-summary.json`.
Single-guest wall/monotonic packet joins are not calibrated compositor timing.

### RDK warm-retune regression

The qualification driver replaces global `ApplyRadioSettings` plus agent
restart/policy replay with `Device.WiFi.WebConfig.Data.Subdoc.South`, using
`radio_2.4G` and a copy of the live `Init_dml` radio configuration. It preserves
all other fields, restores the original auto-channel setting, checks every
band against kernel/native inventory and rejects an agent PID change.

Two underlying reporting defects are fixed: missing OneWifi boolean function
declarations made i386 callers mistake completed radio timers for active ones;
the agent admitted channel reports only during controller channel selection
and considered only the first radio. Single/full-radio callbacks now match
their included radios in operational states; malformed/empty decodes fail closed.
Neither fix changes optimizer policy or invents controller measurements.

Four isolated channel changes plus four load-test changes pass in
**4.296–7.039 s**, without an agent restart or reporting-policy replay.
The 5/6-GHz radios stay at 36/37; all twenty clients regain fresh metrics.
This includes OneWifi's settling/publication timers, not instant retuning.
The initial single-radio attempt timed out after 35 s despite a correct
kernel channel; fixing OneWifi alone exposed the separate native dispatch gate.

Two successful loaded moves have packet traces with zero kernel capture drops.
Request → transmitted BTM takes **0.636–0.876 s**, BTM transmission → target
reassociation response **0.136–0.156 s**, and that response → API verification
**1.163–1.510 s**. These spans are not pure optimizer time; publication and
observation still contribute. Rate-limited journals cannot prove missing
events. The earlier intermittent 15/40-second failures are not yet explained.
Evidence: `/home/rev/work/rdk-retune-steering-0912/`, especially
`single-radio-qualified.json`, `load-2/`, and `load-3/`.

### Extender-loss repair and attribution

Two independent native publication stalls are removed:

1. **OneWifi 0028:** publish pending association deltas after completed control
   events, rather than waiting for the idle-only one-second analyzer.
   The existing encoder, notification path and analytics stay on the control
   thread; the periodic path remains available.
2. **Agent 0186:** advance ready commands after native events, including
   retiring completed work before admitting queued notifications. Preserve
   queue order, exclusive radio ownership and recursive command locking.
   Event dispatch never advances timeout statistics or transient handlers;
   the existing 250-ms timer still owns retries and expiry.

Both OneWifi variants and the agent are rebuilt; only rev140 is deployed.
The agent update preserves running OneWifi processes. Native controller,
HAL, hwsim, wmediumd, supplicant, scan frequencies and PMF timers are unchanged.
No forced roam, shortened security timer or relaxed acceptance gate is used.

Three warm 90-second loss/recovery repeats (`both-1/` through `both-3/`)
pass, followed by the complete 14-room catalog. In every qualified loss run,
the sampled room/topology has no clients on the disabled extender from room
time 25 s until fronthaul restoration at 60 s; backhaul stays connected.
Full-band scanning and the approximately one-second PMF recovery exchange
remain observable.

| Measured boundary | Before | Three warm repaired repeats |
| --- | --- | --- |
| OneWifi association callback → publication entry, median | 448.195 ms | 0.362–0.688 ms |
| Same callback → publication, maximum | 923.286 ms | 3.173 ms across 43 events |
| Native 6-GHz connection complete → controller commit | 524 ms in the failing OneWifi-only repeat | 35–54 ms |
| RF absence acknowledgement → controller commit | 5.115 s in that failing repeat | 4.189–4.610 s |

The first boundary includes callback work, not just queue waiting. Native
function probes use the guest monotonic clock; a sampled offset joins the RF
journal. Topology observations are approximately one second apart, not
compositor timestamps. These are measured deployment intervals, not instant
RF recovery or pure optimizer execution time.

All three repaired repeats have complete agent/controller probe counts with
zero lost events and clean supplicant capture completion. Their management
captures and the full catalog's management/1905 captures have zero kernel drops.
Failed/partial diagnostic captures remain separate from this evidence.

The original post-retune catalog and its focused repeat remain failures:
client `02:00:00:00:0e:00` still appeared on Extender-4 at room time 25 s.
OneWifi-only repeat `after-3/` also fails, showing that removing the first
stall alone was insufficient. The online runner and independent audit share
the unchanged outage gate and exit nonzero on failed or incomplete qualification.

Assembled-source regressions cover immediate publication, pending work,
timeout cadence, radio exclusion, FIFO admission and concurrent completion:

```sh
python3 gen/tests/association-publication-test.py "$ONEWIFI_SOURCE"
python3 gen/tests/orchestrator-ready-test.py "$MESH_SOURCE"
python3 gen/tests/orchestrator-completion-race-test.py "$MESH_SOURCE"
```

### Host headroom and restoration

The owned two-second sampler covers both catalog windows. Expensive frequency
and process attribution are opt-in, off by default. Unsupported counters stay null.

| Full-catalog observation | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| Samples / maximum gap | 811 / 2.005 s | 693 / 2.007 s |
| Total CPU p95 / peak | 14.75% / 20.85% | 33.90% / 41.28% |
| Minimum available RAM | 49.96 GiB | 12.74 GiB |
| Peak sampled sensor | 99.00°C | 85.50°C |
| Package throttling duration / measured window | 1788 ms / 1620.73 s | Unsupported, not zero |
| Package throttling time fraction | 0.1103% | Unsupported |
| Sampler elapsed p95 / max | 3.63 / 5.90 ms | 1.59 / 7.14 ms |

rev140 has limited thermal headroom, not RAM exhaustion or sustained total CPU
overload. Inspect physical cooling separately; these measurements do not
justify swapping hosts or increasing resources. No host power policy changes.

The read-only cooling inventory identifies an Intel NUC12WSKi7 with i7-1260P,
BIOS dated 2022-03-22, `intel_pstate` and the `powersave` governor. No fan-RPM
or PWM control is exposed through hwmon, so software cannot verify a blocked
vent, dust, fan condition or the firmware fan profile. A separate 90-second
paused-default sample averages **10.15%** total CPU, peaks at **13.07% CPU /
89°C**, with **zero additional milliseconds** between its first and last
package throttle-counter samples.
The lab VM uses approximately 1.5 logical CPUs on average, not all sixteen.
This is not evidence that cooling is repaired, nor a sustained overload.

The processor's specified junction limit is **100°C**, not a recommended
operating target; see [Intel's i7-1260P specifications](https://www.intel.com/content/www/us/en/products/sku/226254/intel-core-i71260p-processor-18m-cache-up-to-4-70-ghz/specifications.html).
In a separate maintenance window, the operator should:

1. Check enclosure clearance, unobstructed vents and fan operation; follow the
   manufacturer's cleaning/service guidance rather than changing VM limits.
2. Inspect the firmware Cooling profile and available model-specific firmware
   updates. [ASUS's NUC overheating guidance](https://www.asus.com/us/support/faq/1052612/)
   describes ventilation and BIOS fan controls. Record any change; do not
   update firmware or reboot a host during room qualification.
3. Repeat the same bounded catalog with the same workload and power policy,
   comparing temperature and throttle duration. Persistent limit hits need
   hardware cooling attention, not an unqualified performance claim.

The observer runs on rev150, so results are deployment observations, not
uncontended comparisons. The final prpl catalog follows its dependency repair;
it is not simultaneous with the final RDK window. A separate 180-second prpl
ubus diagnostic overlaps the preceding pre-registration catalog's first rooms,
not either final native/frame profile.

Both labs return to **20 clients/six logical roles**, default world paused at
zero, no lease/fault, fresh complete metrics and cap 100. Catalog restoration
first converges in **26.36 s RDK / 10.14 s prpl**, then holds.
Separate readiness checks pass in **12.484 s RDK / 10.139 s prpl**.
VM autostart remains disabled. No native restart occurs inside either final
catalog. Only internal startup payloads are refreshed; no thin tar or box is made.

### Evidence and limitations

Latest evidence is on rev150 under `/home/rev/work/hal-room-end-to-end-0913/`:

- `final-status.json`: audited catalogs, profiles, restored readiness and exact scope.
- `rdk-all-rooms-final/`, `prpl-all-rooms-registration/`: final 14-room results, sampled JSONL, fullscreen screenshots, host samples and native packets/logs.
- `rdk-native-room-final/`, `prpl-native-room-registration/`: native events, clock brackets, Chrome traces and strict WebGL presentation reports.
- `prpl-all-rooms-final-2/`: passing pre-registration catalog; `registration-audit.json` preserves observed RPC counts, concurrency and durations across both prpl catalogs.
- `packet-group-audit.json`: final prpl packet counts and concurrent-group bounds, distinct from exact single-request timing.
- `prpl-focused/`, `*-playback-fixed/`: candidate and clock/pose focused checks; `prpl-all-rooms/` retains the 13/14 viewer failure and `prpl-all-rooms-final/` the controller-crash attempt.
- `runtime-member-audit.json`, `ubus-runtime-member-audit.json`: exact internal-payload changes; native HAL/ubus source, build, fault-test and failed-deployment logs remain alongside.
- `rdk-final-readiness-2/`, `prpl-final-readiness-4/`: fresh default twenty-client policy convergence, paused/unleased and cap 100.

Earlier native-RCPI/topology timing and controlled overhead qualification remain
under `/home/rev/work/metric-presentation-0912/`; candidate-gap/adapter evidence
under `/home/rev/work/candidate-room-profiling-0913/`; native load and retained
RDK timeout evidence under `/home/rev/work/steering-local-ap-0912/`.
Extender-loss before/after evidence remains under
`/home/rev/work/extender-loss-fix-0912/`. Raw artifacts stay outside the repos;
failed, empty or ambiguous captures are not relabeled as passes.

Python regressions: **707 passed RDK / 605 passed prpl**. Both execute the
five daemon-integration checks using `WMDC_TEST_DAEMON`; RDK's four VirtualBox
contract checks remain explicitly skipped because Ruby is absent. Common
viewer/profiling JavaScript, documentation links and prpl Go race tests pass.
The actual native HAL passes fourteen fault scenarios; ubus dispatch passes
five callback/queue scenarios plus packaging-provenance negative controls.
Builders are stopped; owned captures end and `hwsim0` returns to DOWN.
The user's `hwsim0.pcap` is untouched. No thin release or box is produced.

### Remaining boundaries

The requested candidate-transport, bounded registration, common playback-
ordering and native serving-RCPI→room-presentation work is qualified above. The
ubus follow-up fixes a demonstrated dependency bug, without proving the exact
call chain of the uncored native crash. Preserve a current core/native trace
before any reset if it recurs; the historical uncaptured prpl gap and RDK
15/40-second failures also remain unattributed, not silently fixed by a pass.

Physical cooling inspection on rev140 requires an operator maintenance window.
Physical PHY/DCF, collisions/interference, reception-backed candidates,
calibrated demand/capacity, other native counters, and true RF-generation-to-
display timing are separate extensions. The qualified boundary starts at the
controller's serving-RCPI store, not reception or RF generation; headless
presentation feedback is not physical scanout. Finite tests do not establish
zero external delay or soak reliability. Packaging remains a separate task.
prpl's whole-second timestamp guard remains necessary until native publication
has sufficient request identity or timestamp precision; freshness is not weakened
to remove that measured wait.
