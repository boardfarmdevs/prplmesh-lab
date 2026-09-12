import importlib.util
import json
from pathlib import Path
import select
import subprocess
import sys


SCRIPT = Path(__file__).with_name("room-feature-host-monitor.py")
SPEC = importlib.util.spec_from_file_location("host_monitor", SCRIPT)
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)


def test_cpu_sampling_requires_an_interval_and_excludes_idle_and_iowait():
    assert MONITOR.cpu_busy([10, 0, 0, 20, 5, 0, 0, 0], None) is None
    assert MONITOR.cpu_busy([10, 0, 0, 20, 5, 0, 0, 0], [0] * 8) == 28.57
    assert MONITOR.cpu_busy([0] * 8, [0] * 8) is None


def test_owned_sampler_produces_multiple_samples_and_exits_on_stdin_close():
    process = subprocess.Popen([sys.executable, "-u", str(SCRIPT), "--interval", ".1",
                                "--duration", "30", "--watch-stdin"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        for index in range(2):
            assert select.select([process.stdout], [], [], 3)[0]
            sample = json.loads(process.stdout.readline())
            assert sample["available_memory_kib"] > 0
            assert sample["per_cpu_busy_percent"]
            assert (sample["cpu_busy_percent"] is None) == (index == 0)
        process.stdin.close()
        assert process.wait(timeout=3) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()
