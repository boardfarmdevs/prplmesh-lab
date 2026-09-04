# prplMesh immersive room demonstration

`room-demo` compiles a checked-in Golden World against the live prplMesh lab, runs
it through the existing `wmdcfg` actuator, joins live controller telemetry,
traffic, health and reference-optimizer decisions, and serves the presentation
on the runner's authoritative clock.

Its browser/API remain read-only. `stimulus`, `recommend`, and explicitly
confirmed `act` modes separate presentation from network mutation. The
optimizer's act path is request-only so the scenario runner remains the sole RF
writer.

See [the full operator manual](../docs/live-room-demo/manual.md).
