# Current prplMesh lab

Reviewed 14 September 2026. This is a deployment/release summary, not a live
health monitor. Use [operations](operations.md) to check runtime health.

## Identity

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0913-clean` |
| Canonical checkout | `rev150:/home/rev/git/prplmesh-lab-0913-clean` |
| Deployed VM | `rev150:prplmesh-0913`, accepted from the exact 0913 thin tar |
| Packaged source | `9a2dd2d`, including RF-bound candidates and channel-aware registration reuse |
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
provisioning, tri-band topology, representative private-5-GHz/IoT-6-GHz BTM,
traffic from all 100 clients, and 50-client, 5-to-6-GHz and 10-client room playback.
Default-20 restoration also passes. Initial provisioning/acceptance took
29 minutes 12 seconds on this host, not the time needed to switch rooms.
The addresses below target that imported VM. Inner/outer monitoring and
post-install traffic/readiness pass. The stopped pre-refresh lab VM is retired;
the 0913 thin builder remains stopped and available.

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

Both rev150 and rev140 mirror the accepted download
`/home/rev/releases/0913/prplmesh-0913-thin.tar`, with its adjacent
`.sha256`, `prpl-0913-acceptance.json` and checksummed acceptance evidence.
The tar's source is `9a2dd2d`; its SHA-256 begins `c294a503`. It is imported
and tested without repacking. The previous `aacc9f3` tar and its original
acceptance/evidence are preserved under `previous/prpl-aacc9f3/`.
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
Thin-import evidence is in `/home/rev/releases/0913/evidence/prpl-0913-final/`.
The refreshed source catalog passes 18/18 rooms but retains one transient
traffic-verification failure among 145 submissions. The focused follow-up
passes 30/30 actions; the exact-tar three-room run passes 42/42. See
[performance and failure attribution](../reference/testing/performance.md#0913-rf-cache-qualification)
for the retained failure and timing outlier, rather than treating room passes
as a claim that every individual action succeeded.

Budget at least 200 GiB of free backing storage for a new import, plus space
for retained VMs/exports. A compressed thin download can allocate the full
160-GiB VM disk. The first refresh import hit host ENOSPC; the identical tar
passed after the stopped rollback was privately archived and its VM removed.
This was host capacity exhaustion, not a native RF or steering failure.

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
- Candidate caches and in-flight results are bound to committed RF changes per
  client. Moving a client invalidates its comparisons; moving an AP invalidates
  all affected comparisons. Action submission checks the same RF identity.
  This repair is included in the accepted refreshed thin tar.
- Native candidate-registration reuse is also scoped to each station's channel
  and operating class. The controller has one current query-channel context per
  station; returning to an earlier band must register it again rather than reuse
  historical per-radio registrations. Warm, unchanged registrations still reuse
  the bounded parallel collector. This repair also passes the fifty-client
  movement/default-room restoration diagnostic and is included in the tar.
- Inner/outer Grafana measures container and VM guest resources, not physical
  host cooling or subsecond steering performance.
- RDK/prpl timings on different hosts are deployment results, not an intrinsic
  stack ranking. Keep observer load and thermal evidence with measurements.
- [Neighbor-network rooms](../reference/proposals/neighbor-rooms/design.md)
  remain proposed.

Use [room acceptance](../reference/testing/room-acceptance.md) for fresh claims.
