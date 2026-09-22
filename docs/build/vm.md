# Build and operate the VM

[Build overview](README.md) · [Test tiers](../test/README.md)

## Build from this checkout

Complete the native artifact stage first. All commands are **on the outer LXD
host**, from the repository root:

```sh
source deploy/lxd-vm/lab-config.sh demo-a
bash deploy/lxd-vm/build.sh build
bash deploy/lxd-vm/build.sh urls
bash deploy/lxd-vm/build.sh status
```

The checkout must be committed and clean. The builder transfers a verified
bundle of its exact HEAD, not uncommitted files. It selects the three archives
under `artifacts/`, verifies adjacent `SHA256SUMS`, creates the named storage
pool if missing, checks port conflicts, and refuses to replace an existing VM.
It installs the pinned radio kernel, nested LXD, prplMesh runtime, patched
hwsim/wmediumd, topology, room and **Console NG**. Native acceptance runs before
success; no room campaign or long soak runs during the build. Preserve the
build log on failure; do not treat an existing VM as an accepted build.

Native artifacts are built in Ubuntu 22.04. The radio VM is Ubuntu 24.04 with
the pinned Linux 7 kernel. VM creation does not require Go, Node or Chromium on
the outer host. The repository includes the static Console binary and vendored
browser assets; rebuild those when modifying their source.

## Independent names, pools and ports

`lab-config.sh NAME` chooses a reproducible six-port block from the name:

| Offset | Service | Guest endpoint |
| --- | --- | --- |
| +0 | Network topology | HTTP 8091 |
| +1 | Console NG | HTTP 8090 |
| +2 | Interactive room | HTTP 8891 |
| +3 | Optional inner LXD UI | HTTPS 8443 |
| +4 | Optional Grafana | HTTPS 3000 |
| +5 | Optional outer LXD metrics | HTTPS; host monitoring setup |

Different names normally choose different blocks; hashing is not a reservation.
The builder checks existing proxy devices, including stopped VMs, and bound
host TCP ports. If a block conflicts, use a free `PRPLMESH_PORT_BASE` before
sourcing the helper. Separate concurrent builds still need operator scheduling:
port/IP allocation is checked, not an atomic multi-process reservation.

```sh
PRPLMESH_PORT_BASE=45000
source deploy/lxd-vm/lab-config.sh demo-b
bash deploy/lxd-vm/build.sh build
```

Switching names clears previously derived values; explicit changed overrides
are retained. A new shell selects the same defaults; repeat any custom base,
bind address or pool override when rebuilding. `build.sh urls` reads actual
proxy devices for an existing VM instead of guessing its ports. LXD persists
these forwards across host reboots. No manual forwarding step is needed.
Limit LAN access with your firewall; the room grants lab control and these
interfaces are not suitable for direct Internet exposure.

Default pools use `dir`, which works without an outer-host ZFS module. To use
an existing pool set `PRPLMESH_LXD_STORAGE`; it is never reformatted. For a new
CoW outer pool, set `PRPLMESH_STORAGE_DRIVER=zfs` or `btrfs` and optionally
`PRPLMESH_STORAGE_SIZE=240GiB`, with host backend support installed first.
This **does not change nested storage**: prpl's thin-image capacity/identity
guards currently require its existing directory-backed inner pool. RDK's
parallel BPI roster allocator and inner Btrfs implementation are not portable
to prpl and have not been copied.

## Start, stop and rebuild

```sh
bash deploy/lxd-vm/build.sh stop
bash deploy/lxd-vm/build.sh start
```

VM autostart is disabled. After manual start, guest services start the lab and
default 20-online-client room from the fixed 100-client pool. Other rooms can
change presence without creating/deleting clients.

For a clean rebuild, stop first; **delete removes the entire selected VM and
its snapshots**, but keeps its named storage pool and native builder:

```sh
bash deploy/lxd-vm/build.sh stop
bash deploy/lxd-vm/build.sh delete
bash deploy/lxd-vm/build.sh build
```

Do not delete another tester's VM or a shared pool. For same-source iteration,
an optional stopped-VM snapshot preserves exact runtime state without another
build. It is not a backup against pool loss or proof of reproducibility.

## Monitoring

On the outer host, enable the already-supported optional monitoring bundle:

```sh
HOST_IP=$(ip -4 route get 1.1.1.1 | awk '{for (field=1; field<=NF; field++) if ($field == "src") {print $(field+1); exit}}')
bash deploy/lxd-vm/observability/enable.sh "$PRPLMESH_VM_NAME" "$HOST_IP"
bash deploy/lxd-vm/build.sh urls
```

See [monitoring](../../reference/observability/monitoring.md) for LXD trust,
Grafana credentials and optional outer-VM metrics. Monitoring ports remain
bound to this VM's selection; outer-host LXD metrics are a shared service and
must not be reconfigured independently for each VM.

## Source changes and evidence

Rebuild native archives only when their sources/patches change. Console NG's
daemon extensions require rebuilding wmediumd as well as the observer; a UI
copy alone cannot enable telemetry. A fresh VM build does this automatically.
Use [tests](../test/README.md) after rebuilding. Do not label a source-only
backport live-qualified before those gates pass.
