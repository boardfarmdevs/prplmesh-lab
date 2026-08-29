# VirtualBox/Vagrant appliance

Install current VirtualBox 7.x and Vagrant on an Ubuntu 22.04 or 24.04 x86-64
host. Confirm nested virtualization is available. From a new empty directory,
place the `.box`, `Vagrantfile`, and their SHA-256 files together.

Import once and start:

```sh
sha256sum -c prplmesh-lab-0828-COMMIT-virtualbox.box.sha256
vagrant box add --name prplmesh/lab-0828 \
  prplmesh-lab-0828-COMMIT-virtualbox.box

PRPLMESH_UI_HOST_IP=127.0.0.1 vagrant up
```

For a browser elsewhere on the outer host's LAN, use an address owned by that
host rather than a release-specific hardcoded address:

```sh
PRPLMESH_UI_HOST_IP=192.168.2.150 vagrant up
```

The raw topology adapter is then on port 8090 and the Controller UI on 8091.
Override the host ports if another lab uses them:

```sh
PRPLMESH_UI_HOST_IP=192.168.2.150 \
PRPLMESH_TOPOLOGY_HOST_PORT=18090 \
PRPLMESH_UI_HOST_PORT=18091 \
vagrant up
```

Monitor and operate the guest:

```sh
vagrant ssh -c 'sudo journalctl -fu prplmesh-lab.service'
vagrant ssh -c 'sudo prplmesh-lab-start status'
vagrant halt
vagrant up
```

Delete the VM and optionally the imported box:

```sh
vagrant destroy -f
vagrant box remove prplmesh/lab-0828 --provider virtualbox
```
