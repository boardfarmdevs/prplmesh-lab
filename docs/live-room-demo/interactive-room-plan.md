# Interactive room demonstration plan

## Goal

Extend the existing closed-loop room demonstration so the same presentation can
run from a precooked Golden World, from live operator movement, or from a
combination of both.

The operator can drag a bound client, extender or gateway in the room. The
viewer immediately previews the new radio geometry, while the server computes
and atomically applies the authoritative per-band link changes to wmediumd.
The mesh implementation must then report the resulting measurements through
its normal telemetry path. The optimizer may recommend or execute a steer, and
the viewer shows the measured transition and verified outcome.

The demonstration must never manufacture controller telemetry or visually move
a client between APs merely because its room position changed.

## Presentation modes

| Mode | Movement source | RF changes | Steering authority |
|---|---|---|---|
| Scripted | Precooked scenario timeline | Applied by the configurator runner | stimulus, recommend or act |
| Interactive | Operator drag operations | Applied from live world geometry | recommend by default; explicit act |
| Hybrid | Scenario timeline plus operator overrides | Script continues around leased overrides | recommend by default; explicit act |
| Replay | Recorded evidence only | None | None |

A live interaction can be recorded as keyframes and exported as a valid world
scenario. This makes an improvised demonstration reproducible and allows a
useful session to become a new regression test.

## Closed-loop contract

```text
pointer drag
    |
    +--> browser preview: position and predicted signal only
    |
    '--> room server: validated position intent + world revision
             |
             +--> geometry engine
             |      distance, walls, band model, deterministic noise
             |
             +--> configurator compiler
             |      role bindings -> frequency-qualified radio pairs
             |
             '--> one atomic wmediumd generation
                         |
                         v
               frames experience new RF conditions
                         |
                         v
             agent/controller telemetry path
                         |
                         v
                  reference optimizer
                   /             \
             recommend          explicit act
                |                    |
                |               steering API/BTM
                |                    |
                '------> topology observation
                              |
                              v
                   verified association and traffic
```

The browser's predicted meter is visually distinguished from measured
controller RCPI. Once a fresh measurement arrives, it replaces the preview.
If the two disagree, both values remain visible in the detail panel.

## Interaction model

Only roles already present in the active binding inventory are draggable.

During a drag, the browser updates position and predicted signal at animation
rate without writing to the medium. The browser sends throttled position
intents, at most five per second, and always sends the final pointer-up
position. The server:

1. validates the role, room boundary and active run;
2. rejects stale requests using the expected world revision;
3. calculates link loss for every affected band and obstruction;
4. compiles only the changed radio pairs;
5. applies one atomic generation through the existing control socket;
6. reads the generation back and emits the accepted position and RF delta;
7. waits for normal mesh telemetry and optimizer evaluation.

Moving a client changes its links to all AP radios and relevant peers. Moving
an AP or extender changes every affected fronthaul and backhaul pair. The
initial milestone limits live dragging to clients so cost and behavior remain
easy to bound.

A movement lease prevents two browsers from controlling the same role. A
second observer remains read-only. Losing the lease or closing the run freezes
the role at its last accepted position; stopping the run restores the complete
pre-run RF matrix.

## Server API and events

Keep the existing read-only endpoints:

- `GET /api/demo/current`
- `GET /api/demo/world`
- `GET /api/demo/events`

Add a narrowly scoped interaction API:

- `POST /api/demo/interactions/lease`
- `PUT /api/demo/roles/{role}/position`
- `DELETE /api/demo/interactions/lease`
- `POST /api/demo/recording/start`
- `POST /api/demo/recording/stop`
- `GET /api/demo/recording/world`

A position request contains the lease, expected world revision, coordinates,
optional transition duration and client request sequence. The reply contains
the accepted revision, authoritative position, wmediumd generation and changed
link count.

New ordered events include:

- `interaction.lease.acquired`
- `interaction.position.previewed`
- `interaction.position.accepted`
- `interaction.position.rejected`
- `rf.generation.applied`
- `telemetry.position.effect.observed`
- `optimizer.recommendation`
- `steering.requested`
- `steering.verified`

All events use the current evidence sequence and run identifier.

## Script and live-movement integration

The world model becomes a mutable overlay above an immutable scenario:

```text
base scenario keyframes
          +
operator position overrides
          +
optional recorded live keyframes
          |
          v
authoritative world state at time T
```

In hybrid mode, an operator override leases a role and temporarily supersedes
its scripted path. The UI offers three explicit resolutions:

- resume the original path at the current scenario time;
- rejoin the original path over a selected transition time;
- keep manual control for the rest of the run.

Recording samples accepted positions, simplifies the path within a configured
error tolerance, preserves significant RF/steering event times, and exports
the same scenario schema consumed by the current configurator.

## Delivery phases

### Phase 1: safe interactive preview

- Add draggable client roles and room-boundary constraints.
- Show predicted per-AP signal and the strongest candidate.
- Add lease/revision handling.
- Do not change wmediumd.
- Unit-test geometry, stale revisions and multi-browser ownership.

Exit criterion: dragging remains smooth, deterministic and incapable of
changing the lab.

### Phase 2: live RF actuation

- Compile each accepted client position into frequency-qualified SNR updates.
- Apply changed pairs as one atomic wmediumd generation.
- Rate-limit and coalesce drag updates.
- Read back every generation.
- Restore the exact original RF matrix on stop, error or process termination.

Exit criterion: moving one client changes only its intended RF pairs, measured
RCPI follows, traffic remains bounded, and restore is byte-for-byte exact.

### Phase 3: optimizer loop

- Feed only controller-reported current and candidate measurements to the
  optimizer.
- Present current AP, candidate ranking, hold time and reason codes.
- Keep recommendation as the default authority.
- Add an explicit operator-confirmed BTM action.
- Verify physical association, controller ownership and traffic.

Exit criterion: dragging across a boundary produces an understandable,
repeatable recommendation and an optional verified steer.

### Phase 4: hybrid scripted control and recording

- Allow live takeover of a role during a precooked scenario.
- Implement resume, rejoin and remain-manual behavior.
- Record accepted movements as keyframes.
- Export and replay the generated world and evidence.
- Add a one-command regression test for an exported session.

Exit criterion: a live improvised path can be exported, replayed and produce
the same RF crossover within declared tolerances.

### Phase 5: full-room editing

- Permit extenders and the gateway to move.
- Recompute affected backhaul as well as fronthaul links.
- Add wall creation, movement and attenuation editing.
- Add undo/redo and named scene snapshots.
- Make calculation cost and write coalescing safe for 20, 50 and 100 clients.

Exit criterion: topology, candidate ranking and backhaul consequences remain
correct under bounded interactive changes at every supported scale.

## Safety and usability requirements

- Default to recommend mode; act requires an explicit per-run confirmation.
- Never infer a completed steer from geometry or predicted signal.
- Clearly label predicted, applied and measured values.
- Retain the last confirmed medium generation and controller snapshot.
- Reject controls when the medium instance or inventory generation changes.
- Coalesce pointer motion without dropping the final position.
- Preserve observer-only browsers while one operator holds a lease.
- Restore RF on every normal and abnormal exit.
- Include a prominent Reset Scene action that restores the scenario state,
  not lab provisioning or device identity.
- Store every live control operation in the normal evidence bundle.

## Initial implementation slice

Start with one 5 GHz private client in the existing five-agent room:

1. drag the hero client;
2. preview its signal to every AP;
3. apply its changed wmediumd pairs at pointer-up;
4. observe fresh controller RCPI;
5. show the optimizer recommendation;
6. optionally confirm one BTM steer;
7. verify association and traffic;
8. restore the starting RF matrix;
9. export the movement as a scenario.

This uses the current viewer, world geometry, role bindings, atomic control
plane, optimizer and evidence recorder. It adds interaction rather than a
second demonstration architecture.

