# prplMesh architecture

[Documentation home](README.md) · [Native processes](../reference/platform/software-architecture.md)

The outer VM owns Linux, hwsim, wmediumd and nested LXD. Five mesh containers
contain one controller with colocated agent plus four external agents. Twenty
client containers run station software. Controller and its colocated agent
appear as separate topology roles. No RDK runtime, database, radio pool or
container is reused.

Each mesh device has 2.4/5/6 GHz radios; external agents use a separate backhaul
station VIF on their 5-GHz PHY. Clients use their assigned radio. Startup
`star`, `branch` and `chain` select parentage without changing permanent
radio ownership. This is not native adaptive backhaul policy.

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
