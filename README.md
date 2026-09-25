# prplMesh virtual-radio lab

Run native prplMesh controller, agent and client software in an isolated
Ubuntu/Linux radio host with nested LXD, hwsim and multichannel wmediumd.
The room and topology interfaces match the RDK lab; native build, NBAPI metrics,
steering adapters and deployment remain independent.

<!-- labs block: the same in the four lab repositories -->
**Site:** <https://boardfarmdevs.github.io/prplmesh-lab/>. Part of the boardfarmdevs labs, which serve two
goals: the EasyMesh optimizer ([RDK EasyMesh](https://boardfarmdevs.github.io/meta-cmf-bananapi-vcpe/),
[prplMesh](https://boardfarmdevs.github.io/prplmesh-lab/)) and the OpenSync adapter
([EMOSA](https://boardfarmdevs.github.io/emosa-lab/), [OpenSync](https://boardfarmdevs.github.io/opensync-lab/)), on the way to one
EasyMesh system on wmediumd with native agents and OpenSync pods together.

**Start with the [documentation guide](docs/README.md).**

- [Current deployment, URLs, downloads and limits](docs/current-state.md)
- [Install or operate a lab](docs/operations.md)
- [Use the room and network topology](docs/live-room-demo/README.md)
- [Interactive architecture and room sandbox: build/publish](explorer/README.md)
- [Build artifacts, then a named VM](docs/build/README.md)
- [Test tiers and host-side runner](docs/test/README.md)
- [Technical reference by subsystem](reference/README.md)

One appliance retains 100 client containers; rooms select the online subset
(20 by default). A controller with colocated agent and four extenders provides
five mesh containers / six displayed roles.
The live prplMesh lab belongs on rev150, separately from RDK on rev140.
No screenshot or accepted BTM alone proves convergence; compare physical
association, native ownership, fresh measurements and traffic.
