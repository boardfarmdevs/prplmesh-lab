# prplMesh experiment catalog

This catalog is the starting point for running reproducible experiments on the
portable prplMesh virtual-radio lab. It states what each experiment changes,
what it proves, and which profiles have actually passed it.

For an audience-facing sequence, use [the demonstration guide](demonstrations.md).
For implementation details and all test invariants, use
[the acceptance-test reference](../tests/README.md).

## Golden-reference role

The project uses the pinned prplMesh implementation as the **golden comparison
stack** for equivalent RDK EasyMesh experiments. The reference is:

```text
upstream release: prplMesh 6.0.0
source commit:    2e153c7e00cbcab6b8ee35082f494a364e23f018
lab branch:       codex/0831-clean
```

For cross-stack work, apply the same client cohort, band, topology, wmediumd
stimulus, timing bounds and pass criteria to prplMesh first. Retain its
physical association, NBAPI, packet and timing evidence as the expected
behavioral reference. Then compare RDK against that evidence rather than
against a screenshot or API acknowledgement.

Golden reference does not mean normative authority. IEEE 802.11 and Wi-Fi
EasyMesh specifications remain authoritative. A prplMesh defect must be
diagnosed rather than copied into RDK merely to make the two results match.

## Readiness terms

| State | Meaning |
| --- | --- |
| **Ready** | Passed on the stated current appliance profile and suitable for a demonstration or retained experiment. |
| **Ready, disruptive** | Passed, but intentionally changes topology, stops an Agent, or reconstructs the nested lab. |
| **Runnable** | Implemented with bounded checks, but the stated profile has not completed the same acceptance evidence. |
| **Experimental** | Useful for research or comparison but not part of the default accepted userspace-medium baseline. |
| **Not accepted** | Provisioning or code may exist, but no current result supports a pass claim. |

The validated profiles are:

| Profile | Current qualification |
| --- | --- |
| 20 clients | Full userspace-medium functional acceptance; duration soak and the optional kernel backend retain their separate states below. |
| 50 clients | Star, branch, chain, steering, RCPI, optimizer, Agent recovery, bounded churn, data plane and process gates passed. |
| 100 clients | Portable profile and scaled timeouts exist; complete experiment and duration acceptance is not yet recorded. |

## Enter the appliance

The outer Linux host runs an LXD virtual machine, and that VM runs the nested
prplMesh and client containers:

```text
outer host
  `-- prplmesh-PROFILE-RELEASE VM
        |-- prpl-controller
        |-- prpl-agent-01 ... prpl-agent-04
        `-- prpl-client-01 ...
```

Enter the selected VM from the outer host:

```sh
lxc list
VM=prplmesh-20-0902
lxc exec "$VM" -- bash
```

Inside the VM, load its immutable profile before running experiments:

```sh
cd /opt/prplmesh-lab
set -a
. /etc/default/prplmesh-lab
set +a
export PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT"
export PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT"
export PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY"
```

The normal outer-host proxy ports are:

```text
wmediumd Console:      http://OUTER_HOST:8090/
prplMesh Controller UI: http://OUTER_HOST:8091/
```

Run only one medium or topology writer at a time. An experiment is not
complete until its restoration and final health checks pass.

## Experiment selection

| Question | Experiment | 20 clients | 50 clients | 100 clients |
| --- | --- | --- | --- | --- |
| Is the complete current lab healthy? | Full acceptance gate | **Ready** | **Ready** | **Not accepted** |
| Can one named client be commanded to another AP? | Named BTM steer | **Ready** | **Ready** | **Runnable** |
| Can an observer watch clients circulate across bands, SSIDs and APs? | Tri-band steering demonstration | **Ready** | **Ready** | **Runnable** |
| Does steering work across the complete representative matrix? | Steering matrix | **Ready** | **Ready** | **Runnable** |
| Does controller RCPI follow one controlled link? | Per-link RCPI monitor | **Ready** | **Runnable** | **Not accepted** |
| Does the entire client population follow a medium step? | Global RCPI gradient | **Ready** | **Ready** | **Not accepted** |
| Can the optimizer select and optionally execute the expected target? | Dynamic optimizer crossover | **Ready** | **Ready** | **Runnable** |
| Do clients and the model recover from an Agent outage? | Leaf-Agent outage and recovery | **Ready, disruptive** | **Ready, disruptive** | **Not accepted** |
| Can wireless backhaul form star, branch and chain? | Topology modes | **Ready, disruptive** | **Ready, disruptive** | **Not accepted** |
| Can the complete nested runtime stop and reconstruct? | Lifecycle reconstruction | **Ready, disruptive** | **Ready, disruptive** | **Not accepted** |
| Does real client traffic traverse the selected backhaul? | Data-plane and deepest-leaf traffic | **Ready** | **Ready** | **Not accepted** |
| Are identities and process counts stable across repeated recovery? | Bounded churn | **Ready, disruptive** | **Ready, disruptive** for one cycle | **Not accepted** |
| Does the lab remain healthy for a duration campaign? | Long soak | **Runnable** | **Not accepted** | **Not accepted** |
| Can the optional kernel medium replace userspace frame processing? | Kernel-medium comparison | **Experimental; 20-client acceptance passed** | **Not accepted** | **Not accepted** |

## Common experiment lifecycle

Every retained experiment follows the same sequence:

```text
load immutable profile
  -> run baseline acceptance
  -> capture topology, physical links and medium generation
  -> apply one bounded experiment
  -> require physical + NBAPI agreement
  -> require traffic/metrics appropriate to the experiment
  -> restore the captured state
  -> run final acceptance
  -> retain terminal and machine-readable evidence
```

Use this baseline before and after a demonstration block:

```sh
PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY" tests/run-acceptance.sh
```

The gate checks physical client and backhaul associations, unique NBAPI
ownership, RCPI, representative steering, all-client data traffic,
deepest-leaf traffic, process cardinality and runtime provenance.

## 1. Named EasyMesh steering

**Readiness:** Ready on 20 and 50 clients; runnable but not yet accepted as a
100-client profile result.

```sh
scripts/steer-client.sh sta-02 agent-3
scripts/steer-client.sh iot-04 controller
```

`extender-3` is accepted as an alias for `agent-3`. The script preserves the
client's current SSID and band, announces the move in the Controller UI, and
invokes the per-STA `MultiAPSTA.BTMRequest` action through prplMesh NBAPI.

A pass requires:

1. successful BTM request execution;
2. the client's physical `wpa_supplicant` BSSID to equal the selected target;
3. NBAPI to assign the STA to that same target; and
4. the physical and controller views to remain consistent.

Unlike the RDK deterministic steer helper, this path does not need a temporary
`target=60/source=20/others=-20 dB` RF bias. Its accepted matrix uses the native
prplMesh NBAPI/BTM path against the existing medium state.

## 2. Observer-speed tri-band steering

**Readiness:** Ready on 20 and 50 clients; runnable on 100 without an accepted
result.

```sh
tests/steering-demo.sh --cycles 1 --delay 5
```

The test selects six representative clients: private and IoT clients on 2.4,
5 and 6 GHz. It moves each one through the controller and four external Agents,
creating 30 independently verified BTM transactions per cycle. A preview pulse
marks the next client before it moves.

This is the visual counterpart to the RDK carousel, but the mechanism is
different:

```text
prplMesh steering demo: source remains connected -> NBAPI BTM -> association
RDK client carousel:    RF blackout -> wlan0 down/up -> normal reassociation
```

The prplMesh script therefore demonstrates commanded EasyMesh steering. It
does not currently reproduce the carousel's forced disconnect interval or
`45/-20 dB` wmediumd placement sequence.

## 3. Steering matrix

**Readiness:** Ready on 20 and 50 clients.

```sh
PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT" tests/steering-matrix.sh
```

The matrix moves one private and one IoT client from each of 2.4, 5 and 6 GHz
across the controller and every active Agent. Every cell requires the BTM
action, physical BSSID and NBAPI owner to agree. The accepted four-Agent
matrix is 30/30 cells.

Use the observer-speed steering demo for a presentation and this matrix for
acceptance evidence.

## 4. Per-link RCPI response

**Readiness:** Ready on 20 clients; runnable on 50 clients.

```sh
wmediumd/configurator/run-rcpi-monitor.sh prpl-client-01
```

The scenario changes only the selected client's associated radio pair:

```text
wmediumd SNR: 45 -> 25 -> 45 dB
reported RCPI: 128 -> 88 -> 128
```

Traffic remains active. The script observes NBAPI-derived telemetry, requires
at least the configured RCPI span, and restores the exact captured medium
state. It tests the measurement path, not steering policy.

## 5. Global RCPI gradient

**Readiness:** Ready on 20 and 50 clients.

```sh
PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT" tests/rcpi-gradient.sh
```

The test changes all active client paths from baseline RCPI 118 to 88 and
back to 118. It restarts only wmediumd with the same permanent station roster;
it does not restart controller, Agent or client containers. The final pass
requires every active client and the restored baseline.

Do not run another RF writer until restoration succeeds.

## 6. Closed-loop optimizer crossover

**Readiness:** Ready in recommend and act modes on 20 and 50 clients; runnable
on 100 with scaled deadlines but without an accepted result.

Select a client that is not already on the intended Agent:

```sh
cd wmediumd/configurator
python3 -m wmdcfg.cli inventory -o /tmp/prpl-inventory.json
cd ../..
read -r CLIENT TARGET < <(deploy/lxd-vm/select-optimizer-stimulus.py \
    /tmp/prpl-inventory.json prpl-agent-02)
```

Run observation and recommendation only:

```sh
tests/optimizer-dynamic.sh recommend "$CLIENT" "$TARGET"
```

Then explicitly authorize one action:

```sh
tests/optimizer-dynamic.sh act "$CLIENT" "$TARGET"
```

The configurator compiles a five-node crossover and makes one candidate
uniquely stronger. The optimizer sees only normalized NBAPI topology and
associated/unassociated STA metrics. It cannot read the scenario plan or its
expected target.

Recommend mode must journal the independently designated BSSID. Act mode must
also issue the normal BTM action, observe physical and NBAPI convergence, and
prove exact medium restoration.

See [the optimizer/configurator guide](optimizer-configurator.md) for input
contracts, freshness, journals and policy extension.

## 7. Leaf-Agent outage and recovery

**Readiness:** Ready but disruptive on 20 and 50 clients.

```sh
PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY" tests/ap-recovery.sh
```

The test:

1. steers a known IoT client to the deepest active Agent;
2. stops that Agent without changing its permanent hwsim identity;
3. requires the client to associate elsewhere;
4. waits for NBAPI liveness aging to remove the Agent;
5. starts the same Agent identity; and
6. steers the client back after re-onboarding.

This is an administrative Agent outage, not a pure wmediumd RF-isolation
experiment. Watch the Controller UI for client movement and Agent removal and
return.

## 8. Star, branch and chain backhaul

**Readiness:** Ready but disruptive on 20 and 50 clients.

```sh
tests/topology-modes.sh
```

This is a physical topology reconstruction, not a graphical layout command.
It stops the active nested lab, reconstructs and verifies star, branch and
four-hop chain, then admits the complete client profile in chain mode.

The test ends in `chain`. Use the matching final gate:

```sh
PRPL_TOPOLOGY=chain tests/run-acceptance.sh
```

Every topology must agree in the backhaul station's physical BSSID and the
controller's NBAPI parent model.

## 9. Complete nested-lab reconstruction

**Readiness:** Ready but disruptive on 20 and 50 clients.

This stops the nested runtime inside the appliance VM. It does not delete the
outer VM or change its immutable profile:

```sh
time systemctl stop prplmesh-lab.service
lxc list -c ns --format table

time systemctl start prplmesh-lab.service
journalctl -fu prplmesh-lab.service
```

Follow the journal from a second appliance shell while start is pending. A
non-zero unit result is a failure even if some containers happen to be
running. After start, require the normal acceptance gate.

## 10. Data-plane and deepest-leaf traffic

**Readiness:** Ready on 20 and 50 clients.

```sh
PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY" tests/data-plane.sh
```

The test checks every active client's deterministic `192.168.77.0/24` WLAN
path to the controller. It then chooses a client physically associated with
the deepest populated Agent and sends a longer sample through the selected
wireless backhaul. LXD management addresses cannot satisfy the test.

This is bounded reachability and loss evidence. Sustained throughput, mixed
traffic profiles and congestion thresholds are not implemented yet.

## 11. Bounded churn and duration work

**Readiness:** Three bounded cycles passed on 20 clients; one cycle passed on
50 clients. Long-duration soak remains unaccepted.

```sh
PRPL_CHURN_ITERATIONS=1 tests/churn-soak.sh
```

Each cycle restarts a leaf Agent, exercises steering, and requires physical
and NBAPI ownership plus process cardinality. The hwsim inventory hash and
wmediumd PID must remain unchanged.

This is a bounded recovery test, not a 12-hour stability result. Do not label
20-, 50-, or 100-client duration stability accepted until a time-bounded
campaign records memory, process, medium, traffic and model invariants for its
full interval.

## 12. Userspace and kernel medium comparison

**Readiness:** Userspace wmediumd is the default. The optional kernel medium
has passed the full 20-client acceptance gate and remains experimental.

Run the normal gate through the kernel backend only when deliberately testing
that implementation:

```sh
PRPL_MEDIUM_BACKEND=kernel \
PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT" \
PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT" \
PRPL_TOPOLOGY=star \
  tests/run-acceptance.sh
```

The same compiled configurator scenario can be exercised by setting
`PRPL_MEDIUM_BACKEND=kernel`. Do not treat that opt-in backend as the standard
appliance configuration or extrapolate the 20-client result to 50 or 100.

Use `tests/wmediumd-performance.py` for bounded CPU/RSS and traffic evidence.
See [wmediumd performance](wmediumd-performance.md) and
[medium backends](medium-backends.md) for the accepted comparison boundary.

## Scenario sources and golden worlds

The checked-in wmediumd scenario sources are:

| Source | Role | Live readiness |
| --- | --- | --- |
| `all-strong.wmd` | Stable all-links baseline | Supporting baseline; used by runtime/tests |
| `client-rcpi-monitor.wmd` | One associated-link SNR/RCPI step | **Ready** through `run-rcpi-monitor.sh` |
| `optimizer-five-ap-crossover.wmd` | Five-node candidate crossover | **Ready** through `optimizer-dynamic.sh` |
| `two-ap-crossover.wmd` | Minimal compiler/control example | **Runnable**; not a separate accepted appliance gate |
| `client-extender-outage.wmd` | Pure medium outage source | **Runnable**; current accepted `ap-recovery.sh` instead stops the Agent |

The `wmediumd/configurator/worlds/` tree also contains deterministic 2D
layouts and golden timelines for stationary clients, slow walking, fast
transit, border hovering, disappearance/reappearance, extender loss,
flash-crowds, asymmetric links and band walking.

These golden worlds are valid reusable stimuli and compiler fixtures. They
have not each completed an end-to-end prplMesh policy acceptance campaign, so
their existence must not be reported as a live optimizer pass.

## Evidence to retain

For a comparison-quality result, retain:

- repository revision and upstream prplMesh commit;
- appliance release and immutable profile;
- kernel and selected medium backend;
- client count, SSID/band cohort and topology;
- physical BSSID and NBAPI owner before and after;
- wmediumd instance, generation, touched links and restore result;
- BTM command and response when steering is involved;
- associated and candidate RCPI with source timestamps;
- traffic result, process counts and restart counts;
- optimizer observation, explanation, recommendation and action journal; and
- explicit final acceptance result.

Capture observer-facing output without losing the command status:

```sh
EVIDENCE=/var/tmp/prplmesh-experiments
install -d -m 0755 "$EVIDENCE"
set -o pipefail
tests/run-acceptance.sh |& tee "$EVIDENCE/acceptance.txt"
```

Keep failed evidence. Do not convert a bounded failure into a pass with an
unrecorded daemon or container restart.
