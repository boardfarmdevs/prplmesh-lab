from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0026-bound-ambiorix-signal-dispatch.patch"


@pytest.mark.parametrize("patched", [True, False])
def test_native_signal_dispatch_drains_bursts_without_starvation(tmp_path, patched):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required")
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    fragment = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                         if line.startswith(("+", " ")) and not line.startswith("+++"))
    body = fragment[fragment.index("const auto deadline"):fragment.index("return true;") + len("return true;")]
    body = body.replace("std::chrono::steady_clock::now()", "Clock::now()") if patched else "amxp_signal_read(); return true;"
    source = r'''
#include <chrono>
#include <iostream>
using namespace std::chrono;
struct Clock {
    static microseconds elapsed;
    static steady_clock::time_point now() { return steady_clock::time_point(elapsed); }
};
microseconds Clock::elapsed{0};
unsigned queued = 0, delivered = 0, calls = 0;
microseconds cost{0};
bool refill = false;
int amxp_signal_read() {
    ++calls;
    if (!queued) return -1;
    --queued;
    ++delivered;
    Clock::elapsed += cost;
    if (refill) ++queued;
    return 0;
}
bool dispatch() {
BODY
}
int main() {
    queued = 100000;
    dispatch();
    if (delivered != 256 || queued != 99744) return 1;
    while (queued) dispatch();
    if (delivered != 100000) return 2;
    calls = 0;
    dispatch();
    if (calls != 1) return 3;
    queued = 100;
    delivered = 0;
    cost = microseconds(500);
    dispatch();
    if (delivered != 4 || queued != 96) return 4;
    queued = 1;
    delivered = 0;
    cost = microseconds(0);
    refill = true;
    dispatch();
    if (delivered != 256 || queued != 1) return 5;
    std::cout << "PASS lossless bursts, empty queues, time budget and recursive producers\n";
}
'''.replace("BODY", body)
    program = tmp_path / "dispatch.cpp"
    program.write_text(source)
    binary = tmp_path / "dispatch"
    subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(program), "-o", str(binary)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
    assert result.returncode == (0 if patched else 1), result.stderr
