# prplMesh lab release notes

Release identifiers describe tested lab delivery checkpoints, not upstream prplMesh versions.

## 0824

- No independent prplMesh appliance was delivered; this checkpoint established the virtual-radio lab requirements later reused by the prplMesh implementation.

## 0828

- Established the x86 prplMesh controller and agent lab with hwsim radios, multichannel wmediumd, wireless backhaul, two fronthaul networks, clients, steering, and topology visualization.
- Added reproducible build and deployment scripts, an external controller UI, initial optimizer/configurator integration, and bare-metal plus LXD-VM operation.

## 0831

- Made LXD VM the primary portable appliance and supplied immutable 20-, 50-, and 100-client profiles.
- Stabilized tri-band startup and 6 GHz classification with stock hostapd, and aligned dynamic RCPI scenarios with the canonical medium runtime.
- Added the optional kernel-medium research backend alongside default userspace wmediumd, common performance tests, portable release packaging, and cross-host import guidance.

## 0901

- Made the shared wmediumd Console the public port-8090 service and retained
  the controller topology UI on port 8091 with its NBAPI adapter on loopback.
- Hid unassigned reserve radios from the operational medium graph and selectors
  while retaining them in raw inventory and telemetry.
- Added explicit release identifiers to portable metadata and instance names so
  one universal 0901 archive still selects 20, 50, or 100 clients at import.
