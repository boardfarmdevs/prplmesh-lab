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

The final run with native patches through **0179**, 16:52–17:34 UTC, passes
**4/14 complete room gates**. All 14 play to completion; **13/14 final
settling gates pass**, but nine initial gates fail. Disappear/reappear also
fails a short presence window. This is **not all-room qualification**.

| Room | Overall | Initial / final first policy convergence, seconds |
| --- | --- | --- |
| `home-a-stationary` | Fail | fail / <0.02 |
| `home-a-one-client-handover` | Pass | 27.37 / <0.02 |
| `large-room-extender-evacuation` | Pass | 54.59 / 64.75 |
| `large-room-perimeter-counter-roam` | Fail | fail / 36.44 |
| `home-a-asymmetric-link` | Fail | fail / <0.02 |
| `home-a-band-walk-small` | Fail | fail / 53.60 |
| `home-a-border-hover` | Fail | fail / <0.02 |
| `home-a-disappear-reappear` | Fail | 37.45 / 24.26 |
| `home-a-extender-loss-recovery` | Fail | fail / 60.78 |
| `home-a-fast-transit` | Pass | 28.34 / 30.39 |
| `home-a-flash-crowd` | Fail | fail / fail |
| `home-a-private-client-room-walk` | Pass | 30.45 / <0.02 |
| `home-a-slow-walk-ten` | Fail | fail / 44.57 |
| `home-b-slow-walk-ten` | Fail | fail / 65.92 |

A failed gate includes failure to hold convergence for five seconds:
home-a slow-walk first converges at 56.77 seconds but misses the 60-second
initial gate. Late recovery does not retroactively pass an earlier deadline.

The run verifies **155/159** submitted actions. Successful request-to-verification
p50/p95/max is **2.471/6.078/8.216 s**; the four failed actions remain
separate, not omitted from the verdict. RF apply p50/p95 is **9.9/25.9 ms**;
candidate transaction p50/p95 is **1.032/1.986 s**. There are **four HTTP 504
timeouts**, **40 native busy rejections**, and seven failed collection events
after excluding epoch cancellations.

Remaining failures and next RDK work, in priority order:

1. **Native candidate completion:** all four 504s target Agent-1 private
   5 GHz radio `02:00:00:e6:78:c8`, after roughly eight seconds. The
   ownership fixes remove specific state-corruption paths, not every timeout.
   Correlate native admission, transmit MID, reply and completion before
   changing policy or HTTP deadlines. The retained failure journal suppresses
   3,851 messages across the critical interval; its post-failure PCAP is not
   proof that an earlier query was never transmitted.
2. **6 GHz native steering:** all four association timeouts are STA-0E,
   `02:00:00:00:0e:00`, at about 40 seconds. Capture its BTM request/response,
   target discovery and supplicant association together. Passive scan-cache
   observations suggest a discovery investigation but do not establish the
   cause. The separate 2.4↔5 GHz retune test does not qualify this path.
3. **Presence/model reconciliation:** disappear/reappear's 32–40-second
   window retains unavailable STA-10; returning STA-0C appears at 36 seconds.
   The room/native topology views agree with each other but not the scripted
   roster. Flash-crowd ends with ten visible clients, eleven active records
   and native association count 15 versus expected 14; its unexpected STA-10
   also prevents a complete optimizer snapshot. Trace kernel presence,
   native leave/rejoin events and model reconciliation at the same epoch.
4. **Initial snapshot coverage:** nine initial gates lack sustained qualified
   convergence. Resolve the candidate, association and presence failures
   before interpreting an incomplete snapshot as an optimizer-policy defect.

Scene/script checks, native owner checks and final kernel presence audits
pass for all 14 rooms; native identities remain unchanged. Default restoration
passes with 20 clients/six logical mesh roles, first policy convergence
70.97 seconds plus the stable hold. The normal 100-action cap and paused,
unleased room are restored.

A read-only observer sees 26 association-identity changes across 720 decoded
responses: response-to-SVG-bound identity p50/p95/max is
**25.5/32.1/39.9 ms**. This is not native-commit-to-paint latency.
During the room run, rev140 peaks at **16.34% sampled CPU**, has at least
**51.50 GiB available RAM**, and reaches **87°C sampled temperature**,
but its hardware throttle counter increases **18** times. No Yocto build
overlaps this final run. Host thermal qualification remains a separate item;
these are deployment observations, not intrinsic stack-speed rankings.

Evidence on rev150 is under `/home/rev/work/rf-correctness-0911/`:
`rdk-rooms-policy/results/`, `rdk-rooms-policy/audited-summary.json`,
`rdk-policy-qualification-summary.json`, `rdk-host-policy.jsonl`,
`rdk-render-policy/report.json`, `rdk-policy-binary-manifest.txt`, and
`evidence/rf-policy-candidate-*`. Earlier interrupted/build-overlapping
diagnostics are retained separately and are not a controlled performance
baseline.

### prpl results

All **14/14 rooms pass**. The run verifies **148/148** submitted steering
actions, with no failed verifications. Request-to-verification p50/p95 is
**0.948/1.196 s**; RF apply p50/p95 is **6.8/32.3 ms**. One real 30-second
candidate-collection gap occurs during extender-loss/recovery and recovers
within its room gate; epoch-superseded collections are cancellations, not
additional measurement failures.

| Room | Initial / final first policy convergence, seconds |
| --- | --- |
| `home-a-stationary` | 6.87 / <0.02 |
| `home-a-one-client-handover` | 4.05 / 2.02 |
| `large-room-extender-evacuation` | 12.13 / 9.10 |
| `large-room-perimeter-counter-roam` | 13.18 / 1.02 |
| `home-a-asymmetric-link` | 16.14 / <0.02 |
| `home-a-band-walk-small` | 24.23 / 7.07 |
| `home-a-border-hover` | 22.29 / 12.11 |
| `home-a-disappear-reappear` | 9.11 / <0.02 |
| `home-a-extender-loss-recovery` | 5.07 / <0.02 |
| `home-a-fast-transit` | 5.05 / 5.05 |
| `home-a-flash-crowd` | 6.07 / <0.02 |
| `home-a-private-client-room-walk` | 10.19 / <0.02 |
| `home-a-slow-walk-ten` | 7.09 / 13.17 |
| `home-b-slow-walk-ten` | 22.28 / 15.22 |

These clocks start at the settling gate, not at a client's first movement.
A near-zero final value means it was already converged when that gate began;
the stable hold is additional. Native identities remain unchanged.

Stationary and one-client handover retain one **2-RCPI** stronger-AP gap
(`02:00:00:10:04:00`, `candidate_gain_too_small`). They pass configured
policy, not absolute-strongest-AP convergence; the other final gates satisfy
both. No steering margin was reduced to turn these cases green.

An independent read-only topology observer records 22 identity changes across
360 decoded responses: decoded-response-to-SVG-bound identity p50/p95 is
**21.9/28.2 ms**. This excludes native model-commit time, waiting for the next
poll, paint timing and animation completion. It does not justify an instantaneous native
telemetry claim.

Raw reports, events, screenshots and failed diagnostic runs remain outside
Git in `/home/rev/work/rf-correctness-0911/` on rev150:
`prpl-rooms/results/`, `prpl-rooms/audited-summary.json`,
`prpl-render/report.json`. Native RF reporting and synthetic load latency
are separate checks in the [RF assessment](../radio/virtual-rf-assessment.md).

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
