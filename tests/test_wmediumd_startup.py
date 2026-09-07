import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FUNCTION = (ROOT / "scripts/radio-lab.sh").read_text().split(
    "start_userspace_medium()\n", 1
)[1].split("\nstart_kernel_medium()", 1)[0]


class WmediumdStartupTests(unittest.TestCase):
    def run_startup(self, behavior):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "build/bin").mkdir(parents=True)
            (root / "patches/wmediumd").mkdir(parents=True)
            (root / "patches/wmediumd/test.patch").write_text("fixture\n")
            (root / "config").write_text("fixture\n")
            daemon = root / "build/bin/wmediumd"
            daemon.write_text("""#!/usr/bin/env python3
import os
import socket
import sys
import time

behavior = os.environ['STARTUP_BEHAVIOR']
if behavior == 'exit':
    print('fixture startup failure', flush=True)
    sys.exit(1)
time.sleep(1.3)
sockets = []
for option in ('-C', '-R', '-O'):
    if behavior == 'missing' and option == '-O':
        continue
    connection = socket.socket(socket.AF_UNIX)
    connection.bind(sys.argv[sys.argv.index(option) + 1])
    sockets.append(connection)
time.sleep(30)
""")
            daemon.chmod(0o755)
            script = """set -eu
cd "$ROOT"
export WMEDIUMD_RUNTIME="$ROOT/runtime"
export WMEDIUMD_CONFIG="$ROOT/config"
export WMEDIUMD_CONFIG_SNAPSHOT="$ROOT/config-snapshot"
export WMEDIUMD_CONTROL="$WMEDIUMD_RUNTIME/control.sock"
export WMEDIUMD_METRICS="$WMEDIUMD_RUNTIME/metrics.sock"
export WMEDIUMD_OBSERVER="$WMEDIUMD_RUNTIME/observer.sock"
export WMEDIUMD_PIDFILE="$ROOT/daemon.pid"
export WMEDIUMD_DAEMON_MANIFEST="$ROOT/daemon-manifest"
export WMEDIUMD_LOG="$ROOT/daemon.log"
export WMEDIUMD_COMMIT=fixture
export WMEDIUMD_CPU_AFFINITY=
patchset=$(sha256sum patches/wmediumd/*.patch | sha256sum | awk '{print $1}')
printf 'WMEDIUMD_COMMIT=fixture\nWMEDIUMD_PATCHSET_SHA256=%s\n' "$patchset" > build/bin/wmediumd.provenance.env
stop_medium() {
    if [ -f "$WMEDIUMD_PIDFILE" ]; then
        daemon_pid=$(cat "$WMEDIUMD_PIDFILE")
        kill "$daemon_pid" 2>/dev/null || true
        wait "$daemon_pid" 2>/dev/null || true
        rm -f "$WMEDIUMD_PIDFILE"
    fi
    rm -f "$WMEDIUMD_CONTROL" "$WMEDIUMD_METRICS" "$WMEDIUMD_OBSERVER"
}
getent() { return 1; }
trap stop_medium EXIT
""" + "start_userspace_medium()\n" + FUNCTION + "\nstart_userspace_medium\n"
            return subprocess.run(
                ["bash", "-c", script],
                env={**os.environ, "ROOT": directory, "STARTUP_BEHAVIOR": behavior},
                capture_output=True, text=True, timeout=20,
            )

    def test_waits_for_delayed_sockets(self):
        result = self.run_startup("delayed")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reports_early_exit(self):
        result = self.run_startup("exit")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture startup failure", result.stderr)

    def test_requires_every_socket_with_bounded_wait(self):
        result = self.run_startup("missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("within 10 seconds", result.stderr)


if __name__ == "__main__":
    unittest.main()
