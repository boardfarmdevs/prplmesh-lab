# Current prplMesh lab

Reviewed 13 September 2026. This is a deployment/release summary, not a live
health monitor. Use [operations](operations.md) to check runtime health.

## Identity

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0913-clean` |
| Canonical checkout | `rev150:/home/rev/git/prplmesh-lab-0913-clean` |
| Deployed VM | `rev150:prplmesh-0913`, accepted from the exact 0913 thin tar |
| Guest checkout | `/opt/prplmesh-lab` |
| Native prplMesh | 6.0.0, `2e153c7e00cbcab6b8ee35082f494a364e23f018` |
| Radio host | Ubuntu 24.04 / Linux 7, userspace wmediumd |
| Fixed pool | 100 clients; default room selects 20 online; five mesh containers / six logical roles |
| RDK peer | Independent repository and VM on rev140 |

The default room selects ten private and ten IoT clients. The unified appliance
has 120 permanent hwsim radios. Room presence does not resize the container pool.
Outer VM autostart is disabled; starting the VM starts its lab and room.

## Browser addresses

0913 is deployed from the new canonical checkout. It uses one
100-client-capacity appliance, a default room with 20 online, and the new
`fifty-client-counter-roam` room with 50 online. Native builds and all eighteen
room tests pass. The exact sanitized thin tar also passed fresh 105-container
provisioning, native two-SSID/tri-band BTM, traffic from all 100 clients, 50- and
10-client room playback, and default-20 restoration. The addresses below target
that imported VM. Inner/outer monitoring and post-install default-room readiness
also pass; the obsolete 0908 lab VM and its outer-metrics certificate are removed.

| View | rev150 prplMesh |
| --- | --- |
| Live room | <http://192.168.2.150:18891/> |
| Network topology | <http://192.168.2.150:8091/> |
| wmediumd console | <http://192.168.2.150:8090/> |
| Inner LXD UI | <https://192.168.2.150:18892/ui/> |
| Grafana: inner containers and outer VM | <https://192.168.2.150:18893/> |

Monitoring is installed after accepted sanitized export so enrollment keys
and passwords cannot enter release images. Prometheus scrapes all 105 nested
containers and the outer `prplmesh-0913` VM; both provisioned Grafana dashboards
are available. Follow [monitoring](../reference/observability/monitoring.md) for
browser enrollment and credentials.

The native NBAPI normalization adapter stays on guest loopback port 8092.
The normal room URL needs no `?mode=`. LXD proxy devices survive reboots;
wait for guest services rather than manually recreating forwarding.
Management access requires a trusted LAN/VPN; monitoring requires login.

## Latest distribution and qualification

[Release information](release-notes.md) explains where historical records belong.

The accepted download is
`rev150:/home/rev/releases/0913/prplmesh-0913-thin.tar`, with its adjacent
`.sha256`, `prpl-0913-acceptance.json` and checksummed acceptance evidence.
The tar's source is `aacc9f3`; it is imported and tested without repacking.
Its embedded `status: candidate` records creation-time status; the adjacent
acceptance record identifies and accepts the exact immutable outer-tar hash.
RDK's Windows/VirtualBox box is a separate product; there is no prpl VirtualBox
deployment in this release. Older downloads remain historical artifacts.

The deployed laboratory HAL now preserves candidate socket identity across
interruptions; the topology adapter reads coherent client membership. The
pinned ubus dependency includes upstream reentrant-dispatch fixes. Cold
candidate registration is bounded to four concurrent calls for uncached targets.
Warm rounds reuse successful registrations. The 0913 native controller defers
collection until a registration cohort is complete, rather than querying the
growing registry after every addition. Privileged local ubus calls use a
generation-checked controller namespace instead of per-query LXD exec sessions.
The 0913 thin's startup payloads include these repairs. Current room, RF and native-to-browser qualifications
live in [room acceptance](../reference/testing/room-acceptance.md), not duplicated
release reports. A finite pass is not a zero-latency or soak guarantee.
Thin-import evidence is in `/home/rev/releases/0913/evidence/`.

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
