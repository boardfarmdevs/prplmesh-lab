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

September 12, 2026 UTC (September 11 Pacific), `codex/0908-clean` worktrees:
RDK on rev140 and prpl on rev150. Both pass **14/14 complete room gates**:
load, initial/checkpoint/final policy convergence, Play, fullscreen room and
topology inspection, roster/presence, directional RF readback and
physical/native/rendered ownership. Final catalogs have no native/container/
medium identity changes, browser errors, SSE gaps or worker errors.

Bounds remain **60/45/90 seconds**, plus the **five-second stable hold**.
Steering margins, native reporting intervals and VM resources are unchanged.
The qualification-only 2000-action cap is restored to 100. These are bounded
feature tests, not a soak or an intrinsic stack-speed comparison.

### RDK results

**01:41:59–02:09:55 UTC: 14/14 rooms; 151/151 submitted moves verified**.
There are zero failed verifications, unavailable candidate collections,
native HTTP 504s or busy-admission rejections. Nineteen superseded collections
are cancellations, not measurement failures.

Request-to-verification p50/p95/max: **2.181/4.786/6.211 s**.
Submission p50/p95: **56/69 ms**; candidate transaction: **521/655 ms**;
publication wait: **86/133 ms**; RF application: **9.1/27.1 ms**.
These measure distinct boundaries, not instantaneous RF-to-screen latency.

Native EasyMesh through **0184** and HAL **0038** are unchanged in this
follow-up, retaining fair scheduling, presence/current-RF corrections and
unsent-action bookkeeping. wmediumd advances through **0025**: its opt-in
spatial profile fills independent reservation gaps while preserving sender
FIFO and multicast exclusion. Global contention is unchanged. The actual-queue
regression fails before and passes after; clean builds and sanitizers pass.

### prpl results

**02:09:27–02:32:11 UTC: 14/14 rooms; 145 submissions, 143 verified moves**.
Two old-world verifications are discarded at world switches: one
`verification_cancelled`, one `traffic_failed` after world replacement.
They are **not successful moves**. Native-journal correlation accounts for
both; no unmatched submissions remain. There are zero current-world failed
verifications, unavailable candidate collections or worker errors.
Twelve superseded collections remain separate cancellations.

Request-to-verification p50/p95/max: **0.975/1.181/1.414 s**.
Submission p50/p95: **454/517 ms**; NBAPI operations: **143/173 ms**;
publication wait: **41/113 ms**; complete collection p95/max: **0.990/1.942 s**.
The timestamp-resolution guard remains **498/540 ms**; removing it without
native request correlation would weaken freshness. RF application:
**7.6/32.5 ms**. prpl operations are not directly comparable to RDK transactions.

The false 30-second candidate gap was **fresh RCPI 0 discarded as missing**.
Valid 0–220 is now accepted; reserved/malformed values and unchanged native
timestamps remain rejected. Targeted extender recovery changes from a
**30.323-second incomplete collection** to none; complete post-fix
collections take at most **2.948 s** in that targeted test.

The first full follow-up is retained as **13/14**, not relabeled: a native
`_get_instances` request exceeded its existing five-second limit, and the
observer's availability exception escaped both observation workers, terminating
the room. They now record the outage, preserve original measurement timestamps
and recover. Programming faults remain fatal. Identical concurrent topology
requests share only their in-flight native read; later requests never reuse
completed/error results. Device reads remain parallel: no TTL cache or longer
deadline. Worker recovery, concurrent-read and HTTP failure/recovery tests pass.

prplMesh, hostapd and hwsim binaries are unchanged. The shared medium fix is
**0026**; only adapter/observer/room support code and wmediumd change.

### Per-room convergence

Values are initial/final **first policy convergence** in seconds from each
settling gate, not from the first movement. Near-zero final values mean it
was already converged; the continuous hold is additional.

| Room | RDK initial / final | prpl initial / final |
| --- | --- | --- |
| `home-a-stationary` | 0.02 / <0.02 | 0.02 / <0.02 |
| `home-a-one-client-handover` | 15.18 / 14.20 | 3.03 / <0.02 |
| `large-room-extender-evacuation` | 29.44 / 13.17 | 9.09 / 5.07 |
| `large-room-perimeter-counter-roam` | 30.35 / 5.07 | 8.44 / <0.02 |
| `home-a-asymmetric-link` | 17.21 / 5.07 | 10.13 / <0.02 |
| `home-a-band-walk-small` | 26.29 / 9.12 | 6.06 / <0.02 |
| `home-a-border-hover` | 22.24 / 22.27 | 7.11 / 2.03 |
| `home-a-disappear-reappear` | 21.25 / <0.02 | 6.06 / <0.02 |
| `home-a-extender-loss-recovery` | 10.13 / 7.09 | 5.07 / <0.02 |
| `home-a-fast-transit` | 13.13 / 19.25 | 4.04 / 2.02 |
| `home-a-flash-crowd` | 10.19 / 1.02 | 2.03 / <0.02 |
| `home-a-private-client-room-walk` | 15.21 / 0.03 | 5.06 / <0.02 |
| `home-a-slow-walk-ten` | 24.38 / 21.35 | 5.57 / 3.06 |
| `home-b-slow-walk-ten` | 31.41 / 22.33 | 12.20 / <0.02 |

Absolute-strongest-AP diagnostics retain **2-RCPI** margin-held differences:
RDK asymmetric link (`02:00:00:00:06:00`), prpl evacuation
(`02:00:00:10:06:00`) and band walk (`02:00:00:10:08:00`).
These pass configured policy, not absolute strongest-AP selection.
No steering margin is lowered to manufacture a pass.

### Host evidence and restoration

The owned SSH sampler verifies two samples before mutation, survives the run
and closes with the harness. Reports filter to the exact run window, reject
sampling errors/gaps and leave unsupported counters null. This fixes the
earlier missing-prpl-sampler problem.

| Full-catalog observation | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| Samples / maximum gap | 838 / 2.032 s | 682 / 2.007 s |
| Peak total CPU | 21.27% | 48.67% |
| Minimum available RAM | 51.45 GiB | 13.06 GiB |
| Peak sampled sensor | 93°C | 85.38°C |
| Package throttle-counter increase | **21** | Unsupported, not zero |

CPU/RAM are not exhausted. RDK thermal headroom remains an independent profiling
concern: inspect cooling and host power policy, not weaker test gates.
Both browsers run on rev150 with separate GPU CPU sets. RDK overlaps the first
prpl pass and part of its corrected rerun; timings are deployment observations,
not an uncontended host-speed ranking.

Both labs return to twenty clients/six logical roles, paused at zero,
unleased and fault-free, with fresh complete metrics and cap 100.
Catalog restoration first converges in **29.80 s RDK / 10.12 s prpl**, then
holds. Separate post-maintenance readiness passes. VM autostart stays disabled.
No native stack restarts occur inside the final catalog windows; no release
thin tar or box is created.

### Evidence and remaining boundaries

Evidence on rev150: `/home/rev/work/qualification-fixes-0912/`.
`rdk-all-rooms/` and `prpl-all-rooms-2/` retain final reports, JSONL,
screenshots, native audits and host samples. `prpl-all-rooms/` retains the
failed first pass; targeted logs and `prpl-worker-failure-evidence.tgz`
preserve failure evidence.

The old observer filter omitted `optimizer.verification.discarded`.
The two prpl events are separately retained in
`prpl-all-rooms-2/verification-discarded.journal.jsonl`; reconciled accounting
is in `action-accounting.json`. Original SSE evidence is not rewritten.
The updated harness captures these events and explicitly counts discarded
and unmatched actions. Neither becomes a successful move.

Python regression suites and JavaScript checks pass. The broader RDK suite
has four Ruby-dependent VirtualBox checks unavailable on this observer;
no VirtualBox artifact is being built. Daemon integration runs separately
against both new medium binaries.

- **RF:** prpl passes both bounded spatial windows. RDK retains >5% repeat
  spread despite correct reuse/exclusion ratios; see
  [RF qualification](../radio/virtual-rf-assessment.md#results-and-remaining-work).
  Host thermal and RF-repeatability evidence are separate. Phase 4 remains gated.
- **Latency:** native model commit, publication/polling and actual browser
  paint need separate instrumentation. SVG identity agreement is only one
  component of end-to-end latency.
- Preserve failed actions, short presence mismatches, unavailable snapshots
  and discarded verifications. Never increase timeouts, weaken freshness
  or force targets to manufacture convergence.
