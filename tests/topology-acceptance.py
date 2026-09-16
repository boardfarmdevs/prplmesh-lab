#!/usr/bin/env python3
"""Validate physical hwsim state against the prplMesh NBAPI model."""

import argparse
import collections
import json
import re
import subprocess
import sys
import time
import urllib.request

AP_BASE_INTERFACE = {"2.4 GHz": "wlan0", "5 GHz": "wlan2", "6 GHz": "wlan4"}
AP_SSID_SUFFIX = {"private_ssid": "", "iot_ssid": ".0"}
STATION = re.compile(r"(?m)^Station ([0-9a-fA-F:]{17}) ")


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


def ap_interface(band, ssid):
    try:
        return AP_BASE_INTERFACE[band] + AP_SSID_SUFFIX[ssid]
    except KeyError as error:
        raise ValueError(f"unsupported AP band/SSID: {band}/{ssid}") from error


def parse_ap_stations(output):
    return {match.group(1).lower() for match in STATION.finditer(output)}


def validate_radio_inventory(node, radios):
    assert len(radios) == 3, (node, len(radios))
    by_band = {radio["band"]: radio for radio in radios}
    assert set(by_band) == set(AP_BASE_INTERFACE), (node, set(by_band))
    for offset, band in enumerate(AP_BASE_INTERFACE):
        radio = by_band[band]
        expected_radio = f"02:00:00:00:{node * 3 + offset:02x}:00"
        assert radio["id"] == expected_radio, (node, band, radio["id"], expected_radio)
        assert {bss["ssid"] for bss in radio["bsses"]} == {
            "private_ssid", "iot_ssid", "mesh_backhaul"
        }


def ap_stations(device, radio, bss, cache):
    node = device["name"]
    container = "prpl-controller" if node == "controller" else (
        f"prpl-agent-{int(node.split('-', 1)[1]):02d}"
    )
    interface = ap_interface(radio["band"], bss["ssid"])
    key = (container, interface)
    if key not in cache:
        output = run(
            "lxc", "exec", container, "--", "iw", "dev", interface,
            "station", "dump",
        )
        cache[key] = parse_ap_stations(output)
    return container, interface, cache[key]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--topology", choices=("star", "branch", "chain"), default="chain")
    parser.add_argument("--require-metrics", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8092/api/topology")
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
        validate_radio_inventory(node, device["radios"])
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
    station_cache = {}
    for ordinal in range(1, args.clients + 1):
        cohort = "private" if ordinal % 2 else "iot"
        cohort_ordinal = (ordinal + 1) // 2
        prefix = "10" if cohort == "private" else "20"
        mac = f"02:00:00:{prefix}:{cohort_ordinal:02x}:00"
        expected_macs.add(mac)
        matches = [row for row in rows if row[3]["id"] == mac]
        assert len(matches) == 1, (mac, len(matches))
        device, radio, bss, client = matches[0]
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

        ap_container, interface, station_macs = ap_stations(
            device, radio, bss, station_cache
        )
        assert mac in station_macs, (
            mac, "absent from AP station table", ap_container, interface
        )

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
