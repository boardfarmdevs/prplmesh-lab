#!/usr/bin/env python3
"""Read prplMesh NBAPI state from ubus for the Controller UI adapter."""

import argparse
import datetime as dt
import json
import re
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = "Device.WiFi.DataElements.Network"


def ubus(path, method, arguments):
    result = subprocess.run(
        ["ubus", "-t", "5", "call", path, method, json.dumps(arguments)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = result.stdout.lstrip()
    value, _ = json.JSONDecoder().raw_decode(output)
    return value


def instances(relative_path, depth=1):
    value = ubus(ROOT, "_get_instances", {"rel_path": relative_path, "depth": depth})
    return sorted(key.rstrip(".") for key in value)


def parameters(path):
    value = ubus(path, "_get", {"rel_path": "", "depth": 0})
    return value.get(path + ".", {})


def indexed(paths, expression):
    pattern = re.compile(expression)
    values = []
    for path in paths:
        match = pattern.fullmatch(path)
        if match:
            values.append((int(match.group(1)), path))
    return [path for _, path in sorted(values)]


def relative(path):
    """Return a path relative to the DataElements Network root."""
    return path.removeprefix(ROOT + ".")


def band_for(opclass, channel):
    if 81 <= opclass <= 84:
        return "2.4 GHz"
    if 115 <= opclass <= 130:
        return "5 GHz"
    if 131 <= opclass <= 137:
        return "6 GHz"
    if channel <= 14:
        return "2.4 GHz"
    return "unknown"


def rcpi_dbm(value):
    if type(value) in (int, float) and 0 <= value <= 220:
        return round(value / 2 - 110, 1)
    return None


def device_name(device_id, role, fallback_ordinal):
    """Derive stable lab names from the provisioned AL-MAC identity.

    NBAPI instance order is onboarding order. Parallel Agent onboarding makes
    that order intentionally nondeterministic, so it must never define the
    operator-visible Agent ordinal.
    """
    if role == "controller":
        return "controller"
    octets = str(device_id).lower().split(":")
    if len(octets) == 6 and octets[:4] == ["02", "00", "00", "27"]:
        try:
            ordinal = int(octets[4], 16) - 1
        except ValueError:
            ordinal = 0
        if ordinal > 0:
            return f"agent-{ordinal}"
    return f"agent-{fallback_ordinal}"


def topology(objects=None):
    if objects is None:
        device_paths = instances("Device.")
        with ThreadPoolExecutor(max_workers=8) as executor:
            snapshots = executor.map(
                lambda device: ubus(ROOT, "_get", {
                    "rel_path": "" if device == ROOT else relative(device) + ".",
                    "depth": 0 if device == ROOT else 4}),
                [ROOT, *device_paths],
            )
            objects = {}
            for snapshot in snapshots:
                if not isinstance(snapshot, dict):
                    raise ValueError("NBAPI device snapshot is not an object map")
                objects.update(snapshot)
        stations = ubus(ROOT, "_get", {"rel_path": "Device.*.Radio.*.BSS.*.STA.", "depth": 1})
        if not isinstance(stations, dict):
            raise ValueError("NBAPI station snapshot is not an object map")
        station_path = re.compile(rf"{re.escape(ROOT)}\.Device\.\d+\.Radio\.\d+\.BSS\.\d+\.STA\.")
        objects = {key: value for key, value in objects.items() if not station_path.match(key)}
        objects.update(stations)
    if not isinstance(objects, dict):
        raise ValueError("NBAPI snapshot is not an object map")

    def snapshot_instances(relative_path, depth=1):
        prefix = ROOT + "." + relative_path
        return [key.rstrip(".") for key in objects if key.startswith(prefix)]

    def parameters(object_path):
        return objects.get(object_path + ".", {})

    controller_id = parameters(ROOT).get("ControllerID")
    if (not isinstance(controller_id, str) or
            not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", controller_id) or
            controller_id == "00:00:00:00:00:00"):
        raise ValueError("NBAPI controller identity is unavailable")
    controller_id = controller_id.lower()
    device_paths = indexed(snapshot_instances("Device.", 1), rf"{re.escape(ROOT)}\.Device\.(\d+)")
    devices = []
    for display_index, device_path in enumerate(device_paths, 1):
        device_index = int(device_path.rsplit(".", 1)[1])
        device_data = parameters(device_path)
        device_id = device_data.get("ID", "")
        backhaul_path = device_path + ".MultiAPDevice.Backhaul"
        backhaul = parameters(backhaul_path)
        backhaul_stats = parameters(backhaul_path + ".Stats")
        role = "controller" if device_id.lower() == controller_id else "agent"
        device = {
            "id": device_id,
            "name": device_name(device_id, role, display_index - 1),
            "role": role,
            "profile": device_data.get("MultiAPProfile"),
            "software_version": device_data.get("SoftwareVersion"),
            "backhaul": {
                "parent_id": backhaul.get("BackhaulDeviceID"),
                "type": backhaul.get("LinkType"),
                "mac": backhaul.get("BackhaulMACAddress"),
                "station_mac": backhaul.get("MACAddress"),
                "signal_raw": backhaul_stats.get("SignalStrength"),
                "signal_dbm": rcpi_dbm(backhaul_stats.get("SignalStrength")),
                "signal_updated_at": backhaul_stats.get("TimeStamp"),
            },
            "radios": [],
        }

        radio_paths = indexed(
            snapshot_instances(f"Device.{device_index}.Radio.", 1),
            rf"{re.escape(device_path)}\.Radio\.(\d+)",
        )
        for radio_path in radio_paths:
            radio_index = int(radio_path.rsplit(".", 1)[1])
            radio_data = parameters(radio_path)
            profiles = indexed(
                snapshot_instances(relative(radio_path) + ".CurrentOperatingClassProfile.", 1),
                rf"{re.escape(radio_path)}\.CurrentOperatingClassProfile\.(\d+)",
            )
            active = {}
            for profile_path in profiles:
                candidate = parameters(profile_path)
                if candidate.get("Channel"):
                    active = candidate
                    break
            opclass = int(active.get("Class", 0) or 0)
            channel = int(active.get("Channel", 0) or 0)
            radio = {
                "id": radio_data.get("ID", ""),
                "name": radio_data.get("X_PRPLWARE-COM_Name", f"radio-{radio_index}"),
                "band": band_for(opclass, channel),
                "opclass": opclass,
                "channel": channel,
                "utilization": radio_data.get("Utilization"),
                "bsses": [],
            }

            bss_paths = indexed(
                snapshot_instances(f"Device.{device_index}.Radio.{radio_index}.BSS.", 1),
                rf"{re.escape(radio_path)}\.BSS\.(\d+)",
            )
            for bss_path in bss_paths:
                bss_index = int(bss_path.rsplit(".", 1)[1])
                bss_data = parameters(bss_path)
                bss = {
                    "bssid": bss_data.get("BSSID", ""),
                    "ssid": bss_data.get("SSID", ""),
                    "fronthaul": bool(bss_data.get("FronthaulUse")),
                    "backhaul": bool(bss_data.get("BackhaulUse")),
                    "clients": [],
                }
                # Backhaul STAs are already represented by the agent-to-parent
                # topology edge. Rendering them again as ordinary clients
                # produces misleading sta-N labels and inflates client counts.
                if bss["ssid"] == "mesh_backhaul":
                    radio["bsses"].append(bss)
                    continue
                sta_paths = indexed(
                    snapshot_instances(relative(bss_path) + ".STA.", 1),
                    rf"{re.escape(bss_path)}\.STA\.(\d+)",
                )
                for sta_path in sta_paths:
                    sta = parameters(sta_path)
                    mac = sta.get("MACAddress", "")
                    raw_signal = sta.get("SignalStrength")
                    octets = mac.lower().split(":")
                    suffix = octets[4] if len(octets) == 6 else "?"
                    cohort = "iot" if bss["ssid"] == "iot_ssid" or (
                        len(octets) == 6 and octets[3] == "20"
                    ) else "sta"
                    bss["clients"].append(
                        {
                            "id": mac,
                            "name": f"{cohort}-{suffix}",
                            "cohort": cohort,
                            "signal_raw": raw_signal,
                            "signal_dbm": rcpi_dbm(raw_signal),
                            "signal_updated_at": sta.get("TimeStamp"),
                            "ipv4": sta.get("IPV4Address"),
                            "last_connect_seconds": sta.get("LastConnectTime"),
                        }
                    )
                radio["bsses"].append(bss)
            device["radios"].append(radio)
        devices.append(device)

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "prplMesh Device.WiFi.DataElements NBAPI",
        "devices": devices,
    }


class TopologyReader:
    def __init__(self, reader=None):
        self.reader = reader or topology
        self.lock = threading.Lock()
        self.pending = None

    def read(self):
        with self.lock:
            owner = self.pending is None or self.pending.done()
            if owner:
                self.pending = Future()
            pending = self.pending
        if owner:
            try:
                pending.set_result(self.reader())
            except BaseException as error:
                pending.set_exception(error)
        return pending.result()


class TopologyServer(ThreadingHTTPServer):
    def __init__(self, *arguments, **options):
        super().__init__(*arguments, **options)
        self.topology_reader = TopologyReader()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        body = json.dumps(value, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/topology":
            try:
                value = self.server.topology_reader.read()
            except Exception as error:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
            else:
                self.send_json(HTTPStatus.OK, value)
            return
        if self.path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, message, *args):
        print(f"{self.client_address[0]} {message % args}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    server = TopologyServer((args.listen, args.port), Handler)
    print(f"prplMesh internal topology adapter listening on {args.listen}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
