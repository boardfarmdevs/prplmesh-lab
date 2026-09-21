# wmediumd Console NG

Read-only 3D medium explorer, hierarchical radio/path table, on-demand
properties, service health and RF evidence. Default route `/` opens NG;
`/classic/` redirects. Legacy controls are disabled, not a second collector.

- [Operator manual](../../docs/wmediumd-console-ng.md)
- [RF properties: simulation, provenance and observation](../../reference/radio/console-rf-properties.md)
- [Named-VM build](../../docs/build/README.md) and [test tiers](../../docs/test/README.md)

## Build

Go 1.22+ and Python 3.10+ are required. Vendored browser assets are checked in;
Node/npm are needed only to regenerate them from the pinned package lock.

```sh
bash wmediumd/observer/build.sh
# Only after dependency or vendor-entry changes:
bash wmediumd/observer/build.sh --vendor
```

This regenerates the embedded manual and shared RF catalog and compiles the
static binary. It does not deploy, restart a lab or run tests. The normal VM
build installs this binary and builds the matching patched daemon.

## Runtime integration

Inside the prpl VM, installation uses `install-prplmesh.sh`, not the RDK
launcher. Defaults: HTTP 8090, `/run/prpl-wmediumd/telemetry.sock`, generated
identity inventory in the same directory, room HTTP 8891 and survey status
`/run/wmdcfg-survey.json`. The root lab launcher publishes metadata and socket
permissions. The observer itself never opens LXD or the writable control
socket. The service's mount namespace hides both sockets.

`patches/wmediumd/0033` adds selected on-demand frame/queue/retry detail;
`0034` exposes model provenance. Rebuilding only the observer cannot add daemon
capabilities. Upgrade the daemon, room/optimizer Python code and observer as a
matching set during a maintenance window, or rebuild the VM. Do not replace
wmediumd under an active test.

The normal backend is userspace wmediumd. The experimental kernel-medium proxy
has no NG packet-detail stream: HTTP availability is not telemetry readiness.
Unsupported or absent evidence remains unavailable; do not manufacture zeros.

## Short checks

```sh
(cd wmediumd/observer && go test ./...)
node --test wmediumd/observer/web/ng/model.test.mjs
node tests/wmediumd-console-ng-browser-test.js
```

The browser test needs Playwright Core/Chromium, as described in the test guide.
After boot, inside the VM:

```sh
python3 /opt/prplmesh-lab/wmediumd/observer/check-ready.py \
  --url http://127.0.0.1:8090 --require-room
```

Add `--require-survey` when a survey-enabled world is active. From the outer
host use `build.sh urls` and pass the actual forwarded Console URL instead.
Compare an identical workload with/without the observer before claiming an
observer-cost budget. Compilation and mocked UI checks are not native RF or
full-room qualification.

## API and cost

`/api/v2/health` requires fresh NG telemetry; `/api/v2/rf-catalog` describes
properties and reserved protocol assignments. v2 snapshots/WebSocket streams
are interest-driven: selection, expansion, service/event panels and Freeze
control read subscriptions only. Configuration matrices describe possible
directed delivery, not active flows or controller ownership. `room-excluded`
means room intent; it is not proof that a bound radio emitted no frames.

Optional room/survey/native sources have separate freshness and failure states.
Native load uses the passive room cache even while optimizer candidates are
unavailable. prpl counter conversion remains 1024 bytes per native counter unit.
