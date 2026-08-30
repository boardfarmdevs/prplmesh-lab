# LXD-VM appliance

Install LXD on an Ubuntu 22.04 or 24.04 x86-64 host, initialize an otherwise
unused storage pool, and verify `/dev/kvm` is available. Then import the
portable 0829 backup from an empty working directory:

```sh
PRPLMESH_UI_HOST_IP=127.0.0.1 \
  /path/to/import.sh prplmesh-lab-0829-COMMIT-lxd.tar.zst
```

To expose both UIs on a lab LAN, select an address owned by the outer host:

```sh
PRPLMESH_UI_HOST_IP=192.168.2.140 \
  /path/to/import.sh prplmesh-lab-0829-COMMIT-lxd.tar.zst
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
