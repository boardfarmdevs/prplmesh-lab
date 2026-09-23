import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("arguments,expected,status", [
    (["--prepare-only"], ["preflight", "image mesh", "image client", "modules", "depmod"], 0),
    ([], ["preflight", "image mesh", "image client", "modules", "depmod", "radio-pool", "deploy"], 0),
    (["--unknown"], [], 2),
    (["--prepare-only", "extra"], [], 2),
])
def test_prepare_only_installs_without_touching_loaded_radios(tmp_path, arguments, expected, status):
    scripts = tmp_path / "scripts"
    commands = tmp_path / "commands"
    artifacts = tmp_path / "artifacts"
    for directory in (scripts, commands, artifacts, tmp_path / "build/bin"):
        directory.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/install-from-artifacts.sh", scripts / "install-from-artifacts.sh")
    (artifacts / "SHA256SUMS").write_text("")
    log = tmp_path / "calls"
    log.write_text("")
    programs = {
        scripts / "preflight.sh": 'echo preflight >> "$CALLS"',
        scripts / "build-runtime-image.sh": 'echo "image ${1:-mesh}" >> "$CALLS"',
        scripts / "build-hwsim.sh": 'test "$INSTALL_MODULE" = 1; echo modules >> "$CALLS"',
        scripts / "radio-lab.sh": 'echo "$1" >> "$CALLS"',
        commands / "sudo": 'exec "$@"',
        commands / "lxc": 'test "$*" = "image info prpl-ubuntu-22.04-base"',
        commands / "sha256sum": 'test "$*" = "-c SHA256SUMS"',
        commands / "depmod": 'echo depmod >> "$CALLS"',
        tmp_path / "build/bin/wmediumd": 'exit 0',
    }
    for filename, content in programs.items():
        filename.write_text("#!/bin/bash\nset -eu\n" + content + "\n")
        filename.chmod(0o755)
    environment = {**os.environ, "CALLS": str(log), "PATH": str(commands) + os.pathsep + os.environ["PATH"]}
    environment.pop("PRPL_BASE_IMAGE_ALIAS", None)
    result = subprocess.run(["bash", str(scripts / "install-from-artifacts.sh"), *arguments],
                            env=environment, capture_output=True, text=True)
    assert result.returncode == status, result.stdout + result.stderr
    assert log.read_text().splitlines() == expected


def test_clean_vm_reboots_between_module_installation_and_provisioning():
    builder = (ROOT / "deploy/lxd-vm/build.sh").read_text()
    prepared = builder.index("run bash /opt/prplmesh-lab/scripts/install-from-artifacts.sh --prepare-only")
    rebooted = builder.index('lxc restart "$NAME" --timeout 120', prepared)
    ready = builder.index("wait_agent", rebooted)
    radios = builder.index("run bash /opt/prplmesh-lab/scripts/radio-lab.sh radio-pool", ready)
    provisioned = builder.index("run bash /opt/prplmesh-lab/scripts/radio-lab.sh deploy", radios)
    started = builder.index("run systemctl start prplmesh-lab.service", provisioned)
    assert prepared < rebooted < ready < radios < provisioned < started
