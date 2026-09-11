# LXD UI and Grafana

[Observability reference](README.md) · [Current URLs](../../docs/current-state.md)

The full installation, Windows/Chrome enrollment, TLS, credentials, dashboards,
removal and renewal procedure lives with the installer:
[monitoring bundle](../../deploy/lxd-vm/observability/README.md).
Do not duplicate that procedure here.

From the **physical LXD host**, for an existing running appliance:

```sh
LAB_MONITORING_ALLOW_RESTART=1 \
  bash deploy/lxd-vm/observability/enable.sh VM HOST_IPV4 LAB_LABEL
```

Replace the three arguments deliberately. The explicit restart permission
allows first-time cloned-identity rotation to stop/restart the lab; schedule
maintenance. It is unnecessary for ordinary browser login. Do not reimport a
VM to enable monitoring.

The same bundle can add the **outer VM** to the existing collector:

```sh
bash deploy/lxd-vm/observability/enable-outer-metrics.sh \
  VM HOST_IPV4 HOST_CERT_DNS_NAME LAB_LABEL
```

Use the actual certificate DNS SAN. This adds verified, project-scoped
metrics-only trust, not another monitoring stack or public outer LXD API.

For future thin imports, `--monitoring` enables inner monitoring; set
`LAB_OUTER_METRICS_ADDRESS` and `LAB_OUTER_TLS_NAME` to opt into the outer
scrape too. Dependencies may need Internet access; normal thin import remains
offline. Monitoring does not enable VM autostart.

## Interpret the dashboards

- `easymesh-lxd`: inner containers, including client/mesh CPU, memory and
  interface counters. World-unavailable roles can still be running containers.
- `easymesh-lxd-outer`: outer VM **guest** resources, not physical host totals,
  QEMU RSS, temperature or fan activity.
- Prometheus targets `lxd`, `lxd-outer` and `prometheus` should be UP.
  Allow two or more thirty-second scrapes for rate panels.
- The collector stops with its VM. Independent outage monitoring requires an
  external collector. These dashboards are not subsecond optimizer profiling.

Restrict management reachability to a trusted LAN/VPN. Use per-browser LXD
identities and Grafana Viewer accounts for observers; no shared default password,
anonymous API or copied private certificate. Never package installed monitoring
secrets/data. Disable outer trust before credential renewal or removal.
