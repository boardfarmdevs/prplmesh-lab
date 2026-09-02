# Portable prplMesh release

`prplmesh-0831-thin.tar` is the single portable LXD VM download. It supports
20-, 50-, and 100-client profiles without duplicating the installed Linux 7
guest and runtime artifacts in three archives.

The export contains zero nested lab instances and one local
`prpl-runtime-local` image. Import requires `--profile 20`, `--profile 50`, or
`--profile 100`. Before any nested identity is created, the importer sets the
tested CPU/RAM limits, generates the selected hwsim and wmediumd roster, and
writes an immutable profile lock. A missing or invalid choice is rejected.

Ready appliances remain profile-specific internal builders because they
contain complete controller, Agent and client rosters. The thin artifact may be
created from any accepted ready profile; the source ready VM is consumed by
that conversion.

Create the candidate from an accepted ready VM, using its accepted source as
the runtime base:

```sh
PRPLMESH_RUNTIME_BASE_COMMIT=READY-COMMIT \
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_VM_NAME=prplmesh-20-thin-source \
PRPLMESH_THIN_CONFIRM=prplmesh-20-thin-source \
  deploy/lxd-vm/package-thin.sh release/0831

deploy/lxd-vm/package-release.sh release/0831/prplmesh-0831-thin
```

The second command emits `prplmesh-0831-thin.tar` and
`prplmesh-0831-thin.tar.sha256`. From an empty directory:

```sh
sha256sum -c prplmesh-0831-thin.tar.sha256
tar -xf prplmesh-0831-thin.tar
cd prplmesh-0831-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

The first boot creates the selected roster entirely offline, starts it, and
runs topology, steering, data-plane and resource acceptance before clearing
its pending marker. Later boots use the normal lifecycle. The sparse 160-GiB
logical disk supports the stress profile; smaller profiles consume only blocks
they write, but the destination pool must support the declared logical size.

The exact same outer artifact bytes must be imported independently as profiles
20, 50, and 100. Each selection needs zero-inventory, offline first-boot,
topology, traffic, steering, optimizer, resource, warm-restart and one-hour
churn evidence. The artifact is accepted for distribution only after all three
selections pass.

The RDK repository's `portable-lab-releases.md` defines the shared two-stack
catalog and Google Drive layout. Google credentials and site-specific Drive
URLs are deliberately not stored in either repository.
