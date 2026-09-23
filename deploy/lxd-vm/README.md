# prplMesh LXD-VM appliance

LXD VM is the primary portable deployment. It keeps the Linux 7 radio host,
nested containers, hwsim/wmediumd, prplMesh services, and UIs within one VM.

For a new source build, use the [artifact-first build guide](../../docs/build/README.md)
and [named VM lifecycle](../../docs/build/vm.md). Release import remains below.
New bundles select a reusable named pool and derived per-VM ports; use the
printed URLs rather than assuming the legacy port examples below.

## Use the universal appliance

Use the selected release tar and adjacent checksum in an empty directory.
The 0916 names below are template examples; use the actual downloaded release
name (packaging substitutes it in this guide):

```sh
sha256sum -c prplmesh-0916-thin.tar.sha256
tar -xf prplmesh-0916-thin.tar
cd prplmesh-0916-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
PRPLMESH_UI_HOST_IP=192.168.2.150 ./import.sh
```

0916 uses one appliance with capacity for **100 clients**. There is no import
size choice and no separate 20/50/100 VM. Rooms select the online subset:
the default room uses 20 and `fifty-client-counter-roam` uses 50. Loading a room
automatically applies RF and presence without recreating containers or radios.
All five physical mesh containers (six displayed roles) remain provisioned.

Defaults are 8 vCPUs, 16 GiB RAM, 120 hwsim radios, and a sparse 160-GiB disk.
Budget at least 200 GiB of free backing-storage space for a new import, plus
space for retained VMs, exports and build intermediates. A storage backend may
allocate the full logical disk despite the small compressed download. Check
the selected pool and its backing filesystem before importing. Retain a working
rollback or a verified private export before deleting its VM; an export from
a monitored lab contains credentials and must not become a public download.
Leave resources for the host; do not run multiple appliances to select a room
size. First boot validates all 100 clients, then the room service disconnects
unused stations. Stopping/recovering the room restores that 100-client baseline;
restarting the room returns to its default 20 online.

The importer refuses to overwrite an existing instance. It reseeds the VM,
waits for both the outer VM agent and nested LXD API, records fixed-capacity initialization,
adds site-specific proxy devices, and starts offline first-boot provisioning.
Initialization cannot be published while nested LXD is unavailable. Slow hosts
may adjust `PRPLMESH_NESTED_LXD_READY_ATTEMPTS` and
`PRPLMESH_NESTED_LXD_READY_INTERVAL`.

## Site settings

New imports use outer LXD network `lxdbr0`, a reusable `VM-NAME-pool`, and a
deterministic per-name port block. Older bundles without `instance-config.sh`
retain legacy ports `8090`, `8091`, `18891`. Override explicitly when needed:

```sh
PRPLMESH_LXD_STORAGE=bpi-lab \
PRPLMESH_UI_HOST_IP=192.0.2.10 \
PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT=18090 \
PRPLMESH_UI_HOST_PORT=18091 \
PRPLMESH_ROOM_DEMO_HOST_PORT=18894 \
PRPLMESH_VM_NAME=my-prplmesh-lab \
  ./import.sh
```

Existing pools are reused without changing their backend. A missing named pool
is created with `dir` by default; new CoW pools can select
`PRPLMESH_STORAGE_DRIVER`. Older bundles require the pool to exist. The source
host's pool name is provenance only and is not imposed on the destination.

## First boot and operation

New two-image bundles create the 100-client roster from local `prpl-client-local`;
legacy bundles use `prpl-runtime-local`. Neither downloads runtime artifacts. Monitor
it with the selected instance name:

```sh
lxc console prplmesh-0916 --show-log
lxc exec prplmesh-0916 -- journalctl -fu prplmesh-lab.service
lxc exec prplmesh-0916 -- prplmesh-lab-start status
```

Before creating any radios or containers, first boot checks the retained image's
fingerprint against `thin-image-capacity.json` in `/var/lib/prplmesh-lab` and
budgets all 105 expanded root filesystems on the actual guest pool. Each copy
includes a 5% allocation margin and 64 MiB runtime-growth allowance, with another
8 GiB left free globally; free inodes are checked too. A compressed download's
size is **not** its expanded footprint. Failure preserves the pending marker and
a `thin-firstboot-report.txt.capacity.*.json` diagnostic; missing/mismatched image
measurements also fail closed. Do not remove the guard or mark a partial roster
ready. Preserve diagnostics and correct the image or guest capacity before a
separately recorded recovery. This guard currently requires nested `dir` storage
without per-container root quotas; it does not replace the outer-host space check.

When ready, use the URLs printed by import (not assumed legacy ports).
The room server is
started by `prplmesh-room-demo.service` with 100-client capacity; stop that
service before starting a manual `demo/room-demo` session. The NBAPI adapter
is internal on guest loopback port `8092`. Open the printed room URL for its
built-in manual. The release's `INTERACTIVE.md` covers trusted-network access,
automatic world loading, fixed-pool presence and RF recovery.
Normal lifecycle is:

```sh
lxc stop prplmesh-0916
lxc start prplmesh-0916
lxc config get prplmesh-0916 boot.autostart
```

Imported appliances default to `boot.autostart=false`. Manually starting the
VM starts its nested lab and its interactive room.
The VM does not start automatically when the outer host reboots. Deleting it is
destructive and must be explicit:

```sh
lxc delete prplmesh-0916
```

## Release engineering

Normal import users do not need a source checkout. For a source build, complete
the artifact-first guide linked above, then:

```sh
source deploy/lxd-vm/lab-config.sh demo-a
bash deploy/lxd-vm/build.sh build
bash deploy/lxd-vm/build.sh check
```

Convert an accepted ready VM into the single universal release:

```sh
PRPLMESH_RUNTIME_BASE_COMMIT=READY-COMMIT \
PRPLMESH_VM_NAME=READY-VM \
PRPLMESH_THIN_CONFIRM=READY-VM \
  deploy/lxd-vm/package-thin.sh release/0916
PRPLMESH_RELEASE_ID=0916 \
  deploy/lxd-vm/package-release.sh release/0916/prplmesh-0916-thin
```

Thin conversion removes provisioned nested instances from the source VM,
retains the verified mesh/client images and exact source, and exports a
stopped instance-only backup. It emits `prplmesh-0916-thin.tar`, its adjacent
`.sha256`, schema-2 `release.json`, inner `SHA256SUMS`, and this README.
The bundle also includes `RELEASE-NOTES.md` for the delivered checkpoint.

The runtime image is published from a **dedicated stopped copy**, never directly
from the exercised controller. Only contents of `/var/log`, `/tmp`, `/var/tmp`
and `/var/crash` in that copy are removed. Native binaries/libraries, configuration,
leases and other startup data are preserved, not stripped. Symlinked cleanup roots
and mounted subtrees are refused. SHA-256 and metadata snapshots of every protected
file (including native assets) must agree before/after, and installed `/opt`/`/usr`
assets must match the source controller. Keep the generated
`/var/lib/prplmesh-lab/thin-preparation.*/` evidence with the release record.

Preparation checks temporary copy/publication space, then the projected 105-copy
budget before changing the runtime alias or deleting the stopped roster. Only
actual allocated bytes of explicitly scheduled stopped-container deletions on `dir` are
credited; no credit is assumed for future outer cleanup, compression or sparse
files. The first-boot check repeats against actual free space after import.
Physical block allocation can change during publication without changing file
contents. Schema-2 capacity records retain both the original sanitation footprint
and the post-publication measurement, budgeting the **larger** value. Protected
content and metadata must still match exactly, entry counts must agree, and all
four cleaned directories must remain empty. First boot validates this binding
before provisioning; the 105-copy growth/headroom requirements are unchanged.
Existing schema-1 records retain their original strict single-measurement check.
On failure, the candidate/template and original roster are retained for review.
`deploy/guest/thin-image-guard.py sanitize --output NEW-EVIDENCE-DIR` also supports
`prpl-thin-template` initialized from the retained image without ever booting it;
`--compare-controller` additionally verifies an existing stopped controller.
This helper alone neither publishes an image nor proves release acceptance.
All exports, including already-thin repackaging, repeat the empty-guest capacity
check. `thin-image-capacity.json` and `thin-capacity-check.json` are included in
the bundle checksums; an older unmeasured runtime image cannot bypass this gate.

New builds use the inner Btrfs pool and separate lean-client image described in
[the VM build guide](../../docs/build/vm.md#efficient-inner-storage-and-clients).
Schema-3 thin records bind both sanitized templates, using `prpl-client-01` for
the client copy and rejecting a full mesh installation in that image. Both local
images survive cleanup for offline first boot. Capacity budgets five mesh and
100 client full expansions; Btrfs gets **zero shared-block reclamation credit**,
and the sparse loop's backing filesystem must also have headroom. Guard operations
enter the verified local LXD daemon's mount namespace when needed to inspect its
private Btrfs mount. Existing `dir` pools and schema-1/2 imports remain supported;
changing storage or client images is a fresh-build operation, not an in-place
conversion of an accepted VM.
Packaging trims the inner Btrfs filesystem before trimming the outer guest disk.

## Optional container management and metrics

Newly packaged releases accept `bash import.sh --monitoring`.
For an existing running VM, execute
`bash observability/enable.sh VM HOST_IPV4 LABEL` on its physical LXD host.
This installs the full bundled inner LXD UI and a provisioned Grafana container
dashboard on HTTPS ports 18892 and 18893. Authentication is required, Prometheus
stays private, and VM autostart is unchanged. Omit the flag for the original
offline/no-monitoring import. Existing immutable release archives are unchanged.
See [first login and resource limits](observability/README.md) and the
[detailed reference](../../reference/observability/monitoring.md).
Both backend installers support inner-container and outer-VM monitoring.
See current state for enabled deployments; browser authentication is still required.
