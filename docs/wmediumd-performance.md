# wmediumd performance

## Current decision

The lab keeps one wmediumd RF/scheduler thread and one authoritative hwsim
netlink endpoint. An optional CPU affinity provides isolation, while indexed
telemetry and inactive-override lookups reduce per-frame work. Affinity does
not parallelize the daemon.

A bounded second output thread was tested in the comparable RDK lab. Queuing
TX status caused invalid expired-cookie responses and loss. Restricting the
worker to cloned receive delivery restored correctness, but lowered throughput
and increased CPU because all operations still serialize on the same hwsim
socket. That design is not included.

## Measurement

The accepted prplMesh profile was measured in the four-vCPU
An LXD VM with six vCPUs. Eighteen WLAN client containers each
sent one ICMP echo every 20 ms to `192.168.77.1`.

| Variant | Workload | wmediumd CPU | Packet loss | Mean client RTT |
|---|---:|---:|---:|---:|
| original lookup, unpinned | idle | 11.93% | n/a | n/a |
| indexed lookup, unpinned | idle | 9.40% | n/a | n/a |
| indexed lookup, pinned | idle | 10.17% | n/a | n/a |
| original lookup, unpinned | 18 x 50 pkt/s | 23.50% | 0.032% | 5.31 ms |
| indexed lookup, unpinned | 18 x 50 pkt/s | 21.10% | 0.019% | 4.54 ms |
| indexed lookup, pinned | 18 x 50 pkt/s | 20.76% | 0.032% | 4.84 ms |

CPU is reported as a percentage of one logical CPU. The lookup change reduced
loaded CPU by 10.2% and idle CPU by 21.2% in these short samples while traffic
remained stable. Pinning had only a small loaded effect and slightly worse idle
CPU; it is an isolation control, not a throughput control.

After installing the exact repository-built binary and launcher in the live
VM, a final 18-client run used 20.10% CPU, delivered 13,065 of 13,067 echoes
(0.015% loss), averaged 4.63 ms across client RTT means, and reported zero
netlink receive drops.

## Run the benchmark

```sh
tests/wmediumd-performance.py --mode idle --duration 30

tests/wmediumd-performance.py \
  --mode ping --duration 20 --ping-interval 0.02 --client-limit 18 \
  --output /tmp/prpl-wmediumd-18x50pps.json
```

The JSON result contains process CPU, RSS, thread count, allowed CPUs, context
switches, netlink receive drops, aggregate loss, mean client RTT, and every
client result.

To reserve CPU 3 for wmediumd without restarting mesh containers:

```sh
PRPL_WMEDIUMD_CPU_AFFINITY=3 scripts/radio-lab.sh restart-medium
scripts/radio-lab.sh status
```

Do not make a CPU number the portable default; appliance hosts have different
CPU counts and workloads.

## Scale boundary

The equivalent 20-client RDK lab was stable at 50 packets/s per client and had
no netlink errors at 56 packets/s. At 67 packets/s, its medium queue grew and
loss reached 19.75%; at 100 packets/s, loss reached 66.88%. wmediumd CPU was
only 30--32%, showing that serialized kernel/netlink delivery and pending-frame
state, not user-space compute alone, defined the knee.

Future 50--100-client profiles must therefore specify aggregate offered load
and gate acceptance on queue delay, errors, and loss. Higher frame-rate scaling
would require a kernel-supported per-channel sharding boundary; multiple stock
wmediumd processes cannot safely share one hwsim registration.
