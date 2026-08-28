# Architecture

## Isolation boundary

The experiment lives at `/home/rev/prplmesh-lab/0827` on rev140. Every name is
prefixed with `prpl-`. Native userspace builds run in a dedicated LXD build
container. Radio acceptance runs in an Ubuntu 24.04/Linux 7.0 LXD virtual
machine, with the prplMesh controller, agent, and station placed in nested LXD
containers. This avoids changing rev140's host kernel and gives the experiment
its own bridges, hwsim pool, wmediumd process, configuration, PID, and log. No
RDK container, image alias, bridge, radio, wmediumd process, or database is
reused.

## First milestone

```text
                       dedicated L2 management/backhaul bridge
                 +----------------------------------------------+
                 |                                              |
        +--------+---------+                           +---------+--------+
        | prpl-controller  |  IEEE 1905.1 / EasyMesh  |   prpl-agent    |
        | controller only  |<------------------------>| agent + hostapd |
        +------------------+                           +--------+---------+
                                                                |
                                                        hwsim AP radio
                                                                |
                 +---------------- dedicated wmediumd -----------+
                 |                                              |
          hwsim station radio                                   |
                 |                                              |
        +--------+---------+                                    |
        | prpl-client-01  |-------------------------------------+
        | wpa_supplicant  |          802.11 association
        +-----------------+
```

The controller and agent share only the dedicated L2 backhaul. The station has
only its assigned hwsim radio. This makes onboarding and WLAN behavior separate
observations and prevents a host-side shortcut from masquerading as wireless
success.

## Incremental acceptance

- **M0 — build:** pinned source builds and unit tests complete in a clean x86
  build container.
- **M1 — onboarding:** one controller discovers one agent, completes WSC/M1-M2,
  and reports the agent operational.
- **M2 — client:** one client associates, passes traffic, and is visible to the
  controller with an unambiguous BSSID owner.
- **M3 — steering:** a controller-issued mandate moves the client to a second
  agent and the physical association matches controller topology.
- **M4 — multihop:** the second agent onboards through the first agent's
  wireless backhaul and recovers without identity duplication.

For each milestone, record convergence time, retries, manual interventions,
process restarts, stale topology records, and identity mismatches.

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
The prplMesh adapter is a later milestone, after its native steering path and
telemetry are proven independently.
