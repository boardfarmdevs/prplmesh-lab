# prplMesh lab acceptance tests

The tests compare three independent views instead of accepting a Web UI alone:

1. the physical `wpa_supplicant` association in every client and backhaul STA;
2. the controller's EasyMesh Data Elements model exposed through NBAPI; and
3. the intended fixed hwsim identity and selected topology.

Run the complete currently active profile from the radio-lab VM:

```sh
cd /path/to/prplmesh-lab
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  tests/run-acceptance.sh
```

`topology-acceptance.py` checks unique device, radio, BSS and client ownership,
all physical associations, both `private_ssid` and `iot_ssid`, 2.4/5/6 GHz
distribution, wireless backhaul parentage and reported RCPI. `test-steering.sh`
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
from every active WLAN client. It then places `iot-06` on the deepest active
agent and sends a longer ping through the complete wireless backhaul to the
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

```sh
tests/optimizer-dynamic.sh recommend prpl-client-07 prpl-agent-02
tests/optimizer-dynamic.sh act prpl-client-07 prpl-agent-02
```

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

Topology modes are selected at start time with `PRPL_TOPOLOGY=star`, `branch`
or `chain`. The manifest remains the source of provisioned radio identities;
changing topology does not allocate new hwsim radios.

`topology-modes.sh` is the longer reconstruction test. It cold-starts all four
wireless agents in star, branch and chain layouts, validates each physical
backhaul against NBAPI, then restores the 20-client chain and waits for all
metrics. It intentionally stops and reconstructs the active lab.
