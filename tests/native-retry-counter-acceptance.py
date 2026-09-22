#!/usr/bin/env python3
"""Bounded downlink data-loss and reverse-ACK qualification of native STA counters.

Restored covers trial RF, host route, tested STA association and room service state.
Room health is checked separately for up to 60 seconds when the service was active
and its initial health sample supplied the expected client count.
"""

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


def room_service_active(service):
    state = command("systemctl", "show", "--property=ActiveState", "--value", service).strip()
    require(state in ("active", "inactive", "failed"), f"room service state is not stable: {state}")
    return state == "active"


def room_health_sample(timeout):
    with urllib.request.urlopen("http://127.0.0.1:8891/api/demo/current", timeout=timeout) as response:
        health = json.load(response)["health"]
    require(isinstance(health, dict), "room health sample is unavailable")
    return {key: value for key, value in health.items() if key != "evidence_storage"}


def initial_room_health(was_active, expected):
    check = {"state": "not_checked", "room_was_active": was_active,
             "expected_online_clients": expected, "timeout_seconds": 60,
             "initial": None, "final": None}
    if not was_active:
        check["reason"] = "room service was not active"
        return check
    try:
        check["initial"] = room_health_sample(5)
        require(type(check["initial"].get("expected_online_clients")) is int
                and check["initial"]["expected_online_clients"] == expected,
                "initial expected client count is unavailable or differs from the room")
        require(type(check["initial"].get("healthy")) is bool
                and type(check["initial"].get("api_active")) is int,
                "initial room health is unavailable")
    except Exception as error:
        check["reason"] = f"initial room health not sampled: {type(error).__name__}: {error}"
    else:
        check["state"] = "pending"
    return check


def check_room_health(check):
    if check["state"] != "pending":
        return
    check["state"] = "failed"
    deadline = time.monotonic() + check["timeout_seconds"]
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            health = room_health_sample(min(5, remaining))
            check["final"] = health
            check.pop("last_error", None)
            if (time.monotonic() <= deadline and health.get("healthy") is True
                    and health.get("expected_online_clients") == check["expected_online_clients"]
                    and health.get("api_active") == check["expected_online_clients"]):
                check["state"] = "passed"
                return
        except Exception as error:
            check["last_error"] = f"{type(error).__name__}: {error}"
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(1, remaining))
    check["reason"] = (f"room health did not recover to {check['expected_online_clients']} clients "
                       f"within {check['timeout_seconds']} seconds")


def finish_cleanup(report, actions, identity, original, resume_actions=()):
    from wmdcfg.rf_qualify import restore_actions

    report["cleanup_errors"] = restore_actions(actions)
    report["restored_scope"] = ["trial_rf", "ap_host_route", "tested_sta_association", "room_service_state"]
    try:
        restored_identity = identity()
        report["association_after_cleanup"] = restored_identity
        require(restored_identity == original, "tested STA association differs from original")
    except Exception as error:
        report["cleanup_errors"].append(f"verify association: {type(error).__name__}: {error}")
    report["cleanup_errors"].extend(restore_actions(resume_actions))
    check_room_health(report["room_health"])
    report["restored"] = not report["cleanup_errors"]
    if not report["restored"] or report["room_health"]["state"] == "failed":
        report["state"] = "failed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", choices=("rdk", "prpl"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--yes-change-lab", action="store_true")
    parser.add_argument("--endpoint", choices=("send", "receive"))
    parser.add_argument("--address")
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--port", type=int, default=55209)
    parser.add_argument("--shadow-counter-policy", type=Path,
                        help="evaluate the counter veto on actual native report windows without steering")
    args = parser.parse_args()
    if args.endpoint:
        endpoint(args.endpoint, args.address, args.seconds, args.port)
        return 0
    require(os.geteuid() == 0 and args.yes_change_lab and args.stack and args.output,
            "requires root, --stack, --output and --yes-change-lab")
    require(4 <= args.seconds <= 10, "bounded trials require 4..10 seconds")
    require(not args.output.exists(), "use a new output directory to preserve evidence")
    require(not Path("/run/easymesh-suite-room-guard").exists(), "external suite owns room")
    shadow_config = None
    if args.shadow_counter_policy:
        from optimizer.config import load_policy
        shadow_config = load_policy(args.shadow_counter_policy)
        require(shadow_config.load_counter_guard_enabled, "shadow policy must explicitly enable the counter guard")
    from optimizer.load_observer import NativeLoadProvider
    from wmdcfg.actuator import ControlClient
    from wmdcfg.rf_qualify import MediumRestarter, association_identity
    from wmdcfg.rf_spatial import registered_radio, private_channels

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
    room_was_active = room_service_active(service)
    room_health = initial_room_health(room_was_active, interaction["expected_online_clients"])
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
    report = {"stack": args.stack, "state": "failed", "counters_passed": False,
              "room_health": room_health, "station": station, "ap": ap,
              "bssid": original[0], "frequency_mhz": original[1], "interface": interface,
              "original_links": original_links, "trials": [], "native_reports": [],
              "direction": "AP to client; reverse impairment affects link-layer ACK reception",
              "source_byte_unit": 1 if rdk else 1024, "medium_instance": instance}
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
    def stop_child(child):
        if child.poll() is None:
            child.terminate()
            child.communicate(timeout=3)
    def verify_room_service():
        require(room_service_active(service) == room_was_active, "room service active state changed")
    try:
        if room_was_active:
            command("systemctl", "stop", service, timeout=120)
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
            owner_before = identity()
            require(owner_before == original, "client association changed before trial")
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
            owner_after = identity()
            require(owner_after == original, "client association changed during trial")
            trial = {"name": name, "forward_snr": forward, "reverse_snr": reverse,
                     "impairment_pulse_seconds": .25,
                     "sender": json.loads(sent), "receiver": json.loads(received),
                     "kernel_before": before, "kernel_after": after,
                     "native_before": native_before, "native_after": native_after,
                     "association_before": list(owner_before), "association_after": list(owner_after)}
            for label in ("kernel", "native"):
                trial[label + "_deltas"] = {key: trial[label + "_after"][key] - value
                    for key, value in trial[label + "_before"].items()
                    if key in before and type(value) is int}
            report["trials"].append(trial)
        for trial in report["trials"]:
            qualify_trial(trial, report["source_byte_unit"])
        report["counters_passed"] = True
        report["state"] = "passed"
        if shadow_config:
            from optimizer.counter_shadow import shadow_counter_trials
            report["counter_shadow"] = shadow_counter_trials(report, shadow_config)
            require(report["counter_shadow"]["passed"], "native counter shadow did not observe clear/pressure/recovery")
    except Exception as error:
        report["state"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        actions = [("stop UDP endpoint", lambda child=child: stop_child(child)) for child in children]
        if provider:
            actions.append(("close native provider", provider.close))
        actions.extend(reversed(cleanup))
        resume_actions = []
        if room_was_active:
            resume_actions.append(("restart room", lambda: command("systemctl", "start", service, timeout=120)))
        resume_actions.append(("verify room service", verify_room_service))
        finish_cleanup(report, actions, identity, original, resume_actions)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("trials", "native_reports", "counter_shadow")}))
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
