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

September 13, 2026 UTC, `codex/0908-clean`: both atomic-snapshot/WebGL follow-up catalogs pass
**14/14 after independent audit**, run in parallel on RDK/rev140 and prpl/rev150.
The unchanged five-second extender-loss departure gate passes on both.
Every available room loads and plays at 1×, with initial/checkpoint/final policy convergence, fullscreen
room/topology inspection, presence, directional RF and physical/native/rendered
ownership.
Both catalogs retain unchanged native/container/medium identities, no browser
errors or SSE gaps, and complete host sampling. These are bounded feature
tests, not a soak or an intrinsic stack-speed ranking.

The **60/45/90-second bounds and five-second stable hold** are unchanged.
Native reporting intervals, default steering margins and VM resources are
unchanged. Only the test action cap rises to 2000, then returns to 100.

### Catalog performance

| Observation | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| UTC window | 01:23:25–01:51:23 | 01:25:31–01:52:52 |
| Verified / submitted actions | 147 / 148 | 156 / 156 |
| Failed / discarded / unmatched verifications | 0 / 1 / 0 | 0 / 0 / 0 |
| Request → verification p50 / p95 / max, s | 1.683 / 4.796 / 7.714 | 1.001 / 1.165 / 1.413 |
| Submission p50 / p95 / max, s | 0.060 / 0.076 / 0.114 | 0.496 / 0.564 / 0.629 |
| RF application p50 / p95 / max, ms | 9.770 / 29.487 / 522.090 | 8.425 / 30.318 / 730.851 |
| Candidate publication wait p50 / p95 / max, ms | 83.474 / 130.508 / 628.876 | 38.491 / 86.342 / 712.372 |
| Unavailable collections / native HTTP 504s / busy rejections | 0 / 0 / 0 | 1 / 0 / 0 |
| Superseded collections, separate cancellations | 17 | 11 |

RDK's one discarded verification is cancelled by the next world load, not a
failed native steer or an unaccounted submission. The prpl restoration also
cancels one verification outside the catalog's action window. Neither is
counted as a verified action.

RDK candidate transactions p50/p95/max: **269.196 / 385.478 / 6411.265 ms**.
prpl NBAPI operations: **146.828 / 169.694 / 346.020 ms**;
complete collections: **943.903 / 980.523 / 1938.292 ms**.
prpl's timestamp-resolution guard remains **493/528 ms p50/p95**: removing
it without request correlation would weaken freshness validity. These measure
different boundaries, not interchangeable stack execution time.
Native binaries and steering policy remain unchanged; the prpl adapter now
reads coherent membership;
differences from preceding runs are not proof of a stack speedup.
Passing bounded gates is not a claim of zero external delay.

**Earlier prpl availability failure:** in the preceding catalog, while loading the perimeter room, one candidate
collection waits **30.36 seconds** for six entries on native
`Device.2.Radio.2`. The other four radios publish in about 0.59 seconds;
NBAPI reads remain responsive. The next round recovers and all room/steering
gates pass. This is a retained performance deficiency, not a cancelled round
or a failed steer. Its root cause is unproven; capture the native per-radio
query/response path before changing retry/freshness rules. The bounded follow-up
below captures a later **30.78-second** failure and localizes it before native
1905 response publication. It does not establish the earlier episode's cause.

RDK now includes agent **0185/0186** and OneWifi **0027/0028**, qualified below; its
controller and HAL through **0038**, prplMesh and hostapd remain unchanged.
Existing wmediumd **0026 RDK / 0027 prpl**
fix deadline starvation; common hwsim **0010** restores native aggregation
TX feedback. Neither forces rates, changes policy nor models physical aggregation.

### Per-room convergence

Initial/final **first policy convergence**, seconds from each settling gate,
not the first movement. Near-zero final values mean already converged;
the five-second continuous hold is additional.

| Room | RDK initial / final | prpl initial / final |
| --- | --- | --- |
| `home-a-stationary` | 0.02 / 0.01 | 0.02 / 0.01 |
| `home-a-one-client-handover` | 11.14 / 9.13 | 6.06 / 0.01 |
| `large-room-extender-evacuation` | 20.84 / 13.16 | 0.03 / 1.03 |
| `large-room-perimeter-counter-roam` | 23.28 / 7.10 | 9.72 / 0.01 |
| `home-a-asymmetric-link` | 14.17 / 2.03 | 0.02 / 0.01 |
| `home-a-band-walk-small` | 17.95 / 11.12 | 7.07 / 0.02 |
| `home-a-border-hover` | 20.25 / 0.01 | 6.15 / 2.03 |
| `home-a-disappear-reappear` | 16.17 / 0.01 | 8.08 / 0.01 |
| `home-a-extender-loss-recovery` | 9.48 / 0.01 | 6.07 / 0.01 |
| `home-a-fast-transit` | 12.82 / 8.12 | 8.08 / 3.03 |
| `home-a-flash-crowd` | 2.03 / 0.01 | 2.03 / 0.01 |
| `home-a-private-client-room-walk` | 12.18 / 0.01 | 6.10 / 0.01 |
| `home-a-slow-walk-ten` | 19.26 / 9.17 | 1.04 / 6.12 |
| `home-b-slow-walk-ten` | 23.31 / 8.14 | 40.49 / 0.01 |

Absolute-strongest diagnostics remain separate from policy convergence:

- prpl: `large-room-extender-evacuation`, `02:00:00:10:03:00`, 2 RCPI above the current AP; `candidate_gain_too_small`.

These are policy passes, not claims that every client always selects the
absolute strongest AP. `room-final-readiness.py` uses the same fresh,
complete policy gate and five-second hold; `--require-absolute-best` adds
the stricter optional check. No target is forced to make acceptance pass.

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

| Qualified fullscreen capture | RDK | prpl |
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

The assembled laboratory HAL's `read_snr` uses one `send`/`recv` pair, continues
on a failed receive, and checks frequency but not the echoed source/destination.
An offline fault-injection harness using that exact function reproduces a
missing first metric and misassigned subsequent RSSI when the first `recv`
returns `EINTR`. This proves a transport-handling weakness, **not which errno
occurred live**: the current HAL does not log it. Packet turnaround rules out
a 30-second bridge/1905 delivery delay for this particular response, not all
possible native delays or the earlier six-entry failure.

**Next native-HAL qualification:** preserve one-request/one-response alignment
across interrupted syscalls with a bounded deadline, validate echoed link
identity, and abandon a desynchronized transaction rather than label another
station's signal. Add deterministic interrupted/late/wrong-identity tests,
then rebuild/deploy the prpl laboratory HAL and repeat the full catalog.
This follow-up changes only the adapter, diagnostics and opt-in profilers;
the HAL repair is **not implemented or deployed**, and the live gap is not
claimed fixed. Do not hide it by accepting cached values or relaxing timeouts.

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

### Room WebGL presentation

The common opt-in profiler also covers decoded room network snapshots to
**client gauge materials and association-line geometry, actual WebGL draws,
canvas mailbox preparation, and exact Chrome frame presentation feedback**:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright-core \
CHROMIUM_PATH=/path/to/chromium-139.0.7258.5/chrome \
node gen/tests/room-render-latency.js --url http://192.168.2.140:48891/ \
  --output /tmp/rdk-room-render-new --seconds 65
```

For prpl omit `gen/` and use `http://192.168.2.150:18891/`. Run passively while
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

| Qualified fullscreen profile | RDK band walk | prpl perimeter |
| --- | --- | --- |
| Checked and presented network frames | 259/259 | 258/258 |
| Frames with changed client state | 31 | 38 |
| SSE decode → presentation p95 upper | 230.77 ms | 327.99 ms |
| Maximum presentation upper | 344.97 ms | 428.34 ms |
| Observer callback p95 upper | 0.50 ms | 0.51 ms |
| Observer callback wall-time upper fraction | 0.153% | 0.153% |

The unchanged callback budgets are p95 ≤2 ms and ≤1% of elapsed wall time.
An initial profiler used layout-forcing canvas bounds reads; removing those
reduces its measured callback p95 upper from 4.10 ms to the values above.
Earlier failed/empty captures are retained, not counted as passes.
Different rooms and software GPU scheduling preclude an intrinsic stack-speed
comparison. This is **not** native RF-to-room timing, physical scanout,
pixel-exact framebuffer validation, completed animations, or qualification of
every mesh/wall effect. The topology native-RCPI profile remains separate.

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
| Samples / maximum gap | 839 / 2.005 s | 821 / 2.011 s |
| Total CPU p95 / peak | 15.72% / 20.50% | 36.02% / 52.93% |
| Minimum available RAM | 49.96 GiB | 11.68 GiB |
| Peak sampled sensor | 100.00°C | 85.50°C |
| Package throttling duration / measured window | 980 ms / 1676.76 s | Unsupported, not zero |
| Package throttling time fraction | 0.0584% | Unsupported |
| Sampler elapsed p95 / max | 4.04 / 5.93 ms | 1.62 / 11.54 ms |

rev140 has limited thermal headroom, not RAM exhaustion or sustained total CPU
overload. Inspect physical cooling separately; these measurements do not
justify swapping hosts or increasing resources. No host power policy changes.
The observer runs on rev150, so results are deployment observations, not
uncontended comparisons. These catalogs run simultaneously and share the
observer's CPU 0–1 affinity.

Both labs return to **20 clients/six logical roles**, default world paused at
zero, no lease/fault, fresh complete metrics and cap 100. Catalog restoration
first converges in **28.20 s RDK / 15.94 s prpl**, then holds.
Separate readiness checks pass in **11.210 s RDK / 19.274 s prpl**.
VM autostart remains disabled.
No native restart occurs inside either final catalog; no thin tar or box is made.

### Evidence and limitations

Latest evidence is on rev150 under `/home/rev/work/candidate-room-profiling-0913/`:

- `*-all-rooms/audited-summary.json`: final full catalogs, screenshots, JSONL, host samples and native captures.
- `prpl-perimeter-followup-2/`: retained duplicate-client failure; `prpl-perimeter-fixed/` is the repaired focused pass.
- `candidate-room-prpl-0913*/`: native per-agent packets/logs; `packets-*-summary.json` describes diagnostic repeats and the final catalog. Partial station-set responses remain ambiguous, not successful joins.
- `prpl-catalog-gap-event.json`, `prpl-agent-02-full-monitor-window.log`, `candidate-read-reproduction.log`: the captured late failure and offline interrupted-read reproduction, with the extracted source/harness alongside.
- `rdk-webgl-final/`, `prpl-webgl-qualified/`: qualified fullscreen WebGL profiles; earlier failed/empty attempts remain separate.
- `*-final-readiness/`, `rdk-regression.log`, `prpl-regression-final.log`, `prpl-go-race.log`: restored defaults and regression checks.

The preceding native-RCPI/topology profiles remain under
`/home/rev/work/metric-presentation-0912/`:

- `*-all-rooms/audited-summary.json`: full catalogs, with adjacent fullscreen screenshots, JSONL, host samples and RDK native/management captures.
- `timing-summary.json`: clock-precision reaudits of `rdk-metrics-clocks/`, `prpl-metrics-presentation/` and both `*-associations-final/` captures.
- `*-overhead-qualified/report.json`: controlled observer qualification; `*-final-readiness/` verifies restored defaults.

Earlier failed or empty profiling attempts are retained separately. They
exposed an HTTP-boundary attribution race, a ten-second trace-export timeout,
and lazy tracing-service creation across baseline windows. The profiler fixes
these without changing room gates; captures with no metric transitions remain
unqualified rather than passing with zero samples.

The preceding native-load/timeout follow-up remains under
`/home/rev/work/steering-local-ap-0912/`, including native load coverage and
load-driven BTM. All raw evidence remains outside the repositories.

The earlier extender-loss repair evidence remains under
`/home/rev/work/extender-loss-fix-0912/`: `all-rooms/audited-summary.json`,
screenshots/JSONL, `extender-loss-fixed-catalog/`, `both-1/` through `both-3/`,
before/partial-fix trials, build logs, regression logs and final readiness.
Earlier failed room audits, warm-retune/load qualifications and packet joins
remain under `/home/rev/work/rdk-retune-steering-0912/`.
`hwsim0` returns to DOWN and owned captures stop; no user pcap is modified.
No new thin tar or box is produced.

The earlier `/home/rev/work/policy-profiling-0912/` contains:

- `rdk-all-rooms-clean-final/`, `prpl-all-rooms/`: the earlier 14/14 baseline audits, screenshots, JSONL and host samples.
- `rdk-native-paint-periodic/`, `prpl-native-paint-periodic/`: bounded native/Chrome/clock evidence.
- `rdk-load-policy-0912-13/`, `prpl-load-policy-0912-7/`: qualified policy actions, native control events and restoration; prpl receiver repeat in `prpl-load-policy-0912-6/`.
- `rdk-default-qualified/`, `prpl-default-qualified/`: restored default readiness.

The preceding `rdk-all-rooms-final/` remains **13/14**, with 149/150 moves
verified; the timeout investigation above preserves its failed evacuation
gate. The warm-retune regression qualifies replacing global radio Apply and
agent refresh with single-radio updates that preserve sibling channels and
the running agent's reporting policy.

Python regressions: **702 passed RDK / 590 passed prpl**, including the 12-test
prpl adapter suite and two native-capture lifecycle tests. Five daemon-integration checks per stack require `WMDC_TEST_DAEMON`;
four RDK VirtualBox checks require Ruby. These are explicit skips, not passes.
Documentation/link checks, JavaScript and prpl Go race tests pass. Assembled-source scheduler, channel dispatch, association publication,
ready-command, completion-race and candidate-dispatch regressions pass.
Prior RF/timer/feedback evidence remains under
`/home/rev/work/profiling-gates-0912/`; see
[RF qualification](../radio/virtual-rf-assessment.md#results-and-remaining-work).
Physical PHY/DCF, collision/interference fidelity, reception-backed candidates,
calibrated demand/capacity, all-counter timing and native RF-to-room WebGL timing
remain outside the implemented scope. Native RCPI/topology presentation and
the room's decoded-client-snapshot/WebGL frame boundary are qualified above.
Retain failures; never weaken freshness or room timeouts.

### Remaining implementation order

The RDK extender-loss regression gate is closed by the qualification above.
The serving-RCPI/topology-presentation profiling path is implemented above.
Remaining work is separate:

1. **prpl candidate transport:** repair and qualify the laboratory HAL's
   interrupted-read/response-identity handling described above. Retain both
   availability failures; the 14/14 room result does not close this defect.
2. **RDK timeout attribution:** the bounded investigation above does not
   reproduce the historical failures. Preserve native/client captures if they recur.
3. Broader profiling can join native events to the room's now-qualified WebGL
   boundary and add other counters; do not relabel these subsets as every subsystem.
4. Keep packaging separate; repeat the unchanged regression gates after changes.
   Local AP telemetry is implemented and qualified above, not an open feature.
