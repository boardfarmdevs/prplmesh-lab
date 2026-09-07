# RDK and prplMesh nested-LXD monitoring

Run `enable.sh` on the physical LXD host; it runs `setup.sh` inside the Ubuntu
appliance VM. Never run `setup.sh` in a Yocto/Alpine container or on the outer host.

This source-only bundle works for both RDK (`/etc/default/easymesh-lab`) and
prplMesh (`/etc/default/prplmesh-lab`) appliances. It needs their existing LXD
snap and Docker Compose, but does not depend on a mesh stack or add lab nodes.

## Browser-ready deployment

From the physical LXD host, for an existing running VM:

```sh
LAB_MONITORING_ALLOW_RESTART=1 bash observability/enable.sh rdkeasymesh-20-0906 192.168.2.140 rev140-rdk-0906
```

For a future thin release, `bash import.sh --profile 20 --monitoring` invokes
the same helper after normal VM setup. The prplMesh importer supports the
same flag. Omit it to retain the base thin release's offline/no-monitoring
contract. Monitoring requires image downloads or preloaded matching images.
Only source templates are shipped, never an enabled installation's secrets.

If optional setup fails after an import has created the VM, do not import it
again. Fix the reported dependency/configuration, rerun `enable.sh` for that
existing VM, then start `easymesh-lab.service` / `easymesh-room-demo.service`
(RDK) or `prplmesh-lab.service` / `prplmesh-room-demo.service` (prplMesh) with
`lxc exec VM -- systemctl start ...`.

- LXD UI: `https://HOST_IP:18892/` (inner LXD, not the physical host's LXD).
- Grafana: `https://HOST_IP:18893/` (the LXD dashboard is the home page).
- Override ports with `LAB_LXD_UI_PORT` and `LAB_GRAFANA_PORT` when labs share
  a physical host. Use explicit host IPv4, never wildcard public exposure.
- Prometheus and the authenticated LXD metrics endpoint remain VM-loopback
  only; no host-facing Prometheus port is created.

First network enablement of an unexposed clone requires a new LXD identity and
a planned lab restart. The explicit variable above permits that maintenance;
allow several minutes for the lab to return. Without it, setup refuses to
restart an active lab. Repeated setup with an already reviewed identity does
not restart the lab. A fresh thin import enables monitoring before starting
the selected lab, avoiding a second provisioning cycle.

The helper reserves NAT proxy devices `lab-lxd-ui` and `lab-grafana`, binds
services to the VM's management IPv4, and leaves VM autostart unchanged.
It refuses conflicting owned proxy settings and existing unrelated LXD
listeners. Repeating it preserves matching credentials and data.

On older RDK appliances, setup also corrects the known Boardfarm checks that
counted every Docker container. They now inspect only `dhcp-cpe1` and `wan-cpe1`,
so adding monitoring does not trigger destructive WAN reconstruction at the
next lab restart. Original scripts are backed up under `state/rdk-boardfarm-backups`.
This compatibility repair is not a mesh-stack change and is not applied to prplMesh.

## First login

The lab generates self-signed server certificates. Verify their fingerprints
through your trusted host shell before accepting/importing them in the browser:

```sh
lxc exec VM -- openssl x509 -in /var/snap/lxd/common/lxd/server.crt -noout -fingerprint -sha256
lxc exec VM -- openssl x509 -in /opt/easymesh-observability/secrets/grafana.crt -noout -fingerprint -sha256
```

For LXD, follow the UI's browser-certificate generation/import instructions.
Create a short-lived enrollment token from the trusted host shell, then paste
it into the UI. Do not publish tokens or private browser certificates:

```sh
lxc exec VM -- lxc --force-local config trust add --name=lab-browser
```

This grants management access to the inner VM's LXD, including start/stop and
console operations. Use only for trusted lab operators. Other users should
receive deliberately restricted LXD identities rather than this admin token.

For Grafana, sign in as `admin` with the generated per-VM password:

```sh
lxc exec VM -- cat /opt/easymesh-observability/secrets/grafana-admin-password
```

Change it using Grafana after login, and create Viewer-role users for
read-only consumers. No anonymous access or shared default password is enabled.
The provisioned dashboard has lab/project/container filters, CPU, memory,
network interfaces, disk I/O, filesystem free space, process and OOM panels.
`100%` CPU means one core; memory includes cache. Interface traffic is container
traffic, not an EasyMesh end-to-end throughput or RF-quality measurement.

## Resource and security boundary

Prometheus and Grafana use Docker host networking inside the VM, each capped
at 512 MiB and 0.5 CPU. Grafana also uses `GOMEMLIMIT=256MiB`, a Go runtime
soft target leaving headroom below the hard container cap for mapped binaries
and other memory. Without that target, repeated dashboard loads hit the 512 MiB
cap during rev140 validation. Retention is seven days or 1 GB of TSDB blocks; WAL,
Grafana data and image layers need additional space. The 30-second scrape
interval is shared with dashboard rate queries. No privileged container,
Docker/LXD socket mount or per-client exporter is used.

Prometheus has a metrics-only client certificate and verifies LXD's server
certificate. On the first network-enabled installation, if LXD had no HTTPS
or metrics listener, setup replaces the cloned builder's server identity with
a unique per-VM key/certificate. Its maintenance helper stops active room/lab
units while LXD is still available, restarts LXD, then restores those units.
Do not substitute a plain live daemon reload: the snap's restart can cascade
through `Requires=` dependencies and deadlock lab shutdown. `RestartMode=direct`
did not prevent that on the tested snap, so it is not used as a workaround.
Previously exposed
LXD installations keep their existing identity. Server certificates and the
metrics client certificate expire after one year; renew deliberately before
expiry and update Prometheus's trust anchor if the LXD certificate changes.

## Local-only installation

```sh
sudo bash setup.sh my-lab
cd /opt/easymesh-observability
sudo docker compose config --quiet
sudo docker compose pull
sudo docker compose up -d
```

`setup.sh` alone does not start monitoring. It installs copies
under `/opt/easymesh-observability`, generates local credentials, trusts only
a metrics certificate, and defaults to loopback HTTPS listeners. Docker uses
host networking to reach those listeners without adding a bridge or LXD node.
There is no Docker/LXD socket mount, privileged exporter or nested-container agent.

## Stop and export safely

```sh
lxc exec VM -- bash /opt/easymesh-observability/disable.sh
lxc config device remove VM lab-lxd-ui
lxc config device remove VM lab-grafana
```

Disable restores only owned listener settings and revokes the metrics
certificate; it keeps data and credentials. It does not restore an old cloned
server key. Export guards reject a managed monitoring installation: it contains
per-installation credentials and persistent time-series data. Disable and clean
it first. For a deliberately clean export, after backing up wanted data,
remove the stopped project's Docker volumes and `/opt/easymesh-observability`,
and revoke browser identities/tokens through `lxc config trust`/`lxc auth`.
Ship these templates only. Do not copy an installed `/opt` directory between labs.

Official references: [LXD UI enrollment](https://documentation.ubuntu.com/lxd/latest/howto/access_ui/),
[LXD metrics](https://documentation.ubuntu.com/lxd/latest/metrics/),
[Grafana HTTPS](https://grafana.com/docs/grafana/latest/setup-grafana/set-up-https/).
