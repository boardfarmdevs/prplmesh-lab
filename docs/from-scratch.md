# Build the prplMesh virtual-radio lab from source

This procedure starts with a dedicated x86-64 Ubuntu 24.04 host running a
Linux 7.0 kernel. It downloads pinned upstream source, applies only the patches
stored in this repository, creates a reusable LXD runtime image, provisions the
fixed hwsim inventory and starts the accepted four-agent/20-client profile.

The host may be a physical machine or a virtual machine with nested
virtualization. Do not share its hwsim module or LXD instance names with another
wireless lab.

## 1. Install host tools

Install the build, radio and UI dependencies:

```sh
sudo apt update
sudo apt install -y \
  build-essential ca-certificates dpkg-dev git golang-go iw jq \
  libconfig-dev libnl-3-dev libnl-genl-3-dev libnl-route-3-dev \
  linux-headers-"$(uname -r)" meson ninja-build pkg-config python3

command -v lxc >/dev/null || sudo snap install lxd
sudo usermod -aG lxd "$USER"
```

Log out and back in after adding the LXD group. Initialize an otherwise unused
LXD installation once:

```sh
lxc info >/dev/null 2>&1 || lxd init --auto
```

`build-hwsim.sh` obtains the source matching the installed Ubuntu kernel.
Enable `deb-src` in the Ubuntu deb822 source file by changing its `Types:` line
from `Types: deb` to `Types: deb deb-src`, then refresh the index:

```sh
sudoedit /etc/apt/sources.list.d/ubuntu.sources
sudo apt update
```

Confirm that the host is suitable:

```sh
scripts/preflight.sh
```

## 2. Build and provision

From the repository root:

```sh
scripts/build-all.sh
```

The nested management network uses `1.1.1.1` and `1.0.0.1` by default so its
containers do not depend on a host-local resolver stub. Environments that
require different resolvers can supply a comma-separated list:

```sh
PRPL_DNS_SERVERS=192.0.2.53,192.0.2.54 scripts/build-all.sh
```

The command performs these reproducible stages:

1. creates an Ubuntu 22.04 LXD build container;
2. checks out prplMesh 6.0.0 and hostap at the commits in
   `manifests/lab.env`;
3. applies the repository's native-NL80211 prplMesh patches;
4. emits and verifies the three ignored archives in `artifacts/`;
5. creates the sanitized `prpl-runtime-local` LXD image;
6. builds pinned multichannel wmediumd and the Linux 7.0 hwsim module; and
7. creates the stable 40-radio, five-mesh-node, 20-client inventory.

The script does not start the mesh. Build and provisioning are intentionally
separate from the repeatable runtime lifecycle.

## 3. Start and accept the lab

```sh
sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh start
sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh clients

sudo scripts/topology-visualizer.sh start
sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  tests/run-acceptance.sh
```

Install the optional host EasyMesh Controller UI after the topology adapter on
port 8090 is healthy:

```sh
controller-ui/install.sh
curl -fsS http://127.0.0.1:8091/health | jq .
```

Open `http://HOST-IP:8091/`. The raw NBAPI topology adapter remains available
at `http://HOST-IP:8090/`.

## 4. Stop, restart and rebuild

Everyday lifecycle does not rebuild artifacts or reassign radios:

```sh
sudo scripts/radio-lab.sh status
sudo scripts/radio-lab.sh stop
sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh start
sudo PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  scripts/radio-lab.sh clients
```

Use `scripts/build-all.sh` again only after changing a source revision, patch,
kernel or runtime dependency. Generated archives can always be deleted and
rebuilt; no required source is stored only in `artifacts/`.
