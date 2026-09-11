# Current prplMesh lab

Reviewed 10 September 2026. This is a deployment/release summary, not a live
health monitor. Use [operations](operations.md) to check runtime health.

## Identity

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0908-clean` |
| Canonical checkout | `rev150:/home/rev/git/prplmesh-lab` |
| Production VM | `rev150:prplmesh-20-0908` |
| Guest checkout | `/opt/prplmesh-lab` |
| Native prplMesh | 6.0.0, `2e153c7e00cbcab6b8ee35082f494a364e23f018` |
| Radio host | Ubuntu 24.04 / Linux 7, userspace wmediumd |
| Default pool | Twenty clients; five mesh containers / six logical roles |
| RDK peer | Independent repository and VM on rev140 |

There are ten private and ten IoT clients. Forty permanent hwsim radios serve
the default profile. Room presence does not resize the container pool.
Outer VM autostart is disabled; starting the VM starts its lab and room.

## Browser addresses

| View | rev150 prplMesh |
| --- | --- |
| Live room | <http://192.168.2.150:18891/> |
| Network topology | <http://192.168.2.150:8091/> |
| wmediumd console | <http://192.168.2.150:8090/> |
| Inner LXD UI | <https://192.168.2.150:18892/ui/> |
| Grafana: inner containers and outer VM | <https://192.168.2.150:18893/> |

The native NBAPI normalization adapter stays on guest loopback port 8092.
The normal room URL needs no `?mode=`. LXD proxy devices survive reboots;
wait for guest services rather than manually recreating forwarding.
Management access requires a trusted LAN/VPN; monitoring requires login.

## Latest distribution and qualification

[Release information](release-notes.md) explains where historical records belong.

Both hosts mirror `/home/rev/releases/0909/prplmesh-0909-thin.tar` with adjacent
checksums, bundle metadata and acceptance evidence. **0909 is the latest
packaged download; production still uses the named 0908 VM.** A newer thin tar
is not proof of live redeployment or a native rebuild.

The 0909 thin import passed bounded native, BTM and twenty-client traffic
checks. RDK's Windows/VirtualBox box is a separate product; there is no prpl
VirtualBox deployment in this release.

The room improvement sweep exercised all fourteen rooms; prpl passed the
corrected room gates, but still recorded a native collection timeout and
superseded measurements. A finite pass is not a zero-latency or soak guarantee.
Detailed room evidence is in
`/home/rev/releases/0908/room-feature-improvements-20260909/`;
thin-import evidence is in `/home/rev/releases/0909/evidence/`.
Do not duplicate these reports as current manuals.

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
