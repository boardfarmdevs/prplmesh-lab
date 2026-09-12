# Shared presentation source

This directory is an exact source and Web-asset copy of
`gen/wmediumd/observer` in `meta-cmf-bananapi-vcpe` through commit `4b3ea8f`.
Only the additional `install-prplmesh.sh`, the prplMesh defaults file, and the
packaging handoff test are prplMesh adapters.

The shared implementation includes confirmed association departures and
accurate classification of netlink errors.
These changes are paired with prpl's medium patch `0025`; departure evidence
must not be rendered as a live association.

Do not modify the copied Go implementation or `web/` assets independently.
Refresh them from the RDK repository and run both repositories' Console tests
whenever the common Console changes.
