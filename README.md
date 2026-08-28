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
- a read-only topology Web application at `http://192.168.2.140:8090/`.

The four-hop chain, 20 clients, all metrics, 30-cell tri-band/two-SSID
steering matrix, leaf-agent outage/rejoin, and global RCPI medium step all
pass. All 20 clients also pass isolated data-plane reachability; a leaf client
crosses the complete four-hop wireless chain with zero packet loss in the
acceptance sample. Star, branch and chain pass full stopped-state
reconstruction.

## Daily commands

Run inside the radio VM from `/opt/prplmesh-lab`:

```sh
# Start four agents in a wireless chain, then admit 20 clients.
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh start
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh clients

# Start the read-only topology service and run the normal acceptance gate.
scripts/topology-visualizer.sh start
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
- `scripts/` — build, provisioning, lifecycle, named steering and visualizer.
- `tests/` — acceptance, scale, steering, outage, metrics and resource tests.
- `visualizer/` — read-only NBAPI adapter and SVG Web UI.
- `docs/architecture.md` — lab topology, state boundaries and optimizer seam.
- `docs/software-architecture.md` — prplMesh processes, IEEE 1905 and APIs.
- `docs/validation.md` — accepted results and remaining gaps.
- `docs/progress.md` — dated engineering findings.

Builds use pinned upstream prplMesh release 6.0.0 commit
`2e153c7e00cbcab6b8ee35082f494a364e23f018`. Runtime containers use a sanitized
Ubuntu 22.04 image without snapd or unattended upgrades; radio acceptance runs
inside the isolated Ubuntu 24.04/Linux 7.0 VM on rev140.
