# prplMesh documentation

Read the guide for your subsystem; the reference is not a required reading list.
This is prplMesh's equivalent of RDK's `doc/easymesh/README.md`.

| Task / subsystem | Guide |
| --- | --- |
| Find running services, downloads and known limits | [Current state](current-state.md) |
| Install, start, stop or recover | [Operations](operations.md) |
| Understand the native stack and radio host | [Architecture](architecture.md) |
| Use the room and topology | [Room manual](live-room-demo/README.md) |
| Choose a short demonstration | [Room catalog](../reference/rooms/catalog.md) |
| Develop or diagnose external policy | [Optimizer reference](../reference/optimizer/README.md) |
| Understand RF and the medium | [Radio reference](../reference/radio/README.md) |
| Demonstrate every RF property and its policy boundary | [RF coverage](../reference/radio/rf-property-coverage.md) |
| Open LXD UI and inner/outer Grafana dashboards | [Monitoring](../reference/observability/monitoring.md) |
| Build native artifacts, then a named VM | [Build guide](build/README.md), [legacy entrypoint](from-scratch.md) |
| Validate changes and room convergence | [Test tiers and runner](test/README.md), [testing reference](../reference/testing/README.md) |
| Explore radios, packet paths and RF evidence | [Console NG manual](wmediumd-console-ng.md) |
| Find detailed contracts and proposals | [Reference index](../reference/README.md) |

## Keeping this documentation small

- Update one owning subsystem guide instead of adding a document per fix/chat.
- Keep deployed URLs, release locations and limitations only in current state.
- Component READMEs own CLI/install instructions; link rather than copy them.
- Put contracts in a reference category and add them to that category's index.
  Proposed work is explicitly labeled under `reference/proposals/`.
- Store raw JSON, logs, screenshots, videos and dated test reports with external
  release/run evidence, retaining revisions, world hashes and failures.
  Git history preserves superseded narratives; do not create an archive dump
  in the active documentation tree.
- After implementation, replace proposals with the actual contract and remove
  completed milestones. Keep shared UI semantics aligned with RDK, but retain
  backend-specific commands and qualifications locally.
- Run `python3 tests/test_documentation.py` before submitting docs changes.
  It checks local links, reference indexing and introductory-document budgets.
