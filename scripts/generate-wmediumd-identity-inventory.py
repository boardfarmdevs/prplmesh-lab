#!/usr/bin/env python3
"""Generate stable prplMesh labels for the shared wmediumd Console."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


BANDS = ("2.4 GHz", "5 GHz", "6 GHz")


def radio_mac(ordinal: int) -> str:
    return f"42:00:00:00:{ordinal:02x}:00"


def build(radios: int, agents: int, clients: int, radios_per_node: int) -> dict:
    if radios_per_node != len(BANDS):
        raise ValueError("the tri-band lab requires exactly three radios per mesh node")
    assigned = (agents + 1) * radios_per_node + clients
    if assigned > radios:
        raise ValueError(f"{assigned} assigned radios exceed the {radios}-radio pool")

    stations = []
    for ordinal in range(radios):
        entry = {
            "mac": radio_mac(ordinal),
            "label": f"Spare-{ordinal:02d}",
            "role": "spare",
            "owner": "unassigned",
            "interface": "",
        }
        mesh_node, local_radio = divmod(ordinal, radios_per_node)
        if mesh_node <= agents:
            if mesh_node == 0:
                node_label = "Controller"
                owner = "prpl-controller"
                role = "controller-agent"
            else:
                node_label = f"Extender-{mesh_node}"
                owner = f"prpl-agent-{mesh_node:02d}"
                role = "extender"
            entry.update(
                label=f"{node_label} {BANDS[local_radio]}",
                role=role,
                owner=owner,
            )
        elif ordinal < assigned:
            container_ordinal = ordinal - (agents + 1) * radios_per_node + 1
            cohort_ordinal = (container_ordinal + 1) // 2
            iot = container_ordinal % 2 == 0
            entry.update(
                label=f"{'iot' if iot else 'sta'}-{cohort_ordinal:02d}",
                role="iot-client" if iot else "client",
                owner=f"prpl-client-{container_ordinal:02d}",
                interface="wlan0",
            )
        stations.append(entry)

    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stations": stations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radios", type=int, required=True)
    parser.add_argument("--agents", type=int, required=True)
    parser.add_argument("--clients", type=int, required=True)
    parser.add_argument("--radios-per-node", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build(args.radios, args.agents, args.clients, args.radios_per_node)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
