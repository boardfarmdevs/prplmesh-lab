#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import time


def stimulus_ready(plan, output_root):
    phases = [phase for phase in plan["phases"] if phase["name"] == "destination_hold"]
    if len(phases) != 1:
        raise ValueError("expected exactly one destination_hold phase")
    boundary = phases[0]["start_ms"]
    expected = [event for event in plan["events"]
                if event["time_ms"] == boundary and event.get("updates")]
    if len(expected) != 1:
        raise ValueError("destination_hold must begin with a committed RF generation")
    logs = list(output_root.glob("*/medium-events.jsonl"))
    if not logs:
        return False
    if len(logs) != 1:
        raise ValueError("ambiguous scenario run directory")
    run = logs[0].parent
    if (run / "summary.json").exists():
        raise RuntimeError("scenario finished before optimizer collection started")
    if json.loads((run / "event-plan.json").read_text()) != plan:
        raise ValueError("running scenario does not match the compiled plan")
    events = [json.loads(line) for line in logs[0].read_text().splitlines(keepends=True)
              if line.endswith("\n") and line.strip()]
    if any(event.get("event") == "restore" for event in events):
        raise RuntimeError("scenario restored before optimizer collection started")
    return any(event.get("event") == "generation"
               and event.get("time_ms") == boundary
               and event.get("plan_generation") == expected[0]["generation"]
               for event in events)


def wait_for_stimulus(plan, output_root, process_id, timeout):
    if timeout <= 0 or process_id <= 0:
        raise ValueError("timeout and scenario process ID must be positive")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(process_id, 0)
        except ProcessLookupError as error:
            raise RuntimeError("scenario process exited before RF readiness") from error
        if stimulus_ready(plan, output_root):
            return
        time.sleep(0.1)
    raise TimeoutError("scenario did not commit the destination-hold RF generation")


def main():
    parser = argparse.ArgumentParser(description="Wait for the scenario's verified RF crossover")
    parser.add_argument("plan", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--timeout", default=90, type=float)
    args = parser.parse_args()
    wait_for_stimulus(json.loads(args.plan.read_text()), args.output_root, args.pid, args.timeout)
    print("RF crossover generation committed and read back; starting native optimizer collection")


if __name__ == "__main__":
    main()
