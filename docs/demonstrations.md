# prplMesh appliance demonstrations

This guide exercises the portable prplMesh lab through physical WLAN state,
the EasyMesh NBAPI model, the Controller UI, and the shared wmediumd Console.
It applies to the immutable 20-, 50-, and 100-client appliance profiles.

The demonstrations change live association or medium state. Run only one
writer at a time and require its final pass and restoration checks before
starting the next one.

## Enter the appliance

The portable lab has two LXD layers:

```text
outer Linux host
  `-- prplmesh-PROFILE-RELEASE       (LXD virtual machine)
        `-- prpl-controller, prpl-agent-* and prpl-client-* (nested containers)
```

On the outer host, identify and enter the appliance VM as root. Substitute the
actual profile and release in its name:

```sh
lxc list
VM=prplmesh-50-0901
lxc exec "$VM" -- bash
```

Run all remaining commands inside the VM. Root is needed because the tests
inspect and operate nested LXD containers through the snap-packaged client.
Load the immutable profile instead of hard-coding a client count:

```sh
cd /opt/prplmesh-lab
set -a
. /etc/default/prplmesh-lab
set +a
export PRPL_AGENT_COUNT="$ACTIVE_AGENT_COUNT"
export PRPL_CLIENT_COUNT="$ACTIVE_CLIENT_COUNT"
export PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY"
```

The standard outer-host proxy ports are:

```text
wmediumd Console:   http://OUTER_HOST:8090/
EasyMesh Controller UI: http://OUTER_HOST:8091/
```

If an importer override was used, run `lxc config device show "$VM"` on the
outer host to find the effective listen addresses.

## Preflight and final gate

Wait for first boot or reconstruction to complete before testing:

```sh
systemctl status prplmesh-lab.service --no-pager
prplmesh-lab-start status
```

Then run the same acceptance gate before and after a demonstration block:

```sh
PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY" tests/run-acceptance.sh
```

This is not a UI-only check. It requires physical association, unique NBAPI
ownership, reported RCPI, representative steering, all-client data traffic,
deepest-leaf traffic, expected process cardinality, and correct runtime
provenance.

## Demo 1: manually steer a named client

Keep the Controller UI open and choose **Network Topology**. Named steering
preserves the client's current SSID and band:

```sh
scripts/steer-client.sh sta-02 agent-3
scripts/steer-client.sh iot-04 controller
```

`extender-3` is accepted as an alias for `agent-3`. The command announces the
move in the UI, sends a real EasyMesh BTM request through NBAPI, then requires
the client's `wpa_supplicant` BSSID and the controller's STA owner to agree.
An accepted request alone is not a pass.

## Demo 2: visible two-SSID, tri-band steering

This is the prplMesh equivalent of the RDK client carousel. It moves six
representative private/IoT clients from 2.4, 5, and 6 GHz across the controller
and four agents. The preview pulse identifies the next client before it moves:

```sh
tests/steering-demo.sh --cycles 1 --delay 5
```

One cycle contains 30 independently verified BTM moves. Use a smaller delay
for unattended validation, but retain several seconds for an audience-facing
demonstration.

## Demo 3: change reported RCPI through wmediumd

The per-link monitor changes only the currently associated path of one client,
keeps traffic flowing, samples the NBAPI-derived UI every two seconds, and
restores the exact captured medium state:

```sh
wmediumd/configurator/run-rcpi-monitor.sh prpl-client-01
```

The global gradient is a stronger scale check. It restarts only wmediumd with
the same station roster and changes every active client from baseline RCPI 118
to 88 and back:

```sh
tests/rcpi-gradient.sh
```

Do not start another RF test until the script reports the restored baseline.

## Demo 4: closed-loop optimizer

Choose a station that is not already on `prpl-agent-02`, then run recommend
and act modes. The selector below derives a compatible station from the live
wmediumd inventory:

```sh
cd wmediumd/configurator
python3 -m wmdcfg.cli inventory -o /tmp/prpl-inventory.json
cd ../..
read -r CLIENT TARGET < <(deploy/lxd-vm/select-optimizer-stimulus.py \
    /tmp/prpl-inventory.json prpl-agent-02)

tests/optimizer-dynamic.sh recommend "$CLIENT" "$TARGET"
tests/optimizer-dynamic.sh act "$CLIENT" "$TARGET"
```

The configurator makes one target uniquely stronger. The optimizer receives
NBAPI observations and candidate metrics, not the intended answer. Recommend
mode must journal the expected target. Act mode must additionally complete a
BTM action, observe new ownership, and verify exact medium restoration.

## Demo 5: agent RF outage and recovery

The outage test first places `iot-06` on the leaf agent, stops that agent while
preserving its permanent radio identity, requires the client to recover on
another AP, waits for NBAPI aging, starts the same agent, and steers the client
back:

```sh
PRPL_TOPOLOGY="$DEFAULT_TOPOLOGY" tests/ap-recovery.sh
```

Watch the Controller UI for the client move and agent disappearance/rejoin.

## Demo 6: star, branch, and chain backhaul

This test is a full topology reconstruction, not a graphical layout change:

```sh
tests/topology-modes.sh
```

It stops the active nested lab and proves star, branch, and four-hop chain from
physical backhaul BSSIDs and NBAPI parentage. It then admits the complete
profile in chain mode and waits for metrics. The test ends in `chain`, so use
that topology for the immediate post-test acceptance gate:

```sh
PRPL_TOPOLOGY=chain tests/run-acceptance.sh
```

## Demo 7: stop and reconstruct the complete nested lab

This stops the services and nested nodes inside the appliance VM; it does not
delete the outer VM or change the immutable profile:

```sh
time systemctl stop prplmesh-lab.service
lxc list -c ns --format table

time systemctl start prplmesh-lab.service
journalctl -fu prplmesh-lab.service
```

Run `journalctl -fu` from a second appliance shell while `systemctl start` is
pending. A non-zero start is a failed reconstruction even if some containers
are running. Preserve the journal and retry the whole unit rather than
restarting individual prplMesh processes:

```sh
systemctl reset-failed prplmesh-lab.service
systemctl start prplmesh-lab.service
```

The configured `DEFAULT_TOPOLOGY` is reconstructed, then the normal acceptance
gate must pass.

## Bounded churn

For a short stability demonstration, use one identity-preserving leaf-agent
restart cycle. This is not a long-duration soak:

```sh
PRPL_CHURN_ITERATIONS=1 tests/churn-soak.sh
```

It requires the hwsim inventory hash and wmediumd PID to remain unchanged.

## Evidence discipline

Capture the terminal output in a test-specific directory when a durable record
is required:

```sh
EVIDENCE=/var/tmp/prplmesh-scenario-validation
install -d -m 0755 "$EVIDENCE"
set -o pipefail
tests/run-acceptance.sh |& tee "$EVIDENCE/acceptance.txt"
```

Keep failed output. Do not turn a bounded failure into a pass with an
unrecorded process restart or by relying on a stale browser graph.
