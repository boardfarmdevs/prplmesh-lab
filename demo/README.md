# prplMesh immersive room demonstration

`room-demo` compiles a checked-in Golden World against the live prplMesh lab, runs
it through the existing `wmdcfg` actuator, joins live controller telemetry,
traffic, health and reference-optimizer decisions, and serves the presentation
on the runner's authoritative clock.

Observation/replay are read-only; interactive sessions support leased room
loading, Play and dragging. `stimulus`, `recommend` and explicitly confirmed
`act` modes separate RF stimulus from optimizer authority. The optimizer's
native BTM submission does not become another RF writer.

See [the full operator manual](../docs/live-room-demo/README.md).
