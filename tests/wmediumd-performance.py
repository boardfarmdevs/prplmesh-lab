#!/usr/bin/env python3
"""Measure prplMesh-lab wmediumd CPU and client traffic behavior."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def process_ticks(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text().split()
    return int(fields[13]) + int(fields[14])


def process_status(pid: int) -> dict[str, int]:
    wanted = {
        "Threads": "threads",
        "voluntary_ctxt_switches": "voluntary_context_switches",
        "nonvoluntary_ctxt_switches": "involuntary_context_switches",
        "VmRSS": "rss_kib",
    }
    result: dict[str, int] = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        key, separator, value = line.partition(":")
        if separator and key in wanted:
            result[wanted[key]] = int(value.split()[0])
    return result


def netlink_drops(pid: int) -> int:
    inodes: set[str] = set()
    for descriptor in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(descriptor)
        except OSError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            inodes.add(match.group(1))
    total = 0
    for line in Path(f"/proc/{pid}/net/netlink").read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 10 and fields[9] in inodes:
            total += int(fields[8])
    return total


def clients(prefix: str) -> list[str]:
    output = run("lxc", "list", "--format=csv", "-c", "ns").stdout
    result = []
    for line in output.splitlines():
        name, _, state = line.partition(",")
        if name.startswith(prefix) and state.strip().upper() == "RUNNING":
            result.append(name)
    return sorted(result)


def ping_client(
    client: str, duration: int, interval: float, target: str
) -> dict[str, Any]:
    completed = run(
        "lxc", "exec", client, "--", "sh", "-c",
        f"timeout -s INT {duration}s ping -q -i {interval} -W 2 {target}",
        check=False,
    )
    output = completed.stdout + completed.stderr
    packets = re.search(
        r"(\d+) packets transmitted, (\d+) (?:packets )?received", output
    )
    rtt = re.search(r"= [^/]+/([^/]+)/", output)
    return {
        "client": client,
        "returncode": completed.returncode,
        "transmitted": int(packets.group(1)) if packets else 0,
        "received": int(packets.group(2)) if packets else 0,
        "average_rtt_ms": float(rtt.group(1)) if rtt else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("idle", "ping"), default="idle")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--ping-interval", type=float, default=0.02)
    parser.add_argument("--client-limit", type=int, default=0)
    parser.add_argument("--client-prefix", default="prpl-client-")
    parser.add_argument("--ping-target", default="192.168.77.1")
    parser.add_argument(
        "--pidfile", type=Path,
        default=Path("/run/prpl-wmediumd/wmediumd.pid"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration < 5 or args.ping_interval < 0.001:
        parser.error("duration must be >= 5 and ping interval >= 0.001")

    pid = int(args.pidfile.read_text().strip())
    selected = clients(args.client_prefix) if args.mode == "ping" else []
    if args.client_limit:
        selected = selected[:args.client_limit]
    if args.mode == "ping" and not selected:
        raise RuntimeError("no matching running client containers found")

    before_status = process_status(pid)
    before_ticks = process_ticks(pid)
    before_drops = netlink_drops(pid)
    started = time.monotonic()
    traffic: list[dict[str, Any]] = []
    if selected:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(selected)
        ) as executor:
            traffic = list(executor.map(
                lambda client: ping_client(
                    client, args.duration, args.ping_interval,
                    args.ping_target,
                ),
                selected,
            ))
    else:
        time.sleep(args.duration)
    elapsed = time.monotonic() - started
    after_ticks = process_ticks(pid)
    after_status = process_status(pid)
    transmitted = sum(item["transmitted"] for item in traffic)
    received = sum(item["received"] for item in traffic)
    rtts = [
        item["average_rtt_ms"] for item in traffic
        if item["average_rtt_ms"] is not None
    ]

    result = {
        "schema": 1,
        "mode": args.mode,
        "duration_seconds": elapsed,
        "pid": pid,
        "threads": after_status.get("threads"),
        "allowed_cpus": sorted(os.sched_getaffinity(pid)),
        "cpu_percent_of_one_core": (
            (after_ticks - before_ticks) / os.sysconf("SC_CLK_TCK")
            / elapsed * 100
        ),
        "rss_kib": after_status.get("rss_kib"),
        "voluntary_context_switches": (
            after_status.get("voluntary_context_switches", 0)
            - before_status.get("voluntary_context_switches", 0)
        ),
        "involuntary_context_switches": (
            after_status.get("involuntary_context_switches", 0)
            - before_status.get("involuntary_context_switches", 0)
        ),
        "netlink_receive_drops": netlink_drops(pid) - before_drops,
        "traffic": {
            "clients": len(selected),
            "target": args.ping_target,
            "transmitted": transmitted,
            "received": received,
            "loss_percent": (
                (transmitted - received) / transmitted * 100
                if transmitted else 0.0
            ),
            "mean_client_rtt_ms": sum(rtts) / len(rtts) if rtts else None,
            "per_client": traffic,
        },
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
