# Current prplMesh lab

Reviewed 13 September 2026. This is a deployment/release summary, not a live
health monitor. Use [operations](operations.md) to check runtime health.

## Identity

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0913-clean` |
| Canonical checkout | `rev150:/home/rev/git/prplmesh-lab-0913-clean` |
| Qualification VM | `rev150:prplmesh-0913` (not yet release-accepted) |
| Last accepted VM | `rev150:prplmesh-20-0908`, stopped for rollback |
| Guest checkout | `/opt/prplmesh-lab` |
| Native prplMesh | 6.0.0, `2e153c7e00cbcab6b8ee35082f494a364e23f018` |
| Radio host | Ubuntu 24.04 / Linux 7, userspace wmediumd |
| Fixed pool | 100 clients; default room selects 20 online; five mesh containers / six logical roles |
| RDK peer | Independent repository and VM on rev140 |

The default room selects ten private and ten IoT clients. The unified appliance
has 120 permanent hwsim radios. Room presence does not resize the container pool.
Outer VM autostart is disabled; starting the VM starts its lab and room.

## Browser addresses

0913 is being qualified from the new canonical checkout. It uses one
100-client-capacity appliance, a default room with 20 online, and the new
`fifty-client-counter-roam` room with 50 online. Native builds have completed;
room ownership/convergence failures still block release packaging. There is
no accepted 0913 thin tar yet. The addresses below now target the qualification
VM and may be unavailable while it rebuilds or restarts.

| View | rev150 prplMesh |
| --- | --- |
| Live room | <http://192.168.2.150:18891/> |
| Network topology | <http://192.168.2.150:8091/> |
| wmediumd console | <http://192.168.2.150:8090/> |
| Inner LXD UI | Planned: <https://192.168.2.150:18892/ui/> |
| Grafana: inner containers and outer VM | Planned: <https://192.168.2.150:18893/> |

Monitoring is not installed on 0913 yet. Install it after sanitized export so
enrollment keys and passwords cannot enter release images. The old VM remains
stopped for rollback.

The native NBAPI normalization adapter stays on guest loopback port 8092.
The normal room URL needs no `?mode=`. LXD proxy devices survive reboots;
wait for guest services rather than manually recreating forwarding.
Management access requires a trusted LAN/VPN; monitoring requires login.

## Latest distribution and qualification

[Release information](release-notes.md) explains where historical records belong.

Both hosts mirror `/home/rev/releases/0909/prplmesh-0909-thin.tar` with adjacent
checksums, bundle metadata and acceptance evidence. **0909 is the latest
packaged download; 0908 is the stopped rollback VM.** A newer thin tar
is not proof of live redeployment or a native rebuild.

The 0909 thin import passed bounded native, BTM and twenty-client traffic
checks. RDK's Windows/VirtualBox box is a separate product; there is no prpl
VirtualBox deployment in this release.

The deployed laboratory HAL now preserves candidate socket identity across
interruptions; the topology adapter reads coherent client membership. The
pinned ubus dependency includes upstream reentrant-dispatch fixes. Cold
candidate registration is bounded to four concurrent calls for uncached targets.
Warm rounds reuse successful registrations. Internal
startup payloads include these repairs, unlike the unchanged
0909 release downloads. Current room, RF and native-to-browser qualifications
live in [room acceptance](../reference/testing/room-acceptance.md), not duplicated
release reports. A finite pass is not a zero-latency or soak guarantee.
Thin-import evidence remains in `/home/rev/releases/0909/evidence/`.

## Boundaries and open issues

- Native NBAPI metrics and BTM are live. The deployed client-policy authority
  is the external reference optimizer, not an asserted native autonomous policy.
- Profiling protects startup backhaul. A nearby extender does not automatically
  become another extender's parent; fixed star/branch/chain setup differs from
  adaptive backhaul optimization.
- Native whole-second candidate timestamps require an explicit freshness wait
  of up to one second when the baseline falls in the current second. Collection
  timeouts remain failures, not stale successful observations.
- UI symmetry/directional RF, atomic clock/pose and recovery fixes are implemented;
  preserve their regression coverage rather than repeating completed fix plans.
- Inner/outer Grafana measures container and VM guest resources, not physical
  host cooling or subsecond steering performance.
- RDK/prpl timings on different hosts are deployment results, not an intrinsic
  stack ranking. Keep observer load and thermal evidence with measurements.
- [Neighbor-network rooms](../reference/proposals/neighbor-rooms/design.md)
  remain proposed.

Use [room acceptance](../reference/testing/room-acceptance.md) for fresh claims.
