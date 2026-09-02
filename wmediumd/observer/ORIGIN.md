# Shared presentation source

This directory is an exact source and Web-asset copy of
`gen/wmediumd/observer` in `meta-cmf-bananapi-vcpe` at commit `94192a2`.
Only the additional `install-prplmesh.sh`, the prplMesh defaults file, and the
packaging handoff test are prplMesh adapters.

Do not modify the copied Go implementation or `web/` assets independently.
Refresh them from the RDK repository and run both repositories' Console tests
whenever the common Console changes.
