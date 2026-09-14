# Performance and failure attribution

[Testing reference](README.md)

A deployment measurement is not automatically a native-stack benchmark.
Measure these intervals separately, retaining epochs, request/action IDs,
clock resolution and failures:

1. World intent → committed RF/readback.
2. Native candidate request → complete fresh measurement.
3. Eligible decision → native submission acceptance.
4. Request → physical association / controller ownership / verified traffic.
5. Published state → browser receipt → rendered observation.

Do not sum overlapping collection timings or treat an accepted BTM as completed
roaming. Prpl candidate timestamps have a whole-second freshness boundary;
RDK candidate requests can be refused/busy or time out. Keep those delays
visible instead of returning stale data. Use request-only/unassisted actuation
when profiling native behavior, not a deterministic RF-assisted demonstration.

## Tools and evidence

The repository's `tests/room-feature-acceptance.js` records browser/API
samples and selected SSE; its report helper aggregates action/collection
timings. The [room test plan](room-acceptance.md) owns invocation and gates.
`tests/room-feature-host-monitor.py` samples physical-host load separately.

During a separately controlled moving-room test, run the read-only
`tests/controller-render-latency.js --url TOPOLOGY_URL --seconds 90 --output NEW_DIR`
from the directory containing `tests/` (RDK: `gen/`). It uses the same Playwright
environment variables as room acceptance. It measures a decoded controller
response to the changed SVG-bound association identity across two animation frames,
including removals; it does not measure native commit time, polling wait or
paint timing or animation completion. Zero transitions are insufficient evidence. Timeouts,
superseded transitions and pending observations remain in the report.

For deeper attribution, use the guest audit helpers, native journals and
passive packet/client-control capture. Do not issue reconnect/roam commands
from an observer. Retain capture drop/truncation counters: incomplete evidence
cannot prove event absence. The RDK-specific trace module is not shipped here.

Prefer a separate observer machine or hardware-accelerated browser. If sharing
a lab host, bound only the owned test browser's CPU load and disclose it.
Record host CPU, available memory, pressure, temperature and throttle counters.
Do not change native CPU allocation, metrics intervals or RF policy halfway
through a comparison. A low average CPU does not exclude thermal throttling.

Infrastructure Grafana panels use coarse scraping and are not substitutes for
correlated native traces. Keep PSS/RSS, guest memory and container cgroup memory
separate; they answer different questions. Retain raw measurements beside the
run, not as JSON/log dumps in the active manuals.

## Acceptance

Report successful distributions **and** censored failures, incomplete
measurements, sample gaps, unsupported timestamp fields and restoration status.
Test medium/radio behavior independently before blaming renderer delays.
Passing a finite catalog does not guarantee zero external overhead, real-world
propagation fidelity, convergence under arbitrary conditions or long-term stability.

## 0913 RF-cache qualification

The 14 September 2026 catalog tests source `9a2dd2d` on rev150, from
15:01:12 to 15:32:14 UTC. All eighteen rooms pass the unchanged 60/45/90-second
limits and five-second stable holds; native identities are unchanged and host
sampling has no gaps. The 50-client room passes initial convergence in
30.938 seconds and final convergence in 13.516 seconds. Default-20 restoration
also passes. These are deployment measurements, not a stack-speed ranking.

There are **145 submissions, 144 verified successes and one failed traffic
verification**. The failed action reaches the requested AP but fails its traffic
check; the room subsequently converges. Successful request-to-verification
p50/p95/max is **0.995/1.242/9.029 seconds**. The outlier includes an 8.196-second
submission interval; available evidence does not isolate a native-stack cause.
No native response timeouts or candidate-unavailable collections occur; nine
superseded collections are explicit cancellations.

A separate unchanged band-walk → border-hover rerun passes both rooms and
all **30/30 actions**, with successful request-to-verification p50/p95/max
0.973/2.172/2.207 seconds. It does not erase the earlier failure or establish
that the transient cannot recur. Keep the failed sample with the distributions.

Two external adapter repairs precede this qualification:

- Candidate caches and in-flight publications use committed per-client RF
  identity; AP movement invalidates affected clients, while unrelated warm
  comparisons remain reusable. Action submission rechecks the same identity.
- Native query registrations are rebound when a station's channel/operating
  class changes. The controller has one current query-channel context per
  station, not a permanent independent registration on every historical radio.
  Successful unchanged registrations and bounded parallel collection remain.

Targeted regressions fail before these repairs and pass after them. The full
Python suite passes with 1001 JUnit records including subtests and five skips.
The explicit 2.4-GHz fifty-client movement diagnostic passes all four moves;
default-room restoration passes in 29.688 seconds, where the intermediate
RF-only repair previously exhausted its unchanged 120-second restoration limit.
These repairs do not alter native steering policy, authentication timers or
simulated signal levels.

Evidence is on rev150 under `/home/rev/work/release-0913/evidence/`:
`prpl-channel-registration-qualification/`, `prpl-border-followup/` and the
negative-control/unit reports. Earlier failed runs remain separate. Follow
[current state](../../docs/current-state.md) for the accepted immutable tar and
its independently tested fresh import; a source catalog alone does not accept
an artifact.
