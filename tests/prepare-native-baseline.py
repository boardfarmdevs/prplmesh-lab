#!/usr/bin/env python3
"""Restore the declared star fixture before full-roster tests, without restarting nodes."""

import argparse
import json
from pathlib import Path
import subprocess
import time


def command(*arguments):
    return subprocess.run(arguments, check=True, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=10).stdout.strip()


def restore_parents(agents, seconds=60):
    target = "02:00:00:00:01:02"
    pending = {f"prpl-agent-{ordinal:02d}" for ordinal in range(1, agents + 1)}
    deadline = time.monotonic() + seconds
    while pending and time.monotonic() < deadline:
        for container in sorted(pending):
            prefix = ("lxc", "exec", "--mode", "non-interactive", container, "--", "wpa_cli", "-i", "wlan3")
            status = dict(line.split("=", 1) for line in command(*prefix, "status").splitlines() if "=" in line)
            if status.get("wpa_state") == "COMPLETED" and status.get("bssid") == target:
                pending.remove(container)
                continue
            network = status.get("id", "")
            if not network.isdecimal() or status.get("ssid") != "mesh_backhaul":
                raise RuntimeError(f"{container}: expected the active mesh_backhaul network")
            if command(*prefix, "set_network", network, "bssid", target) != "OK":
                raise RuntimeError(f"{container}: failed to select the baseline parent")
            result = command(*prefix, "roam", target)
            if result != "OK":
                scan = command(*prefix, "scan")
                if scan not in ("OK", "FAIL-BUSY"):
                    raise RuntimeError(f"{container}: baseline scan failed: {scan}")
        if pending:
            time.sleep(1)
    if pending:
        raise RuntimeError("star baseline not established: " + ", ".join(sorted(pending)))
    return {"fixture": "star", "agents": agents, "parent_bssid": target,
            "method": "explicit supplicant fixture setup, not optimizer steering"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes-act", action="store_true")
    parser.add_argument("--agents", type=int, default=4)
    args = parser.parse_args()
    if not args.yes_act or not 1 <= args.agents <= 4:
        parser.error("requires --yes-act and 1..4 provisioned agents")
    if not Path("/run/prplmesh-suite-room-guard").is_dir():
        parser.error("requires the suite room guard")
    if command("systemctl", "show", "prplmesh-room-demo.service", "-p", "ActiveState", "--value") != "inactive":
        parser.error("room service must be stopped before fixture setup")
    print(json.dumps(restore_parents(args.agents)))


if __name__ == "__main__":
    main()
