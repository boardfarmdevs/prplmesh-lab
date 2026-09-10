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
No result here claims zero external overhead, real-world propagation fidelity,
all-room convergence or long-term stability.
