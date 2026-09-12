#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
import time
import urllib.request


def parse_timestamp(value):
    return dt.datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", value).replace("Z", "+00:00"))


def convergence_state(optimizer, clients):
    fleet = optimizer.get("fleet") or {}
    decisions = optimizer.get("client_decisions") or []
    identity = lambda value: value.lower() if isinstance(value, str) else ""
    current = {identity(client.get("sta_mac")): client for client in clients}
    coverage = bool(clients) and all(current) and len(current) == len(clients) == len(decisions) and (
        sorted(identity(row.get("sta_mac")) for row in decisions) == sorted(current)) and all(
        identity(row.get("source_bssid")) and
        identity(row["source_bssid"]) == identity(current[identity(row.get("sta_mac"))].get("connected_bssid")) and
        isinstance(row.get("current_rcpi"), (int, float)) and not isinstance(row["current_rcpi"], bool) and
        math.isfinite(row["current_rcpi"]) for row in decisions)
    same_band_best = coverage and all(all(
        isinstance(score.get("gain_rcpi"), (int, float)) and not isinstance(score["gain_rcpi"], bool) and
        math.isfinite(score["gain_rcpi"]) and score["gain_rcpi"] <= 0
        for score in row.get("scores", []) if score.get("band") == row.get("current_band"))
        for row in decisions)
    return {
        "decision_coverage": bool(coverage),
        "policy_converged": bool(coverage) and fleet.get("converged") is True,
        "absolute_best_converged": bool(same_band_best) and fleet.get("converged") is True and fleet.get("clients_with_stronger_ap") == 0,
        "stronger_candidates": fleet.get("stronger_candidates", []),
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only default room freshness/convergence check.")
    parser.add_argument("--room-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--require-absolute-best", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    stable_since = None
    criterion = "absolute_best_converged" if args.require_absolute_best else "policy_converged"
    report = {"passed": False, "url": args.room_url, "started": time.time(), "convergence_criterion": criterion}
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
                convergence = convergence_state(optimizer, clients)
                sample["convergence"] = convergence
                checks = {
                    "healthy": bool(health.get("healthy")),
                    "default_roster": health.get("api_total") == 20 and len({client["sta_mac"] for client in clients}) == len(clients) == 20 and state["expected_online_clients"] == 20 and all(role["present"] for role in state["roles"].values()),
                    "paused_unleased": state["playback"]["status"] == "paused" and state["playback"]["time_ms"] == 0 and not state["lease"]["held"] and not state["fault"],
                    "action_limit": optimizer.get("maximum_actions") == 100,
                    "current_epoch": current["environment_epoch"] == state["environment_epoch"] == optimizer.get("environment_epoch"),
                    "complete": bool(fleet.get("measurement_complete")) and fleet.get("clients_checked") == 20 and fleet.get("clients_evaluated") == 20,
                    "converged": convergence[criterion],
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
