import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    physical = [{
        "id": f"02:00:00:27:{ordinal + 1:02x}:01",
        "name": "Agent-1" if ordinal == 0 else f"Extender-{ordinal}",
        "backhaulMedia": "Ethernet" if ordinal == 0 else "Wireless LAN",
        "STAList": [dict(mac=f"client-{ordinal}-{index}") for index in range(4)],
        "haulTypes": [{"ssid": ssid} for ssid in ("private_ssid", "iot_ssid", "mesh_backhaul")],
    } for ordinal in range(5)]
    root_id = physical[0]["id"]
    controller = {"id": "controller:" + root_id, "name": "Controller",
                  "backhaulMedia": "Colocated", "STAList": [], "haulTypes": []}
    return {
        "health.json": {"status": "ok", "devices": 5, "clients": 20, "networks": 3},
        "topology.json": {"nodes": physical + [controller], "edges": [
            {"from": root_id, "to": node["id"], "mediaType": "Wireless LAN"}
            for node in physical[1:]
        ] + [{"from": controller["id"], "to": root_id, "mediaType": "Colocated"}]},
        "clients.json": {"clients": [{"hostname": f"{prefix}-{ordinal:02d}"}
                                     for prefix in ("sta", "iot") for ordinal in range(1, 11)]},
        "networks.json": {"networks": [{"ssid": ssid, "client_count": count} for ssid, count in
                                       (("mesh_backhaul", 0), ("iot_ssid", 10), ("private_ssid", 10))]},
    }


def run_gate(tmp_path, documents):
    for name, document in documents.items():
        (tmp_path / name).write_text(json.dumps(document))
    source = (ROOT / "controller-ui/tests/acceptance.sh").read_text().split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    return subprocess.run([sys.executable, "-", str(tmp_path)], input=source, text=True, capture_output=True)


def test_frontend_accepts_five_physical_nodes_and_one_colocated_controller(tmp_path):
    documents = fixture()
    assert run_gate(tmp_path, documents).returncode == 0
    documents["topology.json"]["edges"][1]["from"] = documents["topology.json"]["nodes"][1]["id"]
    assert run_gate(tmp_path, documents).returncode == 0


@pytest.mark.parametrize("failure", [
    "missing_mesh", "duplicate_controller", "controller_identity", "colocated_target",
    "missing_wireless", "wireless_cycle", "wrong_ssid", "missing_client", "hidden_client",
])
def test_frontend_rejects_missing_or_inconsistent_inventory(tmp_path, failure):
    documents = copy.deepcopy(fixture())
    topology = documents["topology.json"]
    if failure == "missing_mesh":
        topology["nodes"].pop(1)
    elif failure == "duplicate_controller":
        topology["nodes"][1] = copy.deepcopy(topology["nodes"][-1])
    elif failure == "controller_identity":
        topology["nodes"][-1]["id"] = "controller:wrong"
    elif failure == "colocated_target":
        topology["edges"][-1]["to"] = topology["nodes"][1]["id"]
    elif failure == "missing_wireless":
        topology["edges"].pop(0)
    elif failure == "wireless_cycle":
        topology["edges"][0]["from"] = topology["nodes"][2]["id"]
        topology["edges"][1]["from"] = topology["nodes"][1]["id"]
    elif failure == "wrong_ssid":
        topology["nodes"][0]["haulTypes"][0]["ssid"] = "unexpected"
    elif failure == "missing_client":
        topology["nodes"][0]["STAList"].pop()
    elif failure == "hidden_client":
        documents["clients.json"]["clients"].pop(0)
    assert run_gate(tmp_path, documents).returncode != 0
