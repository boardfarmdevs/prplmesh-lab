#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def command(*arguments):
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def identities():
    instances = json.loads(command("lxc", "query", "/1.0/instances?recursion=2"))
    result = {}
    for instance in instances:
        name = instance["name"]
        if not name.startswith(("prpl-client-", "prpl-agent-", "prpl-controller")):
            continue
        state = instance["state"]
        if state["status"] != "Running":
            raise RuntimeError(f"{name} is not running")
        result[name] = state["pid"]
        if not name.startswith("prpl-client-"):
            result[name + "/services"] = command("lxc", "exec", name, "--",
                "pgrep", "-a", "-f", "beerocks_|ieee1905_transport|hostapd -B")
    if sum(name.startswith("prpl-client-") for name in result) != 100:
        raise RuntimeError("requires the provisioned 100-client pool")
    result["medium-process"] = command("pgrep", "-a", "-x", "wmediumd")
    return result


def main():
    parser = argparse.ArgumentParser(description="Opt-in fixed-pool world switching acceptance; restores default in finally")
    parser.add_argument("--yes-act", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8891")
    parser.add_argument("--controller-url", default="http://127.0.0.1:8092")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--all-worlds", action="store_true", help="test every compatible installed room")
    parser.add_argument("--world", action="append", help="test only these room IDs, then restore default")
    parser.add_argument("--roster-only", action="store_true", help="check membership and health without claiming optimizer convergence")
    parser.add_argument("--skip-presence", action="store_true", help="omit the additional disappear/reappear cycle")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.yes_act:
        parser.error("--yes-act is required: this changes live room RF")
    if args.all_worlds and args.world:
        parser.error("choose --all-worlds or --world, not both")
    lease = None
    lease_renewed = 0.0
    report = {"worlds": [], "restored_default": False, "passed": False}

    def request(path, body=None, *, controller=False, revision=None, method=None):
        headers = {"Content-Type": "application/json"}
        if body is not None:
            body = {**body, "command_id": "smoke-" + uuid.uuid4().hex}
        if revision is not None:
            headers["If-Match"] = f'"world-revision-{revision}"'
        target = (args.controller_url if controller else args.base_url) + path
        query = urllib.request.Request(target, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        try:
            with urllib.request.urlopen(query, timeout=20 if body is not None else 8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if controller and error.code >= 500:
                raise urllib.error.URLError(f"controller HTTP {error.code}") from None
            detail = json.load(error)
            raise RuntimeError(f"{path}: {detail.get('error')}: {detail.get('message')}") from None

    def renew():
        nonlocal lease_renewed
        if time.monotonic() - lease_renewed >= 8:
            request("/api/demo/interactions/lease", {"token": lease})
            lease_renewed = time.monotonic()

    def apply(name):
        renew()
        snapshot = request("/api/demo/interactions")
        result = request("/api/demo/world/apply", {"token": lease, "world": name}, revision=snapshot["revision"])
        print(json.dumps({"applied": name, "target": result["expected_online_clients"],
                          "generation": result["daemon_generation"]}), flush=True)
        return result

    def wait_for_world(name, expected, require_convergence=True):
        started = time.monotonic()
        stable_since = None
        while time.monotonic() - started < args.timeout:
            renew()
            try:
                current = request("/api/demo/current")
                topology = request("/api/topology", controller=True)
            except (TimeoutError, urllib.error.URLError) as error:
                stable_since = None
                print(json.dumps({"waiting": name, "telemetry_unavailable": str(error)}), flush=True)
                time.sleep(2)
                continue
            actual = {station["id"].lower() for device in topology["devices"]
                      for radio in device.get("radios", []) for bss in radio.get("bsses", [])
                      for station in bss.get("clients", [])}
            desired = {mac for role, mac in mac_by_role.items() if current["roles"].get(role, {}).get("present")}
            health = current.get("health", {})
            optimizer = current.get("optimizer", {})
            fleet = optimizer.get("fleet", {})
            converged = (optimizer.get("expected_online_clients") == expected
                         and optimizer.get("environment_epoch") == current.get("environment_epoch")
                         and fleet.get("converged") is True
                         and fleet.get("measurement_complete") is True
                         and fleet.get("clients_checked") == expected
                         and fleet.get("clients_evaluated") == expected
                         and fleet.get("clients_with_stronger_ap") == 0)
            if (actual == desired and len(actual) == expected and len(topology["devices"]) == 5
                    and health.get("healthy") is True and health.get("expected_online_clients") == expected
                    and (converged or not require_convergence)):
                offline = [role for role in mac_by_role if not current["roles"][role]["present"]]
                def verify_offline(role):
                    link = command("lxc", "exec", containers_by_role[role], "--", "iw", "dev", "wlan0", "link")
                    if "Not connected" not in link:
                        raise RuntimeError(f"{role}: controller roster converged but isolated client remains connected")

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
                    list(workers.map(verify_offline, offline))
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since < 10:
                    time.sleep(3)
                    continue
                result = {"world": name, "clients": len(actual), "mesh_nodes": len(topology["devices"]),
                          "elapsed_seconds": round(time.monotonic() - started, 2), "healthy": True,
                          "kernel_offline_clients_verified": len(offline),
                          "passed": True, "fleet_converged": converged,
                          "clients_checked": fleet.get("clients_checked"),
                          "actions_used": optimizer.get("actions_used"),
                          "kernel_current_link_measurements": optimizer.get("kernel_current_link_measurements", []),
                          "associations": [{"sta_mac": client["sta_mac"],
                                            "ap": client["connected_device_name"],
                                            "bssid": client["connected_bssid"],
                                            "rssi_dbm": client["rssi_dbm"]}
                                           for client in current.get("network", {}).get("clients", [])]}
                print(json.dumps(result), flush=True)
                return result
            stable_since = None
            print(json.dumps({"waiting": name, "actual": len(actual), "expected": expected,
                              "healthy": health.get("healthy"), "fleet_converged": converged,
                              "stronger_ap_clients": fleet.get("clients_with_stronger_ap"),
                              "decision": optimizer.get("decision", {}).get("reason"),
                              "actions_used": optimizer.get("actions_used"),
                              "elapsed": round(time.monotonic() - started)}), flush=True)
            time.sleep(3)
        raise RuntimeError(f"{name}: exact {expected}-client roster and measured best-AP convergence not achieved")

    before = identities()
    preflight_deadline = time.monotonic() + args.timeout
    while True:
        current = request("/api/demo/current")
        if current.get("scenario") != "home-five-agent--private-client-room-walk":
            raise RuntimeError("start acceptance from the default room")
        mac_by_role = {client["role"]: client["sta_mac"].lower() for client in current.get("network", {}).get("clients", [])}
        containers_by_role = {client["role"]: client["container"] for client in current.get("network", {}).get("clients", [])}
        if len(mac_by_role) == 20 and current.get("health", {}).get("healthy") is True:
            break
        if time.monotonic() >= preflight_deadline:
            raise RuntimeError("start acceptance from a healthy default 20-client room")
        time.sleep(2)
    pool = request("/api/demo/worlds").get("client_bindings", {})
    if len(pool) != 100 or any(pool.get(role, {}).get("sta_mac", "").lower() != mac
                               for role, mac in mac_by_role.items()):
        raise RuntimeError("catalog identities must cover the full pool and match the default room")
    mac_by_role = {role: client["sta_mac"].lower() for role, client in pool.items()}
    containers_by_role = {role: client["container"] for role, client in pool.items()}
    report["run_id"] = current["run_id"]
    try:
        lease = request("/api/demo/interactions/lease", {"owner": "prplmesh-world-switch-acceptance"})["token"]
        lease_renewed = time.monotonic()
        names = args.world or ([world["id"] for world in request("/api/demo/worlds")["worlds"]] if args.all_worlds else
                 ["home-a-border-hover", "home-a-stationary", "home-b-slow-walk-ten", "home-a-flash-crowd"])
        for name in [*names, "default"]:
            expected = apply(name)["expected_online_clients"]
            try:
                result = wait_for_world(name, expected, require_convergence=not args.roster_only)
            except RuntimeError as error:
                if not args.all_worlds:
                    raise
                current = request("/api/demo/current")
                if current.get("error") or current.get("state") != "running":
                    raise
                result = {"world": name, "expected_clients": expected, "passed": False,
                          "error": str(error), "health": current.get("health"),
                          "optimizer": current.get("optimizer")}
            report["worlds"].append(result)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        for present, expected in (() if args.skip_presence else ((False, 19), (True, 20))):
            renew()
            snapshot = request("/api/demo/interactions")
            request("/api/demo/roles/sta_mobile_01/presence", {"token": lease, "present": present},
                    revision=snapshot["revision"], method="PUT")
            report["worlds"].append(wait_for_world("client-reappear" if present else "client-disappear", expected,
                                                  require_convergence=not args.roster_only))
        report["containers_and_services_unchanged"] = identities() == before
        if not report["containers_and_services_unchanged"]:
            raise RuntimeError("container, service or medium process identity changed")
        report["passed"] = all(world.get("passed") for world in report["worlds"])
        if not report["passed"]:
            raise RuntimeError("one or more rooms failed measured convergence; see per-room results")
    except Exception as error:
        report["error"] = str(error)
        print(json.dumps({"failed": str(error)}), flush=True)
        raise
    finally:
        try:
            if lease is not None:
                if not request("/api/demo/interactions").get("lease", {}).get("held"):
                    lease = request("/api/demo/interactions/lease", {"owner": "prplmesh-world-switch-acceptance"})["token"]
                    lease_renewed = time.monotonic()
                apply("default")
                wait_for_world("default-restore", 20, require_convergence=False)
                report["restored_default"] = True
                query = urllib.request.Request(args.base_url + "/api/demo/interactions/lease", method="DELETE",
                    data=json.dumps({"token": lease, "command_id": "release-" + uuid.uuid4().hex}).encode(),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(query, timeout=20):
                    pass
        except Exception as error:
            report["restore_error"] = str(error)
            print(json.dumps({"restore_failed": str(error)}), flush=True)
        finally:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        if not report["restored_default"] and report["passed"]:
            raise RuntimeError("acceptance did not restore the default room")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
