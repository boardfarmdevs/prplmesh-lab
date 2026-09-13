#!/usr/bin/env python3
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import sys


def command(*arguments, timeout=25):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def identity(flavor):
    instances = json.loads(command("lxc", "query", "/1.0/instances?recursion=2"))
    selected = [item for item in instances if item["name"].startswith(
        ("bpi", "wlan-client") if flavor == "rdk" else ("prpl-controller", "prpl-agent-", "prpl-client-"))]
    result = {item["name"]: {"pid": item["state"]["pid"], "status": item["state"]["status"]}
              for item in selected}
    for item in selected:
        name = item["name"]
        if name.startswith(("wlan-client", "prpl-client-")):
            continue
        if flavor == "rdk":
            services = ["onewifi", "em_agent"] + (["em_ctrl", "em_cli"] if name == "bpibroadband" else [])
            result[name]["services"] = command("lxc", "exec", name, "--", "systemctl", "show",
                *services, "-p", "Id", "-p", "MainPID", "-p", "NRestarts", "-p", "ActiveState")
        else:
            result[name]["services"] = command("lxc", "exec", name, "--", "pgrep", "-a", "-f",
                "beerocks_|ieee1905_transport|hostapd -B")
    result["medium"] = (command("pgrep", "-a", "-x", "wmediumd") if flavor == "prpl" else
                        command("pgrep", "-a", "-f", "^.*[/]wmediumd[.]patched[ ]+-c"))
    return result


def links(mapping):
    def inspect(item):
        role, container = item
        value = command("lxc", "exec", container, "--", "iw", "dev", "wlan0", "link")
        return role, value
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        return dict(workers.map(inspect, mapping.items()))


def band_probe(target):
    if target not in {"10.0.0.1", "192.168.77.1"}:
        raise ValueError("band traffic target must be the lab gateway")
    link_errors = []

    def link():
        result = subprocess.run(["iw", "dev", "wlan0", "link"], capture_output=True, text=True, timeout=3)
        if result.returncode:
            if result.stderr.strip() != "command failed: No such file or directory (-2)":
                raise RuntimeError(result.stderr or result.stdout)
            link_errors.append(result.stderr.strip())
            return ""
        return result.stdout.strip()

    before = link()
    info = command("iw", "dev", "wlan0", "info", timeout=3)
    traffic = subprocess.run(["ping", "-I", "wlan0", "-c", "1", "-W", "1", target],
                             capture_output=True, text=True, timeout=4)
    after = link()

    def owner(value):
        address = re.search(r"(?mi)^Connected to ([0-9a-f:]{17})", value)
        frequency = re.search(r"(?m)^\s*freq:\s*(\d+(?:\.\d+)?)", value)
        return (address[1].lower(), float(frequency[1])) if address and frequency else None

    address = re.search(r"(?m)^\s*addr ([0-9a-f:]{17})$", info)
    return {"link": after, "station": address[1] if address else None,
            "stable_owner": not link_errors and bool(owner(before)) and owner(before) == owner(after),
            "traffic_ok": traffic.returncode == 0, "traffic": traffic.stdout,
            "transport": "native_client_network_namespace", "link_errors": link_errors}


def band_links(request):
    if request["target"] not in {"10.0.0.1", "192.168.77.1"}:
        raise ValueError("band traffic target must be the lab gateway")
    mapping = request["mapping"]
    if not 1 <= len(mapping) <= 4 or any(not re.fullmatch(r"prpl-client-[0-9]{2,3}|wlan-client(?:-[0-9]{3})?", container)
                                       for container in mapping.values()):
        raise ValueError("band probes require one to four bound WLAN clients")
    instances = json.loads(command("lxc", "query", "/1.0/instances?recursion=2", timeout=5))
    processes = {item["name"]: item["state"]["pid"] for item in instances if item["state"]["status"] == "Running"}

    def inspect(item):
        role, container = item
        process = processes.get(container)
        if type(process) is not int or process <= 1:
            raise RuntimeError(f"{container}: native client namespace is unavailable")
        value = command("nsenter", "--target", str(process), "--net", "--", sys.executable,
                        str(Path(__file__).resolve()), "band-probe", request["target"], timeout=15)
        return role, json.loads(value)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        return dict(workers.map(inspect, mapping.items()))


if __name__ == "__main__":
    print(json.dumps(identity(sys.argv[2]) if sys.argv[1] == "identity" else
                     band_links(json.loads(sys.argv[2])) if sys.argv[1] == "band-links" else
                     band_probe(sys.argv[2]) if sys.argv[1] == "band-probe" else links(json.loads(sys.argv[2]))))
