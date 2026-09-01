# Portable profiles

The prplMesh lab is distributed as separate 20-, 50-, and 100-client LXD VM
appliances. Each profile has its own hwsim and generated wmediumd roster,
identities, resource defaults, release metadata and checksum. Importing another
profile is supported; resizing an imported profile is not.

Every profile is available in two flavors:

- `ready` contains the complete provisioned controller, agents and clients;
- `thin` contains zero nested lab instances and one local runtime image. Its
  first boot creates the selected roster entirely offline, starts it and runs
  topology, steering, data-plane and resource acceptance before clearing its
  pending marker.

The thin flavor trades a longer first start for a much smaller transfer. Later
starts use the same normal lifecycle as the ready flavor.

Build and package one profile:

```sh
PRPLMESH_LAB_PROFILE=20 \
PRPL_RUNTIME_DEPS_ARCHIVE=/absolute/path/prpl-runtime-deps-6.0.0.tar.gz \
PRPL_INSTALL_ARCHIVE=/absolute/path/prpl-install-nl80211-6.0.0.tar.gz \
PRPL_HOSTAP_ARCHIVE=/absolute/path/hostap-runtime-2.10.tar.gz \
  deploy/lxd-vm/build.sh build

PRPLMESH_LAB_PROFILE=20 deploy/lxd-vm/package.sh
deploy/lxd-vm/package-release.sh \
  release/0831/prplmesh-20-0831-COMMIT-lxd
```

Create a thin candidate only from an accepted ready VM, using the accepted
ready source as its runtime base:

```sh
PRPLMESH_RUNTIME_BASE_COMMIT=READY-COMMIT \
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_VM_NAME=prplmesh-20-thin-source \
PRPLMESH_THIN_CONFIRM=prplmesh-20-thin-source \
  deploy/lxd-vm/package-thin.sh release/0831
```

The final `*-bundle.tar` and `.sha256` are suitable for manual Google Drive
upload. The bundle README begins with the empty-directory import workflow.
Packaging labels a release candidate. Acceptance requires a clean import on a
different host and the exact profile's topology, traffic, steering, optimizer,
resource and one-hour soak gates. Thin acceptance also verifies zero initial
nested instances, offline first-boot provisioning, the exact final roster and
a persistent PASS report.

All published profiles are trimmed before export. The bundle's
`trim-report.txt` records cache removal, filesystem discard, guest usage and
the final archive size; the report itself is covered by `SHA256SUMS`.

The RDK repository's `portable-lab-releases.md` defines the shared two-stack
catalog and publishing contract. Google credentials and site-specific Drive
URLs are deliberately not stored in either repository.
