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

World controls come first; Browse rooms explains RF, policy and evidence.
Both views have room titles, resizable panels and fullscreen. Topology follows
the default room-camera orientation, not manual orbit. **CONVERGED** requires
fresh policy, roster and health evidence. prpl health counts five physical
devices; the separate Controller icon is not another device.

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

Both views share the signal scale. The best eligible AP need not have maximum
SNR. Compare native identities, not discovery-order labels.

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

A star can be correct in ordinary rooms: startup backhaul is protected. The
three `backhaul-*` rooms explicitly apply geometry to mesh RF and leave parent
selection to native prplMesh. Outages are visible; no RDK parent actuator is
ported. Returning to an ordinary room restores the protected baseline. The
[coordination reference](../../reference/rooms/architecture.md) separates demonstration
assistance, client profiling and explicitly modeled-backhaul experiments.

## Safe use and troubleshooting

Use one lease and RF writer. Paused rooms still collect/steer; stop the service
before running standalone native experiments.

After failures, retain the fault/journal and check health, world/epoch, native
links and candidate freshness before restarting. Remote access is covered in
[transport and access](../../reference/rooms/access.md).

For a correctness claim, use [room acceptance](../../reference/testing/room-acceptance.md).
A screenshot, accepted API request or interesting animation is not a pass.
