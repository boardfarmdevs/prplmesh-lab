# Current prplMesh lab

[Documents](../README.md)

Reviewed 2 October 2026. This is the last-tested deployment, not a live health
monitor. See [operations](../guides/operations.md).

## Identity

| Item | Current value |
| --- | --- |
| Branch | `main` |
| Development and build checkout | `rev140:/home/rev/git/easymesh-labs/prplmesh-lab` (the easymesh-labs workspace) |
| Last-tested VM | `rev140:prpl-1002` (stopped while the RDK lab runs on rev140: one lab at a time) |
| Guest checkout | `/opt/prplmesh-lab` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, native prplMesh, userspace wmediumd from easymesh-medium (the `medium` submodule); the optimizer from easymesh-optimizer (the `optimizer` submodule) |
| Fixed pool | 100 clients; four Wi-Fi Agents and one wired Agent (`prpl-agent-05`, `extender_5`) |
| RDK peer | meta-cmf-bananapi-vcpe; last-tested VM `rev140:rdk-1002b` |

Default selects ten private and ten IoT clients. Room loading changes presence,
not permanent container or radio identities. Keep VM autostart disabled.

## Qualification

`prpl-1002` was built from scratch on rev140 on 2 October, from this repository as
it is after its cleanup, its native artifacts rebuilt. The expanded acceptance (NBAPI
steering, the 100-client data plane, process footprint) and the optimizer's dynamic
recommendation passed in the build; with the browser on rev150, readiness, five rooms
(`home-a-one-client-handover`, `band-upgrade-24-5`, `received-same-band-roam`,
`large-room-perimeter-counter-roam`, `traffic-quieter-ap`), `backhaul-wired-parent`
with its recovery hold and `fifty-client-counter-roam` passed. The full suite, the
catalog of 27 rooms included, last ran on the VM of 1 October. The VM takes no
automatic updates and no on-demand LXD install.

The controller's memory stays bounded (about 43 to 44 MiB RSS, no growth over a
90-second 20-client measurement); keep native patches 0026 to 0031 and the
dependency provenance together. Do not relax deadlines or treat retries as fresh
data to make a run green; the [RF qualification record](../records/rf-qualification.md)
holds the evidence and the attribution of past failures.

## Rebuild

Pull into a **clean** checkout and regenerate the native artifacts before building a
new VM: the [build guide](../guides/build.md), then [the test suite](../guides/test-suite.md).
Reuse the native build cache, but do not substitute old runtime archives because
their checksums are valid: the artifacts must carry the current repairs and match
their embedded provenance. **prplMesh does not use the Banana Pi images or Yocto.**
A change the lab runs from its checkout (the optimizer, the room service) moves an
accepted VM in place: `deploy/lxd-vm/build.sh update`. Keep old VMs stopped until
their replacements pass.

## Access

The last-tested VM's addresses, not a health promise:

| View | `prpl-1002` |
| --- | --- |
| Live room | <http://192.168.2.140:48582/> |
| Controller dashboard | <http://192.168.2.140:48580/> |
| Console NG | <http://192.168.2.140:48581/> |

Each new VM name receives its own ports. Proxies survive VM restarts; use a trusted
LAN or VPN. Lab monitoring (in [easymesh-medium](https://vcpe.dev/easymesh-medium/))
covers the nested containers and the outer VM. This lab has no remote-access gateway.

## Boundaries

- The external optimizer supplies client policy; native NBAPI and BTM provide
  observations and actuation, not native autonomous client policy.
- Most rooms protect startup backhaul. Geometry rooms change AP-to-AP RF, not a
  prescribed parent configuration.
- Candidates need advancing native timestamps and valid identity and RF epochs;
  retries do not make stale data fresh.
- Convergence includes native membership, ownership, measurements and traffic.
- Guest resource metrics do not measure host cooling or subsecond roam latency.
- Neighbor-network rooms (in [easymesh-medium](https://vcpe.dev/easymesh-medium/))
  remain proposed.
