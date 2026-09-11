# prplMesh deployment

[Operations](../docs/operations.md) owns daily lifecycle and recovery;
[current state](../docs/current-state.md) owns deployed URLs and release names.

| Deployment | Procedure |
| --- | --- |
| Portable LXD VM | [Import, profile selection and packaging](lxd-vm/README.md) |
| Dedicated Linux radio host | [Bare-metal installation](bare-metal/README.md) |
| Native source build | [From scratch](../docs/from-scratch.md) |
| Inner LXD UI and inner/outer-VM Grafana | [Monitoring bundle](lxd-vm/observability/README.md) |

The VM owns Ubuntu/Linux, nested LXD, radio inventory, wmediumd, native prplMesh,
Controller UI, Console and the live room. It needs no source-host mount.
Normal room deployments use twenty clients; larger immutable profiles have
separate resource and acceptance requirements. VirtualBox is RDK-only.

A stopped VM stays stopped after an outer-host reboot. Manually starting it
starts the lab and twenty-client room automatically. Persistent LXD proxies
expose the configured browser ports; the NBAPI adapter remains guest-loopback
only. Source builds need network access; normal thin first boot uses local
artifacts. Optional monitoring may download dependencies.
