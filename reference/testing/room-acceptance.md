# Room correctness and convergence acceptance

[Testing reference](README.md) · [Expected room features](../rooms/catalog.md)

Run every advertised room sequentially within each lab; independent RDK and
prpl runs may overlap across hosts. This is bounded feature testing, not a soak
or intrinsic stack-speed ranking. A targeted `--world` run is not full coverage.

## Preparation

1. Reserve the lab. Save initial room/service configuration, native/container/
   medium identities and source revisions. No other operator lease or RF writer
   may be active. Do not alter native policy, metrics intervals or VM resources.
2. Copy the **deployed guest's** `wmediumd/configurator/worlds/golden/*.world.json`
   to the observer evidence directory. Match hashes to the loaded world.
3. Copy `tests/room-feature-guest-audit.py` and
   `tests/room-feature-rf-audit.py` into the guest's `/tmp/`, keeping names.
4. Use an installed Playwright/Chromium and preferably a separate observer.
   If colocated, restrict only owned browser GPU threads with `--observer-cpus`,
   using valid CPU IDs. Record host CPU/pressure/temperature/throttle counters
   with `tests/room-feature-host-monitor.py` before, during and after.
   Keep it in a foreground session or managed service; verify two samples before
   starting. A background child of a short-lived command may not survive it.
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
| Initial settling | Within 90 s after readiness: exact roster, no duplicate MACs, six mesh roles, matching physical/native/rendered ownership |
| Freshness | Current-epoch complete candidate coverage; evaluation and serving metrics at most 30 s old |
| Policy convergence | Complete fresh evaluation satisfies the configured steering margins; this is the pass gate |
| Strongest AP diagnostic | Report stronger same-band candidates and RCPI gaps separately; do not force margin-only roams |
| Stable gate | All required checks hold continuously for five seconds |
| Play | Real browser Play at 1×; monotonic clock, golden positions/presence, actual SVG nodes/parents |
| During motion | Record transient divergence; flag sustained view mismatch over five seconds only with adequate samples |
| Checkpoints | Allow 60 s per explicit pause, then resume on pass or timeout so later segments still run |
| End | Allow 120 s after completion for the same stable gate |
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
node tests/test-room-feature-acceptance.js
node --check tests/room-feature-acceptance.js
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright-core
export CHROMIUM_PATH=/absolute/path/to/chromium/chrome
node tests/room-feature-acceptance.js --yes-act --flavor prpl \
  --host rev150 --vm prplmesh-20-0908 \
  --room-url http://192.168.2.150:18891/ \
  --topology-url http://192.168.2.150:8091/ \
  --worlds /absolute/path/to/deployed-goldens \
  --output /absolute/path/to/new-results --native-audits 1
node tests/room-feature-report.js /absolute/path/to/new-results \
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
`tests/room-recovery-smoke.py --help`; it deliberately kills only the room
process and must be scheduled, not silently included in a normal room pass.

## Current qualification

September 11, 2026, canonical `codex/0908-clean`: RDK on rev140,
prpl on rev150. This is one pass through each advertised room, including Play,
fullscreen room/topology inspection, roster/presence transitions, RF readback,
native owner agreement and final policy convergence—not a soak or a
hardware-speed comparison. Test bounds are initial **60 s**, checkpoint
**45 s**, final **90 s**, with a five-second stable hold. Steering margins,
native reporting intervals and lab resources are unchanged. The temporary
2000-action qualification cap is restored to the normal 100 afterward.

### RDK results

The rev140 retest, **September 11 23:33–September 12 00:01 UTC**, passes
**14/14 complete room gates**: every initial, checkpoint and final gate, Play,
scene/roster checks, physical presence and native/rendered owner agreement.
Native/container/medium identities remain unchanged; no SSE gaps or browser
errors occur. This supersedes earlier diagnostic results.

The deployed worktree includes native patches through **0184**, Wi-Fi HAL
through **0038**, wmediumd through **0024**, and the corrected room action queue.
Ordinary cold reconstruction also passes 20 clients, five physical mesh nodes
and all native metrics in **527.07 s**. No native services restart during the
catalog run. Six logical mesh roles remain visible in both views.

| Room | Overall | Initial / final first policy convergence, seconds |
| --- | --- | --- |
| `home-a-stationary` | Pass | <0.02 / <0.02 |
| `home-a-one-client-handover` | Pass | 15.15 / 15.19 |
| `large-room-extender-evacuation` | Pass | 34.37 / 23.25 |
| `large-room-perimeter-counter-roam` | Pass | 32.37 / 7.09 |
| `home-a-asymmetric-link` | Pass | 18.21 / 8.09 |
| `home-a-band-walk-small` | Pass | 24.29 / 10.15 |
| `home-a-border-hover` | Pass | 24.29 / 21.29 |
| `home-a-disappear-reappear` | Pass | 20.25 / 7.09 |
| `home-a-extender-loss-recovery` | Pass | 8.08 / <0.02 |
| `home-a-fast-transit` | Pass | 19.19 / 14.17 |
| `home-a-flash-crowd` | Pass | 8.09 / <0.02 |
| `home-a-private-client-room-walk` | Pass | 33.45 / <0.02 |
| `home-a-slow-walk-ten` | Pass | 25.35 / 11.15 |
| `home-b-slow-walk-ten` | Pass | 33.49 / 12.16 |

These are first-convergence times; passing also requires the unchanged
five-second continuous hold. **153/153 submitted actions verify**, with no
failed verifications. Request-to-verification p50/p95/max is
**2.274/5.385/6.610 s**. Submission p50/p95 is **59/74 ms**; candidate
transaction p50/p95 is **509/654 ms**; publication wait p50/p95 is
**84/132 ms**. RF apply p50/p95 is **9.4/27.4 ms**.

The fixes cover four boundaries:

- **Presence and management delivery:** capability updates cannot resurrect
  departed clients; confirmed medium departures survive stale downlink traffic.
  HAL frame sockets cannot block or race teardown, and hostapd uses the normal
  disabled association-comeback test override.
- **Current RF and candidates:** fronthaul samples the confirmed serving
  uplink's simulated matrix RF, not an idle peer's last-packet RSSI. Backhaul
  retains kernel RSSI. This is modeled RF, not a newly received packet.
  Collection remains fair across roaming clients and requires each client's
  complete fresh same-band comparison before choosing a target.
- **Native command scheduling:** candidate and association commands dispatch
  at admission; confirmed commands release their radio before the next FIFO
  admission in that scheduler turn. Validated candidate/BTM reports complete
  during capability reporting without changing ACK ownership. Radio exclusion,
  locking, native retries and accepted-query deadlines remain unchanged.
- **Unsent action bookkeeping:** a full five-verification queue cannot mark an
  unsent client pending. Only requests passing dispatch guards enter pending.
  This removes a false 40-second timeout plus backoff without changing actual
  timeout, cooldown or backoff limits.

A packet-correlated reproduction found an accepted query waiting **8.1 s before
transmission**, behind association commands; its actual reply took **259 ms**.
Patch 0184 removes those avoidable timer turns, not the deadline. Both new
source-extraction regressions fail before the fix and pass on the built source.
Existing compiled native/HAL fixtures pass; final demo/optimizer/configurator
validation is **491 tests and 128 subtests passed**, with no skips. All 25 JavaScript
regression scripts pass at the unchanged UI baseline; the new catalog run also
inspects both live views throughout.

| Observed full-catalog metric | Before 0184 | After 0184 |
| --- | --- | --- |
| Complete room gates | 14/14 | 14/14 |
| Verified / failed moves | 153 / 0 | 153 / 0 |
| Native candidate HTTP 504 | 6 | 0 |
| Busy admission attempts / successful readmissions | 89 / 81 | 0 / 0 |
| Candidate transaction p95 | 1.040 s | 0.654 s |
| Request-to-verification p95 | 6.648 s | 5.385 s |

The targeted evacuation/perimeter/home-B check also passes **3/3**, **63/63**
verified moves and zero candidate timeouts/busy rejections. Epoch cancellations
remain separate from native failures. These bounded results do not guarantee
instant convergence or that future runs can never time out.

Restoration passes with twenty clients and six logical roles: first convergence
**33.44 s**, then the hold. The room is paused at zero, unleased, fault-free,
with its normal 100-action cap. Diagnostic capture is stopped and hwsim0 is down.
No new tar or box is created.

**Host caveat:** 168 rev140 samples show peak CPU **22.71%**, at least
**51.46 GiB available RAM**, peak sampled temperature **92°C**, and **11 package
throttle-counter increments**. CPU/RAM are not exhausted, but thermal headroom
is a separate profiling concern. No build or capture runs on rev140 during
qualification; the browser driver uses isolated CPUs on rev150. Timings are
observed deployment results, not an uncontended intrinsic-stack benchmark.

Evidence on rev150: `/home/rev/work/rdk-rooms-fix-0911/all-rooms-11/` contains
`results/`, `audited-summary.json`, restored state and time-filtered host
samples. `focused-7/` holds the targeted pass; `candidate-timeouts-0911.tar.gz`
contains the before-fix packet/journal trace, and the negative/positive fixture
logs retain regression proof. Earlier results remain separate, not relabeled.

### prpl results

The common-fix retest, **September 12 00:12–00:35 UTC**, passes **14/14 rooms**
and verifies **153/153** submitted steering actions, with no failed
verifications. Every initial/checkpoint/final gate, Play, physical presence,
scene and native/rendered owner check passes. Native/container/medium
identities remain unchanged, with no browser errors or SSE gaps.

Request-to-verification p50/p95/max is **0.924/1.175/1.388 s**; submission
p50/p95 is **451/510 ms**; RF apply p50/p95 is **7.0/32.4 ms**. NBAPI operation
p50/p95 is **142/173 ms**, publication wait **42/121 ms**. The native timestamp
resolution guard remains **501/545 ms**; removing it without native request
correlation would weaken freshness. Heterogeneous prpl collection operations
are not directly comparable to RDK candidate transactions.

One real **30.289-second incomplete candidate collection** remains during
extender-loss/recovery, on `Device.WiFi.DataElements.Network.Device.5.Radio.1`
for clients `02:00:00:10:01:00`, `02:00:00:10:07:00` and
`02:00:00:20:01:00`. It recovers within its room gate, but is not eliminated by
the common fixes. Epoch-superseded collections are cancellations, not additional
measurement failures. The report's HTTP-504-specific counter does not count
this prpl failure; inspect the incomplete operation and failure list too.

| Room | Initial / final first policy convergence, seconds |
| --- | --- |
| `home-a-stationary` | 0.02 / <0.02 |
| `home-a-one-client-handover` | 8.13 / <0.02 |
| `large-room-extender-evacuation` | 8.08 / 5.05 |
| `large-room-perimeter-counter-roam` | 8.08 / <0.02 |
| `home-a-asymmetric-link` | 12.12 / <0.02 |
| `home-a-band-walk-small` | 7.58 / 5.05 |
| `home-a-border-hover` | 6.12 / 2.04 |
| `home-a-disappear-reappear` | 5.06 / <0.02 |
| `home-a-extender-loss-recovery` | 3.05 / <0.02 |
| `home-a-fast-transit` | 4.05 / 5.05 |
| `home-a-flash-crowd` | 3.06 / <0.02 |
| `home-a-private-client-room-walk` | 4.07 / <0.02 |
| `home-a-slow-walk-ten` | 6.08 / 7.08 |
| `home-b-slow-walk-ten` | 11.15 / <0.02 |

These clocks start at the settling gate, not at a client's first movement.
A near-zero final value means it was already converged when that gate began;
the stable hold is additional. Native identities remain unchanged.

Perimeter counter-roam retains one **2-RCPI** stronger-AP gap
(`02:00:00:20:02:00`, `candidate_gain_too_small`). It passes configured policy,
not absolute-strongest-AP convergence; the other final gates satisfy both.
No steering margin was reduced to turn this case green.

The port includes fair collection across ownership changes, continued
collection during cooldown/backoff, complete per-client candidate comparisons,
unsent-action bookkeeping and the paired medium/Console departure tombstone.
prpl's observer, candidate provider, actuator, NBAPI and role mappings remain
native; no prplMesh/hostapd/hwsim binary is replaced. Final demo/optimizer/configurator
tests pass **404 tests and 123 subtests**, with no skips; four new regressions fail against the previous
source and pass with the fixes. Console Go and viewer regression tests pass.
Ordinary cold reconstruction passes in **454.00 s**.

Restoration reaches first policy convergence in **27.36 s**, then the hold,
with twenty clients, six roles, paused time zero, no lease/fault and cap 100.
Evidence is `/home/rev/work/prpl-common-0911/all-rooms-1/` on rev150, including
`results/`, `audited-summary.json` and restored state. Separate RF qualification
and its post-maintenance readiness checks are in the
[RF assessment](../radio/virtual-rf-assessment.md).

**Host sampling limitation:** the background sampler exited before the prpl
catalog began. There are zero in-window physical-host samples; this run cannot
qualify host thermal/load headroom. Later RF samples do not repair that gap.
Use a foreground session or managed service and verify at least two samples
before the next run, then retain the sampler through restoration.

### Remaining qualification boundaries

- prpl: trace the recovered 30-second candidate gap during extender recovery;
  a passing room deadline does not make that gap disappear.
- Common: instrument native model commit, publication/polling and actual
  browser paint separately before claiming controller-to-screen latency.
  The current SVG identity observer measures only one component.
- RDK diagnostics: preserve journal suppression and packet-capture counters.
  A post-failure capture cannot prove what happened before it started, and
  rate-limited journals cannot prove an unlogged transmission never occurred.
- Keep failed native actions, short presence-window mismatches and incomplete
  candidate snapshots in the results. Do not increase timeouts, weaken
  freshness or force clients onto targets to manufacture convergence.
