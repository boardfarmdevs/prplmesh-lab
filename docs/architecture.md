# Architecture

## Isolation boundary

The experiment lives in this repository on a dedicated radio host. Every name is
prefixed with `prpl-`. Native userspace builds run in a dedicated LXD build
container. Radio acceptance runs in an Ubuntu 24.04/Linux 7.0 LXD virtual
machine, with the prplMesh controller, agent, and station placed in nested LXD
containers. This avoids changing the workstation's host kernel and gives the experiment
its own bridges, hwsim pool, wmediumd process, configuration, PID, and log. No
RDK container, image alias, bridge, radio, wmediumd process, or database is
reused.

## Accepted runtime

```text
 +------------------------- Ubuntu 24.04 / Linux 7.0 radio VM -------------------------+
 |                                                                                     |
 |  +-------------------+    5 GHz wireless BH    +---------+    +---------+            |
 |  | prpl-controller   |<------------------------| agent-1 |<---| agent-2 |<--- ...     |
 |  | controller + agent|                         +---------+    +---------+  agent-4    |
 |  | 2.4 / 5 / 6 GHz   |                              each agent: 2.4 / 5 / 6 GHz      |
 |  +-------------------+                                                               |
 |          ^                         IEEE 1905 / EasyMesh over selected backhaul        |
 |          |                                                                          |
 |  +-------+---------------- patched multichannel wmediumd -------------------------+  |
 |  | sees every hwsim frame; applies frequency context and SNR/PER model           |  |
 |  +-------+------------------------------------------------------------------------+  |
 |          |                                                                          |
 |  +-------+----------------------------+                                             |
 |  | 20 WLAN client containers         |  private_ssid + iot_ssid                    |
 |  | wpa_supplicant; 2.4 / 5 / 6 GHz   |                                             |
 |  +------------------------------------+                                             |
 |                                                                                     |
 |  NBAPI -> read-only visualizer :8090     NBAPI BTM <- named steering/tests          |
 +-------------------------------------------------------------------------------------+
```

Each station has only its assigned hwsim radio. External agents use a separate
bSTA VIF on their 5 GHz PHY. `star`, `branch` and `chain` change only the
selected parent BSSID; permanent radio ownership and the wmediumd roster do not
change.

## Incremental acceptance

- **M0 — build:** pinned source builds and unit tests complete in a clean x86
  build container.
- **M1 — onboarding:** one controller discovers one agent, completes WSC/M1-M2,
  and reports the agent operational.
- **M2 — client:** clients associate on all three bands and are visible to the
  controller with unambiguous BSSID ownership. Association, ownership and an
  isolated deterministic data plane are accepted.
- **M3 — steering:** a controller-issued mandate moves the client to a second
  agent and the physical association matches controller topology.
- **M4 — multihop:** four external agents onboard through star, branch and
  chain wireless backhauls and recover without identity duplication.
- **M5 — scale and telemetry:** 20 clients across two SSIDs and three bands
  report associated RCPI and survive a live medium step.
- **M6 — resilience:** a leaf agent ages out, its client roams, and the same
  identity rejoins without medium regeneration.

For each milestone, record convergence time, retries, manual interventions,
process restarts, stale topology records, and identity mismatches.

M1 through M6 are accepted for the bounded test suite. Basic traffic through
the deepest four-hop chain is also accepted. Sustained traffic profiles,
candidate-link metrics, optimizer integration and long-duration soak remain
open.

## Radio and medium baseline

- Linux 7.0 is required for the validated hwsim 6 GHz `regtest=5` behavior.
- The hwsim module carries the reviewed multichannel-wmediumd registration
  change. Linux 7.0 does not need the older strict-regdomain workaround.
- wmediumd is pinned to upstream commit
  `717e5d7fcc23eecbc8e32bd897a8fd4b1e3ba640` and initially carries only the
  multichannel scheduling, learned-VIF delivery, Linux 7 rate flag,
  frequency-filtered multicast, receive-buffer, default-SNR, and associated
  correctness fixes.
- Scenario-control, metrics, and observer socket extensions are excluded from
  the first prplMesh milestone. Static configuration is enough to prove
  simultaneous 2.4, 5, and 6 GHz operation.

## Future optimizer compatibility

The optimizer and configurator must not depend directly on the RDK controller.
The comparison boundary is a small backend adapter:

```text
golden world/scenario -> wmediumd input (shared)
optimizer observation <- topology + metrics adapter <- RDK or prplMesh
optimizer decision    -> steering adapter           -> RDK or prplMesh
acceptance evidence   <- kernel association + controller ownership (shared)
```

This permits identical RF sequences and acceptance definitions on both stacks.
Native associated-client telemetry and named steering are now proven; the next
integration milestone is to implement this adapter without coupling the shared
optimizer to prplMesh-specific object paths.
