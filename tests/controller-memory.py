#!/usr/bin/env python3
"""Bounded controller RSS regression with native reporting, reads and client traffic."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import signal
import subprocess
import time
from urllib.request import urlopen


def roster(topology, expected):
    devices = topology.get("devices", [])
    clients = [client["id"] for device in devices for radio in device.get("radios", [])
               for bss in radio.get("bsses", []) for client in bss.get("clients", [])]
    if len(devices) != 5 or len(clients) != expected or len(set(clients)) != expected:
        raise RuntimeError(f"native roster mismatch: devices={len(devices)} clients={len(clients)} expected={expected}")
    return sorted(clients)


def evaluate(samples, maximum_growth_mib, maximum_rss_mib):
    if len(samples) < 2 or len({sample["pid"] for sample in samples}) != 1:
        raise RuntimeError("missing samples or controller restarted")
    values = [sample["rss_kib"] for sample in samples]
    growth = (max(values) - values[0]) / 1024
    peak = max(values) / 1024
    return {"growth_mib": round(growth, 3), "peak_mib": round(peak, 3),
            "passed": growth <= maximum_growth_mib and peak <= maximum_rss_mib}


def validate_policy(configuration):
    expected = {"LinkMetricsRequestIntervalSec": 1, "StatisticsPollingRateSec": 1,
                "AssocSTALinkMetricsInclusionPolicy": True, "AssocSTATrafficStatsInclusionPolicy": True}
    if any(type(configuration.get(key)) is not type(value) or configuration[key] != value
           for key, value in expected.items()):
        raise RuntimeError("requires the complete one-second native reporting policy")
    return expected


def command(*arguments):
    return subprocess.check_output(arguments, text=True, timeout=15, stdin=subprocess.DEVNULL)


def memory():
    processes = command("pgrep", "-f", "^/opt/prpl-install-nl80211/bin/beerocks_controller($| )").split()
    if len(processes) != 1:
        raise RuntimeError("exactly one native controller is required")
    process = int(processes[0])
    status = Path(f"/proc/{process}/status").read_text()
    match = re.search(r"^VmRSS:\s+(\d+) kB$", status, re.M)
    if not match:
        raise RuntimeError("controller RSS unavailable")
    return {"pid": process, "rss_kib": int(match[1]), "at": datetime.now(timezone.utc).isoformat()}


def topology():
    with urlopen("http://127.0.0.1:8092/api/topology", timeout=10) as response:
        return json.load(response)


def fronthaul_memory():
    output = command("ps", "-eo", "pid=,rss=,args=")
    pattern = r"\s*(\d+)\s+(\d+)\s+/opt/prpl-install-nl80211/bin/beerocks_fronthaul -i (wlan[024])\s*"
    rows = []
    for line in output.splitlines():
        match = re.fullmatch(pattern, line)
        if match:
            rows.append({"pid": int(match[1]), "rss_kib": int(match[2]), "interface": match[3]})
    if len(rows) != 15 or any(sum(row["interface"] == interface for row in rows) != 5
                              for interface in ("wlan0", "wlan2", "wlan4")):
        raise RuntimeError("requires fifteen native fronthauls across five three-radio devices")
    return sorted(rows, key=lambda row: row["pid"])


def evaluate_fronthauls(samples, maximum_growth_mib, maximum_rss_mib):
    if len(samples) < 2:
        raise RuntimeError("missing fronthaul memory samples")
    identities = {row["pid"] for row in samples[0]["processes"]}
    if len(identities) != 15 or any(len(sample["processes"]) != 15 or
                                   {row["pid"] for row in sample["processes"]} != identities
                                   for sample in samples):
        raise RuntimeError("fronthaul process missing or restarted")
    processes = []
    for identity in sorted(identities):
        values = [next(row for row in sample["processes"] if row["pid"] == identity)
                  for sample in samples]
        processes.append({"pid": identity, **evaluate(values, maximum_growth_mib, maximum_rss_mib)})
    return {"passed": all(row["passed"] for row in processes), "processes": processes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-clients", type=int, default=100)
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--maximum-growth-mib", type=float, default=64)
    parser.add_argument("--maximum-rss-mib", type=float, default=1024)
    parser.add_argument("--traffic", action="store_true")
    parser.add_argument("--include-fronthaul", action="store_true")
    parser.add_argument("--maximum-fronthaul-growth-mib", type=float, default=1)
    parser.add_argument("--maximum-fronthaul-rss-mib", type=float, default=128)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.expected_clients <= 100 or not 10 <= args.duration <= 300 or not 0 <= args.warmup <= 60:
        parser.error("clients must be 1..100, duration 10..300 and warmup 0..60")
    if not 0 < args.maximum_growth_mib <= args.maximum_rss_mib <= 2048:
        parser.error("require 0 < growth <= RSS limit <= 2048 MiB")
    if not 0 < args.maximum_fronthaul_growth_mib <= args.maximum_fronthaul_rss_mib <= 1024:
        parser.error("require 0 < fronthaul growth <= RSS limit <= 1024 MiB")
    if args.output.exists():
        parser.error("use a new evidence path")
    report = {"passed": False, "samples": [], "traffic": [], "parameters": vars(args) | {"output": str(args.output)}}
    children = []
    try:
        configuration = command("lxc", "exec", "--mode", "non-interactive", "prpl-controller", "--",
                                "ubus", "-t", "5", "call", "X_PRPLWARE-COM_Controller.Configuration",
                                "_get", '{"rel_path":"","depth":0}')
        report["native_policy"] = validate_policy(json.JSONDecoder().raw_decode(configuration.lstrip())[0].get(
            "X_PRPLWARE-COM_Controller.Configuration.", {}))
        initial = roster(topology(), args.expected_clients)
        report["roster"] = initial
        initial_memory = memory()
        if args.include_fronthaul:
            initial_fronthauls = {row["pid"] for row in fronthaul_memory()}
            report["fronthaul_samples"] = []
        if args.traffic:
            inventory = json.loads(command("lxc", "query", "/1.0/instances?recursion=2"))
            wanted = {f"prpl-client-{ordinal:02d}" for ordinal in range(1, args.expected_clients + 1)}
            clients = [entry for entry in inventory if entry["name"] in wanted
                       and entry["state"]["status"] == "Running" and entry["state"]["pid"] > 1]
            if len(clients) != args.expected_clients:
                raise RuntimeError("client namespaces unavailable for traffic")
            for entry in clients:
                process = subprocess.Popen(
                    ["nsenter", "-t", str(entry["state"]["pid"]), "-n", "ping", "-n", "-q", "-i", ".5",
                     "-c", str(2 * (args.duration + args.warmup)), "-W", "1", "192.168.77.1"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                children.append((entry["name"], process))
        started = time.monotonic()
        while time.monotonic() - started <= args.warmup + args.duration:
            sample = memory()
            elapsed = time.monotonic() - started
            sample["elapsed"] = round(elapsed, 3)
            if sample["pid"] != initial_memory["pid"] or sample["rss_kib"] > args.maximum_rss_mib * 1024:
                raise RuntimeError("controller restart or RSS safety ceiling reached")
            if elapsed >= args.warmup:
                report["samples"].append(sample)
            if args.include_fronthaul:
                processes = fronthaul_memory()
                if ({row["pid"] for row in processes} != initial_fronthauls or
                        any(row["rss_kib"] > args.maximum_fronthaul_rss_mib * 1024 for row in processes)):
                    raise RuntimeError("fronthaul restart or RSS safety ceiling reached")
                if elapsed >= args.warmup:
                    report["fronthaul_samples"].append({"at": sample["at"], "elapsed": sample["elapsed"],
                                                        "processes": processes})
            if roster(topology(), args.expected_clients) != initial:
                raise RuntimeError("native client membership changed during measurement")
            print(json.dumps(sample), flush=True)
            time.sleep(2)
        report.update(evaluate(report["samples"], args.maximum_growth_mib, args.maximum_rss_mib))
        if args.include_fronthaul:
            report["fronthaul"] = evaluate_fronthauls(report["fronthaul_samples"],
                args.maximum_fronthaul_growth_mib, args.maximum_fronthaul_rss_mib)
            report["passed"] = report["passed"] and report["fronthaul"]["passed"]
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=str(error))
    finally:
        for name, process in children:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                output, _unused = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _unused = process.communicate(timeout=5)
                report.update(passed=False, cleanup_error="traffic process required forced termination")
            received = re.search(r"(\d+) (?:packets )?received", output)
            report["traffic"].append({"client": name, "received": int(received[1]) if received else 0,
                                       "exit_code": process.returncode, "summary": output})
        if children and not all(entry["received"] > 0 for entry in report["traffic"]):
            report.update(passed=False, traffic_error="one or more clients received no traffic")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"samples", "fronthaul_samples", "traffic", "roster"}}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
