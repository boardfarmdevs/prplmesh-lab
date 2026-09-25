# Bare-metal deployment

Start with an x86-64 Ubuntu 24.04 host running Linux 7.0. This mode owns the
host hwsim module, wmediumd process and LXD instance namespace; do not run a
second wireless lab on the same host.

Use the canonical source branch in a new directory:

```sh
git clone --branch main https://github.com/boardfarmdevs/prplmesh-lab.git prplmesh-lab
cd prplmesh-lab
```

Install the host packages and initialize LXD as described in
[the source guide](../../docs/from-scratch.md). Build the native artifacts there,
or copy the three checksummed prplMesh/hostap archives and their `SHA256SUMS`
from an accepted release into `artifacts/`, then install them:

```sh
scripts/preflight.sh
scripts/install-from-artifacts.sh
sudo deploy/guest/install-service.sh "$PWD"
sudo systemctl start prplmesh-lab.service
```

Watch cold start and check the result:

```sh
journalctl -fu prplmesh-lab.service
deploy/guest/prplmesh-lab-start status
curl -fsS http://127.0.0.1:8090/api/v1/health
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8092/health
```

Daily lifecycle is:

```sh
sudo systemctl start prplmesh-lab.service
sudo systemctl stop prplmesh-lab.service
sudo systemctl restart prplmesh-lab.service
deploy/guest/prplmesh-lab-start status
```

Removal is deliberately explicit:

```sh
sudo systemctl disable --now prplmesh-lab.service
sudo scripts/radio-lab.sh stop
```

Deleting nested containers, images or the repository is a separate destructive
choice and is not performed by the service uninstaller.
