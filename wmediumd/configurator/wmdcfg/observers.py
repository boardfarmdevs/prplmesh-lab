from __future__ import annotations

import datetime as dt
import json
import subprocess
import time


TOPOLOGY_URL = "http://127.0.0.1:8092/api/topology"


def _run(*args: str) -> str:
    return subprocess.run(
        args, check=True, text=True, capture_output=True, timeout=10
    ).stdout.strip()


def _topology() -> dict:
    return json.loads(_run("curl", "-fsS", TOPOLOGY_URL))


def _associations(topology: dict) -> dict[str, dict]:
    result = {}
    for device in topology.get("devices", []):
        for radio in device.get("radios", []):
            for bss in radio.get("bsses", []):
                for client in bss.get("clients", []):
                    result[str(client["id"]).lower()] = {
                        "bssid": str(bss["bssid"]).lower(),
                        "rcpi": int(client.get("signal_raw") or 0),
                        "device": device.get("name"),
                        "band": radio.get("band"),
                    }
    return result


def snapshot(plan: dict) -> dict:
    started = time.monotonic()
    topology = _topology()
    associated = _associations(topology)
    stations = []
    for role, binding in plan["bindings"].items():
        if binding["role_type"] != "station":
            continue
        mac = str(
            binding.get("station_mac") or binding["radio_permanent_mac"]
        ).lower()
        value = associated.get(mac, {})
        stations.append(
            {
                "role": role,
                "container": binding["container"],
                "mac": mac,
                "bssid": value.get("bssid"),
                "rcpi": value.get("rcpi"),
                "device": value.get("device"),
                "band": value.get("band"),
            }
        )
    return {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "capture_elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "source": topology.get("source", "prplMesh NBAPI"),
        "stations": stations,
    }


def mesh_health(
    expected_agents: int | None = None,
    expected_clients: int | None = None,
) -> dict:
    topology = _topology()
    devices = topology.get("devices", [])
    associations = _associations(topology)
    complete = sum(
        1
        for device in devices
        if len(device.get("radios", [])) == 3
        and all(
            len(radio.get("bsses", [])) >= 3
            for radio in device.get("radios", [])
        )
    )
    result = {
        "source": topology.get("source", "prplMesh NBAPI"),
        "api_active": len(associations),
        "api_total": (
            expected_clients if expected_clients is not None else len(associations)
        ),
        "topology_nodes": len(devices),
        "complete_nodes": complete,
    }
    if expected_agents is not None:
        # The compiler's mesh_devices count includes the controller/colocated
        # Agent, so prplMesh expects exactly this many NBAPI Device objects.
        result["expected_topology_nodes"] = expected_agents
    return result
