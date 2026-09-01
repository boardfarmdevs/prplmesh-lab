# Portable profiles

The prplMesh lab is distributed as pre-provisioned LXD virtual machines with
20, 50, or 100 clients. Each profile has its own hwsim and generated wmediumd
roster, nested containers, identities, resource defaults, release metadata and
checksum. Importing another profile is supported; resizing an imported profile
is not.

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

The final `*-bundle.tar` and `.sha256` are suitable for manual Google Drive
upload. The bundle README begins with the empty-directory import workflow.
Packaging labels a release candidate. Acceptance requires a clean import on a
different host and the exact profile's topology, traffic, steering, optimizer,
resource and one-hour soak gates.

All published profiles are trimmed before export. The bundle's
`trim-report.txt` records cache removal, filesystem discard, guest usage and
the final archive size; the report itself is covered by `SHA256SUMS`.

The RDK repository's `portable-lab-releases.md` defines the shared two-stack
catalog and publishing contract. Google credentials and site-specific Drive
URLs are deliberately not stored in either repository.
