# Generated build artifacts

This directory is deliberately not a binary distribution. Run
`scripts/build-all.sh` to create the three runtime archives from the pinned
upstream source revisions and the patches stored in this repository:

- `prpl-install-nl80211-6.0.0.tar.gz`;
- `prpl-runtime-deps-6.0.0.tar.gz`; and
- `hostap-runtime-2.10.tar.gz`.

`SHA256SUMS` is generated beside them. The archives are ignored by Git because
the prplMesh install archive is larger than GitHub's normal single-file limit.
