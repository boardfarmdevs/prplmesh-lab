# Immersive prplMesh room demonstration manual

## Purpose and claim

The room demo turns a deterministic model of a home into timed wmediumd RF
conditions, observes the response through prplMesh NBAPI, runs the external
reference optimizer, and presents the result in one browser view. In `act`
mode it can submit one real NBAPI BTM request and verify both the resulting
association and client traffic.

The default 20-client profile remains fully loaded: five tri-band mesh
devices, four wireless backhaul stations, ten clients on `private_ssid`, and
ten on hidden `iot_ssid`. `prpl-client-03` is the hero. Its controller MAC is
`02:00:00:10:02:00`, its normal topology label is `sta-02`, and the room calls
it `Private-Laptop`. It is a normal private 5 GHz station.

The floor plan, movement and SNR are simulated. prplMesh discovery, associated
metrics, the unassociated-STA measurement transaction, BTM exchange,
supplicant behavior, controller convergence and IP traffic are live.

## Safety and ownership

- `wmdcfg.Runner` is the only room-demo writer to wmediumd.
- The optimizer never reads the Golden World as decision input.
- Candidate collection is limited to the hero and uses the prplMesh NBAPI
  `AddUnassociatedStation` and `UpdateUnassociatedStationsStats` path.
- Hwsim candidate measurements require the explicit manifest opt-in and retain
  a `simulated` measurement-source label.
- `recommend` is the default and cannot steer.
- `act` requires both `--mode act` and `--yes-act`, has one action budget, and
  can act only from 150 to 220 seconds.
- `scripts/steer-client.sh --request-only` submits the NBAPI BTM operation and
  leaves association/traffic verification to the conductor.
- The browser API is read-only; POST returns HTTP 405.
- The runner captures every touched RF value and restores it on success,
  interruption or failure, then performs a postflight health gate.

Do not run another configurator scenario, a wmediumd Console mutation, or a
steering command that changes RF while a room run owns the lock.

## Files

| File | Responsibility |
| --- | --- |
| `demo/manifests/private-client-room-walk.json` | runtime, health, traffic, optimizer and narrative contract |
| `demo/bindings/private-client-room-walk.json` | world roles to prpl LXD containers |
| `wmediumd/configurator/worlds/mobility/private-client-room-walk.json` | four-minute hero path |
| `wmediumd/configurator/worlds/golden/home-a-private-client-room-walk.world.json` | hash-verified compiled room |
| `optimizer/configs/threshold-policy.yaml` | reference decision policy |
| `demo/room-demo` | check, run and replay command |

The viewer and event/evidence schemas intentionally match the RDK room demo.
The prpl implementation is duplicated for now so either repository packages a
complete demonstration independently.

## Appliance and browser preparation

The 0904 universal thin importer creates all public proxy devices. Its defaults
are:

| Service | Outer-host port | Guest port |
| --- | ---: | ---: |
| wmediumd Console | 8090 | 8090 |
| Controller UI | 8091 | 8091 |
| Room demo | 18891 | 8891 |

Override the room port at import with `PRPLMESH_ROOM_DEMO_HOST_PORT`. The
room server is intentionally not started by systemd; the proxy is inert until
an operator starts a run or replay inside the VM.

Enter the imported 20-client VM:

```sh
VM=prplmesh-20-0904
lxc exec "$VM" -- bash
cd /opt/prplmesh-lab
```

Confirm the lab and the two observation services:

```sh
prplmesh-lab-start status
curl -fsS http://127.0.0.1:8092/api/topology >/dev/null
curl -fsS http://127.0.0.1:8090/api/v1/status >/dev/null
tests/data-plane.sh
```

The default room manifest requires exactly 20 clients. Use the 20-client
profile; 50- and 100-client imports remain supported by the appliance but need
their own room manifest and bindings.

## Compile-only preflight

```sh
demo/room-demo check
```

`check` is read-only. It verifies manifest paths, the Golden World hash, live
hwsim inventory, all role bindings, event compilation and wmediumd control
capabilities. It reports 25 world roles, a 240000 ms duration and both the
hero's permanent hwsim identity and controller-facing station MAC.

SSID, band, RCPI, population and traffic are checked immediately before a run;
failure stops before the first RF generation.

## Run modes

Stimulus-only presentation:

```sh
demo/room-demo run --mode stimulus --listen 0.0.0.0:8891 \
  --linger-seconds 120
```

Safe optimizer recommendation:

```sh
demo/room-demo run --mode recommend --listen 0.0.0.0:8891 \
  --linger-seconds 120
```

One bounded real steering attempt:

```sh
demo/room-demo run --mode act --yes-act --listen 0.0.0.0:8891 \
  --linger-seconds 120
```

Open `http://OUTER_HOST:18891/viewer/?mode=live` as soon as the command prints
the run ID. One run lasts four minutes, followed by the requested linger time.
A second room process is rejected by `/run/lock/prplmesh-room-demo.lock`.

The timeline is stable near Extender-1 through 30 s, walks toward the boundary
through 90 s, crosses the hall/room through 150 s, permits one action from
150–220 s, then cools down and restores at 240 s.

## Reading the presentation

- Dashed red/amber/green is the scenario-best AP for the selected display band.
- Solid cyan is the association reported by prplMesh.
- Dashed gold is the optimizer's current measured target.
- The red tower is the gateway/colocated controller Agent; blue towers are the
  four extenders.
- Blue client stems are private, green stems are IoT, and the gold ring selects
  Private-Laptop.

The room preserves stable `Agent-1` and `Extender-1`…`Extender-4` geometry.
The prpl NBAPI names are `controller` and `agent-1`…`agent-4`; the conductor
maps live BSSID ownership to the stable room roles before rendering.

The Whole lab card reports live mesh/client/cohort counts. The Hero card shows
serving device, BSSID, band, SSID, RCPI/RSSI and ping. The optimizer card shows
policy state, reason, source metric, target metric, hold/window state and
action/verification. Recent events is sourced from the same ordered journal
that becomes evidence.

The companion Controller UI and wmediumd Console remain independent evidence:

```text
http://OUTER_HOST:8091/
http://OUTER_HOST:8090/
```

Select `sta-02` in the Console to follow the hero's hwsim radio. Controller UI
names and controller MACs differ from permanent hwsim identities by design.

## Read-only API

```sh
curl -s http://127.0.0.1:8891/healthz | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/current | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/world | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/events.json | python3 -m json.tool
curl -N 'http://127.0.0.1:8891/api/demo/events?after=100'
```

Every event has `run_id`, global `sequence`, `recorded_at`, authoritative
`world_time_ms`, `producer`, `kind` and `payload`. Runner-local sequence is
retained as `payload.producer_sequence` after central resequencing.

## Evidence and replay

Each attempt receives a unique directory under
`/tmp/prplmesh-room-demo-runs/RUN_ID/`. It includes the world, WMD source,
manifest, bindings, discovered inventory, event plan, medium log, health log,
live event journal, runner summary, demo summary and SHA-256 evidence index.

```sh
RUN_DIR=$(find /tmp/prplmesh-room-demo-runs -mindepth 1 -maxdepth 1 \
  -type d -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
python3 -m json.tool "$RUN_DIR/demo-summary.json"
python3 -m json.tool "$RUN_DIR/evidence-index.json"
demo/room-demo replay "$RUN_DIR" --listen 0.0.0.0:8891
```

Replay performs no LXD, NBAPI or wmediumd operation. Open the same outer URL
with `?mode=replay`.

## Troubleshooting

- `hero ... is absent`: verify `prpl-client-03`, then compare `wpa_cli` with
  the adapter's `/api/topology` result.
- Hero SSID/band mismatch: reconstruct the normal 20-client profile; the room
  contract expects private 5 GHz `sta-02`.
- Candidate timeout: preserve evidence and inspect the prpl controller's
  `UnassociatedSTA` objects; do not replace the metric with Golden World SNR.
- Action submitted but not verified: compare `wpa_cli -i wlan0 status` in
  `prpl-client-03` with NBAPI BSS/STA ownership and retain the failed bundle.
- Incomplete pre/postflight: stop; do not restart individual prplMesh
  processes to make the presentation pass.
- Viewer unavailable: verify the run listens on `0.0.0.0:8891` and inspect the
  outer `room-demo-viewer` proxy device.

After an interrupted run, require `demo-summary.json` to show `restored: true`
before starting another RF scenario.

## 0904 thin-package prerequisites

The release builder needs a clean source checkout, `git`, `jq`, `lxc`, zstd
export support, a working LXD storage pool, and enough free pool space for the
selected profile (the small-profile preflight requires 24 GiB). The accepted
ready VM must have no host-path disk mount, a valid local
`prpl-runtime-local` image, verified `artifacts/SHA256SUMS`, built wmediumd
source/binary/provenance, and a clean `/opt/prplmesh-lab` checkout.

Set all of these explicitly for thin conversion:

```sh
PRPLMESH_RELEASE_ID=0904 \
PRPLMESH_RUNTIME_BASE_COMMIT=ACCEPTED_READY_COMMIT \
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_VM_NAME=ACCEPTED_READY_VM \
PRPLMESH_THIN_CONFIRM=ACCEPTED_READY_VM \
  deploy/lxd-vm/package-thin.sh release/0904
```

The runtime-base commit must exist and be an ancestor of the source being
packaged. The guest checkout must be either that accepted base or the exact
source commit. Packaging refuses dirty host or guest source, an unexpected
nested roster, invalid artifacts, missing runtime image, a non-VM source, or a
host filesystem mount. See [portable releases](../portable-releases.md).
