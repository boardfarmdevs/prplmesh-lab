# Reference EasyMesh optimizer

This host-side Python package is the policy reference used by the prplMesh
virtual-radio lab. It observes the controller, normalizes immutable snapshots,
applies an explainable threshold/margin/hold/cooldown policy, records a
hash-chained journal, and can optionally issue one bounded BTM steer.

The live prplMesh path is:

```text
NBAPI topology + associated RCPI
          +
Unassociated STA Link Metrics candidate RCPI
          -> normalized snapshot -> policy -> recommend
                                      |
                                      +-> explicit act -> BTMRequest -> verify
```

The optimizer never reads a `.wmd` plan, wmediumd control state, intended
target, or scenario phase. In hwsim, candidate observations are marked as
simulated-radio measurements and require `--allow-simulated-candidates`.

Root-in-VM candidate collection runs the same native `ubus` calls through
descriptor-pinned controller mount/root namespaces. LXD discovers the controller
once, not once per registration/query. Four registration workers remain bounded;
only discovery is locked. Native publication timestamps, freshness and RPC
deadlines are unchanged. Transactions record the transport and elapsed time.
Non-root hosts retain `lxc exec`. Namespace failures never silently fall back;
restart observation after a controller restart to discard its registration cache.

On compatible native builds, `_describe` advertises the optional boolean
`AddUnassociatedStation.defer_query`. Collection registers a cohort without
issuing redundant fleet-wide queries for every addition, then uses the existing
explicit `UpdateUnassociatedStationsStats` and waits for fresh native reports.
Older controllers retain their original behavior; no unsupported option is sent.

## Opt-in Native Load Policy

The default remains signal-only. Use `configs/load-aware-policy.yaml` instead
of `configs/threshold-policy.yaml` for an explicitly enabled experiment.
Live recommendation/action requires root in the lab VM and
`--candidate-provider controller`; the owned receiver stops when the command
exits. There is no additional collector in default mode.

From the repository root, copy the room manifest to a temporary JSON file, change only
`policy` to `optimizer/configs/load-aware-policy.yaml`, and start
`demo/room-demo interactive --manifest /absolute/temporary-manifest.json`
with the normal deployment arguments. Stop the existing room service first;
never run two actuating optimizers. Restart the unchanged service to return
to the default policy. The policy does not retune radios or change client
capabilities automatically.

Configure a second **same-band, different-channel** fronthaul AP first.
Default lab clients restrict `freq_list` to preset frequencies: explicitly
allow the new channel before testing BTM; merely scanning it is insufficient.
Do not retune a radio carrying the active backhaul. RDK local channel changes
also require a native operating-channel report; verify controller inventory,
not just `iw`. An agent refresh is test preconditioning, never a timed-steer
repair.

Schema-2 snapshots carry native IEEE 1905 AP utilization (0–255), station
count, packet-counter activity, receipt timestamps and provider epoch.
The receiver consumes only native AP/STA TLVs; the survey bridge supplies
provenance/liveness, **not** utilization or simulated SNR inputs. Activity
is packets/second, not offered demand or calibrated capacity. Backhaul hops
are a conservative cost guard, not a bandwidth estimate.

Strong links balance only from sustained high load to a fresh quieter
channel with viable RF and no extra wireless hop. Both AP reports must advance
after the five-second hold. One active client moves at a time, followed by
settling/cooldown. Weak links retain signal-policy protection. Missing, stale,
skewed, synthetic or epoch-mismatched observations cannot become zero load.
Reasons and evidence are recorded with each decision.

prpl subscribes once to native AP Metrics Response CMDUs on the controller's
`/tmp/beerocks/uds_broker`, covering colocated and remote APs without additional
queries. Snapshot/decision `transport` distinguishes `prpl-local-broker` from
`prpl-1905-broker`. The pinned v6 x86_64 broker's one-second publication
timestamp is retained conservatively; reading queued or cached data cannot
refresh it. Stale reports, unsupported envelopes and disconnects fail closed.
Restart the opt-in experiment after a broker restart. No extra service or port
is needed; RDK continues to capture Ethernet.

Run `PYTHONPATH=optimizer python3 tests/native-load-acceptance.py --stack prpl --output /tmp/native-load-new`
inside the VM for bounded read-only coverage, count, freshness and cleanup
checks. Reception-backed candidates and calibrated capacity remain separate work.

## Test

```sh
cd optimizer
python3 -m pytest -q
```

The deterministic suite covers normalization,
candidate collection, policies, replay, journaling, actuation, verification,
world simulation, and the prplMesh adapter.

## Use

Read-only associated observations:

```sh
python3 -m optimizer.cli observe \
  --backend prplmesh --base-url http://127.0.0.1:8092 \
  --count 5 --interval 1 --journal /tmp/prpl-observe.jsonl
```

Collect live same-band candidates and recommend without changing the mesh:

```sh
python3 -m optimizer.cli recommend \
  --backend prplmesh --base-url http://127.0.0.1:8092 \
  --candidate-provider controller --allow-simulated-candidates \
  --policy configs/threshold-policy.yaml \
  --count 10 --interval 1 --journal /tmp/prpl-recommend.jsonl
```

Actuation additionally requires both `act` and `--yes-act`; it defaults to one
attempt and uses `scripts/steer-client.sh` followed by controller verification.
Use `tests/optimizer-dynamic.sh` for the repeatable closed-loop acceptance
rather than assembling a live act experiment manually.

Offline commands remain available for plain-snapshot evaluation, replay,
deterministic world simulation, experiment matrices, and recommendation-only
backhaul/channel-width planning. Run `python3 -m optimizer.cli --help` for the
complete interface.

See [the dynamic medium and optimizer guide](../reference/optimizer/configurator.md)
for architecture, scenario operation, extension rules, evidence, and the
future two-lab partition.
