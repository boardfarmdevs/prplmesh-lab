# Room and topology manual

[Documentation home](../README.md) ·
[Room catalog](../../reference/rooms/catalog.md) ·
[Current deployment](../current-state.md)

## Open and control

Open the live room and network topology side by side. The room's built-in
Help is the detailed control reference; this page describes the operating rules.
No `?mode=` is required for the normal live URL.

- **Load world** immediately applies its initial geometry, RF and presence to
  the lab. Wait for completion; there is no separate Apply World step.
- **Play / Pause** controls scripted movement. You can also drag devices without
  switching camera/interactive modes. A moving best AP may change continuously.
- **Ctrl-click any client** selects the traffic probe. Selection does not steer
  that station or give it a special permanent role. “Private-Laptop” is not a
  separate appliance capability.
- Station names remain visible. Drag the black properties label out of the way.
- **Full screen** is available in both views; Esc exits. Topology layout fitting
  changes presentation, not radio positions or actual parent selection.
- Stop/restore a custom run before leaving. Return to the default twenty-client
  world and leave it paused when handing the lab to someone else.

Twenty client containers and six logical mesh roles remain provisioned.
Smaller worlds make selected roles unavailable; they do not rebuild the VM.
Absent clients must disappear from the observed roster after convergence.
Disabling an extender's **fronthaul** does not disable its backhaul.

## Read the views correctly

| Indication | Meaning |
| --- | --- |
| Room position and strongest simulated link | World/RF prediction, not native association |
| Actual solid link | Observed serving AP or backhaul parent |
| Thin dashed link | Strongest simulated eligible link, not proof of steering |
| Red / yellow / green bars | Weak / intermediate / strong known signal |
| Grey bars | Unknown or stale measurement, not a measured zero |
| Extender signal | Backhaul uplink to its actual parent |
| Fronthaul disabled | Client-facing AP unavailable; mesh uplink may still work |
| Network topology | Controller-reported ownership; verify independently for tests |

The same signal scale is used in both views. A client can have the best
available AP without green/maximal SNR. Walls, distance, band eligibility,
SSID, policy margins and station behavior still matter. RDK and prpl radios
have different inventory mappings; compare identities, not just drawing labels.

## Optimizer activity

The deployed room can use an external policy that requests native BTM; it is
not evidence of a native autonomous optimizer. Check the displayed authority.

“Reading” is collection activity; “stable/converged” describes the last
qualified evaluation, not a new handover. Auto BTM permits requests—it does
not guarantee immediate movement. Read the current epoch, freshness, target,
decision reason and terminal verification in recent events.

**Measurements unavailable** pauses automatic decisions when a safe fresh
candidate set cannot be obtained. The room remains interactive. Preserve the
error/age/retry information rather than treating grey as zero, borrowing stale
candidates or forcing clients onto the dashed link.

A star can be correct in profiling: startup backhaul is protected. Moving
extenders does not by itself request native backhaul optimization. The
[coordination reference](../../reference/rooms/architecture.md) separates demonstration
assistance, client profiling and explicitly modeled-backhaul experiments.

## Safe use and troubleshooting

Use one operator lease and one RF writer. Do not run a second scenario, manual
RF-assisted steer or conductor against the same medium. A paused room may
still collect/steer; stop its service before a standalone native experiment.

If a load or recovery fails, keep the fault and journal. Do not delete the
ownership record, invent topology entries or restart every native service.
Check service health, current world/epoch, actual station link and candidate
freshness in that order. Remote access is covered in
[transport and access](../../reference/rooms/access.md).

For a correctness claim, use [room acceptance](../../reference/testing/room-acceptance.md).
A screenshot, accepted API request or interesting animation is not a pass.
