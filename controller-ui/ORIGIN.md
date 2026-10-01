# Source origin

This application is a host-native port of the RDK Unified EasyMesh EM CLI Web
application. Its page started as a copy of RDK's patched
`unified-wifi-mesh/src/rdkb-cli/static/` (0908 at layer commit `56a689f`, then
synchronized by hand). Since 1 Oct 2026 there is one page for both labs,
[the medium's topology-ui](../medium/topology-ui/README.md), and this UI
assembles it with its prplMesh profile; its README says what the two copies
differed in and how they were merged.

The page keeps its Apache-2.0 RDK copyright headers. The embedded
Go backend was not copied because the original `main.go` is coupled through
CGo to `libemcli`, RBUS/controller state, container-local `/nvram`, and the RDK
process model. This port preserves the browser contract at `/api/v1` and maps
an external prplMesh Data Elements topology projection into that contract.

No canned `devices.json`, `clients.json`, `system-config.json`, or example
topology files are included. Every displayed node, BSS and client must come
from the configured external API.
