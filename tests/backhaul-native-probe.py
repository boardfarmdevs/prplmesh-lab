#!/usr/bin/env python3
import concurrent.futures
import fcntl
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time


def arp_reply(packet, source_mac, target_ip):
    return (len(packet) >= 42 and packet[:6] == source_mac and
            packet[12:22] == bytes.fromhex("08060001080006040002") and
            packet[6:12] == packet[22:28] and packet[28:32] == target_ip and
            packet[32:38] == source_mac and packet[38:42] == bytes(4))


def arp_probe(interface="br-lan", target="192.168.77.1", timeout=1):
    target_ip = socket.inet_aton(target)
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806)) as channel:
        channel.bind((interface, 0))
        source_mac = fcntl.ioctl(channel.fileno(), 0x8927,
                                 struct.pack("256s", interface.encode()))[18:24]
        request = (b"\xff" * 6 + source_mac + bytes.fromhex("08060001080006040001") +
                   source_mac + bytes(4) + bytes(6) + target_ip)
        channel.send(request)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            channel.settimeout(max(0.001, deadline - time.monotonic()))
            try:
                packet = channel.recv(65535)
            except socket.timeout:
                return False
            if arp_reply(packet, source_mac, target_ip):
                return True
    return False


def native_probe(role):
    if role not in {"gateway", *(f"extender_{ordinal}" for ordinal in range(1, 5))}:
        raise ValueError("unknown mesh role")
    ap = subprocess.run(["iw", "dev", "wlan2.1", "info"], capture_output=True,
                        text=True, timeout=3, check=True).stdout
    link = subprocess.run(["iw", "dev", "wlan3", "link"], capture_output=True,
                          text=True, timeout=3)
    if role != "gateway" and link.returncode:
        raise RuntimeError(link.stderr)
    inventory = subprocess.run(["iw", "dev"], capture_output=True,
                               text=True, timeout=3, check=True).stdout
    aps = sum(line.strip() in {"ssid private_ssid", "ssid iot_ssid"}
              for line in inventory.splitlines())
    method = "icmp-local-gateway" if role == "gateway" else "arp-over-wireless-backhaul"
    reachable = (subprocess.run(["ping", "-I", "br-lan", "-q", "-c", "1", "-W", "1", "192.168.77.1"],
                               capture_output=True, timeout=3).returncode == 0
                 if role == "gateway" else arp_probe())
    return {"raw": ap + (link.stdout or "Not connected.\n") +
            f"\nPROBE_EXIT={0 if reachable else 1}\nFRONTHAUL_APS={aps}\n",
            "probeMethod": method}


def collect():
    inventory = json.loads(subprocess.run(["lxc", "query", "/1.0/instances?recursion=2"],
                           capture_output=True, text=True, timeout=5, check=True).stdout)
    processes = {entry["name"]: entry["state"]["pid"] for entry in inventory
                 if entry["state"]["status"] == "Running"}
    containers = {"gateway": "prpl-controller", **{
        f"extender_{ordinal}": f"prpl-agent-{ordinal:02d}" for ordinal in range(1, 5)}}

    def inspect(item):
        role, container = item
        process = processes.get(container)
        if type(process) is not int or process <= 1:
            raise RuntimeError(f"{container}: native mesh namespace is unavailable")
        result = subprocess.run(["nsenter", "--target", str(process), "--net", "--", sys.executable,
                                 str(Path(__file__).resolve()), role], capture_output=True,
                                text=True, timeout=15, check=True)
        return role, json.loads(result.stdout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as workers:
        return dict(workers.map(inspect, containers.items()))


if __name__ == "__main__":
    print(json.dumps(collect() if len(sys.argv) == 1 else native_probe(sys.argv[1])))
