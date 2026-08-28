# Source origin

This application is a host-native port of the RDK Unified EasyMesh EM CLI Web
application. The Web assets were copied from the patched 0824 source used by
the RDK virtual-radio lab:

```text
unified-wifi-mesh/src/rdkb-cli/static/
```

The copied files retain their Apache-2.0 RDK copyright headers. The embedded
Go backend was not copied because the original `main.go` is coupled through
CGo to `libemcli`, RBUS/controller state, container-local `/nvram`, and the RDK
process model. This port preserves the browser contract at `/api/v1` and maps
an external prplMesh Data Elements topology projection into that contract.

No canned `devices.json`, `clients.json`, `system-config.json`, or example
topology files are included. Every displayed node, BSS and client must come
from the configured external API.
