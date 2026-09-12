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
node tests/test-room-feature-acceptance.js
node --check tests/room-feature-acceptance.js
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright-core
export CHROMIUM_PATH=/absolute/path/to/chromium/chrome
node tests/room-feature-acceptance.js --yes-act --flavor prpl \
  --host rev150 --vm prplmesh-20-0908 \
  --room-url http://192.168.2.150:18891/ \
  --topology-url http://192.168.2.150:8091/ \
  --worlds /absolute/path/to/deployed-goldens \
  --output /absolute/path/to/new-results --native-audits 1 \
  --initial-timeout 60 --checkpoint-timeout 45 --final-timeout 90
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

September 12, 2026 UTC (September 11 Pacific), `codex/0908-clean`:
RDK/rev140 and prpl/rev150 both pass **14/14 complete room gates**.
Coverage includes loading, initial/checkpoint/final policy convergence,
Play, fullscreen room/topology inspection, presence, directional RF readback
and physical/native/rendered ownership. No browser errors, SSE gaps or
native/container/medium identity changes occur inside either final catalog.

The existing **60/45/90-second bounds and five-second stable hold** remain.
No steering margin, native reporting interval or VM resource limit changes.
Qualification temporarily raises the action cap to 2000, then restores 100.
These are bounded feature tests, not a soak or an intrinsic stack-speed ranking.

### RDK results

**04:44:35–05:13:38 UTC: 14/14; 147/147 submitted moves verified**.
Zero failed/discarded/unmatched verifications, unavailable collections,
native HTTP 504s or busy-admission rejections. Seventeen superseded collections
are separate cancellations, not failed measurements.

Request-to-verification p50/p95/max: **2.204/5.104/7.007 s**.
Submission p50/p95: **57/75 ms**; candidate transaction **513/663 ms**;
publication wait **86/134 ms**; RF application **8.9/26.5 ms**.
The candidate transaction maximum remains **5.191 s**; recording only its
median would hide that tail. These intervals measure distinct boundaries.

Native EasyMesh through **0184** and HAL **0038** are unchanged.
wmediumd **0026** fixes earliest-deadline timer starvation; common hwsim
**0010** restores singleton aggregation TX feedback to native rate control.
Neither forces rates, changes steering policy nor adds physical aggregation.

### prpl results

**04:34:06–04:58:33 UTC: 14/14; 154/154 submitted moves verified**.
Zero failed/discarded/unmatched verifications, unavailable collections,
worker errors, native HTTP 504s or busy-admission rejections.
Eleven superseded collections remain separate cancellations.

Request-to-verification p50/p95/max: **1.031/1.227/1.468 s**.
Submission p50/p95 **482/566 ms**; NBAPI operation **150/180 ms**;
publication wait **44/112 ms**; complete collection p95/max **0.983/5.038 s**;
timestamp-resolution wait **470/539 ms**; RF application **9.6/36.4 ms**.
The native freshness guard remains: removing it without request correlation
would weaken measurement validity. prpl operations are not RDK transactions.

prplMesh and hostapd binaries are unchanged. The common timer fix is
wmediumd **0027**, with hwsim **0010**. Existing fixes for fresh RCPI zero,
recoverable observer outages and in-flight-only native-read sharing remain.

### Per-room convergence

Initial/final **first policy convergence**, seconds from each settling gate,
not from the first movement. Near-zero final values mean already converged;
the five-second continuous hold is additional.

| Room | RDK initial / final | prpl initial / final |
| --- | --- | --- |
| `home-a-stationary` | 1.03 / <0.02 | 0.02 / <0.02 |
| `home-a-one-client-handover` | 16.17 / 11.15 | 6.05 / <0.02 |
| `large-room-extender-evacuation` | 25.28 / 23.26 | 7.31 / <0.02 |
| `large-room-perimeter-counter-roam` | 28.33 / 6.11 | 9.19 / <0.02 |
| `home-a-asymmetric-link` | 13.20 / 6.08 | 10.09 / <0.02 |
| `home-a-band-walk-small` | 26.28 / 14.19 | 6.06 / 1.01 |
| `home-a-border-hover` | 30.38 / <0.02 | 5.06 / 1.02 |
| `home-a-disappear-reappear` | 21.28 / <0.02 | 3.04 / <0.02 |
| `home-a-extender-loss-recovery` | 7.45 / <0.02 | 2.04 / <0.02 |
| `home-a-fast-transit` | 19.22 / 21.25 | 2.03 / 7.09 |
| `home-a-flash-crowd` | 8.12 / <0.02 | 6.08 / <0.02 |
| `home-a-private-client-room-walk` | 22.30 / 0.02 | 9.02 / <0.02 |
| `home-a-slow-walk-ten` | 29.52 / 25.37 | 8.19 / 8.21 |
| `home-b-slow-walk-ten` | 32.42 / 16.25 | 10.16 / 1.04 |

Absolute-strongest diagnostics retain **2-RCPI** margin-held differences:
RDK stationary/handover client `02:00:00:00:06:00`, and home-b client
`02:00:00:00:16:00`. prpl final gates have none. These are policy passes,
not claims that every client always selects the absolute strongest AP.

The separate default-readiness checker previously rejected this valid margin,
unlike the catalog. It now requires the same configured-policy convergence,
matching decision ownership/coverage, fresh complete metrics and the original
five-second hold. It still records absolute-best status and stronger candidates.
Use `room-final-readiness.py --require-absolute-best` for the stricter check.
The original **120.973-second strict failure** is retained; no target is forced
and no native margin is lowered to hide it.

### Browser paint attribution

Run the read-only probe during a scheduled moving-room test:

```sh
node gen/tests/controller-render-latency.js --url http://192.168.2.140:48889/ --output /tmp/rdk-paint-new --seconds 180
```

On prpl omit `gen/` and use `http://192.168.2.150:8091/`.
Use the same Playwright/Chromium environment as the catalog.

The probe marks decoded responses and matching SVG associations, then joins
a subsequent Chrome main-thread **Paint covering the client's bounds**.
Wrong-thread, missing/late paint, superseded records, trace loss and pending
associations cannot pass. Two matching animation frames alone are insufficient.
Trace shutdown is bounded and closes its owned stream/browser.

Both three-minute post-feedback probes pass with no lost events:

| Observation | RDK, 32 changes | prpl, 35 changes |
| --- | --- | --- |
| Decoded response → Paint p50 / p95 / max | 17.8 / 38.6 / 49.3 ms | 16.3 / 102.0 / 102.0 ms |
| HTTP request → Paint p50 / p95 / max | 56.0 / 80.3 / 90.4 ms | 46.6 / 131.3 / 131.3 ms |

This **excludes native commit-to-poll waiting, compositor presentation,
physical display and completion of layout animation**. It is not a
zero-external-delay claim.

### Host evidence and restoration

The owned two-second SSH sampler covers each exact catalog window without
errors or gaps. Unsupported counters stay null.

| Full-catalog observation | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| Samples / maximum gap | 872 / 2.032 s | 733 / 2.019 s |
| Total CPU p95 / peak | 13.97% / 57.55% | 43.71% / 48.58% |
| Minimum available RAM | 49.16 GiB | 12.74 GiB |
| Peak sampled sensor | 93°C | 85.5°C |
| Package throttle-counter increase | **36** | Unsupported, not zero |

RAM is not exhausted; RDK has a transient CPU peak and limited thermal headroom.
The sampler does not identify historical per-process CPU ownership, so do not
attribute that peak solely to the lab. Inspect physical cooling/power policy
separately; no host power setting or VM sizing is changed.
Both browsers run on rev150 with separate GPU CPU sets, and the catalogs
partly overlap. These are deployment observations, not uncontended comparisons.

Both labs return to **20 clients/six logical roles**, default world paused at
zero, unleased/fault-free, fresh complete metrics and cap 100. Catalog
restoration first converges in **31.48 s RDK / 13.31 s prpl**, then holds.
Separate final readiness and monitor-ACK checks pass. VM autostart remains
disabled. No native restart occurs inside either final catalog; no release
thin tar or box is created.

### Evidence and remaining boundaries

Current evidence on rev150: `/home/rev/work/profiling-gates-0912/`.
`rdk-all-rooms-feedback/` and `prpl-all-rooms-feedback/` contain final
audits, screenshots, JSONL and host samples; `*-render-paint-feedback/`
contains raw Chrome traces and reports. RF evidence and prior timer-only
catalogs remain beside them. Earlier failed/inconclusive evidence stays under
`/home/rev/work/qualification-fixes-0912/`, not relabeled.

Python and JavaScript regressions pass, including actual-scheduler and hwsim
feedback fixtures. Four Ruby-dependent RDK VirtualBox checks remain unavailable
on this observer; no VirtualBox artifact is being built.

- **RF:** both stacks pass 12- and 20-second spatial windows with unchanged
  reuse/exclusion and <5% repeatability gates; see
  [RF qualification](../radio/virtual-rf-assessment.md#results-and-remaining-work).
  Native rate adaptation is restored, not replaced by fixed rates.
- **Profiling:** exact native commit-to-publication/poll timing and final
  compositor/display presentation still need separate correlation.
- **Model:** modern PHY/DCF, physical collisions/interference, calibrated
  capacity and load-aware policy remain separate future work.
- Retain failures, presence mismatches, unavailable snapshots and discarded
  verifications. Never weaken freshness or timeouts to manufacture convergence.
