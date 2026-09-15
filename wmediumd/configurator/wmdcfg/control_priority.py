from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess


TABLE = "easymesh_control_priority"
OWNER = "easymesh-control-priority-v1"
NODES = {
    "rdk": ["bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003"],
    "prplmesh": ["prpl-controller", *[f"prpl-agent-{ordinal:02d}" for ordinal in range(1, 5)]],
}


def transaction(existing, enable):
    tables = [row["table"] for row in existing.get("nftables", [])
              if "table" in row and row["table"].get("family") == "bridge"
              and row["table"].get("name") == TABLE]
    if tables and (len(tables) != 1 or tables[0].get("comment") != OWNER):
        raise RuntimeError("refusing to replace an unowned control-priority table")
    commands = [f"delete table bridge {TABLE}"] if tables else []
    if enable:
        commands += [
            f'add table bridge {TABLE} {{ comment "{OWNER}"; }}',
            f"add chain bridge {TABLE} forward {{ type filter hook forward priority -150; policy accept; }}",
            f"add rule bridge {TABLE} forward ether type 0x893a counter meta priority set 0x00000107",
        ]
    return "\n".join(commands) + "\n" if commands else ""


def execute(arguments, **options):
    return subprocess.run(arguments, check=True, text=True, capture_output=True, timeout=10, **options).stdout


def configure(stack, enable, selected=None):
    nodes = selected or NODES[stack]
    if len(nodes) != len(set(nodes)) or any(node not in NODES[stack] for node in nodes):
        raise ValueError("only distinct mesh nodes belonging to the selected stack are supported")
    if os.geteuid() != 0:
        raise RuntimeError("requires root inside the lab VM")
    for tool in ("lxc", "nsenter", "nft"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"install {tool} before enabling control priority")
    plans = []
    with ExitStack() as cleanup:
        for node in nodes:
            state = json.loads(execute(["lxc", "query", f"/1.0/instances/{node}/state"]))
            if state.get("status") != "Running" or not isinstance(state.get("pid"), int) or state["pid"] <= 0:
                raise RuntimeError(f"{node} is not running")
            namespace = cleanup.enter_context(Path(f"/proc/{state['pid']}/ns/net").open("rb"))
            descriptor = namespace.fileno()
            command = ["nsenter", f"--net=/proc/self/fd/{descriptor}", "nft"]
            options = {"pass_fds": (descriptor,)}
            listing = json.loads(execute(command + ["-j", "list", "tables"], **options))
            present = any(row.get("table", {}).get("family") == "bridge" and
                          row["table"].get("name") == TABLE for row in listing.get("nftables", []))
            existing = json.loads(execute(command + ["-j", "list", "table", "bridge", TABLE], **options)) if present else {}
            script = transaction(existing, enable)
            if script:
                execute(command + ["-c", "-f", "-"], input=script, **options)
            plans.append((node, command, options, script))
        for node, command, options, script in plans:
            if script:
                execute(command + ["-f", "-"], input=script, **options)
            print(json.dumps({"node": node, "state": "enabled" if enable else "disabled",
                              "table": TABLE, "user_priority": 7 if enable else None}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opt-in bridge classification for lab IEEE 1905 control traffic")
    parser.add_argument("--stack", choices=tuple(NODES), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    parser.add_argument("--node", action="append")
    args = parser.parse_args(argv)
    configure(args.stack, args.enable, args.node)


if __name__ == "__main__":
    main()
