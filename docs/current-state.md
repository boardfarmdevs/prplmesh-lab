# Current prplMesh lab

Reviewed 17 September 2026. This is a deployment summary, not a live health
monitor; use [operations](operations.md) for current service checks.

## Identity and release status

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0916-clean` |
| Canonical checkout | `rev150:/home/rev/git/prplmesh-lab-0916-clean` |
| Candidate appliance | `rev150:prplmesh-0916-repair-02` |
| Packaged source and clean medium build | `79c547e55f5385c32d9ab4673c5ce7b71ac51244` |
| Preserved native runtime archive | SHA-256 prefix `65a8ee22`; separate original build provenance |
| Original native build source | Dirty checkout based on `5c998803568467ce8c7a164b3074535bbccccec7` |
| Guest checkout | `/opt/prplmesh-lab` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, userspace wmediumd |
| Fixed pool | 100 clients; five mesh containers / six logical roles |
| Release classification | 0916 candidate with known issues; not newly full-catalog-qualified |
| RDK peer | Separate repository and appliance on rev140 |

The default room selects ten private and ten IoT clients. Loading a room does
not resize containers or radio identities. Outer VM autostart is disabled.
Documentation commits after the packaged source do not imply native rebuilds.

**The current appliance combines multiple build origins.** Its clean medium
build is not evidence that the native prplMesh archive was rebuilt from the
same clean source. Original native build records, approved source-inventory
differences and actual binary hashes remain authoritative.

## Qualification and remaining gaps

The latest normal lifecycle passes 105 containers and the independent audit of
exactly 100 unique clients, each receiving all three probe packets. Native
files and container identities remain unchanged. Default-20/frontend restoration
and the bounded zero-additional-medium-receive-drop observation pass.

Earlier native-runtime campaigns passed complete catalogs, including proactive
backhaul handover. **The latest combined source/medium has not completed a new
22-client-room + 3-geometry-room campaign.** This is a qualification gap, not a
claim that all current rooms pass or fail. Earlier passes are limited to their
recorded source/runtime.

An earlier thin candidate exhausted backing storage while reconstructing the
client pool. Template sanitation and capacity corrections are now included;
the old failed import is not acceptance of a new archive. Respect the import
storage guard: compressed download size does not represent expanded storage.

The owner requested completing known-issues packaging on 17 September without
further debugging. Failed evidence stays retained; no test gate is reclassified
as passing. Exact-archive fresh-import acceptance must have its own receipt.

Evidence on rev150 is under `/home/rev/work/release-0916/`, particularly:

- `prpl-native-roaming/medium-success-ack/lifecycle-02/`
- `prpl-native-roaming/medium-success-ack/combined-clean-build-draft.json`
- `evidence/prpl-native-roaming-release-input-4b5ce43-v1/build.json`

The combined record's filename is not a claim of a single clean native build.

## Access and distribution

Candidate forwarding is configured for these addresses. Packaging temporarily
stops services; an address is not a promise of current health.

| View | rev150 prplMesh |
| --- | --- |
| Live room | <http://192.168.2.150:19892/> |
| Network topology | <http://192.168.2.150:19891/> |
| wmediumd console | <http://192.168.2.150:19890/> |

Packaging alone does not promote production ports 18891/8091/8090 or enroll
monitoring on 18892/18893. See [monitoring](../reference/observability/monitoring.md)
for nested containers and the outer VM. The native adapter remains guest-loopback
8092. Room URLs need no `?mode=`. Proxies survive reboot; use a trusted LAN/VPN.

### Post-export appliance state

The 0916 export thinned and then restored the qualification appliance through
its normal fixed-100-client first-boot path. That restoration completed with
exit status zero on 17 September; `prplmesh-lab.service` is active and
`prplmesh-room-demo.service` is running. This confirms only post-export service
restoration, not fresh-import or full room-catalog acceptance.

The 0916 thin distribution belongs under `/home/rev/releases/0916/`. Adjacent
SHA-256 files, `release.json`, `KNOWN-ISSUES-0916.md` and packaging receipts
record exact inputs, checks and outstanding gaps. Presence of a tar does not
establish fresh-import, room-catalog or monitoring acceptance.
See [release information](release-notes.md); prpl has no VirtualBox distribution.

The original stopped 0913 VM was retired after verifying a cold rollback on
rev140. That archive remains at
`/home/rev/work/release-0916/private-rollback/prpl-0913-before-0916/cold-rollback.tar.gz`;
its SHA-256 starts `14adffcaa55f`. The verified rollback-check VM is stopped
with autostart disabled. Redundant rev150 release/backup files were removed only
after verifying retained rev140 copies; unique evidence remains.

A fresh import needs at least 200 GiB free backing storage plus retained
VM/export space; a compressed download may allocate the entire 160-GiB disk.

## Boundaries

- The external reference optimizer supplies client policy; native NBAPI/BTM
  provide observations and actuation. This is not native autonomous client policy.
- Most rooms protect startup backhaul. Three geometry rooms change AP-to-AP RF,
  not parent configuration. Native proactive steering and loss recovery differ.
- Candidate metrics require native timestamp advancement, correct radio identity
  and current RF/association epochs. Retrying must not make stale data fresh.
- Convergence includes membership, native ownership, fresh candidates and traffic;
  an accepted BTM request or green badge alone is insufficient.
- Keep cooling and observer load separately attributed. Guest Grafana metrics do
  not measure physical-host totals or subsecond steering performance.
- [Neighbor-network rooms](../reference/proposals/neighbor-rooms/design.md)
  remain proposed.
