# The prplMesh lab's documents

[Repository](../README.md) · [Site](https://vcpe.dev/prplmesh-lab/)

The [site](https://vcpe.dev/prplmesh-lab/) has the system explorer and the room sandbox.
What both optimizer labs share is documented once, with its component: the RF medium,
lab monitoring and the neighbor-rooms proposal in
[easymesh-medium](https://vcpe.dev/easymesh-medium/); the optimizer, the room service
and room access in [easymesh-optimizer](https://vcpe.dev/easymesh-optimizer/). This
lab's documents are below.

| Document | Kind | What it covers |
| --- | --- | --- |
| [Current state](project/current-state.md) | project | the last-tested VM, its qualification, addresses and limits |
| [Architecture](concepts/architecture.md) | concept | the native stack and the radio host |
| [Build](guides/build.md) | guide | the native artifacts from the pinned sources, then a named VM |
| [Build and operate the VM](guides/build-vm.md) | guide | `deploy/lxd-vm/build.sh`: build, check, update, storage and clients |
| [Operations](guides/operations.md) | guide | install, start, stop and recover |
| [Room manual](guides/room-manual.md) | guide | the live room and the network topology |
| [Test suite](guides/test-suite.md) | guide | the test tiers and the host-side runner |
| [Software architecture](reference/software-architecture.md) | reference | prplMesh's processes, their interfaces and the lab's patches |
| [Controller UI](reference/controller-ui.md) | reference | the host's EasyMesh controller dashboard |
| [Topology adapter](reference/topology-adapter.md) | reference | the internal adapter from prplMesh's model to the dashboard and the optimizer |
| [Medium backends](reference/medium-backends.md) | reference | the userspace and kernel data paths and how the lab selects one |
| [Dynamic medium and optimizer](reference/dynamic-medium.md) | reference | driving the medium and the optimizer together in this lab |
| [Room catalog](reference/room-catalog.md) | reference | every room and what to watch in it |
| [Room acceptance](reference/room-acceptance.md) | reference | room correctness and convergence acceptance |
| [Room coordination](reference/room-coordination.md) | reference | the room service's authority, leases and recovery in this lab |
| [Performance](reference/performance.md) | reference | performance and failure attribution |
| [Controller memory](reference/controller-memory.md) | reference | the native controller's memory qualification |
| [RF qualification](records/rf-qualification.md) | record | the RF properties on native prplMesh: counter guard, ownership, load, the catalog |
| [Release information](records/release-notes.md) | record | what a VM is built from; shipped in a packaged VM |

Keep each subject in its owning document; put evidence (JSON, logs, screenshots)
beside the release or test artifacts, not here. Run
`python3 tests/test_documentation.py` before submitting documentation changes.
