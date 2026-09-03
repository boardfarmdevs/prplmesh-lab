# prplMesh lab acceptance tests

## Appliance command context

The portable deployment is an outer LXD VM containing nested prplMesh and
client containers. Enter the selected VM as root from its outer host, then load
the immutable profile before running tests:

```sh
VM=prplmesh-50-0901
lxc exec "$VM" -- bash

cd /opt/prplmesh-lab
set -a
. /etc/default/prplmesh-lab
set +a
export PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT"
export PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT"
export PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY"
```

The first two commands run on the outer host. Commands after the blank line run
inside the VM. Root is needed for the snap-packaged nested LXD client. Never
run an acceptance test against the outer host's LXD inventory by mistake.

The audience-facing sequence and lifecycle commands are collected in
[`docs/demonstrations.md`](../docs/demonstrations.md).

## Observer-facing status

Demo and live-acceptance scripts announce each operation and wait explicitly:

- bright cyan `==>` messages identify a change or request being made;
- bright yellow `...` messages state which convergence gate is pending and
  how long it may take;
- bright green `OK:` messages identify an achieved result;
- blue section and note messages provide scenario context.

These messages use stderr so machine-readable stdout remains stable. ANSI
colors appear only on an interactive terminal; set `NO_COLOR=1` to show the
same progress in plain text.

The tests compare three independent views instead of accepting a Web UI alone:

1. the physical `wpa_supplicant` association in every client and backhaul STA;
2. the controller's EasyMesh Data Elements model exposed through NBAPI; and
3. the intended fixed hwsim identity and selected topology.

`wmediumd-performance.py` separately measures daemon CPU/RSS and drives
concurrent WLAN traffic from active clients. Its JSON output is intended for
build and affinity comparisons; `docs/wmediumd-performance.md` records the
accepted release measurements.

Run the complete currently active profile from the radio-lab VM:

```sh
cd /path/to/prplmesh-lab
PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT" \
PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT" PRPL_TOPOLOGY=chain \
  tests/run-acceptance.sh
```

The same suite accepts the experimental kernel medium when selected
explicitly:

```sh
PRPL_MEDIUM_BACKEND=kernel PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT" \
  PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT" \
  PRPL_TOPOLOGY=star tests/run-acceptance.sh
```

`topology-acceptance.py` checks unique device, radio, BSS and client ownership,
all physical associations, both `private_ssid` and `iot_ssid`, 2.4/5/6 GHz
distribution, wireless backhaul parentage and reported RCPI. Every client must
also exist in the owning AP interface's kernel station table; a stale client-side
`wpa_state=COMPLETED` cannot satisfy the gate after hostapd has removed the
station. `test-steering.sh`
issues BTM requests for a private 5 GHz client and an IoT 6 GHz client and
requires physical and NBAPI convergence. `resource-acceptance.sh` checks fixed
process cardinality, reports the mesh footprint and rejects snap/automatic
upgrade processes in runtime nodes.

The combined gate allows up to one reporting interval for RCPI convergence.
This matters after cold admission or steering: a valid newly owned STA can
briefly have RCPI zero before the next associated-metrics response arrives.

`ap-recovery.sh` places `iot-06` on the leaf extender, removes that extender,
requires the client to reassociate elsewhere, starts the same permanent radio
identity again, and steers the client back after the agent rejoins.

`steering-matrix.sh` moves one private and one IoT client from each of 2.4, 5
and 6 GHz across the controller and every active agent. Each matrix cell
requires the BTM request, station association and controller ownership record
to agree.

`steering-demo.sh` performs the same representative two-SSID/tri-band movement
at observer speed. It pauses eight seconds between clients by default so every
move is visible in the Web UI, which refreshes every two seconds. One cycle
takes roughly four minutes with four agents:

```sh
tests/steering-demo.sh
tests/steering-demo.sh --cycles 2 --delay 5
```

`data-plane.sh` checks the deterministic `192.168.77.0/24` lab data network
from every active WLAN client. It then discovers a client already associated
with the deepest active agent and sends a longer ping through that exact BSSID
and the complete wireless backhaul to the
controller. LXD management addresses are on a different subnet and cannot
satisfy this test.

`rcpi-gradient.sh` restarts only wmediumd with a bounded global SNR step,
requires all active clients to move from RCPI 118 to 88, then restores SNR 40
and RCPI 118. No controller, agent or client container is restarted.

`optimizer-dynamic.sh` is the closed-loop policy acceptance. It discovers the
selected client's current node, SSID and band, then compiles a five-node
crossover in which one requested target becomes uniquely stronger while the
other three candidates remain weak. The optimizer sees only prplMesh NBAPI and
Unassociated STA Link Metrics results; it is not given the plan or target.

The destination hold scales as `max(90, 6 * clients)` seconds so the 20-,
50-, and 100-client serialized controller sweeps remain inside the RF
stimulus. Every lab BSS uses a bounded 1200-second hostapd inactivity timeout.
That margin prevents otherwise-silent synthetic stations from aging out during
the stress-profile sweep; ordinary traffic and the explicit RF-outage tests
still exercise association loss. The harness never reduces the required
profile cardinality and does not repair missing clients during an optimizer
decision.

```sh
tests/optimizer-dynamic.sh recommend prpl-client-07 prpl-agent-02
tests/optimizer-dynamic.sh act prpl-client-07 prpl-agent-02
```

Add `PRPL_MEDIUM_BACKEND=kernel` to run the identical compiled scenario through
the hwsim kernel actuator. Userspace wmediumd remains the default.

Recommendation mode requires the exact expected BSSID in the optimizer
journal. Act mode additionally requires a successful BTM action and observed
target ownership. Both modes wait for and verify the configurator's exact
restore. The selected target must differ from the client's current owner.

`wmediumd/configurator/run-rcpi-monitor.sh` is the simpler measurement-path
acceptance. It varies one associated link between 45 and 25 dB SNR, keeps
traffic flowing, and requires at least a 30-RCPI observed span before restoring
the captured link.

`churn-soak.sh` performs three bounded leaf-agent restart and steering cycles.
It requires topology/physical ownership and process cardinality on every cycle,
and proves that the hwsim inventory hash and wmediumd PID do not change. Set
`PRPL_CHURN_ITERATIONS` to choose another bounded count; this is not a
long-duration soak.

`hwsim-monitor-ack.sh` is a live kernel/userspace regression for multichannel
TX status. It temporarily enables the normally-down `hwsim0` radiotap monitor,
generates acknowledged traffic, and proves that wmediumd remains alive, no
hwsim NULL-dereference appears, and a subsequent nl80211 station dump
completes. Run it after rebuilding and loading the lab's patched Linux 7.0
hwsim module.

Topology modes are selected at start time with `PRPL_TOPOLOGY=star`, `branch`
or `chain`. The manifest remains the source of provisioned radio identities;
changing topology does not allocate new hwsim radios.

`topology-modes.sh` is the longer reconstruction test. It cold-starts all four
wireless agents in star, branch and chain layouts, validates each physical
backhaul against NBAPI, then restores the complete selected client profile in
a chain and waits for all metrics. It intentionally stops and reconstructs the
active lab.
