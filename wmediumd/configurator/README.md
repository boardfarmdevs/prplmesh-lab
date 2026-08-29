# wmediumd configurator

This Python package turns auditable scenario source into live atomic wmediumd
updates. It discovers the prplMesh LXD inventory, freezes role-to-radio
bindings, compiles deterministic event plans, reads back every generation, and
restores the exact captured medium state on success or interruption. It never
restarts wmediumd or a mesh node.

prplMesh mesh nodes expose separate permanent 2.4, 5, and 6 GHz hwsim PHYs.
The inventory retains those per-band identities; a scenario link without an
explicit band follows the bound station's current band.

## Test and inspect

```sh
cd wmediumd/configurator
python3 -m pytest -q
worlds/build-goldens.sh --check
python3 -m wmdcfg.cli status
python3 -m wmdcfg.cli inventory -o /tmp/prpl-inventory.json
```

The current suite has 27 passing tests and one live-socket test that skips when
no compatible daemon is present.

## Compile and run

```sh
python3 -m wmdcfg.cli compile scenarios/two-ap-crossover.wmd \
  --inventory /tmp/prpl-inventory.json \
  --bind client=prpl-client-01 \
  --bind ap_a=prpl-controller \
  --bind ap_b=prpl-agent-01 \
  -o /tmp/prpl-crossover.plan.json

python3 -m wmdcfg.cli run /tmp/prpl-crossover.plan.json
```

Every station/AP pair must be initialized in the first phase. All live plans
require `protect backhaul` and `restore captured`. Run artifacts below
`/tmp/wmdcfg-runs` contain the frozen plan, medium generations, observations,
health gates, restoration proof, and summary.

The `worlds/` frontend provides checked-in deterministic 2D layouts, mobility,
presence intervals, walls, asymmetry, and per-band golden timelines. It is
evaluator stimulus, never optimizer input.

Use this associated-metric acceptance to watch RCPI fall and recover:

```sh
wmediumd/configurator/run-rcpi-monitor.sh prpl-client-01
```

Use `tests/optimizer-dynamic.sh` for the closed loop from scenario through
prplMesh telemetry, policy, optional BTM action, verification, and restore.
See [the full guide](../../docs/optimizer-configurator.md).
