#!/usr/bin/env python3
"""Generate the prplMesh lab's stable VIF-to-hwsim identity mapping."""

import argparse
import json
from pathlib import Path


def mac(prefix: str, ordinal: int, suffix: int = 0) -> str:
    return f"{prefix}:{ordinal:02x}:{suffix:02x}"


def build(agent_count: int, client_count: int, radios_per_node: int) -> dict:
    aliases: dict[str, str] = {}
    mesh_nodes = agent_count + 1

    for node in range(mesh_nodes):
        for local_radio in range(radios_per_node):
            radio = node * radios_per_node + local_radio
            tx_identity = mac("42:00:00:00", radio)
            aliases[tx_identity] = tx_identity
            aliases[mac("02:00:00:00", radio)] = tx_identity
            # The lab creates private, IoT and backhaul BSSes from the same
            # radio with deterministic final-octet suffixes 00, 01 and 02.
            for suffix in (1, 2):
                aliases[mac("02:00:00:00", radio, suffix)] = tx_identity

    # Every wireless Agent uses the 5 GHz radio (local ordinal 1) for its
    # deterministic backhaul STA interface.
    for agent in range(1, agent_count + 1):
        radio = agent * radios_per_node + 1
        aliases[mac("02:00:00:30", agent)] = mac("42:00:00:00", radio)

    first_client_radio = mesh_nodes * radios_per_node
    for container_ordinal in range(1, client_count + 1):
        cohort_ordinal = (container_ordinal + 1) // 2
        prefix = "02:00:00:10" if container_ordinal % 2 else "02:00:00:20"
        station = mac(prefix, cohort_ordinal)
        radio = first_client_radio + container_ordinal - 1
        aliases[station] = mac("42:00:00:00", radio)

    return {
        "schema": "prplmesh.kernel-medium-aliases.v1",
        "aliases": dict(sorted(aliases.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, required=True)
    parser.add_argument("--clients", type=int, required=True)
    parser.add_argument("--radios-per-node", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build(args.agents, args.clients, args.radios_per_node)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
