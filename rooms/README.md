# The prplMesh lab's live room

`room-service` starts the room service, which is easymesh-optimizer's `room_service`
package (this lab pins the repository as `optimizer`): it compiles a checked-in
Golden World against the live prplMesh lab, runs it through the `wmdcfg`
actuator, joins live controller telemetry, traffic, health and the optimizer's
decisions, and serves the presentation on the runner's authoritative clock.

This directory is the lab's side of it: the launcher (`room-service`, which the VM's
`prplmesh-room-service.service` runs), the room manifests (`manifests/`: the
default rooms, the rooms with the wired Agent, the load-aware and counter-guard
profiles) and the role bindings (`bindings/`: which container plays which room
role), and the tests of these (`tests/`). The room service's own tests are in
easymesh-optimizer (`tests/room`).

Observation and replay are read-only; interactive sessions support leased room
loading, Play and dragging. `stimulus`, `recommend` and explicitly confirmed
`act` modes separate RF stimulus from optimizer authority. The optimizer's
native BTM submission does not become another RF writer.

See [the full operator manual](../docs/guides/room-manual.md).
