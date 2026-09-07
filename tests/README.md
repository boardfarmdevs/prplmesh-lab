# prplMesh lab acceptance tests

## Interactive 0906 room

With the default 20-client room service already running, inside the appliance:

```sh
cd /opt/prplmesh-lab
python3 tests/room-world-switch-smoke.py --yes-act --timeout 900 --output /root/room-worlds.json
```

This opt-in test changes live RF, tests several room sizes and client absence/
return, requires measured fleet convergence, checks unchanged container/native
process identities, and restores the default world in `finally`. Do not run
another scenario or RF writer concurrently. Use `--all-worlds` for the entire
compatible catalog. Preserve the output even when a gate fails.

Local deterministic gates (no lab required):

```sh
python3 -m unittest discover -s tests -p test_wmediumd_startup.py
PYTHONPATH=demo:wmediumd/configurator:optimizer python3 -m unittest discover -s demo/tests
PYTHONPATH=optimizer:wmediumd/configurator python3 -m pytest optimizer/tests wmediumd/configurator/tests
node tests/viewer-play-drag-test.js
node tests/viewer-world-loading-test.js
node tests/signal-meter-test.js
```

## Appliance command context

The portable deployment is an outer LXD VM containing nested prplMesh and
client containers. Enter the selected VM as root from its outer host, then load
the immutable profile before running tests:

```sh
VM=prplmesh-50-0904
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
colors appear only on an interactive terminal. Set `PRPLMESH_COLOR=always` to
force them through a nested console or `PRPLMESH_COLOR=never`/`NO_COLOR=1` for
plain text.

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

`scripts/steer-soak.sh` snapshots the currently connected client roster and,
with no argument, considers each client exactly once. An explicit positive
count cycles fairly through that roster. Before every attempt it refreshes the
topology, resolves the client's current device, SSID and band, and selects a
different device with exactly one matching fronthaul BSS:

```sh
scripts/steer-soak.sh
scripts/steer-soak.sh 100
```

The script passes the exact STA MAC and live target BSSID to
`scripts/steer-client.sh`; every issued move must agree physically and in the
NBAPI ownership model. It supports private and IoT clients on all three bands.
Failures remain counted and visible while later attempts continue. A final
nonzero status indicates at least one failure, and a timestamped CSV is stored
under `artifacts/`.

`scripts/steer-batch.sh` moves distinct clients concurrently:

```sh
scripts/steer-batch.sh sta-01 agent-1 sta-02 agent-2 iot-03 controller
scripts/steer-batch.sh --count 5
```

The explicit form accepts the same client and target labels as
`steer-client.sh`. The automatic form selects distinct connected clients and
different live devices carrying the same SSID on the same band. Each worker
uses an exact STA MAC and target BSSID, submits its own per-STA NBAPI BTM
request, and requires both physical association and NBAPI ownership to
converge. Up to eight operations run together by default; set
`PRPL_STEER_BATCH_PARALLEL` to a smaller bounded value when deliberately
measuring controller load. Results are written to a timestamped CSV under
`artifacts/`.

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

## Comparable performance snapshot

The lifecycle service writes `/var/lib/prplmesh-lab/last-start-timing.json`
and `last-stop-timing.json`. Each record uses the same phase/timing structure
as the RDK appliance. Capture a PSS-based ready-state sample as root inside the
outer VM:

```sh
sudo tests/lab-performance-snapshot.py \
  --stack prplmesh --profile 20 --label ready \
  --output /var/tmp/prplmesh-ready.json
```

The collector is identical in both repositories. It records outer-VM memory
and load, nested LXD cardinality, normalized thin first-boot start/finish time,
cumulative lifecycle milestones, relevant process details, and PSS/RSS,
private memory, swap, threads and file-descriptor totals by functional group.
