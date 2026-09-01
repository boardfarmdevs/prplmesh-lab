# Bare-metal deployment

Start with an x86-64 Ubuntu 24.04 host running Linux 7.0. This mode owns the
host hwsim module, wmediumd process and LXD instance namespace; do not run a
second wireless lab on the same host.

Extract the 0831 source artifact into a new directory and verify it:

```sh
tar -xjf prplmesh-lab-0831-COMMIT-source.tar.bz2
cd prplmesh-lab-0831-COMMIT
sha256sum -c artifacts/SHA256SUMS
```

Install the host packages and initialize LXD as described in
`docs/from-scratch.md`, then use the packaged prplMesh/hostap runtime archives:

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
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8091/health
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
