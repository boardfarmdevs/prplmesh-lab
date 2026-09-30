# Radio reference

[Reference home](../README.md)

The RF medium (hwsim, wmediumd, the configurator and its rooms, the Console) is
[easymesh-medium](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/README.md), checked out here as `medium/` at the commit
this lab pins; its documents describe the medium for both labs. This lab keeps
what is its own: how it selects a medium backend and how its native prplMesh
stack is qualified on the medium.

The medium's documents:

- [Virtual RF assessment and implementation roadmap](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/virtual-rf-assessment.md):
  current attributes, implemented survey/BSS Load setup and acceptance,
  Phase 3 airtime/ACK/visibility profiles, measured overhead and open gates;
  the [RDK/prpl RF data-element matrix](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/virtual-rf-assessment.md#32-rdkprpl-data-element-support-matrix)
  and [RF increments and short qualification](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/virtual-rf-assessment.md#127-rf-increments-and-short-qualification).
- [RF property coverage](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/rf-property-coverage.md): the
  property-to-room contract.
- [Console RF property guide](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/console-rf-properties.md): configured versus
  observed evidence, independent native load, freshness and protocol catalog.
- [Configurator CLI](../../medium/configurator/README.md),
  [Console installation and API](../../medium/observer/README.md).

This lab's:

- [RF property demonstrations and coverage on prplMesh](rf-property-coverage.md):
  named rooms, native counter guard, observation/abstention checks and the
  prplMesh qualification results.
- [Medium backends](medium-backends.md): the userspace and kernel data paths
  and how the lab selects one.
- [Future RF development plan](../proposals/easymesh-rf-assessment-and-development-plan.md):
  proposed M0–M9 roadmap for richer observations, neighboring networks, noise,
  overlap, collisions and qualified PHY service; not current runtime capabilities.
