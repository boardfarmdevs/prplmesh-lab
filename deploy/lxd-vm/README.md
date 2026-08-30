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

From any empty working directory, copy the exported bundle directory. It
contains the backup, installer, importer, this README, and `SHA256SUMS`. Verify
and import the portable 0829 backup:

```sh
sha256sum -c SHA256SUMS
PRPLMESH_UI_HOST_IP=127.0.0.1 \
  ./import.sh prplmesh-lab-0829-COMMIT-lxd.tar.zst
```

To expose both UIs on a lab LAN, select an address owned by the outer host:

```sh
PRPLMESH_UI_HOST_IP=192.168.2.140 \
  ./import.sh prplmesh-lab-0829-COMMIT-lxd.tar.zst
```

The defaults are instance `prplmesh-lab-0829`, host port `8090` for the raw
adapter, and `8091` for the Controller UI. Override them with
`PRPLMESH_VM_NAME`, `PRPLMESH_TOPOLOGY_HOST_PORT`, and
`PRPLMESH_UI_HOST_PORT`.

Monitor cold reconstruction:

```sh
lxc console prplmesh-lab-0829 --show-log
lxc exec prplmesh-lab-0829 -- journalctl -fu prplmesh-lab.service
lxc exec prplmesh-lab-0829 -- prplmesh-lab-start status
```

Lifecycle and removal:

```sh
lxc stop prplmesh-lab-0829
lxc start prplmesh-lab-0829
lxc delete prplmesh-lab-0829       # destructive; removes the imported VM
```

The lab automatically reconstructs after a guest reboot. Imported appliances
default to `boot.autostart=true`, so an existing VM also returns after an outer
host reboot. Disable it explicitly when that is not wanted:

```sh
lxc config set prplmesh-lab-0829 boot.autostart false
```

Run a post-import acceptance check after cold reconstruction:

```sh
lxc exec prplmesh-lab-0829 -- prplmesh-lab-start status
curl -fsS http://127.0.0.1:8090/api/topology >/dev/null
curl -fsS http://127.0.0.1:8091/api/topology >/dev/null
```
