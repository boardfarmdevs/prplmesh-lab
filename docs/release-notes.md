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

## 0902

- Validated the universal appliance at 50-client scale across star, branch,
  chain, steering, RCPI, optimizer, agent recovery, churn, data-plane and
  process-footprint gates.
- Made live tests profile-aware for generated medium inventory, optimizer
  candidate deadlines, topology-specific deepest paths and controller aging.
- Added explicit colored action, wait and result messages to observer-facing
  demonstrations and acceptance scripts while preserving machine-readable
  stdout.
- Included the current Console ownership fix so 50-client observer snapshots
  remain bounded and healthy.

## 0903

- Consolidated the current delivery into one universal thin LXD appliance
  supporting immutable 20-, 50-, or 100-client selection at import.
- Added `steer-soak.sh`, which resolves the live NBAPI topology before every
  move and runs either one pass over the initial roster or a bounded number of
  sequential BTM steering attempts.
- Added `steer-batch.sh` for bounded concurrent NBAPI steering with exact
  station/BSSID resolution and independent physical plus controller-model
  verification for every requested move.
- Added a prplMesh experiment catalog and scenario guidance aligned with the
  RDK lab, while marking implementation-specific readiness and command paths.
- Retained userspace wmediumd as the release default and kept the Controller UI
  and shared wmediumd Console behavior aligned with the RDK appliance.

## 0904

- Added the complete live room demonstration with the same viewer, event and
  evidence contract as RDK, adapted to prplMesh NBAPI telemetry, candidate
  measurements, BTM actuation and controller-facing station identities.
- Added the four-minute Private-Laptop Golden World, bounded stimulus,
  recommendation and act modes, exact RF restoration, offline replay, tests,
  and complete operator/design/viewer documentation.
- Added the room-demo proxy to portable imports at outer port 18891 to guest
  port 8891 and advanced thin archive, instance and metadata defaults to 0904.
