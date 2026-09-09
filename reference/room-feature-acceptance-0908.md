# 0908 room correctness and convergence test plan

## Scope

Run one bounded pass through every room advertised by the running RDK lab on
rev140 and prplMesh lab on rev150, concurrently across hosts but sequentially
within each lab. Load each room through the browser selector, check the loaded
state, press the real Play button, observe the entire normal-speed script,
honour explicit scenario checkpoints, and check the final topology. This is
feature acceptance, not a long-running soak or a controlled stack benchmark.

| Lab | Room | Network topology |
| --- | --- | --- |
| RDK, `rdkeasymesh-20-0908` | <http://192.168.2.140:48891/> | <http://192.168.2.140:48889/> |
| prplMesh, `prplmesh-20-0908` | <http://192.168.2.150:18891/> | <http://192.168.2.150:8091/> |

No native stack, VM, container pool, metrics interval, RF policy, freshness
threshold, CPU allocation or fan setting is changed. Preserve the existing
uncommitted VirtualBox work. Save the initial room state, service configuration,
native/container/medium process identities and deployed golden files first.

The room conductor has a **session-wide 100-action limit**, not a per-world
limit. For this finite 14-room test only, use a named `/run/systemd/system/`
drop-in to run each room service with `--max-actions 2000`; restart only the
room service, outside measured phases. Remove that drop-in and restore the
original service after testing. This avoids misreporting budget exhaustion as
native roaming latency. Record the temporary setting and total actions. Do not
restart native controllers, AP services, clients or wmediumd to pass a case.
Finish with the default twenty-client room, paused, and no held test lease.

## Matrix and expected behaviour

The live catalogs are authoritative for enumeration; golden files copied from
each running guest supply positions, presence, duration and checkpoint times.
Match their identity to the selected live world before judging movement.

| Room | Script | Expected feature |
| --- | ---: | --- |
| `home-a-stationary` | 60 s | Ten clients; no scripted movement or sustained AP churn after settling. |
| `home-a-one-client-handover` | 20 s | Eleven clients; one crossing client, actual association follows an eligible better AP. |
| `large-room-extender-evacuation` | 20 s | Twelve clients; moving extender evacuates its cluster toward better serving APs. |
| `large-room-perimeter-counter-roam` | 60 s | Twelve clients; two opposing walkers, checkpoint pauses at 14/28/42 s, inspect both AP paths. |
| `home-a-asymmetric-link` | 60 s | Eleven clients; the walker's declared uplink penalties must survive live playback, not silently become symmetric. |
| `home-a-band-walk-small` | 60 s | Ten moving clients; retain SSID identity and compare eligible same-band APs. |
| `home-a-border-hover` | 60 s | Twelve clients; two boundary walkers; record ping-pong separately from justified roaming. |
| `home-a-disappear-reappear` | 60 s | 12→11→10→11→12 clients at 16/24/32/40 s; preserve identities. |
| `home-a-extender-loss-recovery` | 90 s | Ten clients; logical `extender_4` fronthaul unavailable at 20–60 s, mesh backhaul remains. |
| `home-a-fast-transit` | 30 s | Twelve clients; two fast walkers; measure lag and post-motion recovery. |
| `home-a-flash-crowd` | 60 s | 10→20→10 clients at 20/50 s; no lingering ghost/duplicate stations. |
| `home-a-private-client-room-walk` | 240 s | Twenty clients; one narrated walker and nineteen reference clients. |
| `home-a-slow-walk-ten` | 60 s | Twenty clients; ten walkers and ten fixed clients. |
| `home-b-slow-walk-ten` | 60 s | Twenty clients; shifted AP geometry, same correctness checks without assuming adaptive backhaul. |

Both 0908 releases advertise protected/fixed startup backhaul. Do not require
a chain or branch merely because an extender is closer to another extender.
Require a connected, loop-free five-device mesh, six logical topology roles,
and agreement of actual parents between the room and topology. Record disabled
fronthaul and missing native backhaul measurements without inventing values.

## Gates and measurements

1. **Load:** selecting the room must issue its automatic apply request, finish
   with the correct golden identity, reset playback/overrides, and verify RF
   application. Record click-to-apply acknowledgement and server sub-timings.
2. **Loaded convergence:** allow 90 seconds, requiring five continuous seconds
   of the exact expected roster, no duplicate MACs, matching actual AP/BSSID
   ownership in the room and rendered SVG topology, six mesh roles, healthy
   lab, current-epoch fresh candidate coverage, and no stronger eligible
   same-band AP. Record first roster and convergence times independently.
3. **Play:** use browser Play at 1×. Target one sample per second without issuing
   extra candidate queries. Check scripted positions/presence against the
   golden interpolation, monotonic clock progress and actual SVG client nodes
   and parent bindings. Capture initial, middle and final screenshots of both
   views, plus perimeter checkpoints. Never call the preview `setTime` helper
   or assign APs to manufacture convergence.
   Record actual sampling intervals: screenshots can introduce gaps. Do not
   infer a continuously wrong view across an unobserved interval; require
   consecutive adequately spaced bad observations for a sustained-view failure.
4. **During motion:** record roster changes, native/visible association changes,
   duplicate nodes, sustained view disagreement, incomplete metrics and
   measured convergence coverage. A continuously moving target need not be
   fully converged every instant. A mismatch persisting over five seconds is
   flagged, with transient samples retained separately. Presence phases must
   appear in the actual topology, not just in the room's simulated state.
5. **Checkpoints/end:** allow 60 seconds per explicit checkpoint and 120 seconds
   after completion, again requiring a five-second stable strict gate. Resume
   a checkpoint after pass or timeout so a failure cannot prevent the rest of
   the scenario being exercised. Playback has a wall-clock cap of twice its
   nominal duration plus 30 seconds, excluding explicit checkpoint waits.
6. **Native evidence:** passively subscribe to room SSE events. Record RF apply
   duration, candidate transaction duration/errors, native action submission,
   verified association/traffic result and elapsed verification time. Native
   timings are not browser rendering timings. Record first-observed UI lag at
   the one-second sampling resolution; do not claim sub-second precision or
   causally attribute every spontaneous association change to BTM.
7. **Independent checks:** verify excluded clients with kernel `iw link` at
   settled boundaries, check SSID/BSSID identity, preserve all 25 nested
   container and native-service identities, and record room/medium faults,
   event-stream gaps and browser errors. Do not convert a timeout to a pass.

The RF-specific supplement reads live directional wmediumd links with
`room-feature-rf-audit.py` during the asymmetric script. It issues no mutations
or candidate queries. Compare the walker-to-AP minus AP-to-walker SNR with the
deployed golden: nominally −7/−10/−12 dB for 2.4/5/6 GHz, respectively, subject
to golden clamping and the bands actually present. Reject a sample crossing
an environment epoch. This check was added after a discrepancy was found in
the first pass; retain the original convergence verdict separately from the
RF-feature verdict. During the extender outage, require no remaining clients
on the disabled role after a five-second grace period, while preserving mesh
connectivity.

For a presence failure, a targeted replay can run
`room-feature-presence-audit.py rdk` (or `prpl`) inside the guest. It waits for
the disappearance scenario, then reads both walkers' kernel `iw link` state
alongside the controller roster and expected presence. This distinguishes a
stale controller entry from a genuinely connected supposedly unavailable
station. The sampler is bounded to the script and does not reconnect clients.

Freshness means current-epoch evaluation, evaluation/current-link age at most
30 seconds and complete native candidate coverage. A simulated strongest-link
line, a success response to a steering command, the word “stable”, or healthy
HTTP alone is not convergence. Record policy-margin convergence separately
from absolute same-band best-AP convergence. No arbitrary all-green signal
requirement is imposed.

## Execution and evidence

`gen/tests/room-feature-acceptance.js` runs the same browser/API assertions for
both backends. It requires existing Playwright/Chromium paths supplied through
`PLAYWRIGHT_MODULE` and `CHROMIUM_PATH`, explicit `--yes-act`, URLs, golden-file
directory and an output directory. Run two independent processes concurrently.
The pure assertion checks are in `gen/tests/test-room-feature-acceptance.js`.
Host sampling runs separately every ten seconds, without native metrics queries.
Prefer a separate observer machine or hardware-accelerated browser. Two
unrestricted SwiftShader renderers can consume most of a lab host's CPUs.
If observers must share a lab host, restrict **only test browser** CPU usage
before measuring, document that restriction, and retain before/after host
samples. Never change VM/native CPU allocation to improve a test result.
The recorded run includes such an observer-only adjustment and is therefore
not a clean cross-stack rendering benchmark.

### Reproducing a pass

In the prplMesh repository the same files are under `tests/`, not `gen/tests/`.
Run the assertion tests before accessing a live lab:

```sh
node gen/tests/test-room-feature-acceptance.js
node --check gen/tests/room-feature-acceptance.js
```

Copy `room-feature-guest-audit.py` and `room-feature-rf-audit.py` into the
selected outer VM under `/tmp/`, retaining their filenames. The asymmetric
midpoint audit now runs automatically. Copy the **deployed guest's**
`gen/wmediumd/configurator/worlds/golden/*.world.json` (RDK), or
`wmediumd/configurator/worlds/golden/*.world.json` (prplMesh), into an evidence
directory. Do not silently substitute a newer checkout's generated rooms.
Use a unique output directory for each attempt; SSE evidence is append-only.

First restore the default room through the UI and wait for twenty clients.
Confirm no other operator owns a lease. Save `systemctl cat` and `systemctl show`
for the room service, then install the temporary runtime drop-in described
above by copying its original `ExecStart` with **only** the action cap changed.
Do not edit the persistent unit. After daemon-reload/restart, wait for healthy
twenty-client preflight and the expected cap before starting the browser.
If startup fails, preserve its journal and recovery record; do not blindly
delete the RF ownership journal or restart native components.

Example RDK invocation from a machine that can SSH to the LXD host:

```sh
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright-core
export CHROMIUM_PATH=/absolute/path/to/chromium/chrome
node gen/tests/room-feature-acceptance.js --yes-act --flavor rdk \
  --host rev140 --vm rdkeasymesh-20-0908 \
  --room-url http://192.168.2.140:48891/ \
  --topology-url http://192.168.2.140:48889/ \
  --worlds /absolute/path/to/deployed-goldens --output /absolute/path/to/new-results \
  --observer-cpus 12,13 --native-audits 1
node gen/tests/room-feature-report.js /absolute/path/to/new-results \
  /absolute/path/to/deployed-goldens > audited-summary.json
```

In parallel use `--flavor prpl --host rev150 --vm prplmesh-20-0908`, room port
18891 and topology port 8091, and a separate observer CPU set such as `14,15`.
Choose valid CPU IDs for your observer host. `--observer-cpus` restricts only
owned GPU-process threads, before lab page load, and records the restriction.
`--native-audits 1` samples selected clients' kernel associations during
movement/final phases; it does not issue scans or candidate queries.
Omitting `--world` selects the whole live catalog;
repeat `--world ROOM_ID` only for explicitly labelled targeted reproductions.
The report helper adds an independent rendered-parent audit and aggregates
submitted actions without double-counting their preceding requested events.
An absent native timing field is reported as unavailable, not zero.

Always remove only the named temporary drop-in, daemon-reload, restore the
original room service and verify default twenty-client paused state again.
Stop the owned host samplers. A nonzero test exit still requires cleanup and
reporting; it is not permission to discard failed-room evidence.

Record JSON per room, compact sampled JSONL, selected SSE JSONL, world hashes,
browser screenshots and a final Markdown matrix. Report load and post-motion
convergence as separate pass/fail columns, playback/presence correctness,
handover verification counts, p50/p95/max times and unresolved failures.
Do not discard failed rooms from performance statistics: report timed-out cases
as censored failures, not as zero latency or omitted successes.

The two machines have different CPUs and thermal behaviour. rev140 previously
showed thermal throttling, and the browser observer runs on rev150 outside its
lab VM. Capture host temperatures, throttling counters, CPU and pressure before,
during and after testing. These results describe these deployments; they cannot
establish an intrinsic RDK-versus-prplMesh speed ranking. No long-term stability
or Windows/VirtualBox qualification is implied.

## Results

Execution results will be recorded in the companion
`room-feature-results-0908.md`, with the exact evidence directory and any
test-harness corrections/repeated cases disclosed.
