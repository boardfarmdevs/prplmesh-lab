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
assert len(topology["nodes"]) == 5, len(topology["nodes"])
assert len(topology["edges"]) == 4, len(topology["edges"])
assert sum(len(node["STAList"]) for node in topology["nodes"]) == 20
assert all({haul["ssid"] for haul in node["haulTypes"]} ==
           {"private_ssid", "iot_ssid", "mesh_backhaul"}
           for node in topology["nodes"])
assert {client["hostname"] for client in clients} >= {"sta-10", "iot-10"}
counts = {network["ssid"]: network["client_count"] for network in networks}
assert counts == {"mesh_backhaul": 0, "iot_ssid": 10, "private_ssid": 10}, counts
print("PASS: EM CLI host UI exposes 5 devices, 20 clients and three live networks")
PY

grep -q 'EasyMesh Controller' "$work/index.html"
grep -q 'static/script.js' "$work/index.html"
