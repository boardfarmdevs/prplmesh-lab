# prplMesh architecture

[Documentation home](README.md) · [Native processes](../reference/platform/software-architecture.md)

The outer VM owns Linux, hwsim, wmediumd and nested LXD. Five mesh containers
contain one controller with colocated agent plus four external agents. Twenty
active clients are selected by the default room from 100 provisioned station
containers. Controller and its colocated agent
appear as separate topology roles. No RDK runtime, database, radio pool or
container is reused.

Each mesh device has 2.4/5/6 GHz radios; external agents use a separate backhaul
station VIF on their 5-GHz PHY. Clients use their assigned radio. Startup
`star`, `branch` and `chain` select initial parentage without changing permanent
radio ownership. Geometry rooms also exercise the lab's native controller
backhaul-roaming extension; its evidence and safety rules are described in
[room coordination](../reference/rooms/architecture.md).

| Path | Owner |
| --- | --- |
| Simulated frame delivery and signal | hwsim + patched multichannel wmediumd |
| Client/AP association and security | Native hostapd/supplicant and prplMesh |
| IEEE 1905, native metrics and BTM | prplMesh controller/agents |
| Normalized topology and candidate reads | Loopback NBAPI adapter |
| Geometry, presence and atomic RF changes | Shared-design room/configurator runner |
| Bounded client policy | External optimizer |
| Presentation | Controller UI, room viewer and wmediumd Console |
| Resource trends | Inner Prometheus/Grafana, optional outer-VM scrape |

The observer/actuator seam normalizes native state rather than rewriting it.
World geometry is not a hidden oracle for native candidate measurements.
A passed test compares physical association, controller NBAPI ownership,
fresh measurements and traffic.

[Software architecture](../reference/platform/software-architecture.md) owns
process and IEEE 1905 details; [adapter](../reference/observability/topology-adapter.md)
owns normalized APIs; [optimizer](../reference/optimizer/configurator.md) owns
external policy integration. [Room coordination](../reference/rooms/architecture.md)
describes epochs, authority, replay and recovery. Source identities and
qualification limits belong in [current state](current-state.md).
