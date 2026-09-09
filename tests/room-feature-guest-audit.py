#!/usr/bin/env python3
import concurrent.futures
import json
import subprocess
import sys


def command(*arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=25)
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


if __name__ == "__main__":
    print(json.dumps(identity(sys.argv[2]) if sys.argv[1] == "identity" else links(json.loads(sys.argv[2]))))
