# Live room demo

The live room demo combines a reproducible 3D home, dynamic wmediumd RF
conditions, controller telemetry and the reference optimizer in one
presentation. Start here:

- [Operator manual](manual.md) — complete setup, operation, replay,
  troubleshooting and customization instructions.
- [Architecture and design](design.md) — system boundaries, data flow and
  implementation decisions.
- [Viewer reference](viewer.md) — stimulus-only viewer controls and visual
  conventions.
- [Interactive room plan](interactive-room-plan.md) — staged development for
  scripted, live drag-driven and hybrid demonstrations.

The normal entry point is `demo/room-demo`. The prplMesh Network Topology view
remains the authority for the controller's current association model, while
the room viewer presents the physical scenario and the wmediumd console shows
the medium's live frame and SNR observations.
