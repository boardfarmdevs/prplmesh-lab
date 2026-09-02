# Portable prplMesh appliance

`prplmesh-0831-thin.tar` is the only portable prplMesh download. The same
archive supports 20, 50, and 100 clients; there are no profile-specific release
files.

The 0831 archive is 1,777,039,360 bytes. Its SHA-256 is
`9ef007df292742ebc8c36e9405d71810c8754e7f1f802baa58b68cd9bf45f598`
and its source commit is `4eb6bcc32beff12e90328660fcd10970a4694a16`.

The archive contains an installed Ubuntu 24.04/Linux 7 LXD VM, exact source,
the local prplMesh runtime image, hwsim/wmediumd support, the shared wmediumd
Console, and the Controller UI. It contains zero provisioned nested lab instances and no selected
profile.

## Install from an empty directory

Download the tar and its adjacent checksum, then run:

```sh
sha256sum -c prplmesh-0831-thin.tar.sha256
tar -xf prplmesh-0831-thin.tar
cd prplmesh-0831-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

Use `--profile 50` or `--profile 100` on a sufficiently sized host. Import
waits for nested LXD, writes an immutable profile lock, creates the complete
roster from local inputs, and starts the lab. A missing or invalid profile is
rejected.

| Profile | vCPU | RAM | hwsim radios | Sparse disk |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 6 | 8 GiB | 40 | 160 GiB |
| 50 | 8 | 12 GiB | 72 | 160 GiB |
| 100 | 12 | 20 GiB | 120 | 160 GiB |

First boot is intentionally longer because it creates the selected roster.
Provisioning is offline: it does not clone, pull, or download runtime inputs.
Normal later boots reconstruct the existing lab.

## Site settings

Select an existing destination storage pool or LAN-facing UI address without
changing the appliance:

```sh
PRPLMESH_LXD_STORAGE=bpi-lab \
PRPLMESH_UI_HOST_IP=192.168.2.140 \
  ./import.sh --profile 50
```

Default host ports are `8090` for the wmediumd Console and `8091` for the
Controller UI. The internal NBAPI adapter is not exposed. The included README
documents instance-name and port overrides.

## Monitor and operate

Replace `20` with the selected profile:

```sh
lxc exec prplmesh-20-0831 -- journalctl -fu prplmesh-lab.service
lxc exec prplmesh-20-0831 -- prplmesh-lab-start status
lxc stop prplmesh-20-0831
lxc start prplmesh-20-0831
```

Imported appliances default to `boot.autostart=true`. The importer refuses to
overwrite an existing instance.

## Release identity

The outer `.tar.sha256` verifies the download. After extraction,
`SHA256SUMS` verifies the VM backup and every bundled instruction/metadata
file. `release.json` records schema 2, the source commit, runtime base, profile
map, sparse disk, and zero-instance offline-first-boot contract.

The archive contains no host source mount, Git credential, fixed LAN address,
or profile-specific nested inventory.
