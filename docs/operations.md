# Install and operate prplMesh

[Documentation home](README.md) · [Current deployment](current-state.md)

## Install once

Use the [LXD appliance guide](../deploy/lxd-vm/README.md) for checksummed thin
import and port overrides. 0916 has one fixed 100-client pool; the default
room selects 20 online and other rooms select their own subset. There is no
VM size profile. Allow eight vCPUs and 16 GiB RAM for the appliance.
For native builds use [the build guide](build/README.md); for a dedicated direct
radio host use [bare metal](../deploy/bare-metal/README.md).

Thin provisioning uses local artifacts. Source builds and optional monitoring
dependencies need Internet access. Do not reimport an existing VM to recover
a URL or add [monitoring](../reference/observability/monitoring.md).

## Everyday lifecycle

On the physical LXD host, replace the name with the actual selected instance:

```sh
source deploy/lxd-vm/lab-config.sh demo-a
VM=$PRPLMESH_VM_NAME
lxc config get "$VM" boot.autostart
lxc start "$VM"
lxc exec "$VM" -- systemctl is-active prplmesh-lab.service prplmesh-room-demo.service
lxc exec "$VM" -- journalctl -u prplmesh-lab.service -u prplmesh-room-demo.service -n 80 --no-pager
```

Start only a stopped VM; `lxc stop "$VM"` performs normal shutdown.
Imports default to `boot.autostart=false`. Once manually started, the VM's lab
and room services come up automatically; there is no separate room launch.

## Browser use and reboot recovery

Open the room and topology from current state. Load a room, wait for apply,
then Play or drag. See the [room manual](live-room-demo/README.md).

Proxy devices are persistent LXD configuration. Inspect these before changing
forwarding after a reboot:

```sh
lxc config device show "$VM"
lxc exec "$VM" -- ip -4 address
lxc exec "$VM" -- systemctl --failed
lxc exec "$VM" -- curl -fsS http://127.0.0.1:8891/api/demo/state
lxc exec "$VM" -- curl -fsS http://127.0.0.1:8092/api/topology
```

If guest services work but host URLs do not, check bind address, proxy target,
guest address and firewall. If guest services fail, diagnose their journals.
Do not add duplicate proxies or replace the native topology with fake entries.

## Tests and recovery

The guest repository is `/opt/prplmesh-lab`. Stop
`prplmesh-room-demo.service` before standalone acceptance/scenario tools so the
room cannot change RF concurrently. Restore it afterward even on test failure.
The appliance `build.sh check` path can start the lab unit, which wants the
room: verify the room is stopped **after** that startup, or run native acceptance
directly against an already-active lab with the room stopped.

For room-specific tests, leave its service running and use
[the browser acceptance plan](../reference/testing/room-acceptance.md).
Do not run a second conductor or RF-assisted manual steer alongside it.

The privileged room provider pins the native controller's mount namespace for
direct ubus calls. If the native controller container is restarted independently,
restart the room service afterward. A dead or replaced namespace fails closed;
it must not reuse registrations from the previous controller generation.

Recovery verifies journal, daemon generation and stable inventory before
restoring RF/client presence. Preserve a rejected journal and diagnose the
mismatch; do not delete ownership evidence or restart everything to pass a case.
Delete only positively identified obsolete VMs after preserving wanted evidence.
