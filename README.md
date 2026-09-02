# prplMesh virtual-radio lab

This independent x86/LXD lab evaluates upstream prplMesh 6.0.0 with Linux 7.0
`mac80211_hwsim` radios and multichannel wmediumd. It does not use or modify
the RDK-B EasyMesh source tree, images, containers, medium, or runtime.

## Accepted profile

The current scale profile contains:

- one controller with a colocated agent;
- four external agents, each with 2.4, 5 and 6 GHz radios;
- wireless backhaul selectable as `star`, `branch`, or `chain`;
- 20 clients: 10 on `private_ssid` and 10 on `iot_ssid`;
- both SSIDs represented independently on 2.4, 5 and 6 GHz;
- 40 permanently identified hwsim radios registered once with wmediumd;
- NBAPI topology, ownership and RCPI telemetry; and
- complete same-band candidate RCPI through the standard Unassociated STA
  Link Metrics transaction;
- dynamic scenario execution through the live wmediumd control plane;
- an external reference optimizer with recommend and bounded act modes;
- the same read-only wmediumd Console used by the RDK lab on port 8090;
- a host EasyMesh Controller UI on port 8091; and
- a loopback-only NBAPI normalization adapter on port 8092.

The four-hop chain, 20 clients, all metrics, 30-cell tri-band/two-SSID
steering matrix, leaf-agent outage/rejoin, and global RCPI medium step all
pass. All 20 clients also pass isolated data-plane reachability; a leaf client
crosses the complete four-hop wireless chain with zero packet loss in the
acceptance sample. Star, branch and chain pass full stopped-state
reconstruction. A five-node dynamic RF crossover has passed both
recommendation-only and acting optimizer acceptance, including exact target
selection, BTM convergence, and medium restoration.

## Daily commands

Run from the repository root on the dedicated radio host:

```sh
# Start four agents in a wireless chain, then admit 20 clients.
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh start
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh clients

# Start the internal NBAPI adapter and the common medium Console.
scripts/topology-adapter.sh start
scripts/wmediumd-console.sh start
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  tests/run-acceptance.sh
```

The normal gate includes topology, ownership, RCPI, representative steering,
all-client data reachability, a deepest-leaf traffic sample, process
cardinality and runtime footprint.

Named steering uses the same client and agent labels as the Web view:

```sh
scripts/steer-client.sh sta-02 agent-3
scripts/steer-client.sh iot-04 controller
```

Longer tests intentionally change active topology or medium state:

```sh
PRPL_AGENT_COUNT=4 tests/steering-matrix.sh
PRPL_AGENT_COUNT=4 PRPL_TOPOLOGY=chain tests/ap-recovery.sh
PRPL_CLIENT_COUNT=20 tests/rcpi-gradient.sh
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 tests/topology-modes.sh
wmediumd/configurator/run-rcpi-monitor.sh prpl-client-01
tests/optimizer-dynamic.sh recommend prpl-client-07 prpl-agent-02
tests/optimizer-dynamic.sh act prpl-client-07 prpl-agent-02
```

Stop all lab nodes and wmediumd with:

```sh
scripts/radio-lab.sh stop
```

## Evidence rule

A test passes only when the intended identity agrees with both:

1. the physical backhaul/client `wpa_supplicant` association; and
2. the controller's `Device.WiFi.DataElements` NBAPI ownership model.

A Web screenshot or accepted API request alone is not success. Metrics tests
also wait for the reported RCPI value, and lifecycle tests check stable PHY,
AL-MAC and BSSID identities plus fixed process counts.

## Repository map

- `manifests/` — fixed inventory, SSIDs, credentials and medium baseline.
- `patches/` — small hwsim, wmediumd and prplMesh NL80211 deltas.
- `scripts/` — build, provisioning, lifecycle, named steering and service launchers.
- `artifacts/` — ignored, reproducibly generated runtime archives.
- `tests/` — acceptance, scale, steering, outage, metrics and resource tests.
- `optimizer/` — normalized observations, policies, replay, journals and
  bounded actuation.
- `wmediumd/configurator/` — scenario language, world compiler and atomic
  dynamic-medium runner.
- `topology-adapter/` — internal read-only NBAPI normalization API; no public UI.
- `controller-ui/` — host Go port of the RDK EM CLI topology application.
- `wmediumd/observer/` — exact shared RDK wmediumd Console implementation.
- `docs/architecture.md` — lab topology, state boundaries and optimizer seam.
- `docs/controller-ui.md` — host UI adapter, API and multi-network model.
- `docs/software-architecture.md` — prplMesh processes, IEEE 1905 and APIs.
- `docs/optimizer-configurator.md` — closed-loop operation and extension guide.
- `docs/validation.md` — accepted results and remaining gaps.
- `docs/wmediumd-performance.md` — CPU, affinity and overload measurements.
- `docs/from-scratch.md` — complete host-to-accepted-lab build procedure.
- `deploy/README.md` — bare-metal and portable LXD-VM deployment.
- `docs/portable-releases.md` — 20/50/100 appliance build and release contract.
- `docs/release-notes.md` — concise delivery history for the lab releases.

Builds use pinned upstream prplMesh release 6.0.0 commit
`2e153c7e00cbcab6b8ee35082f494a364e23f018`. Runtime containers use a sanitized
Ubuntu 22.04 image without snapd or unattended upgrades. The radio host is
Ubuntu 24.04 with Linux 7.0. See `docs/from-scratch.md` for the complete build.
