# Medium backends

[Subsystem index](README.md)

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

Userspace exports modeled legacy-rate, 20 MHz airtime through the survey bridge
and native BSS Load reporting. These are modeled activity counters, not calibrated
AP capacity. The kernel backend does not implement this full survey path. See the
[virtual RF assessment](virtual-rf-assessment.md) for provenance and qualification.

Medium patch `0032` disables libnl's automatic administrative success-ACK requests
after synchronous family lookup. It removes redundant kernel replies, not simulated
802.11 acknowledgments: RF/PER calculations, frame delivery, TX status and negative
netlink errors remain unchanged. Existing patches, including `0031` access-category
admission, still apply. Unexpected kernel netlink receive drops are transport loss,
not modeled RF loss; track their counter delta independently during startup and room
qualification. A rebuilt medium needs a normal lifecycle startup and fresh native
100-client/room qualification; a live swap alone does not establish acceptance.

The focused [netlink tests](../../tests/README.md#netlink-transport) exercise actual
patched functions with real libnl plus read-only Linux generic-netlink queries.

Medium patch `0025` preserves confirmed client departures. Read-only
`GET_ASSOCIATION` returns flag `4`, a zero owner and zero frequency for a known
departure; genuinely unknown ownership still returns unavailable. Only successful
association or station-originated data can establish an owner. Stale downlink
traffic cannot resurrect it. The paired Console decoder excludes departed entries
from active associations. prplMesh's native HAL and controller paths are unchanged.

## Startup concurrency

`PRPL_START_MODE=gated` is the default. It starts and configures the controller,
then starts, configures and admits each Agent in order. Clients begin only after
the mesh gate and are admitted in bounded batches controlled by
`PRPL_START_PARALLELISM` (default `10`).

`PRPL_START_MODE=overlap` is an experiment that overlaps only the inexpensive
Agent container boots with controller setup. Radio mutation and EasyMesh Agent
onboarding remain serialized because parallel NL80211 setup previously exposed
an attach race and produced layer-2 associations without controller ownership.

Starting every container without gates is unsupported. Concurrency is useful
only when radio and protocol dependencies remain explicit.
