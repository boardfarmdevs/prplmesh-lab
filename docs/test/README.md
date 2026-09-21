# Test an installed prplMesh VM

[Build guide](../build/README.md) · [Detailed test tools](../../tests/README.md)

Run the suite **on the outer LXD host**, from the matching checkout. It enters
the selected VM itself; do not install browser tools inside client containers.
No tests in this guide export, delete or rebuild the VM.

## Prepare

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

The default without sections is `static`. Use `--list` to see selected tiers.
For a Python virtual environment, install pytest there and activate it first.
No other host tooling is installed automatically.

## Tiers

| Section | Scope / effect |
| --- | --- |
| `static` | Documentation, Python configurator/optimizer/room/regressions, Console and topology Go tests. No VM. |
| `webui` | Deterministic Node render/layout/RF/steering and Console models. No VM. |
| `browser` | Mock/local browser presentation, Console NG, sidebar, fullscreen/dividers. No live RF writes. |
| `rooms` | Every compatible room: load, initial convergence, **Play**, native associations/traffic and topology checks; geometry rooms run separately. Mutates RF. |
| `live` | Console health, full 100-client native provenance/topology/BTM/data-plane/resource checks. Mutates RF. |
| `soak` | Bounded leaf restart/steering churn, permanent radio and daemon identity checks; three cycles by default. Mutates RF. |

`all` runs those tiers in dependency order. These are functional/regression
gates, not a hardware RF-capacity certification or an unlimited endurance soak.
Failures and prerequisite blocks produce nonzero exit and are never passes.

## Live campaign

Use an idle, freshly started default room with no browser control lease,
recording or competing RF writer. Host and guest checkouts must be clean and
at the same commit. Review the source-match failure rather than bypassing it.
The full catalog can take hours; select tiers for a shorter run.

```sh
bash tests/run-prplmesh-suite.sh rooms live --yes-act --install-browser-deps
bash tests/run-prplmesh-suite.sh all --yes-act --install-browser-deps
```

Actual URLs are read from the selected VM's proxy devices. The runner pushes
the read-only room audit helpers, runs locally without SSH, and stores separate
ordinary-room and geometry-room reports. Each room driver restores the default
world. Native tiers stop/mask the room **once**, require the full 100-client
baseline, hold that state across acceptance and churn, and restore the prior
service state in cleanup, including reported restoration failures.

```sh
bash tests/run-prplmesh-suite.sh soak --yes-act --churn-iterations 10
```

Progress, per-step logs, durations, `results.tsv`, `summary.json`, source identity
and browser/room evidence go to a new `test-results/TIMESTAMP-VM/` directory.
Retain failed reports. Room counts, client identities, native ownership, fresh
metrics and traffic must agree; a green animation alone is not convergence.
For RF-specific qualification see the [assessment](../../reference/radio/virtual-rf-assessment.md).
