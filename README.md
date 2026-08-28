# prplMesh virtual-radio lab

This repository is an independent x86/LXD experiment for evaluating upstream
prplMesh with `mac80211_hwsim` and `wmediumd`. It does not use or modify the
RDK-B EasyMesh repository, images, containers, radio inventory, or runtime.

The first accepted milestone is deliberately small:

1. build upstream prplMesh reproducibly;
2. run one controller and one agent in separate LXD containers;
3. give the agent dedicated 2.4, 5, and 6 GHz hwsim radios mediated by a
   dedicated multichannel wmediumd;
4. associate one hwsim WLAN client;
5. prove controller-agent onboarding and client visibility from logs, protocol
   capture, and the prplMesh management interface.

Only after that baseline is repeatable will the lab add steering, a second
agent, and multihop. The resulting measurements will be compared with the RDK
lab using the same acceptance definitions rather than comparing screenshots.

## Layout

- `upstream/prplMesh/` — pinned official upstream source submodule.
- `docs/progress.md` — dated evidence, decisions, blockers, and results.
- `docs/architecture.md` — isolation and runtime design.
- `docs/software-architecture.md` — prplMesh controller/agent processes,
  IEEE 1905 transport, libraries, platform dependencies, and interfaces.
- `scripts/` — idempotent build and lifecycle commands.
- `manifests/` — desired controller, agent, client, radio, and medium state.
- `evidence/` — test summaries and small text artifacts; large builds and
  packet captures remain untracked.

The operator interface will be added only after the manual first milestone has
identified the actual prplMesh process and platform requirements.

Radio acceptance runs in an isolated Ubuntu 24.04/Linux 7.0 LXD virtual
machine. This keeps rev140's host kernel and the RDK lab untouched while
providing the validated 6 GHz hwsim regulatory behavior. The medium uses only
the reviewed multichannel correctness subset of the existing wmediumd work;
scenario-control and observer sockets are intentionally excluded initially.
