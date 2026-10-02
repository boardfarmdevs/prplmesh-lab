# prplmesh-lab: the prplMesh EasyMesh lab

<!-- labs block: the same in every repository of the EasyMesh labs, but for the Site line -->
**Site:** <https://vcpe.dev/prplmesh-lab/>
The [EasyMesh labs](https://mesh.vcpe.dev/) serve three
goals: EasyMesh optimizer development
([easymesh-optimizer](https://vcpe.dev/easymesh-optimizer/)) in a rich
virtual lab, on both stacks
([RDK EasyMesh](https://vcpe.dev/meta-cmf-bananapi-vcpe/),
[prplMesh](https://vcpe.dev/prplmesh-lab/)); unchanged OpenSync
pods as EasyMesh agents under a local controller, without the OpenSync cloud
([EMOSA](https://vcpe.dev/emosa-lab/), with the
[OpenSync lab](https://vcpe.dev/opensync-lab/)'s pods); and
EasyMesh on physical hardware
([Protocol lab](https://vcpe.dev/easymesh-lab/)). Two core
components carry them: the RF medium
([easymesh-medium](https://vcpe.dev/easymesh-medium/)) and EMOSA's
OVSDB ⇄ EasyMesh conversion. The rest is infrastructure, tools (the
[room builder](https://vcpe.dev/easymesh-room-builder/)) and learning
around them.
<!-- /labs block -->

The same EasyMesh lab as the RDK one, on native prplMesh: an LXD VM with the prplMesh
controller, four Wi-Fi Agents and a wired one, and 100 clients on simulated radios
(`mac80211_hwsim` behind multichannel wmediumd), the RF medium, the optimizer and an
interactive room. The room and the topology views match the RDK lab's; the native build,
the NBAPI metrics, the steering adapter and the deployment are this lab's own. One VM
keeps 100 client containers and rooms select the online subset (20 by default). No
screenshot or accepted BTM alone proves convergence: compare the physical association,
native ownership, fresh measurements and traffic.

## Components

| Part | What it is |
| --- | --- |
| [manifests/](manifests), [patches/](patches/README.md) | the pinned prplMesh 6.0, hostapd and dependency sources, and this lab's patches to them |
| [scripts/](scripts) | the native artifact build, the radio lab inside the VM, steering, the topology adapter's launcher |
| [deploy/](deploy/README.md) | the lab VM (`deploy/lxd-vm`: build, check, update, package, import), the guest's setup, bare-metal deployment |
| [controller-ui/](controller-ui/README.md) | the controller dashboard: a Go service around the medium's topology page |
| [topology-adapter/](topology-adapter) | the internal adapter that serves prplMesh's model to the dashboard and the optimizer |
| [rooms/](rooms/README.md) | the lab's live room: its launcher, manifests and bindings |
| [tests/](tests/README.md) | the suites: static, browser, room, native and churn |
| [explorer/](explorer/README.md) | the site: the system explorer and the room sandbox |
| [artifacts/](artifacts/README.md) | where the native runtime archives are generated (not committed) |
| `medium`, `optimizer` | easymesh-medium and easymesh-optimizer, pinned as submodules |

## Getting started

Build the native artifacts, then a VM from them, then qualify it:

```sh
git clone --recurse-submodules https://github.com/boardfarmdevs/prplmesh-lab.git
cd prplmesh-lab
deploy/lxd-vm/build-artifacts.sh       # the native artifacts, from the pinned sources
deploy/lxd-vm/build.sh build           # a named LXD VM from them
tests/run-prplmesh-suite.sh all        # the suite
```

The [build guide](docs/guides/build.md) has the host prerequisites and every step; the
[operations guide](docs/guides/operations.md) runs an installed lab.

## Documentation

The [site](https://vcpe.dev/prplmesh-lab/) has the system explorer and the room
sandbox. The documents are indexed in [docs/README.md](docs/README.md): the current
state, the architecture, the build, operations, the room manual, the tests and the
reference and records.
