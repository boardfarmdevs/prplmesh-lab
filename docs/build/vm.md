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
It installs the pinned radio kernel, nested LXD, separate mesh/client images, patched
hwsim/wmediumd, topology, room and **Console NG**. Native acceptance runs before
success; no room campaign or long soak runs during the build. Preserve the
build log on failure; do not treat an existing VM as an accepted build.

Unattended guest commands and container creation close stdin explicitly; they
must not wait for keyboard input when output is logged through `tee`. Older
builders can stall after `Built .../wmediumd` while `lxc init` awaits optional
YAML on stdin. If that exact wait is confirmed, send Ctrl-D on an empty line
in the original terminal to continue; do not delete the VM. Runtime image setup
logs to `/tmp/prpl-runtime-image-build.log` inside the VM
and `/tmp/prpl-client-image-build.log` for clients
(`RUNTIME_IMAGE_BUILD_LOG` overrides either for standalone runs).

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
This outer-host choice is independent of the **inner container pool**.

## Efficient inner storage and clients

Fresh VM builds create `prpl-lab`, a Btrfs copy-on-write pool. Containers share
unchanged image data rather than unpacking 105 independent Ubuntu root filesystems.
The default `120GiB` loop file is sparse: it is a capacity ceiling, not 120 GiB
immediately consumed. The VM disk default remains 160 GiB until new builds are
qualified; do not assume a smaller disk will pass capacity checks.

Optional overrides, exported before `build.sh build`:

```sh
export PRPLMESH_NESTED_STORAGE_POOL=prpl-lab
export PRPLMESH_NESTED_STORAGE_DRIVER=btrfs
export PRPLMESH_NESTED_STORAGE_SIZE=120GiB
```

Use `dir` only when explicitly needed; it loses image sharing. Existing pools
are reused only with a matching driver, never reformatted. The setup helper
refuses to switch an existing roster to another pool. **Existing VMs are not
migrated or shrunk.** Build a separately named VM to validate these improvements
without disturbing an accepted lab.

```sh
source deploy/lxd-vm/lab-config.sh demo-prpl-cow
bash deploy/lxd-vm/build.sh build
```

Commit the source first; reuse the existing verified native archives. No native
prplMesh, hostap, or BPI image rebuild is required for these packaging changes.

Five mesh containers use `prpl-runtime-local`; 100 clients use
`prpl-client-local`. The lean client remains Ubuntu 22.04 for ABI compatibility,
but omits the native controller/agent installation and AP daemon. It keeps the
exact patched `wpa_supplicant`/`wpa_cli` from the checksummed hostap archive,
including 6 GHz/SAE and BTM support, plus `iw`, traffic/capture tools and Python.
Package-refresh services are disabled and package caches removed before publishing.
It does not substitute the distribution's supplicant or change radio policy.

Both images are built automatically. To rebuild just the client image inside
an isolated build VM, after installing the three verified archives:

```sh
SOURCE_IMAGE=prpl-ubuntu-22.04-base bash scripts/build-runtime-image.sh client
```

This updates the local image, not existing containers. Thin exports retain and
fingerprint both role images. Capacity checks budget five mesh and 100 client
full copies plus growth/headroom, without assuming CoW savings or crediting
shared Btrfs blocks as reclaimable. They also check free space behind the sparse
pool. Legacy single-image thin manifests retain their original checks.

After a new build, inspect `lxc storage list` inside the VM, then run the
[static/live/room tiers](../test/README.md) before accepting size or speed claims.
New-image cold boots and full room behavior still require live qualification.

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
