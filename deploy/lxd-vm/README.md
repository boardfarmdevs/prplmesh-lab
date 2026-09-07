# prplMesh LXD-VM appliance

LXD VM is the primary portable deployment. It keeps the Linux 7 radio host,
nested containers, hwsim/wmediumd, prplMesh services, and UIs within one VM.

## Use the universal appliance

Start with `prplmesh-0904-thin.tar` and its adjacent checksum in an empty
directory:

```sh
sha256sum -c prplmesh-0904-thin.tar.sha256
tar -xf prplmesh-0904-thin.tar
cd prplmesh-0904-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
PRPLMESH_UI_HOST_IP=192.168.2.140 ./import.sh --profile 20
```

The same archive supports all profiles:

| Profile | vCPU | RAM | hwsim radios | Sparse disk |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 6 | 8 GiB | 40 | 160 GiB |
| 50 | 8 | 12 GiB | 72 | 160 GiB |
| 100 | 12 | 20 GiB | 120 | 160 GiB |

Use `--profile 50` or `--profile 100` only on a sufficiently sized host. The
choice is mandatory and immutable. To use another profile, import the universal
archive as a different instance.

The importer refuses to overwrite an existing instance. It reseeds the VM,
waits for both the outer VM agent and nested LXD API, writes the profile lock,
adds site-specific proxy devices, and starts offline first-boot provisioning.
The profile cannot be published while nested LXD is unavailable. Slow hosts
may adjust `PRPLMESH_NESTED_LXD_READY_ATTEMPTS` and
`PRPLMESH_NESTED_LXD_READY_INTERVAL`.

## Site settings

The defaults use outer LXD network `lxdbr0`, its default storage pool, and host
ports `8090`, `8091`, and `18891`. Override them without changing the appliance:

```sh
PRPLMESH_LXD_STORAGE=bpi-lab \
PRPLMESH_UI_HOST_IP=192.168.2.140 \
PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT=18090 \
PRPLMESH_UI_HOST_PORT=18091 \
PRPLMESH_ROOM_DEMO_HOST_PORT=18892 \
PRPLMESH_VM_NAME=my-prplmesh-lab \
  ./import.sh --profile 50
```

The selected storage pool must already exist. The source host's pool name is
provenance only and is not imposed on the destination.

## First boot and operation

First boot creates the selected roster from the local `prpl-runtime-local`
image. It does not clone repositories or download runtime artifacts. Monitor
it with the selected instance name:

```sh
lxc console prplmesh-20-0904 --show-log
lxc exec prplmesh-20-0904 -- journalctl -fu prplmesh-lab.service
lxc exec prplmesh-20-0904 -- prplmesh-lab-start status
```

When ready, the wmediumd Console is on host port `8090`, the Controller UI is
on `8091`, and the room-demo proxy is on `18891`. The room server is
started by `prplmesh-room-demo.service` for the 20-client profile; stop that
service before starting a manual `demo/room-demo` session. The NBAPI adapter
is internal on guest loopback port `8092`. Open
`http://HOST_IP:18891/viewer/?mode=interactive` for the live room and its
built-in manual. The release's `INTERACTIVE-0906.md` covers credentials,
automatic world loading, fixed-pool presence and RF recovery.
Normal lifecycle is:

```sh
lxc stop prplmesh-20-0904
lxc start prplmesh-20-0904
lxc config get prplmesh-20-0904 boot.autostart
```

Imported appliances default to `boot.autostart=false`. Manually starting the
VM starts its nested lab and, for the 20-client profile, its interactive room.
The VM does not start automatically when the outer host reboots. Deleting it is
destructive and must be explicit:

```sh
lxc delete prplmesh-20-0904
```

## Release engineering

Normal users do not need a source checkout or the build commands below. A
release builder creates a ready VM from clean, checksummed inputs:

```sh
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_LXD_STORAGE=default \
PRPL_RUNTIME_DEPS_ARCHIVE=/absolute/path/prpl-runtime-deps-6.0.0.tar.gz \
PRPL_INSTALL_ARCHIVE=/absolute/path/prpl-install-nl80211-6.0.0.tar.gz \
PRPL_HOSTAP_ARCHIVE=/absolute/path/hostap-runtime-2.10.tar.gz \
  deploy/lxd-vm/build.sh build
PRPLMESH_LAB_PROFILE=20 deploy/lxd-vm/build.sh check
```

Convert an accepted ready VM into the single universal release:

```sh
PRPLMESH_RUNTIME_BASE_COMMIT=READY-COMMIT \
PRPLMESH_LAB_PROFILE=20 \
PRPLMESH_VM_NAME=READY-VM \
PRPLMESH_THIN_CONFIRM=READY-VM \
  deploy/lxd-vm/package-thin.sh release/0904
PRPLMESH_RELEASE_ID=0904 \
  deploy/lxd-vm/package-release.sh release/0904/prplmesh-0904-thin
```

Thin conversion removes provisioned nested instances from the source VM,
retains the verified local runtime image and exact source, and exports a
stopped instance-only backup. It emits `prplmesh-0904-thin.tar`, its adjacent
`.sha256`, schema-2 `release.json`, inner `SHA256SUMS`, and this README.
The bundle also includes `RELEASE-NOTES.md` for the delivered checkpoint.
## Optional container management and metrics

Newly packaged releases accept `bash import.sh --profile 20 --monitoring`.
For an existing running VM, execute
`bash observability/enable.sh VM HOST_IPV4 LABEL` on its physical LXD host.
This installs the full bundled inner LXD UI and a provisioned Grafana container
dashboard on HTTPS ports 18892 and 18893. Authentication is required, Prometheus
stays private, and VM autostart is unchanged. Omit the flag for the original
offline/no-monitoring import. Existing immutable release archives are unchanged.
See [first login and resource limits](observability/README.md) and the
[detailed reference](../../reference/lxd-ui-and-monitoring.md).
This source support is shared with RDK; runtime deployment/testing for this
change is RDK on rev140 only, not the prplMesh lab on rev120.
