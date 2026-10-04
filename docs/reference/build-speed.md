# Build speed: copies, the base image, the artifact store, the records

[Documents](../README.md) · [Build and operate the VM](../guides/build-vm.md)

What makes a lab VM cheaper to build, to try things on and to requalify, from the labs'
[faster, cheaper labs](https://github.com/boardfarmdevs/easymesh-labs/blob/main/docs/proposals/faster-labs.md)
proposal. The RDK lab has the same mechanisms under the same names.

## Copies

`bash deploy/lxd-vm/build.sh copy NEW` copies a VM in its storage pool, with its own LXD
identities, address and port block (from NEW's name, or `PRPLMESH_COPY_PORT_BASE`), and
leaves it stopped; `PRPLMESH_VM_NAME=NEW bash deploy/lxd-vm/build.sh start` starts it. A
running VM is copied through a snapshot. On a Btrfs or ZFS pool
(`PRPLMESH_STORAGE_DRIVER=btrfs` for a new lab's pool) the copy takes seconds and shares
the original's blocks; on `dir` it is a full copy. Its DHCP client identity is its MAC
(`prepare-appliance.sh`, and the base image's netplan), and `start` makes its reservation
and proxies follow the address it runs on. Experiment on copies; never run a suite on two
copies of one lab at the same time.

## The base VM image

A build starts from a base VM image when this host or the artifact store has one: the
Ubuntu VM with the lab's kernel, its packages and LXD, nothing from the checkout, named by
those inputs (`prplmesh-base-KEY`: the VM image, the kernel, the package list and the guest
functions that install them, `base_host` in `build.sh`). Without one, the build makes it
on the way and publishes it:

| `PRPLMESH_BASE_IMAGE` | |
| --- | --- |
| `auto` (default) | start from the base image if there is one, else make and publish it |
| `off` | build every step, publish nothing |
| `rebuild` | make the base image anew |

The first build on a host pays for the publish once (a compressed image of the VM's
disk). The build waits for the guest's LXD after the base's restart and after a base
image's first boot.

## The artifact store

The umbrella's artifact store (easymesh-labs, `docs/reference/artifact-store.md`) keeps
what is slow to build by the inputs it is built from:

| Component | What | Its key (`deploy/lxd-vm/native-inputs.sh`) |
| --- | --- | --- |
| `prplmesh-native` | the three native archives | the pinned prplMesh and hostap revisions, the native build scripts, every patch |
| `prplmesh-client` | the Alpine clients' supplicant | the pinned hostap revision, its patches, the build script, the Alpine image |
| `prplmesh-base-vm` | the base VM image | as above |

With `EASYMESH_ARTIFACT_STORE=http://HOST:8180`, `deploy/lxd-vm/build-artifacts.sh`
fetches the native archives and the client supplicant whose inputs match this checkout
instead of building them, and a build fetches the base image. With
`EASYMESH_ARTIFACT_PUBLISH=DIR` or `HOST:/DIR`, what is built here is published.
`BUILD_FORCE=1` builds anyway. `artifacts/prplmesh-native.key` and
`artifacts/prplmesh-client.key` record which inputs the local archives were built from.

## The records

Every build, update and copy writes a record to `build-evidence/KIND-NAME-STAMP/`
(`PRPLMESH_BUILD_RECORDS` moves it): `environment.txt` (host, commit, image, kernel, sizes,
clients, storage driver, whether it started from the base image; an update adds what it
rebuilt), `phases.tsv` (each phase's start and seconds), `summary.txt`, `exit-code` and, on
failure, `failed-phase`. `latest-KIND-NAME` links the newest. The suite runner's
`summary.json` carries the run's start, end and seconds and each section's seconds.

## A development lab

`PRPLMESH_DEV_CLIENTS=20 bash deploy/lxd-vm/build.sh build` builds a lab with 20 clients
instead of 100 (1 to 99): quicker to build and lighter to run, for work on the mesh, the
medium and steering. It has no room service (its unit needs the full roster), its
acceptance checks its own roster, an update skips the room's settling, and packaging
refuses it. Qualification and every room run need the full lab.

## What a change needs

`tests/affected-suites.py BASE` prints the least an accepted lab needs for a change
(nothing, `update`, `build`, or new native archives first) and the suite sections that can
see it ([test tiers](../guides/test-suite.md)).
