# Build speed: copies, the base image, the artifact store, the records

[Documents](../README.md) · [Build and operate the VM](../guides/build-vm.md)

What makes a lab VM cheaper to build, to try things on and to requalify, from the labs'
faster, cheaper labs proposal (in [easymesh-labs](https://mesh.vcpe.dev/)). The RDK lab has
the same mechanisms under the same names.

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

## Measured

rev140 (16 CPUs, 62 GiB), 4 October 2026, with another lab VM running beside the builds,
from the builds' records. `prpl-fast-a` was first built cold, which made and published the
base image (its build then stopped at the client image on a fault fixed since), then built
again from that image, and passed its acceptance with Alpine clients:

| Phase | Cold | From the base image |
| --- | ---: | ---: |
| inputs, create, start | 34 s | 57 s |
| the base: kernel, packages, LXD, and the restart | 332 s | — |
| publishing the base image (once per key; 1.35 GiB) | 382 s | — |
| inputs pushed, nested storage | | 34 s |
| the mesh and client images, the radio module, a restart | | 371 s |
| the radio pool and 105 containers | | 382 s |
| the guest's services, the controller UI | | 27 s |
| the lab's start (100 clients associated) | | 728 s |
| acceptance (100 of 100 clients reach the controller; the optimizer check) | | 1140 s |
| total | | 2739 s (45.6 min) |

The base image saves 5.5 minutes a build here (the prplMesh base is small: no WAN, no
radio module). The native archives come from the store in 4 s instead of 15.5 minutes. A
copy of the accepted lab on its Btrfs pool took 7 s, and the two labs share 13.9 GiB; the
copy started on its own address and ports in 757 s.

The copy was then updated to a commit that changed the medium's daemon, console and radio
module, a guest service and a script the clients run: 18.9 minutes, of which 2.8 to build
and install them (the radio module 150 s), 14.1 to restart and start the lab, and 2 for
the room to settle with its 20 clients. It then passed `check` in full (100 of 100 clients
over the data plane, the steering acceptance, the optimizer's recommend check). A build of
the same commit takes the 45.6 minutes above. The first two attempts stopped at the radio
module, on faults fixed since; the third resumed from the commit the copy was built at.

## The Alpine clients

The client image is Alpine with the lab's own supplicant built for musl
([build and operate the VM](../guides/build-vm.md)). Set up the same way in a container on
rev140 (3 October 2026), its root filesystem is 45.7 MB; the Ubuntu 22.04 client image it
replaces was 366 MB. On the nested Btrfs pool the 100 clients share their image's blocks,
so the gain is in the image itself, its build and what each client runs.

## A development lab

`PRPLMESH_DEV_CLIENTS=20 bash deploy/lxd-vm/build.sh build` builds a lab with 20 clients
instead of 100 (1 to 99): quicker to build and lighter to run, for work on the mesh, the
medium and steering. It has no room service (its unit needs the full roster), its
acceptance checks its own roster, an update skips the room's settling, and packaging
refuses it. Qualification and every room run need the full lab.

Measured on rev140 (4 October 2026, from the same base image as the full lab above):
`prpl-fast-d` with 20 clients built and passed its acceptance (20 of 20 clients over the
data plane, the steering acceptance, the optimizer's recommend check) in 24.2 minutes
against the full lab's 45.6: its radio pool and containers took 145 s instead of 382, the
lab's start 9.6 minutes instead of 12.1, the acceptance 5.0 instead of 19.0.

## Update in place

`bash deploy/lxd-vm/build.sh update` rebuilds what a commit changed of what a build installed
(the guide says what), restarts the VM and lets the room settle; its record says what it
rebuilt. An update that stops part-way is finished by running it again: it starts from the
last commit a build or a whole update applied (`user.prplmesh.applied-commit`), not from the
checkout it may have moved already. The radio module is built from the kernel's stock
source each time.

## What a change needs

`tests/affected-suites.py BASE` prints the least an accepted lab needs for a change
(nothing, `update`, `build`, or new native archives first) and the suite sections that can
see it ([test tiers](../guides/test-suite.md)).
