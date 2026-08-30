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
mkdir -p bin
go test ./...
go build -o bin/easymesh-controller ./cmd/easymesh-controller
bin/easymesh-controller
```

Open `http://HOST-IP:8091/`. Network Topology is the default page and
refreshes every two seconds. Mesh Devices and Connected Clients also consume
live data. All other pages are explicit placeholders.

The default source is:

```text
http://127.0.0.1:8090/api/topology
```

Override it with `-source` or `EASYMESH_TOPOLOGY_URL`. The EM CLI-compatible
API exposed by this process includes:

```text
GET /health
GET /api/v1/topology
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
