# Host EasyMesh Controller UI

This is the RDK EM CLI network-topology experience ported to a standalone Go
process on the radio host. It uses the external prplMesh topology API rather than CGo,
RBUS, MariaDB, or files inside the controller container.

## Run

Install the tested binary and a path-correct systemd unit from any checkout:

```sh
./install.sh
```

For foreground development:

```sh
cd /path/to/prplmesh-lab/controller-ui
bash prepare-web-assets.sh
mkdir -p bin
go test ./...
go build -o bin/easymesh-controller ./cmd/easymesh-controller
bin/easymesh-controller
```

The checked-in `web-vendor.tar.gz` contains pinned D3 7.9.0, Chart.js 3.9.1,
Animate.css 4.1.1 and Font Awesome Free 6.4.0 assets, fonts, upstream licenses
and checksums. Preparation verifies and expands these offline before Go embeds
them. No runtime CDN access is required. The archive matches RDK's vendor
payload; update both together and retain its upstream license files.

Open `http://HOST-IP:8091/`. Network Topology is the default page and
polls live controller data. Concurrent requests share only an in-flight source
request; completed responses have no additional cache lifetime. Source errors
and empty inventories are failures, never successful stale snapshots.
Mesh Devices and Connected Clients also consume
live data. All other pages are explicit placeholders.

The default source is:

```text
http://127.0.0.1:8092/api/topology
```

Override it with `-source` or `EASYMESH_TOPOLOGY_URL`. The EM CLI-compatible
API exposed by this process includes:

```text
GET /health
GET /api/v1/topology
GET /api/v1/room-layout
GET /api/v1/devices
GET /api/v1/clients
GET /api/v1/bsses
GET /api/v1/networks
GET /api/v1/config
GET /api/v1/steering-event
POST /api/v1/steering-event
```

The steering endpoint carries a short-lived `planned`, `moving`, `completed`,
or `failed` visualization event. `scripts/steer-client.sh` uses it to identify
the next client before BTM; it is not a steering control API.

## Room and topology parity

The September 14 UI follows live room mesh coordinates by device identity,
using the default room camera orientation. The room title stays in the existing
topology header. Grey dividers resize both views; topology packing preserves
orientation and fits the available drawing area with a thin margin. Dragging a
mesh icon switches to manual layout; Follow room restores coordinate following.
Manual room-camera orbit remains local to that browser, not a topology rotation.

The independent read-only layout proxy uses `EASYMESH_ROOM_URL`, default
`http://127.0.0.1:8891`; an empty value disables it. It has a 750 ms upstream
deadline, 64 KiB response limit and 200 ms in-flight/coalesced cache. No topology
query or steering request waits for this proxy. Outages retain diagram positions
and mark the last room title as previously observed.

Six-second roam trails mark the old client position and current association:
teal means a matching accepted native BTM request, pink an explicit non-BTM
operator report, grey unknown. Planned/moving intent alone never proves BTM.
The room projects accepted optimizer events into a bounded 30-second history;
there are no extra native measurements or synchronous UI calls in the actuator.
For explicit non-BTM reports, add `method: "non-btm"`, `source_bssid` and
`target_bssid` to a completed steering event. This annotates, never steers.
The separate Controller icon does not add a sixth physical NBAPI mesh device.

## Multiple networks and VLANs

`config/networks-untagged.json` is the live accepted profile:

- `private_ssid` → Private/Fronthaul;
- `iot_ssid` → IoT; and
- `mesh_backhaul` → Backhaul.

All three are currently untagged. `config/networks-vlan-example.json` shows
the same model with VLANs 100, 200 and 300. Selecting that file changes the UI
and API presentation only. It does not claim traffic separation until
prplMesh, bridges, DHCP, and packet captures independently prove VLAN
enforcement end to end.

Additional SSIDs can be added as additional network objects. Multiple networks
may share a visual role such as `Fronthaul`; they remain separate SSID bubbles.

Select a profile with:

```sh
EASYMESH_NETWORKS_FILE=config/networks-vlan-example.json \
  bin/easymesh-controller -listen 0.0.0.0:8092
```

## Service

Build the binary, install `systemd/prplmesh-controller-ui.service` under
`/etc/systemd/system/`, then enable it. The service runs without root and
restarts independently of the controller and radio VM.
