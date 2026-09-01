# LXD-VM appliance

LXD VM is the primary portable deployment. It avoids a second hypervisor
management stack while retaining a complete guest boundary around the radio
host, nested containers and lab services.

On an Ubuntu 22.04 or 24.04 x86-64 host, install the prerequisites once:

```sh
sudo ./install-host.sh
newgrp lxd
```

The installer verifies hardware virtualization and initializes LXD only when
it has no storage pool. Review its output before importing a VM.

## Build a clean appliance

Release builders select an immutable client profile, provide the three
checksum-verified runtime archives, and let the builder create the Ubuntu
24.04/Linux 7 guest, nested LXD inventory, generated wmediumd roster,
controller, four Agents, both UIs, and boot service:

```sh
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_LXD_STORAGE=default \
PRPL_RUNTIME_DEPS_ARCHIVE=/absolute/path/prpl-runtime-deps-6.0.0.tar.gz \
PRPL_INSTALL_ARCHIVE=/absolute/path/prpl-install-nl80211-6.0.0.tar.gz \
PRPL_HOSTAP_ARCHIVE=/absolute/path/hostap-runtime-2.10.tar.gz \
  deploy/lxd-vm/build.sh build
PRPLMESH_LAB_PROFILE=20 deploy/lxd-vm/build.sh check
```

Profiles `20`, `50`, and `100` produce separate, pre-provisioned appliances.
Do not resize an imported appliance: use the artifact matching the required
roster so cold start only reconstructs runtime state. The source checkout must
be clean. Source enters the VM as a commit-bounded
Git bundle; runtime archives enter as checksummed files. The result has no host
source mount, Git credential, fixed host address, or dependency on the build
directory. Use `build.sh status|start|stop|restart|delete` for the named build
instance.

`PRPLMESH_LXD_STORAGE` selects the outer LXD pool for a clean build. The
builder reports capacity, used space, free space, and the profile-aware free
space requirement before it creates the VM. The selected build pool is saved
as provenance in the release metadata but is never forced on another host.

Package a checked export for Google Drive with:

```sh
PRPLMESH_LAB_PROFILE=20 deploy/lxd-vm/package.sh
deploy/lxd-vm/package-release.sh \
  release/0831/prplmesh-20-0831-COMMIT-lxd
```

The builder and packager each run the relevant acceptance gates. They do not
create or export an `accepted` LXD snapshot: on non-copy-on-write storage a
snapshot duplicates the complete VM disk, while the portable export is
instance-only and does not consume snapshots.

Before export, packaging stops the lab, removes only reconstructible package,
journal, Docker and nested-LXD image caches, and issues filesystem discard.
It never removes provisioned containers, identities, configuration or source.
Every bundle includes `trim-report.txt` with before/after guest usage,
discard output and the final compressed archive size.

## Offline thin flavor

The ready flavor above contains the complete provisioned roster and starts it
on every boot. The optional thin flavor is an installed appliance with the
same kernel, services, runtime artifacts and profile, but its export contains
zero nested lab instances. It retains one local `prpl-runtime-local` image, so
first boot provisions the selected 20, 50 or 100-client roster without a
network download or operator repair, then starts and validates the normal lab.
The pending marker is removed only after topology, steering, data-plane and
resource acceptance pass. The persistent
`/var/lib/prplmesh-lab/thin-firstboot-report.txt` records the zero-instance
starting condition, final roster count and PASS state.

Create a thin candidate only from a separately imported and fully accepted
ready appliance. The explicit confirmation is required because conversion
removes that VM's nested roster:

```sh
PRPLMESH_RUNTIME_BASE_COMMIT=READY-COMMIT \
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_VM_NAME=prplmesh-20-thin-source \
PRPLMESH_THIN_CONFIRM=prplmesh-20-thin-source \
  deploy/lxd-vm/package-thin.sh release/0831
deploy/lxd-vm/package-release.sh \
  release/0831/prplmesh-20-0831-COMMIT-thin-lxd
```

The source VM remains stopped and thin-pending after export. Import acceptance
must use the exact emitted archive and confirm `nested_instances_before=0`,
the profile-sized final roster, and the same full gates as the ready flavor.
Release metadata records both the thin tooling source and the accepted ready
runtime base so those two code identities are not conflated.

Upload the resulting `*-bundle.tar` and `.sha256`. From any empty working
directory, download the selected profile, verify and extract it:

```sh
sha256sum -c prplmesh-20-0831-COMMIT-lxd-bundle.tar.sha256
tar -xf prplmesh-20-0831-COMMIT-lxd-bundle.tar
cd prplmesh-20-0831-COMMIT-lxd
sha256sum -c SHA256SUMS
PRPLMESH_UI_HOST_IP=127.0.0.1 ./import.sh
```

To import into a non-default outer LXD pool, add
`PRPLMESH_LXD_STORAGE=POOL`. The pool must already exist.

For a thin bundle, first boot takes longer because the VM creates the offline
nested inventory before starting the radios and executing acceptance. The
service allows up to 60 minutes for a stress-profile first boot. Monitor
`prplmesh-lab.service`; no extra provisioning command is required.

To expose both UIs on a lab LAN, select an address owned by the outer host:

```sh
PRPLMESH_UI_HOST_IP=192.168.2.140 \
  ./import.sh
```

The release metadata selects instance `prplmesh-CLIENTS-0831` and its tested
CPU/RAM limits. Host port `8090` serves the raw adapter and `8091` serves the
Controller UI. Override them with
`PRPLMESH_VM_NAME`, `PRPLMESH_TOPOLOGY_HOST_PORT`, and
`PRPLMESH_UI_HOST_PORT`.

Monitor cold reconstruction:

```sh
lxc console prplmesh-20-0831 --show-log
lxc exec prplmesh-20-0831 -- journalctl -fu prplmesh-lab.service
lxc exec prplmesh-20-0831 -- prplmesh-lab-start status
```

Lifecycle and removal:

```sh
lxc stop prplmesh-20-0831
lxc start prplmesh-20-0831
lxc delete prplmesh-20-0831       # destructive; removes the imported VM
```

The lab automatically reconstructs after a guest reboot. Imported appliances
default to `boot.autostart=true`, so an existing VM also returns after an outer
host reboot. Disable it explicitly when that is not wanted:

```sh
lxc config set prplmesh-20-0831 boot.autostart false
```

Run a post-import acceptance check after cold reconstruction:

```sh
lxc exec prplmesh-20-0831 -- prplmesh-lab-start status
curl -fsS http://127.0.0.1:8090/api/topology >/dev/null
curl -fsS http://127.0.0.1:8091/api/topology >/dev/null
```

Release engineering runs `deploy/lxd-vm/build.sh check` before
`deploy/lxd-vm/package.sh`, then imports the emitted backup under a different
instance name and host ports and repeats the same acceptance.
