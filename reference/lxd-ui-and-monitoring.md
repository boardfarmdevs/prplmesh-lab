# prplMesh inner LXD UI, Prometheus and Grafana

The portable implementation and full step-by-step instructions are in
[deploy/lxd-vm/observability/README.md](../deploy/lxd-vm/observability/README.md).
The bundle includes setup, safe LXD reload, removal, pinned Compose services,
verified metrics-only TLS scraping, Grafana datasource provisioning and a
ready home dashboard with ten panels. No exporter is installed in a mesh/client
container; monitoring runs in two limited Docker containers inside the VM.

## Enable an existing appliance

On its physical LXD host, from this checkout:

```sh
LAB_MONITORING_ALLOW_RESTART=1 bash deploy/lxd-vm/observability/enable.sh prplmesh-20-0906 HOST_IPV4 my-prpl-lab
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

## Open and authenticate

- `https://HOST_IPV4:18892/`: full inner LXD UI, not the outer VM host UI.
- `https://HOST_IPV4:18893/`: Grafana, username `admin`, provisioned dashboard home.
- Retrieve Grafana's generated password privately using
  `lxc exec VM -- cat /opt/easymesh-observability/secrets/grafana-admin-password`.
- Follow LXD UI's browser-certificate flow; obtain a one-use trust token with
  `lxc exec VM -- lxc --force-local config trust add --name=lab-browser`.

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

## Validation scope

This change provides reusable source setup for both RDK and prplMesh.
Runtime deployment and browser/metrics testing are restricted to RDK on rev140.
No prplMesh VM on rev120 or RDK VM on rev150 is changed or runtime-tested here.
