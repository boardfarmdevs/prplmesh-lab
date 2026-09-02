# Host EasyMesh Controller UI

The host controller UI reuses the RDK EM CLI Web application and its topology
renderer while replacing the embedded RDK backend with a standalone Go
adapter. It runs on the radio host rather than inside an EasyMesh node.

```text
 prplMesh controller container
 Device.WiFi.DataElements NBAPI
              |
              v
 internal read-only NBAPI adapter :8092
              |
              | JSON devices/radios/BSSs/STAs/backhaul
              v
 +---------------------------------------------------+
 | host easymesh-controller-ui (Go)            :8091 |
 |                                                   |
 | prplMesh adapter -> EM CLI /api/v1 contract       |
 | network profile -> SSID / role / optional VLAN    |
 | embedded RDK EM CLI static topology application   |
 +---------------------------------------------------+
              |
              v
 browser: original topology look, pan/zoom, optimize,
 export, two-second refresh and steering move cues
```

The Web process has no LXD, root, RBUS, database, or controller-container
access. Its only topology input is the configured HTTP API. It preserves the
last valid source response across a short failed refresh rather than replacing
the graph with an empty topology.

## Live surfaces

- Network Topology: original EM CLI renderer and interaction model.
- Mesh Devices: live prplMesh controller and agents.
- Connected Clients: live ownership, BSSID, band, channel and RCPI/RSSI.
- Networks: observed BSS and client counts per SSID.

Dashboard, coverage, policy, performance, security, firmware, reports and
system settings are explicit placeholders. They do not display canned data.

`Optimize Layout` uses the same Controller-first landscape hierarchy as the
RDK UI for star and branch topologies. A complete chain follows parent-child
order across an upper and lower row. The topology pane is bounded to the
visible browser area and does not grow in response to SVG resize events.

## Steering visualization

The client association reported by NBAPI only changes after a roam. To make an
operator-driven steer observable from its beginning, `scripts/steer-client.sh`
publishes a short-lived intent event to the UI before sending BTM:

1. the current client receives an orange pulse and a `NEXT` badge for three
   seconds;
2. the badge changes to `MOVING` while BTM and convergence are in progress;
3. a purple client marker follows the path to the new AP; and
4. the authoritative NBAPI ownership redraw places and pulses the client at
   its new position.

The hint is visualization metadata only. Physical association and NBAPI
convergence remain the acceptance criteria. If port 8091 is unavailable,
steering continues without the preview rather than failing the control action.

## Network model

Every observed BSS is joined to a declarative network by SSID:

| Network | SSID | EM CLI visual role | Current VLAN |
|---|---|---|---|
| Private | `private_ssid` | Fronthaul | untagged |
| IoT | `iot_ssid` | IoT | untagged |
| Mesh Backhaul | `mesh_backhaul` | Backhaul | untagged |

This creates three distinct topology bubbles on every tri-band mesh device.
Clients are placed in the bubble matching their actual associated SSID.

The VLAN example profile assigns 100/200/300. Those values are intentionally
marked `presentation-only`: selecting it proves that the API and renderer can
represent traffic-separated networks, but not that the controller, agents,
bridges and DHCP path enforce them. VLAN acceptance requires tagged packet
captures, address separation and reachability/isolation tests.

## Operation

The service is `prplmesh-controller-ui.service`. Check it with:

```sh
systemctl status prplmesh-controller-ui
curl http://127.0.0.1:8091/health
cd /path/to/prplmesh-lab/controller-ui
tests/acceptance.sh
```

Build and configuration details are in `controller-ui/README.md`.
