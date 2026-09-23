#!/usr/bin/env python3
"""Unattended LXD builders must finish without EOF from their caller."""

import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def shell_function(path, name):
    source = (ROOT / path).read_text()
    match = re.search(rf"^{name}\(\)\n\{{\n.*?^\}}", source, re.M | re.S)
    if not match:
        raise AssertionError(f"missing function {name} in {path}")
    return match.group()


class UnattendedLxdTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="prpl-unattended-")
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        self.log = self.work / "calls"
        mock = self.work / "lxc"
        mock.write_text("""#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$MOCK_LXC_LOG"
case "$1" in
    info) exit 1 ;;
    init|launch|exec)
        input=$(cat)
        [ -z "$input" ] || exit 92
        [ "$1" != exec ] || exit "${MOCK_EXEC_RESULT:-0}"
        ;;
esac
""")
        mock.chmod(0o755)
        self.environment = dict(os.environ, PATH=f"{self.work}:{os.environ['PATH']}",
                                MOCK_LXC_LOG=str(self.log),
                                RUNTIME_IMAGE_BUILD_LOG=str(self.work / "runtime.log"))

    def run_with_open_stdin(self, script, expected=0):
        with subprocess.Popen(
            ["bash", "-euc", script], env=self.environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            try:
                result = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                self.fail("unattended command waited for caller stdin")
            output, errors = process.communicate()
        self.assertEqual(result, expected, (output, errors))

    def test_runtime_image_build(self):
        self.environment.update(SOURCE_IMAGE="test-base", IMAGE_ALIAS="test-runtime")
        self.run_with_open_stdin(f'bash "{ROOT}/scripts/build-runtime-image.sh"')
        calls = self.log.read_text()
        self.assertIn("init test-base prpl-runtime-image-build", calls)
        self.assertIn("exec --mode non-interactive prpl-runtime-image-build", calls)
        self.assertIn("publish prpl-runtime-image-build --alias test-runtime", calls)

    def test_runtime_setup_failure_is_not_published(self):
        self.environment.update(SOURCE_IMAGE="test-base", MOCK_EXEC_RESULT="17")
        self.run_with_open_stdin(f'bash "{ROOT}/scripts/build-runtime-image.sh"', expected=1)
        self.assertNotIn("publish ", self.log.read_text())

    def test_client_image_uses_separate_base_setup_and_alias(self):
        self.environment.update(SOURCE_IMAGE="test-base")
        self.run_with_open_stdin(f'bash "{ROOT}/scripts/build-runtime-image.sh" client')
        calls = self.log.read_text()
        self.assertIn("init test-base prpl-client-image-build", calls)
        self.assertIn("scripts/container/setup-client-base.sh", calls)
        self.assertIn("publish prpl-client-image-build --alias prpl-client-local", calls)
        self.assertNotIn("setup-runtime-base.sh", calls)

    def test_vm_exec_argument_and_failure_passthrough(self):
        command = shell_function("deploy/lxd-vm/build.sh", "run")
        self.environment["MOCK_EXEC_RESULT"] = "17"
        self.run_with_open_stdin(command + '\nNAME=test-vm\nrun echo "two words"', expected=17)
        self.assertIn("exec --mode non-interactive test-vm -- echo two words", self.log.read_text())

    def test_native_build_container(self):
        self.run_with_open_stdin(f'bash "{ROOT}/scripts/create-build-container.sh"')
        self.assertIn("launch ubuntu:22.04/amd64 ", self.log.read_text())

    def test_radio_container_creation(self):
        setup = """
RUNTIME_IMAGE=test-runtime
CLIENT_IMAGE=test-client-image
instance_state() { echo STOPPED; }
ensure_project_mount() { :; }
ensure_metrics_mount() { :; }
ensure_radio_device() { :; }
radio_host_name() { echo "radio-$1"; }
ensure_wired_backhaul() { :; }
remove_wired_backhaul() { :; }
"""
        for name, arguments in (("create_node", "test-node 0 wireless"),
                                ("create_client", "test-client 15")):
            with self.subTest(name=name):
                command = shell_function("scripts/radio-lab.sh", name)
                self.run_with_open_stdin(setup + command + f"\n{name} {arguments}")
        self.assertIn("init test-client-image test-client", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
