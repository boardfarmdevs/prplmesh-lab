#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import time
import urllib.request


def parse_timestamp(value):
    return dt.datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", value).replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser(description="Read-only default room freshness/convergence check.")
    parser.add_argument("--room-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    stable_since = None
    report = {"passed": False, "url": args.room_url, "started": time.time()}
    with (args.output / "samples.jsonl").open("w") as stream:
        while time.monotonic() - started < args.timeout:
            sample = {"time": time.time()}
            try:
                states = {}
                for endpoint in ("current", "interactions"):
                    with urllib.request.urlopen(args.room_url.rstrip("/") + "/api/demo/" + endpoint, timeout=10) as response:
                        states[endpoint] = json.load(response)
                current, state = states["current"], states["interactions"]
                health = current.get("health") or {}
                optimizer = current.get("optimizer") or {}
                fleet = optimizer.get("fleet") or {}
                clients = current.get("network", {}).get("clients", [])
                evaluated = parse_timestamp(optimizer["evaluated_at"])
                now = dt.datetime.now(dt.timezone.utc)
                ages = [(now - parse_timestamp(client["metric_observed_at"])).total_seconds() for client in clients]
                same_band_best = all(all(score["gain_rcpi"] <= 0 for score in decision.get("scores", [])
                    if score["band"] == decision["current_band"]) for decision in optimizer.get("client_decisions", []))
                checks = {
                    "healthy": bool(health.get("healthy")),
                    "default_roster": health.get("api_total") == 20 and len({client["sta_mac"] for client in clients}) == len(clients) == 20 and state["expected_online_clients"] == 20 and all(role["present"] for role in state["roles"].values()),
                    "paused_unleased": state["playback"]["status"] == "paused" and state["playback"]["time_ms"] == 0 and not state["lease"]["held"] and not state["fault"],
                    "action_limit": optimizer.get("maximum_actions") == 100,
                    "current_epoch": current["environment_epoch"] == state["environment_epoch"] == optimizer.get("environment_epoch"),
                    "complete": bool(fleet.get("measurement_complete")) and fleet.get("clients_checked") == 20 and fleet.get("clients_evaluated") == 20,
                    "converged": bool(fleet.get("converged")) and fleet.get("clients_with_stronger_ap") == 0 and same_band_best,
                    "fresh": 0 <= (now - evaluated).total_seconds() <= 30 and len(ages) == 20 and all(0 <= age <= 30 for age in ages) and all((client.get("rcpi") or 0) > 0 for client in clients),
                }
                sample["checks"] = checks
                if all(checks.values()):
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 5:
                        report["passed"] = True
                else:
                    stable_since = None
                for endpoint, value in states.items():
                    (args.output / (endpoint + ".json")).write_text(json.dumps(value, indent=2) + "\n")
            except (OSError, ValueError, KeyError, TypeError) as error:
                stable_since = None
                sample["error"] = str(error)
            stream.write(json.dumps(sample) + "\n")
            stream.flush()
            if report["passed"]:
                break
            time.sleep(1)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["finished"] = time.time()
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
