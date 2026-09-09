# 0908 phased room-feature improvements

## Scope and evidence

This follows the 2026-09-09 room-feature findings, on RDK/rev140 and
prplMesh/rev150 only. Both remain on `codex/0908-clean`. The historical
`room-feature-results-0908.md` remains the original baseline, not rewritten
as a passing run. This is bounded feature testing, not soak testing or an
intrinsic cross-stack benchmark. No native EasyMesh/prplMesh binary, RF
policy, native metrics interval, VM CPU allocation or thin tar is changed.

Published local evidence on both rev140 and rev150:
`/home/rev/releases/0908/room-feature-improvements-20260909/`.
Working evidence: `/home/rev/work/room-improvements-0908-0909/` on rev150.
Each backend has deployed goldens, raw browser/API samples, selected SSE
transactions, screenshots, native identities, host telemetry and cleanup logs.
The aborted first prpl attempt is retained under `prpl/attempt-1/` and is
not mixed into the final sweep. Private monitoring backups are not publishable
artifacts and must be excluded from any evidence copy or archive.

## Phased implementation ledger

| Phase | Item | Implementation and acceptance |
| --- | --- | --- |
| 1, common | C1 directional RF metadata | Merge validated, hash-matched mobility RF gains into live nodes for apply, Play and drag. Recorded/uploaded worlds carry explicit signed RF metadata. Check live uplink/downlink values, not only a green convergence badge. |
| 1, common | C2 terminal shutdown | Serialize close calls, preserve the original exception and cache a terminal disabled/fault snapshot even when session close and snapshot both fail. Repeated close remains idempotent. |
| 1, common | C3 clock/pose publication | Publish all authoritative role positions/presence and playback clock in one event with revision, RF epoch and daemon generation. Do not emit intermediate per-role playback commits; retain manual drag events. |
| 1, common/RDK | R3 presence no-op | Disconnect/reconnect required roles even if the calculated RF values did not change. Do not send an empty RF update. This fixes a definite control bug, but does not by itself establish the cause of the original intermittent reporting anomaly. |
| 2, RDK | R1 native command admission | Tested bounded readmission only for explicit HTTP 503 `Error_Prev_Cmd_In_Progress` refusals. The two-second default trial failed acceptance and is withdrawn; the provider option defaults to zero. Preserve each attempt/timing and cancellation checks; never retry an ambiguously submitted HTTP 504 or accept stale candidates. R1 remains open. |
| 2, RDK | R2 6-GHz verification | Correlate each failed action to the submitted source, target, operating class, channel and native result. Collect independent kernel association evidence. Do not force association, shorten the 40-second failure into success or attribute it to rendering without evidence. |
| 2, common | R4 interrupted-room recovery | Before health preflight, recover a checksummed prior journal only when inventory, medium instance and generation ownership match. Reconnect paused clients only under the same guard. Contamination remains a hard refusal. |
| 3, common | C4 correlated timeline | Add action IDs, request time, world/environment epoch, RF apply time, measurement time, submission duration and request-to-verified duration. Retain native collection operations/timings. Missing native timestamps are unavailable, not invented. |
| 3, prpl | P1 collection instrumentation | Record NBAPI method/object, start/end, elapsed and error for discovery, update and bulk reads; record completeness/missing pairs and native timestamp-resolution admission wait. |
| 3, prpl | P2 adapter overhead | Replace per-radio polling calls with one wildcard native read, and per-station object enumeration with one exact-MAC wildcard lookup. Reject duplicate/missing station objects. Preserve native BTM and freshness requirements. |
| 4, common | H1 observer load | Restrict only owned browser GPU processes before loading a lab page, using `--observer-cpus`; retain SwiftShader sampling limits and telemetry. No VM/native affinity changes. |
| 4, hosts | H2 capacity | Record physical-host CPU, available memory, pressure, temperatures and throttle counters separately. A cooling/throttle finding is not an optimizer or renderer fix. |
| 4, common | H3 monitoring | Enable inner-container and outer-VM Prometheus/Grafana scrapes on both labs. Fix pinned-leaf TLS validation and raw-query project handling; add dependency preparation for explicit future monitoring enablement. |

## Important remaining timing boundary

prpl's native unassociated metrics carry whole-second timestamps. Bulk reads
exposed a freshness ambiguity when the next update was requested in the same
second as its baseline. The first development run correctly refused that
same-stamp result and timed out; it was stopped and preserved.

Before requesting the next update, the corrected adapter waits only for that
baseline second to end (at most one second), checks cancellation while waiting,
and records `timestamp_resolution_wait`. Old or higher-resolution baselines
need no wait. This is an explicit native timestamp-resolution constraint,
not zero outside-stack latency. A native sequence ID or sub-second measurement
timestamp would remove the ambiguity without weakening freshness.

The RDK 6-GHz failures are not explained by the previously suspected channel
37-versus-1 adapter error: submitted records use channel 37 for the gateway's
6135 MHz BSS and channel 1 for extender BSSes at 5955 MHz. Command acceptance
is not verified arrival. Keep failed verifications and their final actual BSSID
in the report; a native/client-side investigation must distinguish BTM handling,
scanning/association and controller publication before choosing a fix.

A passive client control subscription later records native
`CTRL-EVENT-ASSOC-REJECT ... status_code=30` followed by connection to a
different BSS and a later successful WNM-directed attempt. The deployed hostap
header identifies 30 as `WLAN_STATUS_ASSOC_REJECTED_TEMPORARILY`. This proves
at least some real association refusals occur below the room/topology views,
but the first passive capture has no per-event timestamps and does not prove
that every earlier 40-second verification failure has the same cause. Preserve
`rdk/sta-static-10-passive-wpa-events.txt` and the controller/source journals.

Recovery compares a separate stable inventory identity: container/radio/
interface MAC identity and AP channels, not discovery time or a station's
current association. The original complete inventory hash is retained as
evidence. Empty, duplicate or changed identities are refused, as are old
unfinished journals without this identity field; use guarded manual recovery
for those rather than deleting their ownership record.

## Validation procedure

Run Python room/optimizer tests, candidate-admission regressions, monitoring
helper tests, prpl station-lookup tests and the existing viewer unit tests.
Use the browser acceptance harness for actual SVG owners, positions, labels,
rosters and freshness; do not substitute a preview animation.

Run common unit checks from the prpl repository root, or RDK's `gen/`:

```sh
PYTHONPATH=demo:demo/tests:optimizer:wmediumd/configurator \
  pytest --import-mode=importlib -o addopts= -q \
  demo/tests optimizer/tests tests/test_lxd_outer_metrics.py
node tests/test-room-feature-acceptance.js
```

For prpl also include `tests/test_nbapi_station_lookup.py`. The explicit
fixture path is needed by the existing shared room-test fixtures.

For the bounded live sweep, follow `room-feature-acceptance-0908.md` with
`--observer-cpus 12,13 --native-audits 1` for RDK and `14,15` for prpl on
this observer host. These CPU sets are examples, not portable defaults.
`--native-audits 1` adds read-only kernel samples in movement/final phases
for the selected presence/6-GHz cases; it does not provide continuous packet
capture or initial-load timing precision. Install both guest audit helpers
before running. The asymmetric audit is automatic at mid-script.

The runtime action cap is temporarily 2000 for the complete catalog and is
restored to 100 afterward. Only room services restart around measured phases.
One planned native prpl lab restart was necessary for first monitoring
identity rotation, completed before this sweep's identity baseline. Its cold
start lasted about seven minutes. This and different host cooling/load prevent
claiming all before/after variation is caused solely by the source patches.

After each full sweep and restoration, run `tests/room-recovery-smoke.py`
(`gen/tests/` in RDK) with `--yes-act --flavor LAB --output NEW_DIRECTORY`.
It requires a healthy paused default room with no lease, applies ten clients,
checks the committed journal, kills only the room service main process, and
requires automatic recovery to twenty clients with unchanged native/container/
medium identities. It never discards the journal or restarts native services.
Follow with an independent strict default convergence check; roster health
alone is not strongest-AP convergence.

## Live results

Both full 14-room sweeps completed on 2026-09-09, including 940 seconds of
normal-speed scripted movement per backend. Native/container/medium identities
were unchanged throughout each measured sweep. RDK's extra two-second busy
readmission policy did **not** produce a reliable acceptance improvement:
its default enablement is withdrawn. The optional provider mechanism remains
tested and disabled by default; do not call R1 resolved.

| Strict gate | Original RDK | RDK 2-s admission trial | Original prpl | New prpl full sweep |
| --- | ---: | ---: | ---: | ---: |
| Loaded convergence | 9/14 | 5/14 | 14/14 | 14/14 |
| Post-motion convergence | 12/14 | 11/14 | 14/14 | 14/14 |
| Perimeter checkpoints | 1/3 | 1/3 | 3/3 | 3/3 |
| All required room checks | 5/14 | 4/14 | 9/14 | 14/14 |
| Verified actions / verification failures | 150 / 4 | 144 / 3 | 150 / 0 | 153 / 0 |

The RDK trial is a **failed rollout experiment**, not an improved release
claim. Changed room RF correctness, native history and host conditions mean
the worse gates cannot be attributed solely to readmission. Keeping it
enabled would nevertheless be unjustified. Final default-policy targeted
checks are recorded separately, not substituted for the failed full sweep.

| Room | RDK trial load / end | RDK all checks | prpl all checks |
| --- | --- | --- | --- |
| home-a-stationary | pass / pass | pass | pass |
| home-a-one-client-handover | pass / pass | pass | pass |
| large-room-extender-evacuation | fail / pass | fail | pass |
| large-room-perimeter-counter-roam | fail / pass | fail | pass |
| home-a-asymmetric-link | fail / pass | fail | pass |
| home-a-band-walk-small | fail / fail | fail | pass |
| home-a-border-hover | fail / pass | fail | pass |
| home-a-disappear-reappear | pass / pass | pass | pass |
| home-a-extender-loss-recovery | fail / pass | fail | pass |
| home-a-fast-transit | fail / pass | fail | pass |
| home-a-flash-crowd | pass / pass | pass | pass |
| home-a-private-client-room-walk | fail / pass | fail | pass |
| home-a-slow-walk-ten | pass / fail | fail | pass |
| home-b-slow-walk-ten | fail / fail | fail | pass |

Both sweeps pass scripted pose/presence, rendered scene and view-agreement
checks in all 14 rooms, with no browser errors, SSE gaps, duplicate clients
or wrong rendered AP owners. The asymmetric native RF audit passes all
15 AP/band directions on each lab, with one stable generation and expected
−7/−10/−12 dB penalties. Disappearance/reappearance and flash-crowd identity
phases pass on both; the old intermittent RDK anomaly is not reproduced.
These successful common-feature checks do not turn a failed native
convergence gate into a pass.

### Measured performance

Times are seconds unless marked ms; triples are p50 / p95 / maximum.
Successful-action percentiles exclude failed verifications, which are reported
separately rather than counted as zero latency.

| Measurement | Original RDK | RDK trial | Original prpl | New prpl full sweep |
| --- | --- | --- | --- | --- |
| Native submission | .053 / .064 / .073 | .055 / .067 / .093 | 2.306 / 3.606 / 3.813 | .511 / .589 / .636 |
| Request → verified | 3.786 / 11.436 / 22.491 | 3.095 / 14.200 / 24.141 | 2.872 / 4.151 / 4.515 | 1.061 / 1.309 / 1.654 |
| Verification phase | 3.728 / 11.372 / 22.423 | 3.030 / 14.124 / 24.085 | .549 / .760 / 1.019 | .547 / .712 / 1.133 |
| RF apply, ms | 13.976 / 60.326 / 444.930 | 10.347 / 27.165 / 422.648 | 17.761 / 99.419 / 686.507 | 9.972 / 37.990 / 736.489 |

prpl median submission is about **78% lower** and request-to-verification
about **63% lower**; its native verification phase stays approximately .55 s.
This supports removal of adapter overhead, not a claim that native BTM itself
became faster. RDK's tail verification performance does not improve.

RDK records 148 submitted actions: 144 verified, three 40-second verification
timeouts (all `sta_static_10`), and one submission without a matching terminal
verification in the captured room timeline. Keep that unmatched action censored.
There are 1,159 explicit busy rejections, 1,106 bounded readmissions, 53
busy-failed rounds, 41 HTTP 504 rounds and 19 superseded rounds. The extra
attempt count is another reason not to retain default readmission.

prpl records one incomplete native collection at 30.311 s and 13 superseded
rounds despite passing the room gates. Its recorded NBAPI operations are
155.815 / 198.744 / 281.963 ms; complete collection durations are
927.260 / 1001.101 / 2978.497 ms. The timestamp-resolution wait remains explicit:
445.944 / 497.080 / 847.605 ms. Mixed operation timings overlap; do not add
them together or compare the generic transaction distribution across stacks.

### Follow-up checks and recovery

Recovery testing uncovered two further concrete startup problems:

- RDK's roster can return before hero traffic is ready. Recovery preflight now
  checks health **and** native traffic within the same bounded 30-second
  rejoin budget. Unexpected errors and cancellation still fail closed; ordinary
  startup does not acquire a new retry policy.
- prpl published its radio-object cache incrementally. A world switch during
  discovery could leave a partial cache, then terminate the optimizer on a
  missing radio. Discovery now publishes only a complete mapping; missing
  cached targets invalidate it and produce a recoverable unavailable result.
  A single wildcard read replaces 22 separate discovery calls. A live cold
  probe finds all 15 radios in one 146.270 ms native call.

The corrected crash checks restore twenty clients without restarting native
services: RDK in 38.219 s and prpl in 21.219 s. These include the existing
15-second systemd restart delay and post-recovery health/traffic checks;
they are not normal steering latency. Successful evidence is
`rdk/recovery-smoke-2/` and `prpl/recovery-smoke-4/`.

Preserve failed development attempts: prpl attempt 1 hit the whole-second
metrics ambiguity; its first recovery check mishandled an initially empty
health snapshot; `recovery-smoke-3/` exposed partial radio discovery before
the planned crash. The first RDK recovery restored RF/clients but failed
traffic preflight, then restarted again without the recovery event in its
new run. One RDK test restart hit the room service's existing start-rate
limit; its failed counter alone was reset, not the policy or any native service.
The first extra read-only readiness checker could not parse native nanosecond
timestamps on Python 3.10; this test-only parser is fixed and regression-tested.
None of those failed attempts is silently reclassified as a pass.

On the final source, prpl's handover and disappearance rooms both pass again
(`prpl-discovery-fix/`), including strict default restoration and unchanged
native identities. This targeted pass follows the startup-only cache and
single-read discovery fixes; it is not presented as another full 14-room sweep.

With RDK readmission disabled, both targeted rooms (`home-a-band-walk-small`
and `home-b-slow-walk-ten`) still fail loaded and final convergence, while
their script/scene/view checks pass. `rdk-no-readmission/` records 48 verified
actions, no failed verifications, one unmatched submitted action, 236 busy
rejections, zero readmissions and 22 native response timeouts. Its strict
default-restoration gate also times out. Native identities remain unchanged.
The failures therefore persist without the experimental retry window; do not
assign their root cause to that window alone.

Final Python validation passes **388 RDK and 299 prpl tests** (687 total), plus
82 subtests, the shared JavaScript acceptance assertions and existing
non-Playwright viewer unit tests. Browser coverage comes from the full and
targeted live passes, not a claimed run of every standalone browser test.
Shell syntax and both repository whitespace checks pass.

Independent post-cleanup readiness passes on prpl (`final-readiness-5/`).
RDK's `final-readiness/` times out after 120.786 s with incomplete candidate
coverage; do not describe RDK as best-AP converged. Both labs retain a healthy
twenty-client roster, six logical mesh roles, paused default playback at zero,
no lease/fault and the original 100-action cap. All native/container/medium
identities still match their measured baselines, and all three monitoring
targets remain UP. Owned browsers and host samplers are stopped.

Changes are synchronized into RDK's canonical rev140 checkout and both live
guest source trees, preserving unrelated VirtualBox work. This implementation
is recorded on the existing `codex/0908-clean` branch. No native image,
thin tar or VirtualBox box is produced by this update.

### Capacity and remaining work

RDK's full trial uses at most 16.8% aggregate host CPU with at least 50.2 GiB
available, but reaches 91°C and adds 187 package-throttle events. prpl peaks at
52.4% CPU, 85.375°C and has at least 12.4 GiB available; an equivalent hardware
throttle counter is unavailable there. There is no evidence of memory
exhaustion. rev120 was unreachable, so the observers stayed bounded on rev150.
Host cooling/power investigation remains separate; no fan setting, VM sizing
or native CPU affinity was altered.

C1/C2/C3, presence no-op handling, action/collection tracing, prpl adapter
overhead, safe recovery and monitoring have concrete fixes and tests.
**RDK R1/R2 remain open**: capture timestamped BTM responses/AP association
refusals alongside candidate request/response completion, diagnose native
orchestration stalls and 6-GHz PMF/association handling, then rerun affected
rooms before another full sweep. A partial cache or renderer workaround must
not conceal native failure. prpl's occasional incomplete native round and
coarse timestamp limitation also remain explicit. H2 cooling is a separate
host task. There is no claim of instantaneous end-to-end behavior.

## Monitoring

| Lab | Inner LXD UI | Grafana (inner containers and outer VM) |
| --- | --- | --- |
| RDK | <https://192.168.2.140:48892/ui/> | <https://192.168.2.140:48893/> |
| prplMesh | <https://192.168.2.150:18892/ui/> | <https://192.168.2.150:18893/> |

Both have `lxd`, `lxd-outer` and `prometheus` UP and healthy Grafana
HTTP checks. Dashboard UIDs: `easymesh-lxd`, `easymesh-lxd-outer`.
Authenticated, certificate-verified Grafana API reads confirm provisioned
dashboards with ten inner and eleven outer panels on each lab. Prometheus
returns CPU rates and memory/network series for all 25 inner containers and
six CPU counters for the exact selected outer VM, not other host VMs.
The new dependency helper's installed-package fast path passes on both VMs
without apt output. Missing-dependency installation was performed manually
for this first prpl enablement; its new automated path is source/shell-tested,
not a second destructive fresh-appliance qualification.
See `lxd-ui-and-monitoring.md` for authenticated access and setup. Do not
publish generated passwords/certificates. Outer-VM metrics are not physical
host temperature sensors; rev140 thermal throttling remains a separate issue.
