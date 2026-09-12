#!/usr/bin/env python3
import argparse
import datetime
import glob
import json
from pathlib import Path
import signal
import select
import sys
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


running = True


def stop(_signal, _frame):
    global running
    running = False


def cpu_busy(current, previous):
    elapsed = sum(current) - sum(previous) if previous else 0
    if elapsed <= 0:
        return None
    return round(100 * (elapsed - current[3] + previous[3] - current[4] + previous[4]) / elapsed, 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded physical-host resource sampling")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--duration", type=float, default=7200)
    parser.add_argument("--watch-stdin", action="store_true")
    args = parser.parse_args(argv)
    if not .1 <= args.interval <= 10 or not args.interval <= args.duration <= 7200:
        parser.error("requires 0.1..10 second interval and interval..7200 second duration")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    previous = {}
    deadline = time.monotonic() + args.duration
    while running and time.monotonic() < deadline:
        started = time.monotonic()
        counters = {line.split()[0]: list(map(int, line.split()[1:9]))
                    for line in read("/proc/stat").splitlines() if line.startswith("cpu")}
        temperatures = {}
        for directory in glob.glob("/sys/class/hwmon/hwmon*"):
            if read(directory + "/name") not in {"coretemp", "k10temp", "acpitz"}:
                continue
            for path in glob.glob(directory + "/temp*_input"):
                value = read(path)
                if value is not None:
                    temperatures[path] = int(value) / 1000
        memory = dict(line.split(":", 1) for line in read("/proc/meminfo").splitlines())
        frequencies = {path: int(value) for path in glob.glob(
            "/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq") if (value := read(path)) is not None}
        print(json.dumps({"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "cpu_busy_percent": cpu_busy(counters["cpu"], previous.get("cpu")),
            "per_cpu_busy_percent": {name: cpu_busy(values, previous.get(name))
                                     for name, values in counters.items() if name != "cpu"},
            "cpu_frequency_khz": frequencies,
            "available_memory_kib": int(memory["MemAvailable"].split()[0]),
            "temperatures_celsius": temperatures,
            "package_throttle_count": read("/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count"),
            "cpu_pressure": read("/proc/pressure/cpu"), "memory_pressure": read("/proc/pressure/memory"),
            "io_pressure": read("/proc/pressure/io")}), flush=True)
        previous = counters
        next_sample = min(deadline, started + args.interval)
        while running and time.monotonic() < next_sample:
            remaining = min(1, next_sample - time.monotonic())
            if remaining <= 0:
                break
            if args.watch_stdin:
                if select.select([sys.stdin], [], [], remaining)[0] and not sys.stdin.read(1):
                    return 0
            else:
                time.sleep(remaining)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
