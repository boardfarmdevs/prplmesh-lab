# prplMesh lab deployment

The 0829 release supports the same accepted controller, four-Agent and
20-client profile in two execution models. The EasyMesh processes always run
in LXD containers; the only choice is whether those containers run directly
on the host or inside a portable LXD virtual machine.

| Model | Artifact or input | Normal entry point | Use when |
|---|---|---|---|
| Bare metal | source release plus runtime archives | `scripts/install-from-artifacts.sh` | Linux 7 is already installed on a dedicated host |
| LXD VM | portable LXD backup | `deploy/lxd-vm/import.sh` | the outer host already uses LXD |

All three require x86-64 hardware virtualization. Bare metal and the guest
images use Ubuntu 24.04 and Linux 7.0. The VM profiles allocate 6 vCPUs, 8 GiB
RAM and an 80 GiB sparse disk. Four vCPUs work for functional use but make
cold onboarding and optimizer candidate collection materially slower.

The appliance guest owns its complete repository at `/opt/prplmesh-lab` and
starts `prplmesh-lab.service` at boot. That service reconstructs the radio
pool, wmediumd, controller, Agents, clients, NBAPI topology adapter and
Controller UI. It does not rely on a directory mounted from the packaging
host.

The two browser surfaces are:

- `8090`: raw NBAPI topology adapter;
- `8091`: EasyMesh Controller UI.

Host bind addresses and host ports are deployment settings, not image
identity. They are selected during LXD import.

See the model-specific procedures:

- [bare metal](bare-metal/README.md)
- [LXD VM](lxd-vm/README.md)

Release engineering uses `package-source.sh` and `lxd-vm/package.sh`. Every
emitted artifact has the `0829` release tag, source commit, and a sibling
SHA-256 file.

VirtualBox and Vagrant are not supported deployment dependencies. Old box
artifacts remain reproducible from earlier Git history, but are not part of
the current release or acceptance matrix.

Userspace wmediumd is the appliance default. The experimental kernel medium
and bounded overlap startup are described in
[Medium backends](../docs/medium-backends.md). Backend selection belongs in
`/etc/default/prplmesh-lab`; it does not require a different appliance image.
