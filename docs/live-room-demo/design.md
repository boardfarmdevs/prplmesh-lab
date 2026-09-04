# Live prplMesh room demo design

## Boundaries

The implementation duplicates the RDK room-demo presentation layer for this
release. The UI, HTTP paths, event schemas, evidence schemas, world and
narrative remain identical. Only platform adapters and fixed bindings differ.

```text
Golden World -> wmdcfg Runner -> wmediumd -> hwsim
                      |                         |
                      | clock/events            v
                      |                  prplMesh + clients
                      |                         |
                      v                         v
                 EventStore <- PrplMeshObserver/NBAPI
                      ^             |
                      |             v
                  viewer       threshold policy
                                      |
                              optional NBAPI BTM
```

The Runner is authoritative for scenario time, applied generations and RF
restoration. `EventStore` centrally sequences Runner, telemetry, traffic,
health, narrative, optimizer, action and verification events. The HTTP server
only reads that state and serves the vendored viewer assets.

## Platform seam

RDK uses its controller HTTP API and actuator. prpl uses:

- `PrplMeshObserver` over the loopback NBAPI topology adapter on port 8092;
- `PrplMeshCandidateProvider` for `AddUnassociatedStation`,
  `UpdateUnassociatedStationsStats` and `UnassociatedSTA` results;
- `scripts/steer-client.sh --request-only` for the NBAPI `BTMRequest`; and
- the isolated prpl data-plane target `192.168.77.1`.

The provider accepts a client selector so the room transaction measures only
the hero. This prevents a presentation cycle from registering every client on
every compatible radio while preserving the normal optimizer API.

## Identity model

Three identities must not be conflated:

| Namespace | Hero value |
| --- | --- |
| container | `prpl-client-03` |
| controller-facing STA MAC / UI | `02:00:00:10:02:00` / `sta-02` |
| permanent hwsim radio | discovered `42:...` identity |

World roles bind to containers. Controller observations match `station_mac`,
while wmediumd updates use the permanent/transmit identities produced by the
configurator. AP associations map to stable world geometry through discovered
BSSID ownership, with NBAPI device-name fallback.

## Authority modes

`stimulus` starts no optimizer. `recommend` evaluates policy but converts a
steer decision into retained recommendation state. `act` has an explicit
confirmation, action window and maximum of one attempt. The actuator returns
after the controller accepts the request; `OutcomeVerifier` independently
polls a passive prpl observer and checks hero traffic.

No mode allows the viewer to mutate the lab. No optimizer path writes RF.

## Failure and evidence model

Preflight must prove exact topology/cohort counts, hero SSID/band/metric,
traffic and wmediumd capability before applying a generation. Runner updates
are read back before events are published. Touched pair/frequency values are
captured and restored in `finally`; restoration is read back. Postflight uses
the normal configurator health contract.

Unexpected worker exceptions are fatal and retained. Bounded transient network
and health sampling failures are warnings, but do not substitute a successful
final gate. Every attempt writes summaries and a SHA-256 file index. Completed
evidence can instantiate the same store without live lab access.

## Packaging

The 0904 importer creates a `room-demo-viewer` NAT proxy at outer port 18891
to guest port 8891 alongside the existing Console and Controller UI proxies.
The server stays operator-controlled and is not a boot service. Release
metadata records the default port, and import tests prove proxy creation occurs
only after the VM agent, guest IP, nested LXD and profile selection are ready.

Future commonization should move the viewer, event store, HTTP server and
schema tests into a shared package. Until then, repository-local duplication
keeps each thin archive complete and independently reproducible.
