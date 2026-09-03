# prplMesh lab deployment

The current release supports one controller, four Agents, and immutable 20-,
50-, or 100-client profiles in two execution models. The EasyMesh processes
always run in LXD containers; the only choice is whether those containers run
directly on the host or inside a portable LXD virtual machine.

| Model | Artifact or input | Normal entry point | Use when |
|---|---|---|---|
| Bare metal | source release plus runtime archives | `scripts/install-from-artifacts.sh` | Linux 7 is already installed on a dedicated host |
| LXD VM | portable LXD backup | `deploy/lxd-vm/import.sh` | the outer host already uses LXD |

Both require x86-64 hardware virtualization. Bare metal and the guest images
use Ubuntu 24.04 and Linux 7.0. Portable profiles allocate 6/8/12 vCPUs and
8/12/20 GiB RAM for 20/50/100 clients respectively. All use a 160 GiB sparse
disk; sparse capacity is not download size or immediate physical allocation.

The appliance guest owns its complete repository at `/opt/prplmesh-lab` and
starts `prplmesh-lab.service` at boot. That service reconstructs the radio
pool, wmediumd, controller, Agents, clients, internal NBAPI adapter, common
wmediumd Console and Controller UI. It does not rely on a directory mounted from the packaging
host.

The two browser surfaces are:

- `8090`: wmediumd Console, identical to the RDK lab;
- `8091`: EasyMesh Controller UI.

The NBAPI normalization adapter listens only on guest loopback port `8092`.

Host bind addresses and host ports are deployment settings, not image
identity. They are selected during LXD import.

See the model-specific procedures:

- [bare metal](bare-metal/README.md)
- [LXD VM](lxd-vm/README.md)

Release engineering uses `package-source.sh`, `lxd-vm/build.sh`, and
`lxd-vm/package.sh`. Every
emitted artifact has the `0831` release tag, source commit, and a sibling
SHA-256 file.

Userspace wmediumd and controller-first startup are the appliance defaults.
The experimental kernel medium and overlap mode are described in
[Medium backends](../docs/medium-backends.md). Backend selection belongs in
`/etc/default/prplmesh-lab`; it does not require a different appliance image.
