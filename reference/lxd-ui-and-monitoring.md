# prplMesh LXD UI, container and outer-VM monitoring

The portable implementation and full step-by-step instructions are in
[deploy/lxd-vm/observability/README.md](../deploy/lxd-vm/observability/README.md).
The bundle includes setup, safe LXD reload, removal, pinned Compose services,
verified metrics-only TLS scraping, Grafana datasource provisioning and a
ready home dashboard with ten panels. No exporter is installed in a mesh/client
container; monitoring runs in two limited Docker containers inside the VM.

## Enable an existing appliance

On its physical LXD host, from this checkout:

```sh
LAB_MONITORING_ALLOW_RESTART=1 bash deploy/lxd-vm/observability/enable.sh prplmesh-20-0908 HOST_IPV4 my-prpl-lab
```

The explicit variable permits the first identity-rotation maintenance restart
of an active lab; allow several minutes. Omit it to refuse any such restart.
Repeated setup preserves the identity. A fresh thin import enables monitoring
before starting the lab, so it does not provision the roster twice.

Replace `HOST_IPV4` with the physical host's reachable IPv4 and the VM name
with the actual name from `lxc list`. Do not run this inside an Alpine mesh
container. The helper discovers the guest's management address, installs into
`/opt/easymesh-observability`, starts monitoring and adds two outer NAT proxies.
For future newly packaged thin releases, use
`bash import.sh --profile 20 --monitoring`. Without the flag the original
offline import contract is unchanged. Existing 0906 archives are not modified.

Explicit enablement now checks guest dependencies before setup. On a managed
Ubuntu 24.04 lab VM, missing Docker/Compose, curl, OpenSSL, jq or Python packages
are installed using apt; this needs repository access. Other guest versions
require operator-provided dependencies. Already provisioned guests take the
read-only dependency fast path. This does not add network access to an import
without `--monitoring` or change existing immutable archives.

## Open and authenticate

- `https://HOST_IPV4:18892/`: full inner LXD UI, not the outer VM host UI.
- `https://HOST_IPV4:18893/`: Grafana, username `admin`, provisioned dashboard home.
- Retrieve Grafana's generated password privately using
  `lxc exec VM -- cat /opt/easymesh-observability/secrets/grafana-admin-password`.
- Follow the modern LXD UI's browser-certificate flow; first review
  `lxc exec VM -- lxc auth group show local:admins`, then create an identity token:
  `lxc exec VM --mode=interactive -- lxc auth identity create local:tls/lab-browser --group admins`.

For Windows PowerShell over SSH, also allocate its terminal with `ssh -t`:

```powershell
ssh -t rev@HOST "lxc exec local:VM --mode=interactive -- lxc auth identity create local:tls/windows-chrome-ui --group admins"
```

Replace HOST/VM with the actual deployment. Both terminal layers prevent the
LXD 6.9 command waiting for nonterminal certificate input. The portable bundle
guide covers Chrome certificate import, group provisioning, token endpoint
differences, and read-only troubleshooting. `config trust add` tokens belong
to the legacy `/1.0/certificates` endpoint, not the modern identity endpoint.
Metrics-only certificate enrollment still correctly uses `config trust add`.
Use a fresh browser identity name; do not delete an existing working identity.

Grafana is `admin` plus its generated per-VM password, not `admin/admin`.
The secret file initializes the account only once; after a password change,
use the changed password. Follow account recovery rather than deleting data
or recreating services. First-login troubleshooting needs no lab restart.

Verify self-signed server fingerprints before browser acceptance; commands
are in the bundle guide. LXD enrollment grants administrative management access.
Use Grafana Viewer accounts for observers and protect management ports with a
trusted LAN/VPN. Override `LAB_LXD_UI_PORT` and `LAB_GRAFANA_PORT` for co-located
labs. Prometheus 9090 and authenticated LXD metrics 8444 are VM-loopback-only.

Select lab/project/container filters to inspect CPU, memory including cache,
per-interface traffic, disk I/O, filesystem availability, processes and OOMs.
Allow two or more 30-second scrapes for rates. Compare the running-container
count with the inner `lxc list`; unavailable world roles are still provisioned
containers unless actually stopped. This measures container resources, not
radio SNR, client steering quality, host resources or Boardfarm Docker traffic.

## Lifecycle and safety

If the optional outer scrape below is enabled, run
`bash deploy/lxd-vm/observability/disable-outer-metrics.sh VM` on the host first.
The VM-side disable refuses while outer state remains to avoid leaving trusted
metrics credentials on the physical host.

Each monitoring service is capped at 512 MiB and 0.5 CPU; Prometheus retains
seven days or 1 GB of data blocks, plus WAL/head and image/Grafana storage.
No root/privileged exporter or administrative socket mount is used. Per-VM
credentials are generated rather than shipped, and certificates last one year.
First network setup can replace an unexposed cloned server identity. It stops
active room/lab units while LXD remains available, restarts LXD, then restores
the units. This avoids the dependency/shutdown deadlock observed with plain
live reloads. Do not substitute an ordinary LXD reload during a demonstration.

The bundle guide includes TLS/target checks, credential renewal, repeated
setup, disabling, proxy removal and cleanup. Exporters reject an enabled
installation directory to prevent accidentally distributing secrets/data.
Outer VM `boot.autostart` is never changed by monitoring setup.

## Optional appliance VM metrics in the same Grafana

After the normal monitoring setup, run on the physical LXD host:

```sh
bash deploy/lxd-vm/observability/enable-outer-metrics.sh \
  VM HOST_IPV4 HOST_CERT_DNS_NAME my-prpl-lab
```

Use the actual DNS SAN from the host's existing public LXD server certificate,
not an arbitrary name. The helper enables only an authenticated metrics listener
(default 8444), verifies TLS, and trusts the VM's public metrics certificate as
metrics-only, restricted to its outer project. Its private key stays in the VM.
`LAB_OUTER_PROJECT` and `LAB_OUTER_METRICS_PORT` override their defaults.
Restrict listener reachability to the VM/management network. Conflicting or
unauthenticated listeners are refused; the full outer LXD API is not exposed.

The added job `lxd-outer` retains only the exact VM/project/type. Open Grafana's
**EasyMesh outer LXD VM** dashboard, UID `easymesh-lxd-outer`, with the existing
login. The nested dashboard remains home. Outer CPU capacity is counted from
per-vCPU idle series, avoiding the sometimes-zero effective-CPU gauge. Guest
memory is `MemTotal - MemAvailable`; absent metric families show No data.
These are guest VM metrics, not physical-host totals or QEMU RSS. The in-VM
collector itself stops if the VM stops; continuous outage monitoring needs an
independent collector. No extra exporter or monitoring service is installed.

Setup validates with the running promtool, verifies VM metrics and target UP,
reloads only Prometheus via SIGHUP, and lets Grafana discover its new dashboard.
It preserves the live bind-mounted config inode, saves private backups and
attempts rollback on failure. Inspect any reported rollback failure rather
than restarting the lab. There is no LXD/Grafana/lab/VM restart or autostart change.
Managed outer settings persist across normal setup reruns.

For future thin deployments, opt in through the existing importer:

```sh
LAB_OUTER_METRICS_ADDRESS=HOST_IPV4 LAB_OUTER_TLS_NAME=HOST_CERT_DNS_NAME \
  bash import.sh --profile 20 --monitoring
```

Omitting the outer address keeps monitoring nested-only. Do not reimport an
existing lab to enable this. Before certificate renewal or removal, disable
outer first; this removes the job/dashboard and revokes the recorded outer
trust while retaining the host listener for other consumers. Review other
scrapers before manually removing a listener originally created by this setup.
Full prerequisites, checks, rollback and renewal steps are in the portable
[bundle guide](../deploy/lxd-vm/observability/README.md#optional-outer-vm-dashboard).

## Validation scope

On 2026-09-09 both layers are enabled and scrape-verified for RDK 0908 on
rev140 and prplMesh 0908 on rev150. `lxd`, `lxd-outer` and `prometheus` targets
are UP in both VMs; both Grafana health endpoints report a healthy database.

| Lab | Inner LXD UI | Grafana, inner and outer dashboards |
| --- | --- | --- |
| RDK | <https://192.168.2.140:48892/ui/> | <https://192.168.2.140:48893/> |
| prplMesh | <https://192.168.2.150:18892/ui/> | <https://192.168.2.150:18893/> |

Dashboard UIDs are `easymesh-lxd` and `easymesh-lxd-outer`. These checks do not
replace browser certificate enrollment or prove physical-host cooling health.
The first prpl enablement required its documented identity-rotation lab restart;
it completed before the new room measurements. No native metrics intervals
were changed. Later outer-only setup does not restart the lab.

Outer setup now accepts a pinned LXD leaf certificate with OpenSSL partial-chain
verification, preserving hostname and expiry checks, and passes project scope
in the raw query URL rather than an unsupported `lxc query --project` flag.
TLS verification and metrics authentication remain mandatory. These are source
and live-deployment updates, not repackaged thin tarballs.
