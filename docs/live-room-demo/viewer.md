# Room viewer reference

The prpl room viewer intentionally uses the same HTML, Three.js asset, event
contract and visual language as the RDK room viewer.

## Start

Inside a ready 20-client appliance:

```sh
cd /opt/prplmesh-lab
demo/room-demo run --mode recommend --listen 0.0.0.0:8891
```

Open `http://OUTER_HOST:18891/viewer/?mode=live`. The 0904 importer creates the
outer 18891 to guest 8891 proxy automatically. Override the outer port with
`PRPLMESH_ROOM_DEMO_HOST_PORT` during import.

## Visual conventions

- red tower: gateway/colocated controller Agent;
- blue tower: extender;
- blue/green stems: private/IoT station;
- gold ring and purple trail: Private-Laptop and traveled path;
- translucent planes: modeled walls;
- dashed traffic-light line: scenario-best AP;
- solid cyan line: prpl controller-observed association;
- dashed gold line: measured optimizer target.

Scenario, actual and optimizer links are separate facts. A green scenario link
does not assert association, and a gold target does not assert a request.

## Controls

In live mode the Runner owns the clock, so file selection, play, speed and
scrubbing are disabled. Orbit, shift-pan, zoom, labels, trails, backhaul,
scenario links and display-band selection remain available. Display-band
selection changes rendering only; it never configures a radio.

The state cards show the current narrative, whole-lab counts, live hero
association/metric/traffic, optimizer state and recent ordered events. After a
run, use the linger interval or replay its evidence directory.

## API and replay

The viewer consumes:

- `/api/demo/current` for a current snapshot;
- `/api/demo/world` for immutable geometry and SNR;
- `/api/demo/events` for resumable SSE; and
- `/api/demo/events.json` for complete browser replay.

```sh
demo/room-demo replay /tmp/prplmesh-room-demo-runs/RUN_ID \
  --listen 0.0.0.0:8891
```

Open the same URL with `?mode=replay`. Replay is read-only and does not require
prplMesh, LXD or wmediumd.

## Companion views

Use the Controller UI on outer port 8091 for NBAPI topology truth and the
wmediumd Console on outer port 8090 for applied medium/frame truth. Select
`sta-02` in the Console to follow Private-Laptop. Its permanent radio identity
and controller-facing `02:00:00:10:02:00` MAC are different namespaces.

If the viewer is blank, test `/healthz`, confirm the run listens on
`0.0.0.0:8891`, and inspect `lxc config device show VM` for
`room-demo-viewer`. Browser controls cannot repair a failed run; use the event
journal and `demo-summary.json`.
