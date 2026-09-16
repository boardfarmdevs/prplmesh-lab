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

### Native backhaul roaming (0916 qualification)

Native patch `0025-native-controller-backhaul-roaming.patch` adds a controller
task and a connected-STA scan provider. This is native prpl policy, separate
from the external client optimizer. It is under bounded live qualification;
compilation alone does not qualify the release or any room.

The controller requests independent receiver scans every five seconds through
prpl vendor-specific 1905 messages. Each request has a task ID, round sequence,
agent and radio identity; responses must arrive within four seconds. The STA
uses `SCAN TYPE=ONLY` on its actual connected frequency, waits for the native
completion event, then reads `SCAN_RESULTS` and each BSS's native age. Entries
older than two seconds, malformed RSSI, a changed connection, unavailable scans
or more than 64 entries are not eligible. Scanning does not initiate an
autonomous supplicant roam. No coordinates, world IDs, SNR-matrix queries or
invented link measurements participate in this policy.

The current and candidate links use received RSSI from the same STA receiver.
Only known, enabled backhaul BSSes on the current channel/operating class and
SSID are candidates. Controller topology must agree with the measured current
parent, STA and radio. The task walks the target's ancestors to the gateway,
rejecting self/descendant targets, cycles, unknown/disconnected parents and
missing or expired wireless-link observations. Non-gateway wired paths without
a qualified link model are conservatively ineligible.

Selection requires at least **6 dB local-link improvement**, candidate RSSI at
least −80 dBm, and a non-degrading root-path bottleneck. An extra hop is allowed
only if the bottleneck improves. Thus an 11→26 dB local improvement via a relay
whose upstream link is 13 dB can qualify: requiring another 6 dB improvement
of the whole path would incorrectly reject it. This example explains the
policy; the implementation contains no scenario identities or MAC constants.

A parent must dwell for ten seconds, and the same eligible target must occur
in at least two distinct fresh rounds spanning four seconds. One topology-
changing request is outstanding at a time to prevent simultaneous reciprocal
reparenting; measurements continue independently. The controller sends a
standard EasyMesh **Backhaul Steering Request to the moving agent**, not its
old AP and not a room-side `wpa_cli` command. The native agent uses its existing
target scan/ROAM flow. Success requires a new receiver observation and matching
rooted controller topology; the matching native response is also recorded. A lost response
does not hide a later physically verified target association. A command
acknowledgment alone is not convergence. The native agent publishes its actual
connected parent immediately; the controller refreshes native source/target
topology while verification is pending.

The native NL80211 receiver updates the active supplicant network's BSSID to
the controller-selected target before `ROAM`. Leaving its old startup/recovery
pin causes WPA's four-way handshake to reject the new AP with "No SSID info
found", despite a successful association. A rejected ROAM command restores the
previous pin; the HAL does not report the target as connected before a native
connection/status event. This is native steering actuation, not an external
room-selected parent or autonomous background roaming.

Successful handover has a 20-second cooldown. Pre-send failures back off for
20/40/60 seconds. A sent request still unresolved after 15 seconds retains the
topology reservation: no different reparent operation can use an uncertain
ancestry. At most three same-target sends, separated by at least 35 seconds,
are allowed while fresh receiver identity, original parent and native policy
still qualify. Timeout or a negative response does not prove that a delayed
native operation cannot complete. Measurements continue while reserved.
A native receiver completion receipt records the MID and target only after an
actual matching connection event, with a new completion generation to reject
old receipts even after MID reuse. A fresh identity-matched scan carrying that
receipt plus a currently rooted native topology can release a reservation when
the target was reached and subsequently lost during independent recovery.
That outcome is logged as `completed_then_recovered`, not current-target success.
No timeout, command acceptance, old scan or uncorrelated receipt suffices.
Native disconnect/reconnect recovery remains available. Logs use
`native_backhaul_roaming observation`, `request` and `complete` and include
the measured RSSI, source/target, request ID and verified elapsed time.

The patch also corrects native topology's radio lookup to use the backhaul STA
MAC rather than its parent's BSSID, preserves the steering response MID, and
captures the timeout callback's target by value instead of a dangling local
reference. Providers without the fresh-scan HAL extension return unavailable.
Hostapd patch `0003-report-multi-ap-role-without-wps.patch` reports its configured
`multi_ap` value even when WPS is not compiled. Without it, prpl incorrectly
labels backhaul-only BSSes as fronthaul and native eligibility fails closed.
The prpl observation extension requires matching native controller/agent builds;
it is not advertised as a vendor-neutral measurement protocol or certification.

### Native recovery safety

Controller-only DFS does not govern legacy disconnect/reconnect selection.
Native scan requests therefore also carry actual controller BSS/agent/parent/
backhaul-STA identities, bounded to 48 backhaul BSSes. Receiver recovery combines
that graph with its current AP-associated station list: local child attachments
override older controller parent entries. Self, currently attached children,
known descendants, cycles and unknown BSS identities are rejected. A child
that has physically left is not indefinitely barred by an old direct-child
entry. This cached recovery guard does not assert that unknown ancestry is
currently rooted; actual controller communication remains required.

Missing optional scan requests do not prove upstream loss. Positive native
unicast contact from the expected controller preserves reachability. After
15 seconds without native control contact, the manager sends the existing
Higher Layer Data / 1905 ACK keepalive, with independent MIDs. Only three
actually sent, unanswered probes spaced two seconds apart permit recovery;
local send failure is not remote-loss evidence. Recovery briefly excludes its
old parent for five seconds and prefers a freshly received gateway BSS of at
least −80 dBm when available. It does not disable fronthaul APs, invent RSSI,
or consult room data. Controller radio recreation triggers bounded native
Backhaul STA Capability Query and Topology Query rediscovery, never a guessed
radio identity or indefinitely disabled sampling.
Managed recovery uses fresh native BSS ages and never bypasses its guard by
falling back to an unconstrained hidden-network association. This addresses
orphaned links after root loss, not an external room-side reconnect service.
An expected disconnect is consumed only for its actual old BSSID within five
seconds, so the asynchronous HAL event cannot restart the native manager while
its recovery scan is starting. A newly connected link receives 15 seconds to
reestablish controller communication; this grace does not assert a rooted path.

Native topology queries also reconcile unchanged client associations after a
backhaul outage. An agent can correctly retain a client while the controller
removes its device/BSS or marks that station disconnected; the old association
age must not permanently prevent same-owner restoration. Recovery requires a
matching native query MID and source/AL identity, a one-shot response within
five seconds, and a query sent after the station's last ownership event. Only
the recorded BSSID can restore a disconnected or missing-data-model station.
Unsolicited, replayed, expired and pre-event responses cannot use this exception;
association-age protection still rejects older cross-AP ownership. Successful
restoration advances the ownership fence without synthetic disconnects or roams.

### External client protection

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
