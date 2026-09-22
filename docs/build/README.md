# Build a prplMesh lab

[Documentation home](../README.md) · [VM build](vm.md) · [Tests](../test/README.md)

Build native artifacts **first**, then construct an isolated LXD VM. Run every
command below on the outer Linux host, from this checkout unless noted.
No Yocto tree, BPI images, dated directory or named build server is required.
Upstream revisions are pinned in [manifests/lab.env](../../manifests/lab.env);
the checkout supplies reviewed dependency and radio patches. Keep that manifest
and patch set together. Do not substitute upstream `latest`.

## 1. Prepare the host

Use x86-64 Ubuntu **22.04 or 24.04**, hardware virtualization (`/dev/kvm`),
Internet access, at least eight available cores and 24 GiB host RAM. The VM
uses eight vCPUs and 16 GiB; stop the native builder before starting it on a
small host. Allow at least 240 GiB free disk plus native build space.
Containers inside the VM still use directory storage; 100 root filesystems
make capacity important. Do not run simultaneous full-scale builds/tests on
an undersized host.

```sh
sudo apt update
sudo apt install -y git ca-certificates
git clone https://github.com/boardfarmdevs/prplmesh-lab.git
cd prplmesh-lab
sudo bash deploy/lxd-vm/install-host.sh
```

Log out/in for LXD group membership, return to the checkout, then check:

```sh
lxc info
test -c /dev/kvm
source deploy/lxd-vm/lab-config.sh demo-a
```

LXD membership is root-equivalent. The helper selects `demo-a-pool` and a
deterministic, validated port block. It creates nothing until a build starts.
Choose another name for a second VM; no scripts need editing.

## 2. Build native artifacts

```sh
bash deploy/lxd-vm/build-artifacts.sh
(cd artifacts && sha256sum -c SHA256SUMS)
lxc stop "$PRPLMESH_VM_NAME-builder"
```

This creates an **Ubuntu 22.04 build container**, isolated build network and
reusable `demo-a-build-pool`. It compiles native NL80211 prplMesh and hostap,
including dependency patches, and exports three checksummed archives into
`artifacts/`. It does not install radios on the outer host or start a mesh.
Logs and stage durations go to ignored `build-evidence/`.

Re-run the same command for incremental compilation after native source or
patch changes. Reuse artifacts only with their matching provenance; a checksum
alone does not prove that a tar contains the current patch set. The runtime
installer and acceptance gate check embedded provenance too.

Optional resource overrides: `PRPL_BUILD_CPUS`, `PRPL_BUILD_MEMORY`,
`BUILD_CONTAINER`, `PRPL_BUILD_STORAGE`, `PRPL_DNS_SERVERS`. Defaults work
without exports. Different builds in one checkout share `artifacts/`; use
separate checkouts for simultaneous artifact builds.

## 3. Build the VM, then test

```sh
bash deploy/lxd-vm/build.sh build
bash deploy/lxd-vm/build.sh urls
```

Continue with [VM lifecycle, storage and ports](vm.md), then
[tiered tests](../test/README.md). The runtime guest remains **Ubuntu 24.04
with the pinned Linux 7 kernel**; Ubuntu 22.04 describes the native builder
and supported outer host, not a replacement radio kernel.

For a dedicated radio host rather than a VM, follow [bare metal](../../deploy/bare-metal/README.md).
Do not run `scripts/build-all.sh` on an ordinary shared outer host: that
advanced path installs kernel modules and provisions radios locally.
