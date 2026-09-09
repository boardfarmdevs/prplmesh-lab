# prplMesh 0908: independent lab and live room on rev150

## Ownership and URLs

Canonical prplMesh source is `rev150:/home/rev/git/prplmesh-lab`, branch
`codex/0908-clean`. RDK has its own `codex/0908-clean` branch and canonical
Yocto workspace on rev140. Do not build, package, or deploy prplMesh on rev140.
The retired rev140 checkout, including its uncommitted work, and the stopped
native build container have a checksum-verified private backup on rev150 at
`/home/rev/retired/rev140-prpl-0908`. The rev140 prplMesh UI service, checkout,
build container, packaging VM, and private LXD networks are retired.

The intended 0908 endpoints are:

| View | RDK on rev140 | prplMesh on rev150 |
| --- | --- | --- |
| Network topology | `http://192.168.2.140:48889/` | `http://192.168.2.150:8091/` |
| Interactive room | `http://192.168.2.140:48891/` | `http://192.168.2.150:18891/` |
| wmediumd console | `http://192.168.2.140:48890/` | `http://192.168.2.150:8090/` |
| Room manual | `http://192.168.2.140:48891/viewer/manual.html` | `http://192.168.2.150:18891/viewer/manual.html` |

Each room owns its own RF writer, optimizer, inventory, lease and evidence.
Opening both URLs side by side does not share control or move the other lab.
No `?mode=` parameter or operator token is needed. These are trusted-LAN
control endpoints, not authenticated Internet services; use an authenticated
gateway or VPN before exposing them beyond the lab. Same-origin checks,
exclusive control leases and world revisions still protect mutations.

## Viewer parity and backend boundaries

The viewer and shared room coordination are synchronized with RDK 0908:
fullscreen in both views, floor-level backhaul links, consistent red/yellow/
green signal bars with grey unknown segments, larger readable labels,
non-rearranging fit-to-window, draggable properties, always-visible station
names, Ctrl-click traffic-probe selection, stable optimizer panels, and
automatic application of loaded rooms. The room catalog includes short
handover, disappearance, extender evacuation and counter-rotating perimeter
scenarios. Play and drag work together.

The topology shows Agent-1 and the colocated logical Controller separately,
plus four extenders. These are six displayed roles, not six independent
mesh containers. The physical pool remains five mesh containers and twenty
client containers. Loading a smaller room changes availability, not pool
size; restoring the default room returns all twenty clients.

prplMesh retains its own Data Elements NBAPI metrics, stable MAC bindings,
and NBAPI BTM actuator. It does not call RDK RBUS, EM CLI native endpoints,
or the RDK OneWifi parent-selection adapter. Unsupported RDK configuration
pages remain explicitly unavailable rather than pretending to implement
them. Unreported backhaul metrics remain unknown, never geometry-derived
controller measurements.

The default room uses unassisted BTM profiling: no pre-action highlight wait,
forced scans, RF steering boost, or movement-stability gate. Candidate
collection publishes fresh per-radio results without blocking association
rendering. Candidate identity and timestamps remain checked; unavailable
measurements are not reported as convergence. The external room policy is
not claimed to be prplMesh's autonomous optimizer. The default mesh backhaul
RF matrix is protected; native-observation runs can explicitly model it with
`--mode stimulus --profiling --model-backhaul`, without external parent
selection. RDK's external adaptive-parent adapter is not a prplMesh feature.

## Portable release and import

0908 refreshes committed source, viewer, services and orchestration on the
qualified prplMesh native runtime retained in the 0907 thin archive. This is
not a new native prplMesh compilation or a Yocto build. `release.json`, the
runtime provenance and checksums identify the exact inputs. Packaging must
contain a clean committed source tree, zero provisioned nested instances,
the retained local runtime image, and no monitoring credentials.

After release qualification, install from the new thin tar on rev150:

```sh
cd /home/rev/releases/0908
sha256sum -c prplmesh-0908-thin.tar.sha256
tar -xf prplmesh-0908-thin.tar
cd prplmesh-0908-thin
sha256sum -c SHA256SUMS
PRPLMESH_VM_NAME=prplmesh-20-0908 \
PRPLMESH_UI_HOST_IP=192.168.2.150 \
PRPLMESH_LXD_STORAGE=bpi-lab ./import.sh --profile 20
lxc config get prplmesh-20-0908 boot.autostart
lxc exec prplmesh-20-0908 -- cat /var/lib/prplmesh-lab/thin-firstboot-report.txt
lxc exec prplmesh-20-0908 -- systemctl is-active prplmesh-lab.service prplmesh-room-demo.service
```

Always use the bundled import wrapper: it remaps the outer network address
before LXD validates the backup. Raw `lxc import` without device overrides
can fail when the destination subnet differs from the source host.
Outer VM autostart remains false; explicitly starting the VM starts its lab
and default room. Monitoring remains opt-in with the included observability
scripts; use separate prplMesh ports 18892 for nested LXD UI and 18893 for
Grafana. No changes to rev120 are implied by this release.

## Bounded acceptance

Qualification must use an actual import of the new 0908 thin archive, not
the packaging VM. Check the offline first-boot report, 25 nested containers,
20 client associations, observed mesh edges, both fullscreen controls,
Ctrl-click probe selection, Play/Pause, a smaller world and return to the
default room. Inspect browser errors and evidence for worker failures.
Full all-room soak testing is not required for this release. Record exact
source IDs, hashes, timing and any limitations beside the release archive.

## Fresh-import findings

The first candidate provisioned all 25 nested containers offline, but the
new whole-network recursive NBAPI read returned no payload at full depth
and prevented UI readiness. The adapter now discovers device IDs once and
reads each device subtree concurrently with bounded depth and native call
timeouts. This includes BSS/STA measurements without serializing hundreds
of object reads or requesting one oversized network response. The repaired
live adapter returned five mesh devices and twenty clients in a 44 ms sample;
that is one observation, not a latency guarantee or a steering benchmark.
Regression coverage checks concurrent merging and propagates a failed device
read as unavailable rather than a deceptively empty topology.

Failed transient adapter units are reset before recreation and have bounded
shutdown. Native statistics polling is configured to one second at lab startup,
with associated-link and traffic reporting included and NBAPI readback verified.
`PRPL_METRICS_INTERVAL_SEC` may select 1–60 seconds for less demanding deployments.
The separate `LinkMetricsRequestIntervalSec` timer is disabled: in this retained
runtime it also broadcasts empty unassociated-STA queries, clearing the candidate
collector's in-flight registrations. The external room collector owns explicit
NBAPI candidate requests instead. Periodic 1905 neighbor-link statistics from
that timer are consequently disabled; topology parent observation and native
AP/STA reporting remain active. No synthetic freshness or one-second roaming
guarantee is implied.

In the live diagnostic import, disabling the competing timer eliminated the
unavailable cohorts and produced a complete converged snapshot within thirty
seconds: twenty clients checked, eighty fresh candidate comparisons, and no
client with a stronger eligible AP. This is a bounded default-room observation,
not an all-room soak or a native autonomous-optimizer benchmark.
The room is also wanted by the lab service so an explicit lab start brings
its viewer up after native readiness.

Candidate archives preceding these fixes are diagnostic inputs,
not qualified deliveries. Final qualification still requires another fresh
import of the packaged committed source and the bounded checks above.
