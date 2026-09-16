#!/usr/bin/env python3
"""Qualify prplMesh AP-metrics periodic, query, threshold and restart behavior."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

from optimizer.load_observer import NativeLoadProvider
from optimizer.prplmesh import PrplMeshObserver
from room_demo.traffic_experiment import namespace_udp


OBJECT = "X_PRPLWARE-COM_Controller.Configuration"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def execute(*arguments, timeout=30, input_text=None):
    return subprocess.run(arguments, check=True, capture_output=True, text=True,
                          input=input_text, timeout=timeout)


def ubus(method, payload):
    output = execute("lxc", "exec", "prpl-controller", "--", "ubus", "-t", "8", "call",
                     OBJECT, method, json.dumps(payload)).stdout.lstrip()
    return json.JSONDecoder().raw_decode(output)[0]


def configuration():
    return ubus("_get", {"rel_path": "", "depth": 0})[OBJECT + "."]


def configure(values):
    ubus("_set", {"parameters": values})
    observed = configuration()
    require(all(observed.get(name) == value for name, value in values.items()),
            "native controller did not apply reporting policy")
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({"state": "prepared", "stack": "prpl",
                          "mutations": ["temporary reporting policy", "bounded UDP", "one leaf-agent restart"]}))
        return 0
    require(os.geteuid() == 0, "requires root inside the prpl lab VM")
    args.output.mkdir(parents=True, exist_ok=False)
    with urllib.request.urlopen("http://127.0.0.1:8891/api/demo/interactions", timeout=5) as response:
        room = json.load(response)
    require(not room["lease"]["held"] and room["playback"]["status"] == "paused"
            and room["selected_world"] == "home-five-agent--private-client-room-walk",
            "requires the idle default room")
    fields = ("LinkMetricsRequestIntervalSec", "StatisticsPollingRateSec",
              "APReportingChannelUtilizationThreshold",
              "AssocSTALinkMetricsInclusionPolicy", "AssocSTATrafficStatsInclusionPolicy")
    saved_config = configuration()
    saved = {name: saved_config[name] for name in fields}
    reports = []
    report_lock = threading.Lock()

    def observed(value):
        with report_lock:
            reports.append({**value, "captured_monotonic_ns": time.monotonic_ns()})

    provider = NativeLoadProvider("prpl-controller", report_observer=observed,
                                  byte_counter_unit_bytes=1024)
    observer = PrplMeshObserver(ownership_observer=provider.observe_owners)
    report = {"stack": "prpl", "state": "failed", "saved_policy": saved,
              "periodic": {}, "query": {}, "threshold": {}, "restart": {},
              "restoration_errors": []}
    restored = False

    def drive(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            snapshot = observer.observe()
            provider.enrich(snapshot, observer.last_raw)
            time.sleep(.2)
        return snapshot

    def captured_since(mark):
        with report_lock:
            return [row for row in reports if row["captured_monotonic_ns"] >= mark]

    try:
        periodic_mark = time.monotonic_ns()
        snapshot = drive(5)
        bsses = [bss for device in observer.last_raw["topology"]["devices"]
                 for radio in device.get("radios", []) for bss in radio.get("bsses", [])]
        expected_sources = {device["id"].lower() for device in observer.last_raw["topology"]["devices"]}
        periodic_rows = captured_since(periodic_mark)
        periodic_counts = {source: sum(row["source"] == source for row in periodic_rows)
                           for source in expected_sources}
        require(all(count >= 2 for count in periodic_counts.values()),
                "periodic AP metrics did not cover every mesh device twice")
        report["periodic"] = {"passed": True, "seconds": 5, "reports_per_source": periodic_counts,
                              "configured_interval_seconds": saved["LinkMetricsRequestIntervalSec"]}

        station = execute("lxc", "exec",
            json.loads((args.root / "demo/bindings/private-client-room-walk.json").read_text())["roles"]["sta_static_01"],
            "--", "cat", "/sys/class/net/wlan0/address").stdout.strip().lower()
        client = next(row for row in snapshot.clients if row.sta_mac == station)
        current_load = provider.loads.get((client.connected_device_id, client.connected_bssid))
        require(current_load is not None, "selected client has no native serving-load baseline")
        threshold = min(240, max(100, current_load["utilization"] + 30))
        configured = {**saved, "LinkMetricsRequestIntervalSec": 60,
                      "StatisticsPollingRateSec": 1,
                      "APReportingChannelUtilizationThreshold": threshold,
                      "AssocSTALinkMetricsInclusionPolicy": True,
                      "AssocSTATrafficStatsInclusionPolicy": True}
        configure(configured)
        drive(3)

        query_mark = time.monotonic_ns()
        execute("lxc", "exec", "prpl-controller", "--",
                "/opt/prpl-install-nl80211/bin/beerocks_cli", "-c", "hostap_stats_measurement",
                timeout=12)
        drive(3)
        queried = captured_since(query_mark)
        query_sources = {row["source"] for row in queried}
        require(expected_sources <= query_sources, "AP Metrics Query did not return every mesh device")
        report["query"] = {"passed": True, "seconds_to_last_source":
            max((row["captured_monotonic_ns"] - query_mark) / 1e9 for row in queried
                if row["source"] in expected_sources), "sources": sorted(query_sources)}

        binding = json.loads((args.root / "demo/bindings/private-client-room-walk.json").read_text())["roles"]
        traffic_started = threading.Event()
        phase = {"role": "sta_static_01", "start_ms": 0, "end_ms": 18000,
                 "mode": "udp", "offered_mbps": 12, "payload_bytes": 1200}
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(namespace_udp, binding["sta_static_01"], "192.168.77.1",
                                     phase, 18000, admit=nullcontext, register=lambda _process: None,
                                     running=lambda _value: traffic_started.set())
            require(traffic_started.wait(3), "bounded threshold traffic did not start")
            threshold_mark = time.monotonic_ns()
            while not future.done():
                drive(.5)
            endpoint = future.result()
        require(endpoint.get("state") == "completed", "bounded threshold traffic failed")
        threshold_rows = [row for row in captured_since(threshold_mark)
                          for load in row["loads"] if load["bssid"] == client.connected_bssid
                          and load["utilization"] >= threshold]
        require(threshold_rows, "upward utilization threshold produced no native AP report")
        report["threshold"] = {"upward_passed": True, "threshold": threshold,
            "baseline_utilization": current_load["utilization"],
            "maximum_reported_utilization": max(load["utilization"] for row in threshold_rows
                                                for load in row["loads"]
                                                if load["bssid"] == client.connected_bssid),
            "endpoint_sender_bits_per_second": endpoint["sender"]["bits_per_second"]}
        downward_mark = time.monotonic_ns()
        drive(12)
        downward = [row for row in captured_since(downward_mark)
                    for load in row["loads"] if load["bssid"] == client.connected_bssid
                    and load["utilization"] < threshold]
        report["threshold"]["downward_spontaneous_report"] = bool(downward)
        report["threshold"]["downward_contract"] = (
            "observed" if downward else "not emitted by the native upward-crossing policy")

        configure(saved)
        restored = True
        restart_mark = time.monotonic_ns()
        execute(str(args.root / "scripts/radio-lab.sh"), "restart-agent", "1", timeout=90)
        drive(35)
        agent_id = next(device["id"].lower() for device in observer.last_raw["topology"]["devices"]
                        if device.get("name") == "agent-1")
        recovered = [row for row in captured_since(restart_mark) if row["source"] == agent_id]
        require(recovered, "agent-1 AP metrics did not recover after restart")
        report["restart"] = {"passed": True, "agent_id": agent_id,
                             "first_report_seconds": (recovered[0]["captured_monotonic_ns"] - restart_mark) / 1e9}
        report["state"] = "passed"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if not restored:
            try:
                configure(saved)
                restored = True
            except Exception as error:
                report["restoration_errors"].append(str(error))
        provider.close()
        report["policy_restored"] = restored
        with report_lock:
            (args.output / "reports.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in reports))
        if report["restoration_errors"]:
            report["state"] = "failed"
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
