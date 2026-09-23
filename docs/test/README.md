# Test an installed prplMesh VM

[Build guide](../build/README.md) · [Detailed test tools](../../tests/README.md)

Run from the matching **outer-host checkout**; reuse existing VMs.

Live/soak tiers guard/stop the room until native tests finish, then restore its
prior active state. Cleanup failures fail qualification. Room tests use `worlds/golden`.

For RF checks, set `ROOM_URL` to the live-room URL from
`bash deploy/lxd-vm/build.sh urls`. Proxies usually bind the LAN IP, not localhost:

```sh
python3 tests/rf-access-smoke.py \
  --room-url "$ROOM_URL" \
  --output "test-results/rf-access-$(date -u +%Y%m%dT%H%M%SZ).json"
```

This is not convergence or physics qualification. Independent power/noise/CCA
currently has only an offline reference contract; live activation is unavailable.
Add `--require-backhaul-load` on a healthy connected room to require fresh
native utilization for every reported wireless backhaul hop. Unknown context
fails rather than borrowing a fronthaul sample. Room drivers install their
native audit helpers automatically, replacing old operator-owned `/tmp` copies.

## Prepare

Activate the host test environment:

```sh
python3 -m venv "$HOME/.venvs/prplmesh-tests"
source "$HOME/.venvs/prplmesh-tests/bin/activate"
python3 -m pip install -r tests/requirements.txt
```

Have Python 3.10+, pytest, a C/C++ compiler, Go 1.22+, Node 22+, npm and LXD
access. Ubuntu's default Node may be too old; use a supported Node installation.
The browser tiers need Playwright Core, Chromium and its Linux shared libraries.
An optional flag installs local npm dependencies under ignored `browser-tools/`
and downloads Chromium; it does not install system packages. Preserve its
lockfile with test evidence. If browser launch reports missing libraries, use
Playwright's `install-deps chromium` command after reviewing its sudo/apt work.
Alternatively supply `NODE_PATH` and `CHROMIUM_PATH` for an existing installation.

```sh
source deploy/lxd-vm/lab-config.sh demo-a
unset DISPLAY WAYLAND_DISPLAY
bash tests/run-prplmesh-suite.sh static webui browser --install-browser-deps
```

Default: `static`; `--list` lists tiers. Tool installation is opt-in.

## Tiers

| Section | Scope / effect |
| --- | --- |
| `static` | Documentation, Python configurator/optimizer/room/regressions, Console and topology Go tests. No VM. |
| `webui` | Deterministic Node render/layout/RF/steering and Console models. No VM. |
| `browser` | Mock/local browser presentation, Console NG, sidebar, fullscreen/dividers. No live RF writes. |
| `rf` | Two rooms, counter manifest/shadow and contracts; bounded RF writes. |
| `rf-actions` | Native guarded load BTM, retry-pressure veto and weak-signal rescue. Temporarily retunes private 2.4 GHz. |
| `rooms` | Every compatible room: load, initial convergence, **Play**, native associations/traffic and topology checks; geometry rooms run separately. Mutates RF. |
| `live` | Console health, full 100-client native provenance/topology/BTM/data-plane/resource checks. Mutates RF. |
| `soak` | Bounded leaf restart/steering churn, permanent radio and daemon identity checks; three cycles by default. Mutates RF. |

`live/controller-memory` gates acceptance→soak: [90-second RSS/100-client/1s-metrics check](../../reference/testing/controller-memory.md).

See [RF action qualification](../../reference/radio/rf-property-coverage.md#native-load-action-qualification).

`all` runs those tiers in dependency order. These are functional/regression
gates, not a hardware RF-capacity certification or an unlimited endurance soak.
Failures and prerequisite blocks produce nonzero exit and are never passes.

## Live campaign

Use an idle, freshly started default room with no browser control lease,
recording or competing RF writer. Host and guest checkouts must be clean and
at the same commit. Review the source-match failure rather than bypassing it.
The full catalog can take hours; select tiers for a shorter run.

Authorized dirty diagnostics: [direct RF helpers](../../reference/radio/rf-property-coverage.md#direct-prpl-diagnostic-checks), not suite qualification.

```sh
bash tests/run-prplmesh-suite.sh rooms live --yes-act --install-browser-deps
bash tests/run-prplmesh-suite.sh all --yes-act --install-browser-deps
```

URLs come from the selected VM's proxies; audit helpers install automatically.
Room drivers restore Default and report ordinary/geometry rooms separately.
Native tiers guard/stop the room **once**, restore root parents as an explicit
test fixture (not optimizer steering), and require 100 clients throughout
acceptance/churn. Cleanup restores the prior service state; restoration errors fail.

```sh
bash tests/run-prplmesh-suite.sh soak --yes-act --churn-iterations 10
```

Progress, per-step logs, durations, `results.tsv`, `summary.json`, source identity
and browser/room evidence go to a new `test-results/TIMESTAMP-VM/` directory.
Retain failed reports. Room counts, client identities, native ownership, fresh
metrics and traffic must agree; a green animation alone is not convergence.
For RF-specific qualification see the [assessment](../../reference/radio/virtual-rf-assessment.md).
