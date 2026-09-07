# prplMesh 0906: thin appliance and interactive room

## Deployment scope

The prplMesh appliance is `prplmesh-20-0906` on rev120. RDK 0906 runs separately
on rev140 and rev150. Each appliance owns its room server, optimizer and RF
writer. This release deliberately duplicates the viewer; selecting a remote
RDK/prplMesh backend from one common viewer is not implemented.

| Service | rev120 URL |
| --- | --- |
| Interactive room | `http://192.168.2.120:18891/viewer/?mode=interactive` |
| Controller topology | `http://192.168.2.120:8091/` |
| wmediumd console | `http://192.168.2.120:8090/` |
| Viewer manual | `http://192.168.2.120:18891/viewer/manual.html` |

All outer VMs have `boot.autostart=false`. Manually starting this appliance
starts its nested lab and room service. The room defaults to 20 clients and
five physical mesh containers (the controller and colocated gateway can be
drawn separately). It does not create or destroy containers when loading a
smaller world: absent clients are RF-isolated and disconnected using their
actual `wpa_supplicant` interface. Returning clients reconnect. Controller
topology reports observed associations, not a browser-side filtered roster.

## Import the thin tar

On rev120, preserve the old appliance until the replacement passes acceptance.
Stop it to release its published ports, then:

```bash
cd /home/rev/releases/0906
sha256sum -c prplmesh-0906-thin.tar.sha256
tar -xf prplmesh-0906-thin.tar
cd prplmesh-0906-thin
sha256sum -c SHA256SUMS
PRPLMESH_VM_NAME=prplmesh-20-0906 bash ./import.sh --profile 20
lxc config get prplmesh-20-0906 boot.autostart
lxc exec prplmesh-20-0906 -- journalctl -fu prplmesh-lab.service
```

The archive contains no provisioned nested containers; offline first boot
creates the 25-container roster from the retained runtime image. It reuses
the qualified 0904 native prplMesh, kernel and wmediumd build. This is a source,
viewer and orchestration refresh, not a new native compilation. The exact
uncommitted source snapshot is identified separately from its Git base commit
in the release manifest and per-file checksum list. Do not treat the base
commit alone as the release source identity.

The universal thin format retains 20/50/100-client provisioning support. The
interactive room's installed binding manifest and acceptance target are the
20-client profile; do not enable that room against other profiles unchanged.

Cold-start radio setup waits up to ten seconds for all three wmediumd sockets
and fails promptly if the daemon exits. This replaces the former fixed
one-second delay, which failed on the initial rev120 deployment. A readiness
timeout remains a deployment failure: inspect the service journal and
`/tmp/prpl-wmediumd.log` rather than treating the room as ready.

## Operate the live room

The persistent service is `prplmesh-room-demo.service` inside the VM. Read-only
viewing needs no credential. To edit, obtain the current capability through
your trusted shell and enter it in the viewer's prompt:

```bash
lxc exec prplmesh-20-0906 -- cat /run/prplmesh-room-demo/operator.token
```

Do not share this secret or publish the operator URL. A short exclusive lease,
revision checks, idempotency keys and a single command queue protect writes.
Drag devices to change geometry; drag empty space to orbit. Play and drag may
be used together. Loading a supported world automatically applies its initial
RF/presence state. Mesh backhaul remains protected at its startup matrix.
Fronthaul disabling does not switch off an extender's control/backhaul radio.

The optimizer uses prplMesh NBAPI associated and unassociated STA metrics and
the existing `scripts/steer-client.sh` BTM path. Candidate transactions require
a changed measurement timestamp, not merely an old cached result. Missing
candidate measurements inhibit steering and are reported as unavailable.
Non-atomic NBAPI sweeps can briefly report a roaming client under both BSSes;
the observer retries these ambiguous snapshots and withholds decisions rather
than inventing an owner or terminating the interactive session.
An explicitly marked kernel `iw link` fallback can fill a missing serving
metric only after traffic succeeds on the same observed BSSID and band.
Geometry predictions are never relabeled as controller observations. The
simulated hwsim/wmediumd candidate provider remains explicitly identified.

The room projects mesh parent relationships from prplMesh NBAPI using stable
BSSID ownership, not discovery-order node names. Unreported backhaul signal
or band stays unknown; it is not inferred from room geometry. Signal meters
use red/yellow/green with grey unfilled segments.

Automatic steering has a 100-action per-session circuit breaker. The viewer
shows the budget and fleet measurement/convergence state. A smaller room can
take several telemetry/hold/steering cycles to settle; loading does not imply
immediate convergence.

## Health, shutdown and recovery

```bash
lxc exec prplmesh-20-0906 -- systemctl is-active prplmesh-lab.service prplmesh-room-demo.service
lxc exec prplmesh-20-0906 -- cat /var/lib/prplmesh-lab/thin-firstboot-report.txt
lxc exec prplmesh-20-0906 -- curl -fsS http://127.0.0.1:8891/api/demo/current
lxc exec prplmesh-20-0906 -- systemctl stop prplmesh-room-demo.service
```

Stopping the room drains commands, reconnects paused clients and verifies
restoration of the exact pre-room RF matrix. Evidence is stored under
`/var/lib/prplmesh-lab/room-runs/RUN_ID/`; inspect `interactive-summary.json`
for restoration and worker outcomes. Before a standalone scenario, stop the
room service: two RF writers must not run together.

After an interrupted session, inside the appliance:

```bash
cd /opt/prplmesh-lab
demo/room-demo recover
systemctl start prplmesh-room-demo.service
```

Recovery refuses an unexpected medium instance or unexplained generation.
Do not bypass that guard by deleting its journal. A VM reboot creates a new
runtime directory and the lab reconstructs its normal startup RF state.

Delete superseded lab VMs only after new thin-import acceptance and live room
checks. Preserve release tars/evidence and unrelated kernel-development VMs.
