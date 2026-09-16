# Current prplMesh lab

Reviewed 16 September 2026. This is a deployment summary, not a live health
monitor; use [operations](operations.md) for current service checks.

## Identity

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0916-clean` |
| Canonical checkout | `rev150:/home/rev/git/prplmesh-lab-0916-clean` |
| Running qualification VM | `rev150:prplmesh-0916`; fresh build, not released |
| Client-catalog / latest runtime source | `a9ee070` / `ccc97f4` |
| Guest checkout | `/opt/prplmesh-lab` |
| Native prplMesh | 6.0.0, `2e153c7e00cbcab6b8ee35082f494a364e23f018`, patches through 0024 |
| Platform | Ubuntu 24.04 / Linux 7 radio host, userspace wmediumd |
| Fixed pool | 100 clients; five mesh containers / six logical roles |
| Rollback | `prplmesh-0913` stopped; previous downloads retained |
| RDK peer | Independent repository and appliance on rev140 |

The default room selects ten private and ten IoT clients from the permanent
pool. Loading a room does not resize containers or radio identities.
Outer VM autostart is disabled; manually starting the VM starts its lab.

## Browser addresses

These temporary ports serve the running qualification VM:

| View | rev150 prplMesh |
| --- | --- |
| Live room | <http://192.168.2.150:19892/> |
| Network topology | <http://192.168.2.150:19891/> |
| wmediumd console | <http://192.168.2.150:19890/> |

Normal ports 18891/8091/8090 still target the stopped rollback, not the candidate.
Its monitoring endpoints 18892/18893 are not currently available. Monitoring
is not installed in the candidate: it follows accepted sanitized export so
enrollment credentials cannot enter release images. The supported setup covers
all 105 nested containers and the outer VM; see
[monitoring](../reference/observability/monitoring.md).

The native adapter stays on guest loopback 8092. Room URLs need no `?mode=`.
LXD proxy devices survive reboot; wait for guest services rather than recreating
forwarding. Management interfaces require a trusted LAN/VPN.

## Latest distribution and qualification

**0916 remains held; no thin tar is published and no older downloads removed.**
The earlier native build passes its 100-client baseline and **22/22** client
catalog. The new native proactive build passes **3/3 geometry rooms**, including
ext3→ext2→ext1 handover, strict rosters/kernel ownership, traffic, both views,
unchanged native identities and Default restoration. Native scans, rooted safety
and standard 1905 steering drive the moves, not external parent forcing.
Fresh full **22+3 qualification remains pending** on this combined build.

[Room acceptance](../reference/testing/room-acceptance.md#0916-release-recovery-checks)
records source identities, recovered failures, retries and remaining gates.
Native credentials/scans, renewed NBAPI paths, controller identity and bounded
lost-query retries are repaired without external forced parent changes.

The recorded accepted rollback is
`/home/rev/releases/0913/prplmesh-0913-thin.tar`, source `9a2dd2d`,
SHA-256 prefix `c294a503`, mirrored on rev140/rev150. Its adjacent SHA-256
and `prpl-0913-acceptance.json` identify the exact immutable archive. Historical
import/catalog evidence does not qualify the new build.
See [release information](release-notes.md); prpl has no VirtualBox distribution.

A fresh import needs at least 200 GiB free backing storage plus retained
VM/export space; a compressed download may allocate the entire 160-GiB disk.

## Boundaries and open issues

- The reference optimizer supplies client policy; native NBAPI and BTM provide
  observations and actuation. This does not assert native autonomous optimization.
- Most rooms protect startup backhaul. Three geometry rooms change AP-to-AP RF,
  not parent configuration. Native proactive steering and loss recovery are
  separate from the external client optimizer; see [native policy](../reference/rooms/architecture.md#native-backhaul-roaming-0916-qualification).
- Candidates require native timestamp advancement, correct radio identities
  and current RF/association epochs. Retries neither reuse stale values nor
  reset the original collection deadline.
- Strict convergence includes membership, physical/native ownership, fresh
  eligible candidates and traffic. An accepted BTM request alone is insufficient.
- Keep host cooling and observer load separate from native performance.
  Grafana guest metrics do not measure physical-host totals or subsecond steering.
- [Neighbor-network rooms](../reference/proposals/neighbor-rooms/design.md)
  remain proposed.
