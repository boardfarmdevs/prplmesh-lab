from collections import Counter
import json
from pathlib import Path
import subprocess

# the counter-guard room this lab's manifest names (easymesh-optimizer's
# acceptance/counter-guard-room-smoke.py runs it): its cohorts are the bound clients'
ROOT = Path(__file__).resolve().parents[1]


def test_manifest_cohorts_match_bound_world_clients_not_pool_headcount():
    prefix = ROOT / "gen" if (ROOT / "gen").is_dir() else ROOT
    manifest = json.loads((prefix / "rooms/manifests/native-counter-guard-room-profile.json").read_text())
    world = json.loads((ROOT / manifest["world"]).read_text())
    bindings = json.loads((ROOT / manifest["bindings"]).read_text())["roles"]
    selected = [bindings[role] for role, kind in world["roles"].items() if kind == "station"]
    if prefix != ROOT:
        plan = subprocess.run([str(prefix / "wlan-client-pool.sh"), "plan", "--profile", "unified"],
                              check=True, capture_output=True, text=True).stdout
        cohorts = {fields[1]: fields[2] for line in plan.splitlines()[4:] if (fields := line.split("\t"))}
    else:
        source = (ROOT / "scripts/radio-lab.sh").read_text()
        function = "client_cohort()" + source.split("client_cohort()", 1)[1].split("\n}", 1)[0] + "\n}"
        command = function + '\nfor container in "$@"; do suffix=${container##*-}; client_cohort "$((10#$suffix))"; done'
        rows = subprocess.run(["bash", "-c", command, "cohort-check", *selected],
                              check=True, capture_output=True, text=True).stdout.splitlines()
        cohorts = dict(zip(selected, rows))
    counts = Counter(cohorts[container] for container in selected)
    assert counts == {"private": 9, "iot": 1}
    assert manifest["health"]["expected_clients"] == len(selected)
    assert manifest["health"]["expected_private_clients"] == counts["private"]
    assert manifest["health"]["expected_iot_clients"] == counts["iot"]
