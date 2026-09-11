# prplMesh virtual-radio lab

Run native prplMesh controller, agent and client software in an isolated
Ubuntu/Linux radio host with nested LXD, hwsim and multichannel wmediumd.
The room and topology interfaces match the RDK lab; native build, NBAPI metrics,
steering adapters and deployment remain independent.

**Start with the [documentation guide](docs/README.md).**

- [Current deployment, URLs, downloads and limits](docs/current-state.md)
- [Install or operate a lab](docs/operations.md)
- [Use the room and network topology](docs/live-room-demo/README.md)
- [Build from source](docs/from-scratch.md)
- [Technical reference by subsystem](reference/README.md)

Default room deployments retain twenty client containers, a controller with
colocated agent and four extenders: five mesh containers / six displayed roles.
The live prplMesh lab belongs on rev150, separately from RDK on rev140.
No screenshot or accepted BTM alone proves convergence; compare physical
association, native ownership, fresh measurements and traffic.
