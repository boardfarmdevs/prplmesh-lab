# Native memory qualification

[Testing reference](README.md)

The native controller was killed by the guest OOM killer after its anonymous
RSS reached 6.95 GiB. Observer suspension happened afterward. A controller-only
restart initially looked healthy at 29 MiB, but rediscovered only one device and
37 stations and reset reporting to 60/10-second intervals without station
inclusion. That was **not a matched-workload comparison**.

## Isolated mechanism

Restore five native mesh devices, 100 clients and the normal one-second native
reporting policy before comparing memory. Four backhaul stations may additionally
appear in the raw model; the topology's client roster remains exactly 100.

Topology reads alone did not reproduce the runaway. With matched reporting,
100-client traffic and topology reads, the unpatched controller exceeded the
64 MiB growth limit: **104.219 MiB growth** during the 90-second measured window,
after a 20-second warmup. RSS continued increasing after the traffic ended.
A read-only debugger sample found **198,686 pending Ambiorix notifications**.

Native metric handlers produce many notifications per report, including TID
instance replacement. Each queued notification owns its payload. The native
Ambiorix callback previously consumed only one notification per event-loop turn;
busy broker callbacks could produce many more. Delayed removal notifications
also postpone freeing ubus registration wrappers. High TID instance indices alone
do not prove that those instances remain alive.

Patch **0026** drains at most 256 notifications or two milliseconds per callback,
under the existing reader mutex. Remaining work keeps the level-triggered
descriptor readable. No events are discarded, reporting intervals are unchanged,
and the loop regains control at the budget. This addresses consumption rate,
not memory by hiding native metrics. **0026 alone is insufficient**: the matched
rerun grew 225.180 MiB in 90 seconds and still queued 184,051 notifications.

Patch **0028** addresses the producer: it reconciles TID rows by their TID key
instead of removing and recreating every row on every report. Unchanged reports
produce no structural events; changed sizes retain their instance identity.
New keys and their sizes are initialized together in one transaction, absent
keys are removed, and empty reports clear the table. Duplicate input keys are
rejected before mutation. Values, native cadence and client coverage are not
reduced to obtain a memory pass.

Patch **0027** separately releases NBAPI action variants on all return paths and
owns strings returned by `amxc_var_dyncast`. These are confirmed ownership leaks,
not a substitute for fixing the notification backlog.

Two further fronthaul ownership defects have separate fixes. Patch **0030**
constructs candidate-event payloads with typed shared ownership: the old byte
array never constructed or destroyed its vector, leaking its final allocation.
Patch **0031** scopes the native neighbor cache, releasing it on the empty-table,
error and exceptional paths as well as ordinary populated returns. Their
compiled allocation tests include original-code negative controls.

An aged fronthaul also retained about 500 MiB of anonymous memory. A bounded
allocation stack points to 8 KiB libnl neighbor-cache hash tables, but the
subsequent observed populated-cache window allocated and freed those tables
correctly. This does not prove the empty-cache leak accounts for all historical
RSS. Keep this evidence boundary separate from the reproduced controller OOM.

The combined-patch runs pass the unchanged 100-client/one-second gates:
**0.000 MiB measured growth**, **47.781 MiB peak RSS** in each of two consecutive
90-second windows, with traffic from all 100 clients and topology polling.
The first has a 20-second warmup; the second has none and uses the same native
PID. An independent read verifies **832 stable TID instances across 104 stations**
(including four backhaul stations), five seconds apart. A subsequent debugger
sample finds **no pending notifications**. Native 5 GHz/private and 6 GHz/IoT
BTM checks then pass physical ownership, NBAPI ownership and native-response
agreement without restarting the controller. Evidence is retained under
`test-results/prpl-memory-fix/`; this is not a long-soak or full-catalog claim.

## Regression commands

Offline, from the repository root:

```sh
python3 -m pytest -q tests/test_native_signal_dispatch.py tests/test_controller_memory.py \
  tests/test_nbapi_action_memory.py tests/test_native_tid_reconciliation.py
```

The compiled negative control rejects the original single-event handler. Tests
cover lossless bursts, empty queues, recursive producers, count/time fairness,
changed process identities, mismatched rosters and reset reporting policy.

In an idle lab VM, stop the room normally and wait for its full-roster restoration.
Keep the topology adapter running. Then:

```sh
python3 /opt/prplmesh-lab/tests/controller-memory.py \
  --expected-clients 100 --traffic --include-fronthaul --duration 90 --warmup 20 \
  --output /var/lib/prplmesh-lab/test-results/controller-memory.json
```

Use a new evidence path for every run. The tool requires five devices, unique
unchanged client membership and the complete one-second native reporting policy.
It sends bounded traffic from each client's network namespace, records RSS and
process identity, checks the growth/absolute limits and cleans up its traffic.
Native reporting or RF configuration is never changed by this test. A controller
restart, topology error, missing traffic or memory-limit breach fails the run.

The top-level suite includes `live/controller-memory` after native acceptance,
while its existing full-roster guard still holds the room stopped. Failed native
acceptance blocks this test; a memory failure blocks subsequent soak testing.
No debugger is required by the regression. Restore the room after focused manual
testing; do not restart processes to make a measurement pass.

Native binary replacement is a preparation step, never part of the measured
window. Install an ABI-consistent build on all mesh nodes, retain rollback
artifacts, and restore the documented controller-first/star bootstrap before
reattaching the full roster. An ad-hoc simultaneous restart retained an
Ext-1↔Ext-2 backhaul cycle during this investigation; its one-device model was
rejected, not counted as a low-memory success. Normal baseline RF and bootstrap
BSSIDs restored all five devices before the client and reporting gates ran.

A later native reporting-path repair (0029) was compiled and installed separately;
its controller restart is not included in the earlier same-PID comparison.
After five devices, all 100 clients and the same one-second policy were restored,
a further 90-second traffic/read regression passed: **0.027 MiB growth** and
**48.867 MiB peak RSS**. See `test-results/rf-backport/model-repair-memory.json`.
After adding its missing matching-owner query trigger, the same full-roster
90-second check passed again: **0.000 MiB growth**, **48.598 MiB peak**
(`test-results/rf-backport/model-trigger-memory.json`). These use separate
controller PIDs and are not one continuous memory window.
The previously patched controller had also remained alive for over seven hours
at roughly 90 MiB after room changes; these spot checks are not a long-soak test.

`--include-fronthaul` requires all fifteen native fronthaul processes (three
radios on each of five mesh nodes), stable PIDs and individually bounded RSS.
Defaults are at most 1 MiB growth and 128 MiB peak per fronthaul; the controller
retains its existing limits. Samples and per-process verdicts are saved, so an
aggregate or controller-only pass cannot hide one leaking radio process.
The suite's live memory step includes this check. It still requires normal
reporting and the exact client roster; no restart or observer suppression is
performed to obtain a pass.

The final deployed 0026–0031 build passes a further matched 90-second window:
controller **0.031 MiB growth / 39.750 MiB peak**; all fifteen fronthauls
**0–0.004 MiB growth**, with a maximum **14.309 MiB peak**. All 100 clients
receive traffic, native reporting remains one second, and all measured PIDs
remain unchanged. The native restart and standard client bootstrap precede
the warmup; neither is counted as room convergence evidence. Raw evidence:
`test-results/rf-backport/fronthaul-controller-memory.json`. This is bounded
qualification, not a claim that every historical allocation is explained or
that a long soak has passed.

Retain queue samples alongside RSS: a stopped producer and drained queue may
leave reusable allocator arenas resident. RSS alone cannot distinguish retained
arenas, queued work and genuinely leaked allocations. Qualify startup, traffic,
room convergence and native report freshness separately from this bounded check.
