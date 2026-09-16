#!/usr/bin/env python3
"""Bounded downlink data-loss and reverse-ACK qualification of native STA counters."""

import argparse
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(*arguments, timeout=15):
    return subprocess.run(arguments, check=True, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout).stdout


def endpoint(mode, address, seconds, port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as channel:
        started = time.monotonic()
        packets = 0
        unique = set()
        if mode == "receive":
            channel.bind((address, port))
            channel.settimeout(.2)
            print("ready", flush=True)
            while time.monotonic() - started < seconds + 1:
                try:
                    data = channel.recv(2000)
                except socket.timeout:
                    continue
                if len(data) == 1000 and data[4:] == bytes(996):
                    unique.add(struct.unpack("!I", data[:4])[0])
                    packets += 1
        else:
            channel.settimeout(.1)
            while time.monotonic() - started < seconds:
                try:
                    channel.sendto(struct.pack("!I", packets) + bytes(996), (address, port))
                except (TimeoutError, BlockingIOError):
                    continue
                packets += 1
                time.sleep(max(0, started + packets / 400 - time.monotonic()))
        print(json.dumps({"packets": packets, "unique_packets": len(unique),
                          "seconds": time.monotonic() - started}), flush=True)


def kernel_counters(text):
    fields = {"tx packets": "packets_sent", "rx packets": "packets_received",
              "tx retries": "retransmissions", "tx failed": "tx_packet_errors",
              "rx drop misc": "rx_packet_errors", "tx bytes": "bytes_sent",
              "rx bytes": "bytes_received"}
    return {fields[match[1]]: int(match[2]) for match in
            re.finditer(r"(?m)^\s*(tx packets|rx packets|tx retries|tx failed|rx drop misc|tx bytes|rx bytes):\s*(\d+)\s*$", text)}


def qualify_trial(trial, byte_unit):
    driver = trial["kernel_deltas"]
    native = trial["native_deltas"]
    require(driver["packets_sent"] > 0, "no actual AP downlink traffic")
    require(all(value >= 0 for value in (*driver.values(), *native.values())), "counter reset during trial")
    for key in ("retransmissions", "tx_packet_errors"):
        require(abs(native[key] - driver[key]) <= max(10, driver[key] * .1),
                f"{trial['name']}: native {key} {native[key]} differs from kernel {driver[key]}")
    require(abs(native["bytes_sent"] * byte_unit - driver["bytes_sent"])
            <= max(2 * byte_unit, driver["bytes_sent"] * .1), "native byte units differ from AP driver")
    received, sent = trial["receiver"]["unique_packets"], trial["sender"]["packets"]
    require(sent > 0 and received <= sent, "invalid UDP endpoint accounting")
    if trial["name"] in ("data_loss", "ack_loss"):
        require(driver["retransmissions"] > 0 and driver["tx_packet_errors"] > 0,
                "loss fixture did not exercise retry exhaustion")
    if trial["name"] == "data_loss":
        require(received < sent, "data-loss fixture did not lose data")
    else:
        require(received >= sent * .9, "strong forward-link delivery did not recover")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", choices=("rdk", "prpl"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--yes-change-lab", action="store_true")
    parser.add_argument("--endpoint", choices=("send", "receive"))
    parser.add_argument("--address")
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--port", type=int, default=55209)
    args = parser.parse_args()
    if args.endpoint:
        endpoint(args.endpoint, args.address, args.seconds, args.port)
        return 0
    require(os.geteuid() == 0 and args.yes_change_lab and args.stack and args.output,
            "requires root, --stack, --output and --yes-change-lab")
    require(4 <= args.seconds <= 10, "bounded trials require 4..10 seconds")
    from optimizer.load_observer import NativeLoadProvider
    from wmdcfg.actuator import ControlClient
    from wmdcfg.rf_qualify import MediumRestarter, association_identity, restore_actions
    from wmdcfg.rf_spatial import registered_radio, private_channels, roam_client

    with urllib.request.urlopen("http://127.0.0.1:8891/api/demo/interactions", timeout=5) as response:
        interaction = json.load(response)
    require(not interaction["lease"]["held"] and not interaction["recording"]["active"], "room is in use")
    require(interaction["selected_world"] == "home-five-agent--private-client-room-walk"
            and interaction["expected_online_clients"] == 20
            and interaction["playback"]["status"] == "paused"
            and interaction["playback"]["time_ms"] == 0
            and not interaction["playback"]["manual_roles"], "requires untouched paused default room")
    rdk = args.stack == "rdk"
    client = "wlan-client" if rdk else "prpl-client-01"
    nodes = ["bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003"] if rdk else [
        "prpl-controller", "prpl-agent-01", "prpl-agent-02", "prpl-agent-03", "prpl-agent-04"]
    service = "easymesh-room-demo" if rdk else "prplmesh-room-demo"
    medium = MediumRestarter("rdk" if rdk else "prplmesh")
    registered = {row[field] for row in medium.links for field in ("source", "destination")}
    def identity():
        return association_identity(command("lxc", "exec", client, "--", "iw", "dev", "wlan0", "link"))
    original = identity()
    require(original is not None, "client must already be associated")
    matches = [(node, interface, radio) for node in nodes for interface, radio in
               private_channels(command("lxc", "exec", node, "--", "iw", "dev")).items()
               if (radio["bssid"], radio["frequency"]) == original]
    require(len(matches) == 1, "serving private AP must be unambiguous")
    ap, interface, radio = matches[0]
    ap_radio = registered_radio(ap, interface, registered)
    client_radio = registered_radio(client, "wlan0", registered)
    station = command("lxc", "exec", client, "--", "cat", "/sys/class/net/wlan0/address").strip()
    processes = {node: json.loads(command("lxc", "query", f"/1.0/instances/{node}/state"))["pid"]
                 for node in (ap, client)}
    def net(node, *arguments):
        return command("nsenter", "-t", str(processes[node]), "-n", *arguments)
    address = next(row["local"] for row in json.loads(net(client, "ip", "-j", "-4", "addr", "show", "wlan0"))[0]["addr_info"]
                   if row["scope"] == "global")
    bridge = json.loads(net(ap, "ip", "-j", "link", "show", interface))[0].get("master", interface)
    require(not net(ap, "ip", "route", "show", "exact", address + "/32").strip(), "AP host route already exists")
    updates = [{"source": source, "destination": destination, "frequency_mhz": radio["frequency"], "value": 40}
               for source, destination in ((ap_radio, client_radio), (client_radio, ap_radio))]
    original_links = []
    with ControlClient(medium.socket) as control:
        instance = control.status().instance_id
        for row in updates:
            generation, value, override = control.get_frequency_link(row["source"], row["destination"], row["frequency_mhz"])
            original_links.append({**row, "value": value, "override": override})
    def apply(rows):
        with ControlClient(medium.socket) as control:
            require(control.status().instance_id == instance, "medium instance changed")
            control.apply_frequency(control.status().generation + 1, rows)
            for row in rows:
                result = control.get_frequency_link(row["source"], row["destination"], row["frequency_mhz"])
                require(result[1:] == (row["value"], row.get("override", True)), "RF readback mismatch")
    def kernel():
        return kernel_counters(net(ap, "iw", "dev", interface, "station", "get", station))
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"stack": args.stack, "state": "failed", "station": station, "ap": ap,
              "bssid": original[0], "frequency_mhz": original[1], "interface": interface,
              "original_links": original_links, "trials": [], "native_reports": [],
              "direction": "AP to client; reverse impairment affects link-layer ACK reception",
              "source_byte_unit": 1 if rdk else 1024}
    cleanup = []
    children = []
    provider = None
    def native_report(row):
        if any(item["sta_mac"] == station for item in row["traffic"]):
            report["native_reports"].append(row)
    def latest():
        rows = [row for row in report["native_reports"] if any(load["bssid"] == original[0] for load in row["loads"])]
        if not rows:
            return None
        row = rows[-1]
        return {**next(item for item in row["traffic"] if item["sta_mac"] == station),
                "received_at": row["received_at"], "source": row["source"]}
    def fresh(after):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            value = latest()
            if value and value["received_at"] >= after:
                return value
            time.sleep(.1)
        raise RuntimeError("native STA report deadline exceeded")
    try:
        cleanup.append(("restart room", lambda: command("systemctl", "start", service, timeout=120)))
        command("systemctl", "stop", service, timeout=120)
        cleanup.append(("restore association", lambda: roam_client(client, *original)))
        cleanup.append(("restore RF", lambda: apply(original_links)))
        net(ap, "ip", "route", "add", address + "/32", "dev", bridge)
        cleanup.append(("remove AP host route", lambda: net(ap, "ip", "route", "del", address + "/32", "dev", bridge)))
        provider = NativeLoadProvider(nodes[0], report_observer=native_report,
                                      byte_counter_unit_bytes=report["source_byte_unit"])
        apply(updates)
        net(ap, "ping", "-c", "1", "-W", "2", address)
        fresh(time.time())
        for name, forward, reverse in (("baseline", 40, 40), ("data_loss", -5, 40),
                                       ("ack_loss", 40, -20), ("recovery", 40, 40)):
            require(identity() == original, "client association changed before trial")
            before = kernel()
            native_before = latest()
            apply(updates)
            prefix = [sys.executable, str(Path(__file__).resolve()), "--address", address,
                      "--seconds", str(args.seconds), "--port", str(args.port)]
            receiver = subprocess.Popen(["nsenter", "-t", str(processes[client]), "-n", *prefix, "--endpoint", "receive"],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            children.append(receiver)
            require(receiver.stdout.readline().strip() == "ready", "UDP receiver did not bind")
            sender = subprocess.Popen(["nsenter", "-t", str(processes[ap]), "-n", *prefix, "--endpoint", "send"],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            children.append(sender)
            deadline = time.monotonic() + args.seconds
            impaired = False
            while time.monotonic() < deadline and sender.poll() is None:
                impaired = not impaired
                apply([{**updates[0], "value": forward}, {**updates[1], "value": reverse}]
                      if impaired else updates)
                time.sleep(.25)
            apply(updates)
            sent, sender_error = sender.communicate(timeout=args.seconds + 3)
            received, receiver_error = receiver.communicate(timeout=3)
            require(sender.returncode == receiver.returncode == 0, sender_error + receiver_error)
            after = kernel()
            native_after = fresh(time.time() + 2)
            require(identity() == original, "client association changed during trial")
            trial = {"name": name, "forward_snr": forward, "reverse_snr": reverse,
                     "impairment_pulse_seconds": .25,
                     "sender": json.loads(sent), "receiver": json.loads(received),
                     "kernel_before": before, "kernel_after": after,
                     "native_before": native_before, "native_after": native_after}
            for label in ("kernel", "native"):
                trial[label + "_deltas"] = {key: trial[label + "_after"][key] - value
                    for key, value in trial[label + "_before"].items()
                    if key in before and type(value) is int}
            report["trials"].append(trial)
        for trial in report["trials"]:
            qualify_trial(trial, report["source_byte_unit"])
        report["state"] = "passed"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=3)
        if provider:
            provider.close()
        report["cleanup_errors"] = restore_actions(reversed(cleanup))
        report["restored"] = not report["cleanup_errors"] and identity() == original
        if not report["restored"]:
            report["state"] = "failed"
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("trials", "native_reports")}))
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
