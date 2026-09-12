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

September 12, 2026 UTC, `codex/0908-clean` working trees: the latest
RDK/rev140 catalog passes **14/14 after independent audit**, including the
unchanged five-second extender-loss departure gate. Three preceding warm
loss/recovery repeats also pass without resetting native services between runs.
The unchanged prpl/rev150 qualification remains **14/14**. Every room loads
and plays at 1×, with initial/checkpoint/final policy convergence, fullscreen
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
| UTC window | 21:41:57–22:08:21 | 16:03:14–16:26:59 |
| Verified / submitted actions | 150 / 150 | 155 / 155 |
| Failed / discarded / unmatched verifications | 0 / 0 / 0 | 0 / 0 / 0 |
| Request → verification p50 / p95 / max, s | 1.711 / 5.907 / 7.999 | 1.032 / 1.231 / 1.719 |
| Submission p50 / p95 / max, s | 0.059 / 0.074 / 0.104 | 0.485 / 0.590 / 0.635 |
| RF application p50 / p95 / max, ms | 8.662 / 29.496 / 515.927 | 8.949 / 51.301 / 677.072 |
| Candidate publication wait p50 / p95 / max, ms | 85.145 / 130.681 / 743.800 | 42.391 / 107.784 / 630.228 |
| Unavailable collections / native HTTP 504s / busy rejections | 0 / 0 / 0 | 0 / 0 / 0 |
| Superseded collections, separate cancellations | 17 | 17 |

RDK candidate transactions p50/p95/max: **268.480 / 387.504 / 7833.369 ms**.
prpl NBAPI operations: **149.754 / 181.344 / 299.624 ms**;
complete collections: **936.268 / 980.837 / 2954.019 ms**.
prpl's timestamp-resolution guard remains **480/534 ms p50/p95**: removing
it without request correlation would weaken freshness validity. These measure
different boundaries, not interchangeable stack execution time.
RDK's median request → verification improves from 2.477 to 1.711 s versus
the failed post-retune catalog, but its p95/max tails do not improve.
Passing bounded gates is not a claim that every latency decreases.

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
| `home-a-stationary` | 1.04 / 0.01 | 8.37 / 0.01 |
| `home-a-one-client-handover` | 11.15 / 2.04 | 6.06 / 0.01 |
| `large-room-extender-evacuation` | 19.22 / 13.18 | 8.11 / 1.02 |
| `large-room-perimeter-counter-roam` | 23.25 / 8.12 | 9.13 / 0.01 |
| `home-a-asymmetric-link` | 14.19 / 6.08 | 11.14 / 0.01 |
| `home-a-band-walk-small` | 17.36 / 8.11 | 8.08 / 3.03 |
| `home-a-border-hover` | 23.27 / 17.25 | 10.13 / 2.03 |
| `home-a-disappear-reappear` | 18.25 / 0.01 | 3.04 / 0.01 |
| `home-a-extender-loss-recovery` | 7.08 / 0.01 | 3.05 / 0.01 |
| `home-a-fast-transit` | 18.21 / 18.25 | 11.12 / 6.06 |
| `home-a-flash-crowd` | 8.11 / 0.01 | 6.07 / 0.02 |
| `home-a-private-client-room-walk` | 13.21 / 0.01 | 3.04 / 0.01 |
| `home-a-slow-walk-ten` | 17.28 / 10.15 | 3.06 / 6.10 |
| `home-b-slow-walk-ten` | 25.36 / 6.09 | 12.18 / 3.04 |

Absolute-strongest diagnostics remain separate from policy convergence:

- rdk: no stronger same-band candidate remains at the settled final samples.
- prpl: `home-a-stationary`, `02:00:00:10:04:00`, 2 RCPI held by the configured margin.
- prpl: `home-a-one-client-handover`, `02:00:00:10:04:00`, 2 RCPI held by the configured margin.
- prpl: `home-a-slow-walk-ten`, `02:00:00:20:08:00`, 2 RCPI held by the configured margin.

These are policy passes, not claims that every client always selects the
absolute strongest AP. `room-final-readiness.py` uses the same fresh,
complete policy gate and five-second hold; `--require-absolute-best` adds
the stricter optional check. No target is forced to make acceptance pass.

### Native commit → browser Paint

Use the catalog's Playwright/Chromium environment and a new output directory
during scheduled movement. On RDK:

```sh
node gen/tests/controller-render-latency.js \
  --url http://192.168.2.140:48889/ --output /tmp/native-paint-new \
  --seconds 150 --native-stack rdk --host rev140 --vm rdkeasymesh-20-0908
```

On prpl omit `gen/`, use URL `http://192.168.2.150:8091/`,
`--native-stack prpl --host rev150 --vm prplmesh-20-0908`.
The guest requires root Python/BCC and the exact qualified native binary hash.
Unknown builds fail closed. The probe owns its bounded uprobe receiver,
browser and streams; there is no always-on collector or native binary change.

| Periodically calibrated capture | RDK | prpl |
| --- | --- | --- |
| Unambiguous native association → Paint joins | 29/29 | 34/34 |
| p95 interval | 391.00–393.02 ms | 254.85–255.66 ms |
| Maximum upper bound | 401.85 ms | 263.73 ms |
| Maximum clock uncertainty | 2.85 ms | 2.69 ms |

Monotonic clock brackets refresh every ten seconds and include drift at each
event. Per-STA watermarks prevent ambiguous recurrence joins. Native/perf
loss, wrong-thread or non-covering Paint, missing joins and trace errors fail.
Retain raw native events, clock samples and Chrome traces.

The removed prpl **750-ms completed-response cache** previously yielded
native-to-Paint p95 **815.72–843.02 ms**; a post-fix 25-transition follow-up
yielded **149.01–156.61 ms**. Concurrent reads now share only an in-flight
request; errors cannot return successful stale topology. Different movement
samples are not a controlled intrinsic-stack speed comparison.

Scope is **association-model commit to covering main-thread Paint**, not all
metric commits, exact server publication, layout-animation completion,
compositor or physical display. Request/decode timestamps bracket publication,
polling and transport. No zero-external-delay claim is made. Paint attribution
is independent of room convergence and cannot turn a failed room into a pass.

### Opt-in policy outcome

Two RDK warm-retune repetitions and the separate prpl qualification pass with
the production twenty-client pool intact. Native AP metrics/activity drive one gentle BTM to a slightly
weaker, quieter AP on another 2.4-GHz channel. Signal-only remains the default.
Both live-room recommend-mode smoke tests also pass, including owned receiver
shutdown and restoration; these smoke tests authorize no steering.

| Observation | RDK | prpl |
| --- | --- | --- |
| Source → target RCPI | 148 → 144 | 148 → 144 |
| Native utilization, octet 0–255 | 234 → 11–12 | 235 → 15 |
| Sustained condition before action | 10.533–10.553 s | 5.058 s |
| Request → native verified association | 1.954–2.522 s | 0.674 s |
| Verifier-only interval | 1.903–2.470 s | 0.229 s |
| Additional actions during ≥20 s settling | 0 | 0 |

RDK uses five-second report skew/freshness and a ten-second hold because its
independent native periodic reports arrive staggered. prpl uses one-second
skew/five-second hold. Both AP reports must advance; default room gates and
native reporting intervals do not change. Unknown/stale load never means idle.

Two 12-Mbit/s UDP senders deliver approximately **13.55 → 29.60 Mbit/s RDK**
in receiver windows 5–15 s and 65–75 s. The separate prpl repeat delivers
**12.58 → 25.04 Mbit/s** in the same windows. Later windows include queued
traffic draining and can exceed the 24-Mbit/s offered rate; these are receiver
delivery observations, **not calibrated capacity or steady-state gains**.
Packet activity is not offered demand; wireless hops are not backhaul capacity.

Client control events confirm native BTM reception, scan and association.
Setup scans/roams and retunes occur before timed
steering; cleanup restores them and verifies fresh twenty-client metrics.
The RDK target starts and ends at **6/36/37** (2.4/5/6 GHz); only its
2.4-GHz channel changes. This is not arbitrary radio-configuration qualification.
Earlier RDK preparation failures and a 15-second native BTM verification
timeout remain failed evidence; one later successful move does not explain
away that timeout. No forced roam repairs a measured failure.

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
| Samples / maximum gap | 792 / 2.006 s | 713 / 2.007 s |
| Total CPU p95 / peak | 15.54% / 19.28% | 43.92% / 50.63% |
| Minimum available RAM | 49.96 GiB | 12.61 GiB |
| Peak sampled sensor | 97.00°C | 85.50°C |
| Package throttling duration / measured window | 1164 ms / 1582.73 s | Unsupported, not zero |
| Package throttling time fraction | 0.0735% | Unsupported |
| Sampler elapsed p95 / max | 3.60 / 5.88 ms | 1.62 / 6.87 ms |

rev140 has limited thermal headroom, not RAM exhaustion or sustained total CPU
overload. Inspect physical cooling separately; these measurements do not
justify swapping hosts or increasing resources. No host power policy changes.
The observer runs on rev150, so results are deployment observations, not
uncontended comparisons. The final catalogs do not run simultaneously.

Both labs return to **20 clients/six logical roles**, default world paused at
zero, no lease/fault, fresh complete metrics and cap 100. Catalog restoration
first converges in **27.43 s RDK / 10.19 s prpl**, then holds.
Separate readiness checks pass in **5.094 s RDK / 5.113 s prpl**.
VM autostart remains disabled.
No native restart occurs inside either final catalog; no thin tar or box is made.

### Evidence and limitations

Latest RDK evidence is on rev150 under
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
verified: evacuation's initial gate failed on one 40.088-second native
verification timeout, despite later convergence. Retuning experiments also
exposed stale staged channel values and volatile reporting policy after agent
refresh. The new driver instead preserves all radio channels and the running
agent; the retune regression above qualifies this replacement. The timeout's cause is
not proven, and the clean rerun is not evidence that it can never recur.

Python regressions: **670 passed RDK / 543 passed prpl**, plus ten prpl adapter
tests. Five daemon-integration checks per stack require `WMDC_TEST_DAEMON`;
four RDK VirtualBox checks require Ruby. These are explicit skips, not passes.
Both 65-test documentation/monitoring subsets, JavaScript and prpl Go race
tests pass. Assembled-source scheduler, channel dispatch, association publication,
ready-command, completion-race and candidate-dispatch regressions pass.
Prior RF/timer/feedback evidence remains under
`/home/rev/work/profiling-gates-0912/`; see
[RF qualification](../radio/virtual-rf-assessment.md#results-and-remaining-work).
Physical PHY/DCF, collision/interference fidelity, reception-backed candidates,
calibrated demand/capacity and non-association/compositor timing remain outside
the implemented scope. Retain failures; never weaken freshness or timeouts.

### Remaining implementation order

The RDK extender-loss regression gate is closed by the qualification above.
Remaining profiling/load-policy work is separate:

1. **RDK native steering:** retain the earlier 15/40-second failures and capture
   request admission, transmitted BTM, client response and native commit on
   any recurrence. The latest 150/150 moves do not establish their root cause.
2. **prpl local AP telemetry:** add native colocated AP report provenance and
   freshness to the opt-in load collector; never timestamp cached NBAPI reads
   as new measurements or substitute bridge-modeled load for native reports.
3. **Common profiling:** cover non-association metric publication and
   compositor completion, with bounded observer overhead and clock uncertainty.
4. Keep packaging separate; repeat the unchanged regression gates after changes.
