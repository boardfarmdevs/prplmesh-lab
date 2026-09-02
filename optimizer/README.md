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

## Test

```sh
cd optimizer
python3 -m pytest -q
```

The current suite has 71 deterministic tests covering normalization,
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

See [the dynamic medium and optimizer guide](../docs/optimizer-configurator.md)
for architecture, scenario operation, extension rules, evidence, and the
future two-lab partition.
