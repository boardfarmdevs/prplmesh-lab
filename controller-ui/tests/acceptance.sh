#!/bin/bash
set -euo pipefail

base=${EASYMESH_UI_URL:-http://127.0.0.1:8091}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsS "$base/health" >"$work/health.json"
curl -fsS "$base/api/v1/topology" >"$work/topology.json"
curl -fsS "$base/api/v1/clients" >"$work/clients.json"
curl -fsS "$base/api/v1/networks" >"$work/networks.json"
curl -fsS "$base/" >"$work/index.html"

python3 - "$work" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
load = lambda name: json.loads((root / name).read_text())
health = load("health.json")
topology = load("topology.json")
clients = load("clients.json")["clients"]
networks = load("networks.json")["networks"]

assert health["status"] == "ok", health
assert (health["devices"], health["clients"], health["networks"]) == (5, 20, 3), health
assert len(topology["nodes"]) == 6, len(topology["nodes"])
assert len(topology["edges"]) == 5, len(topology["edges"])
physical = [node for node in topology["nodes"] if node["backhaulMedia"] != "Colocated"]
logical = [node for node in topology["nodes"] if node["backhaulMedia"] == "Colocated"]
assert len(physical) == 5 and len(logical) == 1
assert {node["name"] for node in physical} == {"Agent-1", "Extender-1", "Extender-2", "Extender-3", "Extender-4"}
physical_ids = {node["id"] for node in physical}
assert len(physical_ids) == 5
root_id = next(node["id"] for node in physical if node["name"] == "Agent-1")
controller = logical[0]
assert controller["id"] == "controller:" + root_id and controller["name"] == "Controller"
assert controller["STAList"] == [] and controller["haulTypes"] == []
wireless = [edge for edge in topology["edges"] if edge["mediaType"] == "Wireless LAN"]
colocated = [edge for edge in topology["edges"] if edge["mediaType"] == "Colocated"]
assert len(wireless) == 4 and len(colocated) == 1
assert colocated[0]["from"] == controller["id"] and colocated[0]["to"] == root_id
assert {edge["to"] for edge in wireless} == physical_ids - {root_id}
assert all(edge["from"] in physical_ids for edge in wireless)
parents = {edge["to"]: edge["from"] for edge in wireless}
for node_id in physical_ids - {root_id}:
    visited = set()
    while node_id != root_id:
        assert node_id not in visited, "wireless topology contains a cycle"
        visited.add(node_id)
        node_id = parents[node_id]
assert sum(len(node["STAList"]) for node in topology["nodes"]) == 20
assert all({haul["ssid"] for haul in node["haulTypes"]} ==
           {"private_ssid", "iot_ssid", "mesh_backhaul"}
           for node in physical)
assert len(clients) == 20
assert {client["hostname"] for client in clients} >= {"sta-10", "iot-10"}
counts = {network["ssid"]: network["client_count"] for network in networks}
assert counts == {"mesh_backhaul": 0, "iot_ssid": 10, "private_ssid": 10}, counts
print("PASS: EM CLI host UI exposes 5 physical devices plus the colocated Controller, 20 clients and three live networks")
PY

grep -q 'EasyMesh Controller' "$work/index.html"
grep -q 'static/script.js' "$work/index.html"
