#!/usr/bin/env python3
import datetime
import glob
import json
from pathlib import Path
import signal
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


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
previous = None
deadline = time.monotonic() + 7200
while running and time.monotonic() < deadline:
    counters = list(map(int, read("/proc/stat").splitlines()[0].split()[1:9]))
    elapsed = sum(counters) - sum(previous) if previous else 0
    temperatures = {}
    for directory in glob.glob("/sys/class/hwmon/hwmon*"):
        if read(directory + "/name") not in {"coretemp", "k10temp", "acpitz"}:
            continue
        for path in glob.glob(directory + "/temp*_input"):
            value = read(path)
            if value is not None:
                temperatures[path] = int(value) / 1000
    memory = dict(line.split(":", 1) for line in read("/proc/meminfo").splitlines())
    print(json.dumps({"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cpu_busy_percent": round(100 * (elapsed - counters[3] + previous[3] - counters[4] + previous[4]) / elapsed, 2) if elapsed else None,
        "available_memory_kib": int(memory["MemAvailable"].split()[0]),
        "temperatures_celsius": temperatures,
        "package_throttle_count": read("/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count"),
        "cpu_pressure": read("/proc/pressure/cpu"), "memory_pressure": read("/proc/pressure/memory"),
        "io_pressure": read("/proc/pressure/io")}), flush=True)
    previous = counters
    for interval in range(10):
        if not running:
            break
        time.sleep(1)
