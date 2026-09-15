# Room coordination and authority

[Room reference](README.md)

The browser submits control intent; the room conductor owns the live session.
The configurator runner is the single RF writer. It compiles world positions,
walls, directional gains and presence into atomic wmediumd changes, reads them
back, and publishes the committed revision/environment epoch. The native stack
and station software—not the scene graph—own association.

## State and observation

- Playback publishes all role positions/presence and the clock in one commit.
  Loading resets playback/overrides and applies the initial world immediately.
- The fixed pool is not resized. Presence transitions disconnect/reconnect
  the affected roles even when the calculated RF matrix needs no change.
- Candidate collection, decisions, submission and verification retain correlated
  action IDs, timestamps, RF epoch and native operation timings.
- Superseded observations are discarded. A missing roster member or incomplete
  fresh candidate coverage remains visible; it cannot be hidden to claim that
  the whole fleet converged.
- Passive serving-state/traffic observation continues without using geometry
  as a secret native-metrics oracle. Simulated measurements stay labeled.

RDK uses controller HTTP APIs; prplMesh uses native NBAPI via its local adapter.
Whole-second prpl candidate timestamps can require a recorded wait until the
baseline second ends. RDK native command admission and response timeouts remain
a real constraint. Neither backend has a zero-outside-stack-latency guarantee.

## Select one authority

| Room CLI mode | Client steering | Backhaul |
| --- | --- | --- |
| `interactive --mode act --yes-act --profiling` | External policy, unassisted native BTM | Startup RF protected |
| `interactive --mode stimulus --profiling` | No external client policy/candidate requests | Startup RF protected |
| `interactive --mode stimulus --profiling --model-backhaul` | No external client policy | AP-to-AP RF follows world |

The CLI entry point is `demo/room-demo`; inspect `--help` for all
options before replacing a service's command. These CLI modes are distinct from
the browser's default URL. Serving-state and traffic observations remain active.

`--model-backhaul` is restricted to stimulus profiling. It does not add a
backhaul parent-selection algorithm; weak paths can disconnect nodes. Do not
silently restore a star to make such a test pass. An assisted backhaul demo
must be labeled separately from native backhaul-policy evaluation.

## Steering protection

Interactive automatic steering has no default lifetime request cap. The installed
service uses `--steering-rate-limit 300`: at most 300 submissions in any rolling
60 seconds, with at least five seconds between submissions to the same client.
Admission is atomic across concurrent batches. In-flight requests, native
verification, policy cooldowns and failure backoff remain in force; this is
external lab protection, not a change to the native EasyMesh implementation.

Only the affected client pauses after three consecutive terminal failures within
180 seconds, or before a fourth alternating A→B/B→A request within 60 seconds
under unchanged RF. Successful verification resets its failure streak.
Relevant client/AP RF changes clear that client's stale failure/oscillation
history; unrelated client movement does not. Measurements and other eligible
clients continue. A full request window recovers automatically.

**Resume steering**, beside External optimizer, clears client protection pauses.
It does not restart the room or reset positions, presence, playback, RF,
lifetime counters, cooldowns or the rolling window. Loading a world clears old
world-specific pauses but retains rate accounting. Preview, replay and
observation-only sessions cannot resume steering. Explicit `--max-actions N`
remains available for deliberately finite runs; Resume does not bypass it.

`GET /api/demo/optimizer/safety` reports the current guard without actuation.
`POST /api/demo/optimizer/resume` requires the browser control lease, same-origin
request, world `If-Match` revision, unique `command_id` and the GET response's
`expected_pause_revision`. Duplicate command IDs return the original response
without rearming a later pause. A changed pause revision returns 409 for review.
Safety revisions protect HTTP/SSE state from older evaluations.

## Recovery and bounded evidence

A checksummed journal records touched RF state, daemon/generation ownership
and stable radio/container identities. Restore only if those still match.
Recovery does not delete an incompatible journal or blindly restart native
services. After rejoining, require health and real client traffic before ready.

Interactive evidence uses a bounded asynchronous writer and bounded history.
Overflow, disk errors or expired history are explicit qualification failures;
a partial tail is not a complete replay. SSE cursor expiry triggers resync.
HTTP/SSE capacity is bounded so a slow observer cannot own the control loop.

Per-run bounds do not clean old run directories or unlimited user recordings.
Archive/delete completed evidence under an explicit retention policy. Never
ship installed secrets, private monitoring backups or raw credentials.

See [room acceptance](../testing/room-acceptance.md) for independent physical,
native and browser checks; see [performance](../testing/performance.md) before
attributing collection or display delay to native steering.
