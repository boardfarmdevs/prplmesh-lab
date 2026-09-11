# Proposals and open work

[Reference home](../README.md)

Proposals are not current runtime capabilities. An accepted implementation
belongs in its owning subsystem contract, not in an indefinitely growing plan.

- [Neighbor-network rooms](neighbor-rooms/design.md): preserved design and
  illustration from the supplied archive; discovery/contention fidelity levels,
  external AP actors and scenario acceptance gates. **Proposed, not implemented.**

The [virtual RF assessment](../radio/virtual-rf-assessment.md) owns the current
radio-capability audit and phased common/RDK/prpl implementation work. Consult
it before relying on older implementation observations in the neighbor design.

## Priorities to carry forward

| Owner | Work | Completion evidence |
| --- | --- | --- |
| RDK native metrics | Diagnose busy admission and incomplete candidate responses; never mask with stale cache or default retry storms | Timestamped native request/response trace and affected-room rerun |
| RDK 6-GHz association | Correlate BTM, AP refusals, station association and controller publication | Exact target/BSSID/opclass evidence, verified traffic, failures retained |
| prpl metrics interface | Remove whole-second ambiguity with a native sequence ID or higher-resolution timestamp if available | Freshness regression without artificial stale admission |
| Common RF | Qualify fail-closed behavior, overload/drop classification, explicit receiver eligibility and reception-backed measurements | Standalone conformance tests plus a physical reference comparison |
| Common deployment | Consolidate duplicated platform-neutral room/monitoring code only with independent release reproducibility | Both backend unit/import/room gates |
| Hosts | Investigate cooling, throttling and observer load separately from stack logic | Comparable before/after host telemetry |

Larger appliance/inventory refactors are not prerequisites for operating the
current fixed-pool lab. Start with a demonstrated defect and a bounded test,
not another broad architecture proposal. Keep new work items small, assign an
owner and acceptance gate, and remove them when completed. Historical detailed
plans and measurement narratives remain available through Git history.
