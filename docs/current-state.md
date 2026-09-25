# Current prplMesh lab

Reviewed 22 September 2026. This is the source/checkpoint and last-tested
deployment summary, not a live health monitor. See [operations](operations.md).

## Identity and release status

| Item | Current value |
| --- | --- |
| Canonical branch | `main` |
| Development checkout | `rev150:/home/rev/git/prplmesh-lab-0916-clean` |
| Last-tested build host checkout | `rev120:/home/rev/git/prplmesh-lab` |
| Last-tested VM | `rev120:demo-prpl` |
| Guest checkout | `/opt/prplmesh-lab` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, native prplMesh, userspace wmediumd |
| Fixed pool | 100 clients; five mesh containers / six displayed roles |
| Current classification | Development checkpoint; fresh-VM/full-suite acceptance pending |
| RDK peer | Separate repository; last-tested VM `rev140:demo-a` |

Default selects ten private and ten IoT clients. Room loading changes presence,
not permanent container/radio identities. Preserve disabled VM autostart.

## Qualification and remaining gaps

The ordinary catalog has passing evidence for **24 rooms across two runs**:
19/24 initially, followed by successful targeted reruns of all five failures.
The five failures came from re-entering the same user namespace in privileged
client containers; the checked-in fix skips that operation only when namespace
identity is verified. Browser fullscreen cleanup was also repaired. The original
failed report remains failed; this is not one all-green full-catalog run.

| Remaining gate | Last observation |
| --- | --- |
| Geometry branch formation | Scenario checks passed. |
| Geometry parent handover | Scenario checks passed. |
| Geometry isolation/recovery | Failed: Ext-4's reported 6 GHz inventory disappeared after isolation; room and Default recovery remained incomplete. |
| Guarded load steering | Passed with matching native BTM, 0.681-second native verification and post-steer receiver delivery. |
| Pressure veto / weak-signal rescue | No complete live proof; stimulus/ownership conditions did not qualify the required policy decision. |

After isolation, three clients still had native wireless links and successful
traffic, but were absent from the reported inventory. The exact native-model
versus adapter cause is unresolved. A subsequent **manual Ext-4 native-process
restart** is recovery work, not a passing isolation test. The last observed room
restart failed its inactive-client preflight and reached the service restart
limit; do not assume the old room viewer is ready.

The earlier memory runaway remains repaired in the bounded follow-up:
controller RSS approximately 43–44 MiB, with zero growth during the 90-second
20-active-client measurement. This is not a new 100-client/long-duration memory
qualification. Keep native patches 0026–0031 and dependency provenance together.

See the [maintained RF qualification record](../reference/radio/rf-property-coverage.md#room-catalog-qualification-and-open-failures)
for exact reports and evidence boundaries. The `rf-actions` tier is included in
`all`; incomplete or failed qualification remains nonzero. Optional live
visibility/priority modes are deferred; offline medium selftests are not live
mode acceptance.

## Rebuild checkpoint

Pull the current branch into a **clean** checkout and regenerate the native
artifacts before building the new VM. Reuse the documented native build cache,
but do not substitute old runtime archives merely because their checksum is
valid. Native artifacts must include the current memory/model repairs and match
their embedded provenance. **prpl does not use BPI images or Yocto.**

Follow [build native artifacts, then VM](build/README.md), then
[the test suite](test/README.md). Check the fresh 100-client baseline and bounded
controller-memory gate before treating broader room results as qualification.
Preserve the old VM stopped and keep its failed evidence until the replacement
passes. A fresh build tests reproducibility; it does not automatically repair
the known isolation/reporting issue.

This checkpoint creates no thin archive or release promotion. The optional
Tailscale session gateway was added to the RDK repository only; no remote
access service was installed on this prpl host.

## Access and distribution

These are the last-tested VM's configured addresses, not a health promise:

| View | prplMesh |
| --- | --- |
| Live room | <http://192.168.2.120:49428/> |
| Network topology | <http://192.168.2.120:49426/> |
| Console NG | <http://192.168.2.120:49427/> |

The room endpoint may remain unavailable after the failed recovery described
above. New VM names receive independent ports. Proxies survive VM restart;
use a trusted LAN/VPN. See [monitoring](../reference/observability/monitoring.md)
for nested containers and the outer VM.

Older 0916 downloads under `/home/rev/releases/0916/` are separately identified
candidates, not builds of this checkpoint. Original archive manifests retain
their mixed-source/native-artifact provenance and fresh-import limitations;
new source commits do not rewrite those receipts.
See [release information](release-notes.md). prpl has no VirtualBox distribution.
Allow the [documented build/import space](build/README.md), rather than using
compressed archive size as a storage estimate.

## Boundaries

- The external optimizer supplies client policy; native NBAPI/BTM provide
  observations and actuation, not native autonomous client policy.
- Most rooms protect startup backhaul. Geometry rooms change AP-to-AP RF,
  not prescribed parent configuration.
- Candidates need advancing native timestamps and valid identity/RF epochs;
  retries do not make stale data fresh.
- Convergence includes native membership, ownership, measurements and traffic.
- Guest resource metrics do not measure host cooling or subsecond roam latency.
- [Neighbor-network rooms](../reference/proposals/neighbor-rooms/design.md)
  remain proposed.
