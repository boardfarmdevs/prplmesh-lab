# Portable prplMesh appliance

`prplmesh-0904-thin.tar` is the current portable prplMesh download. One archive
supports 20, 50, and 100 clients; there are no profile-specific release files.

The archive contains an installed Ubuntu 24.04/Linux 7 LXD VM, the exact
prplMesh lab source, local runtime image, hwsim/multichannel-wmediumd support,
wmediumd Console, and Controller UI. It contains zero provisioned nested lab
instances and no selected profile. The adjacent checksum and the extracted
`release.json` are authoritative for archive size, SHA-256, source commit, and
runtime-base identity.

## Install from an empty directory

```sh
sha256sum -c prplmesh-0904-thin.tar.sha256
tar -xf prplmesh-0904-thin.tar
cd prplmesh-0904-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

Use `--profile 50` or `--profile 100` only on a sufficiently sized host. Import
waits for the VM agent and nested LXD, writes an immutable profile lock,
creates the complete roster from local inputs, and starts the lab. It rejects
a missing or invalid profile and never overwrites an existing instance.

| Profile | vCPU | RAM | hwsim radios | Sparse disk |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 6 | 8 GiB | 40 | 160 GiB |
| 50 | 8 | 12 GiB | 72 | 160 GiB |
| 100 | 12 | 20 GiB | 120 | 160 GiB |

First boot is longer than a normal restart because it creates the selected
nested roster. Provisioning is offline: it does not clone repositories, pull
images, or download runtime artifacts.

## Site settings

```sh
PRPLMESH_LXD_STORAGE=bpi-lab \
PRPLMESH_UI_HOST_IP=192.168.2.140 \
  ./import.sh --profile 50
```

Default host ports are `8090` for the wmediumd Console, `8091` for the
Controller UI, and `18891` for the operator-started room demo. The NBAPI
adapter stays on guest loopback. The included README documents instance-name
and port overrides.

## Monitor and operate

Replace `20` with the selected profile:

```sh
lxc exec prplmesh-20-0904 -- journalctl -fu prplmesh-lab.service
lxc exec prplmesh-20-0904 -- prplmesh-lab-start status
lxc stop prplmesh-20-0904
lxc start prplmesh-20-0904
```

Imported appliances default to `boot.autostart=true`.

## Integrity and identity

The outer `.tar.sha256` verifies the download. After extraction, `SHA256SUMS`
verifies the VM backup and every bundled instruction and metadata file.
`release.json` records schema 2, release and source identity, runtime base,
profile map, sparse disk, and the zero-instance offline-first-boot contract.

The appliance contains no host source mount, Git credential, fixed LAN
address, or profile-specific nested inventory.
