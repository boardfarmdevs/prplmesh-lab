# Medium backends

The lab supports two interchangeable RF data paths. Scenario source, compiled
event plans, prplMesh telemetry, steering, stable hwsim identities and the
operator workflow remain the same.

| Backend | Data path | Control | Status |
|---|---|---|---|
| `userspace` | mac80211_hwsim sends frames through netlink to wmediumd | wmediumd atomic control and metrics sockets | Default and accepted |
| `kernel` | the patched hwsim module applies link state, loss, rate/PER and bounded delay before delivery | atomic debugfs link-matrix banks; read-only compatibility metrics socket | Experimental, opt in |

Userspace stays the default:

```sh
scripts/radio-lab.sh stop
PRPL_MEDIUM_BACKEND=userspace scripts/radio-lab.sh start
PRPL_MEDIUM_BACKEND=userspace scripts/radio-lab.sh clients
```

Select the experimental backend only after installing the complete hwsim
patch series:

```sh
sudo INSTALL_MODULE=1 LOAD_MODULE=1 scripts/build-hwsim.sh
scripts/radio-lab.sh stop
PRPL_MEDIUM_BACKEND=kernel scripts/radio-lab.sh start
PRPL_MEDIUM_BACKEND=kernel scripts/radio-lab.sh clients
```

For an appliance service, put the selection in `/etc/default/prplmesh-lab`:

```sh
PRPL_MEDIUM_BACKEND=kernel
```

Then restart `prplmesh-lab.service`. Remove the line, or set it to
`userspace`, to return to the accepted backend.

The kernel actuator preserves the configurator contract:

```sh
cd wmediumd/configurator
python3 -m wmdcfg.cli status --backend kernel
python3 -m wmdcfg.cli run --backend kernel /path/to/event-plan.json
```

Scenario SNR values are converted to dBm with a default noise floor of
`-91 dBm`. A complete matrix generation is written into the inactive bank and
committed with one bank flip. The runner reads the result and restores the
prior state exactly as it does with userspace wmediumd.

The kernel metrics proxy is intentionally read only. It presents the existing
wmediumd metrics ABI at `/run/prpl-wmediumd/metrics.sock`, so the patched
prplMesh monitor HAL continues to obtain candidate-link measurements. Scenario
writers use the debugfs actuator; they do not write through the proxy.
Live STA and BSSID MACs are resolved to their permanent hwsim radio identities
through `/run/prpl-wmediumd/kernel-medium-aliases.json`; scenario matrices
therefore remain stable when VIFs are recreated.

The kernel backend is not a feature-complete replacement for wmediumd. Keep
userspace for release baselines, detailed observer telemetry and behavior not
covered by the kernel model. Backend comparisons must use the same topology,
traffic and scenario plans.

## Startup concurrency

`PRPL_START_MODE=overlap` boots the controller and active Agent containers
concurrently, then applies controller configuration and onboards Agents in
parallel. Clients begin only after the mesh gate. Client setup is bounded by
`PRPL_START_PARALLELISM` (default `10`). `PRPL_START_MODE=gated` retains the
older controller-first container sequence for diagnosis.

Starting every container without gates is deliberately unsupported. In the
corresponding 55-container RDK experiment, all LXC instances launched in about
14 seconds, but only 44 of 50 clients supplied telemetry and the formal cold
acceptance failed. Concurrency is useful only when protocol dependencies stay
explicit.

## Measured 0829 profile

The current rev140 LXD-VM profile contains one controller, four Agents and 20
clients (25 nested containers). Both measurements start from stopped
containers, use `star` backhaul, overlap Agent boot, admit clients in batches
of ten, and finish only after both Web endpoints pass health checks.

| Backend | Mesh gate | Client gate | UI gate | Total cold start | Clean stop |
|---|---:|---:|---:|---:|---:|
| userspace | 167 s | 31 s | 1 s | 199 s | 15 s |
| kernel | 165 s | 20 s | 4 s | 189 s | 15 s |

The roughly ten-second cold-start difference is not a throughput benchmark;
onboarding timing has normal run-to-run variation. The important result is
functional parity:

- both backends passed 5 devices, 4 Agents, 20 clients and all 20 associated
  metrics;
- both passed representative 5 GHz and 6 GHz BTM steering and 20/20 data-plane
  reachability;
- userspace passed the dynamic NBAPI candidate-metric recommendation scenario;
- kernel passed both recommendation and acting scenarios, including BTM
  convergence and exact medium restoration; and
- process cardinality stayed fixed. Userspace wmediumd used 4.0 MiB RSS; the
  current kernel compatibility metrics proxy used 18.8 MiB RSS.

Userspace remains the release default because it has the complete observer
telemetry and established behavior. Kernel mode is a controlled experiment,
not yet a general replacement.

Build outputs carry provenance. The prplMesh runtime archive records the
upstream commit and complete prplMesh patch digest. The wmediumd binary has a
matching sidecar containing its upstream commit and patch digest. Startup and
acceptance fail closed when either artifact does not match the checked-out
patch series.
