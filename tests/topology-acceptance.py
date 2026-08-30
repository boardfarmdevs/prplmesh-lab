#!/usr/bin/env python3
"""Validate physical hwsim state against the prplMesh NBAPI model."""

import argparse
import collections
import json
import subprocess
import sys
import time
import urllib.request


def run(*args, timeout=15):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout).stdout


def topology(url, attempts=20):
    error = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.load(response)
        except Exception as current:
            error = current
            time.sleep(1)
    raise RuntimeError(f"topology API unavailable: {error}")


def expected_parent(ordinal, mode):
    if mode == "star":
        return 0
    if mode == "branch":
        return 0 if ordinal == 1 else 1
    return ordinal - 1


def expected_band(ordinal):
    cohort_ordinal = (ordinal + 1) // 2
    return (
        "2.4 GHz", "5 GHz", "5 GHz", "6 GHz", "5 GHz",
        "6 GHz", "2.4 GHz", "5 GHz", "5 GHz", "6 GHz",
    )[(cohort_ordinal - 1) % 10]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--topology", choices=("star", "branch", "chain"), default="chain")
    parser.add_argument("--require-metrics", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8090/api/topology")
    args = parser.parse_args()

    data = topology(args.url)
    devices = data["devices"]
    assert len(devices) == args.agents + 1, (len(devices), args.agents + 1)
    by_name = {device["name"]: device for device in devices}
    expected_names = {"controller", *(f"agent-{n}" for n in range(1, args.agents + 1))}
    assert set(by_name) == expected_names, set(by_name)

    ids = [device["id"] for device in devices]
    assert len(ids) == len(set(ids)), "duplicate EasyMesh device ID"
    for node in range(args.agents + 1):
        name = "controller" if node == 0 else f"agent-{node}"
        device = by_name[name]
        expected_id = f"02:00:00:27:{node + 1:02x}:01"
        assert device["id"] == expected_id, (name, device["id"], expected_id)
        assert len(device["radios"]) == 3, (name, len(device["radios"]))
        for local_radio, radio in enumerate(device["radios"]):
            expected_radio = f"02:00:00:00:{node * 3 + local_radio:02x}:00"
            assert radio["id"] == expected_radio, (name, radio["id"], expected_radio)
            assert {bss["ssid"] for bss in radio["bsses"]} == {
                "private_ssid", "iot_ssid", "mesh_backhaul"
            }
        if node:
            parent = expected_parent(node, args.topology)
            expected_parent_id = f"02:00:00:27:{parent + 1:02x}:01"
            expected_parent_bssid = f"02:00:00:00:{parent * 3 + 1:02x}:02"
            assert device["backhaul"]["type"] == "Wi-Fi", device["backhaul"]
            assert device["backhaul"]["parent_id"] == expected_parent_id, device["backhaul"]
            assert device["backhaul"]["mac"] == expected_parent_bssid, device["backhaul"]

            container = f"prpl-agent-{node:02d}"
            status = run("lxc", "exec", container, "--", "wpa_cli", "-i", "wlan3", "status")
            values = dict(line.split("=", 1) for line in status.splitlines() if "=" in line)
            assert values.get("wpa_state") == "COMPLETED", (container, values)
            assert values.get("bssid") == expected_parent_bssid, (container, values)

    rows = []
    for device in devices:
        for radio in device["radios"]:
            for bss in radio["bsses"]:
                for client in bss["clients"]:
                    if client["id"].startswith(("02:00:00:10:", "02:00:00:20:")):
                        rows.append((device, radio, bss, client))
    assert len(rows) == args.clients, (len(rows), args.clients)
    assert len({row[3]["id"] for row in rows}) == args.clients, "duplicate client ownership"

    expected_macs = set()
    for ordinal in range(1, args.clients + 1):
        cohort = "private" if ordinal % 2 else "iot"
        cohort_ordinal = (ordinal + 1) // 2
        prefix = "10" if cohort == "private" else "20"
        mac = f"02:00:00:{prefix}:{cohort_ordinal:02x}:00"
        expected_macs.add(mac)
        matches = [row for row in rows if row[3]["id"] == mac]
        assert len(matches) == 1, (mac, len(matches))
        _, radio, bss, client = matches[0]
        assert bss["ssid"] == f"{cohort}_ssid" if cohort == "private" else bss["ssid"] == "iot_ssid"
        assert radio["band"] == expected_band(ordinal), (mac, radio["band"], expected_band(ordinal))
        if args.require_metrics:
            assert client["signal_raw"] not in (None, 0), (mac, client["signal_raw"])

        container = f"prpl-client-{ordinal:02d}"
        status = run("lxc", "exec", container, "--", "wpa_cli", "-i", "wlan0", "status")
        values = dict(line.split("=", 1) for line in status.splitlines() if "=" in line)
        assert values.get("wpa_state") == "COMPLETED", (container, values)
        assert values.get("address") == mac, (container, values.get("address"), mac)
        assert values.get("ssid") == bss["ssid"], (container, values.get("ssid"), bss["ssid"])

    assert {row[3]["id"] for row in rows} == expected_macs
    ssids = collections.Counter(row[2]["ssid"] for row in rows)
    bands = collections.Counter(row[1]["band"] for row in rows)
    ssid_bands = collections.Counter((row[2]["ssid"], row[1]["band"]) for row in rows)
    owners = collections.Counter(row[0]["name"] for row in rows)
    print(f"PASS devices={len(devices)} agents={args.agents} clients={len(rows)} topology={args.topology}")
    print("SSIDs", dict(ssids), "bands", dict(bands), "owners", dict(owners))
    print("SSID/band", {f"{ssid}/{band}": count for (ssid, band), count in ssid_bands.items()})
    if args.require_metrics:
        signals = collections.Counter(row[3]["signal_raw"] for row in rows)
        print("metrics", dict(signals))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
