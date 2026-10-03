"""The lab's side of the LXD monitoring bundle (easymesh-medium's lxd-monitoring/): its
wrapper with this lab's ports, the import's opt-in flag and the exporters' copy."""

import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LXD = ROOT / "deploy/lxd-vm"


def test_import_monitoring_is_explicit_and_exports_carry_the_medium_bundle():
    importer = (LXD / "import.sh").read_text()
    assert "monitoring=false" in importer.lower() and "--monitoring)" in importer
    assert "observability/enable.sh" in importer and '"$monitoring" = true' in importer.lower()
    for exporter in (LXD / "package.sh", LXD / "package-thin.sh"):
        source = exporter.read_text()
        assert "test ! -d /opt/easymesh-observability" in source
        assert "find observability -type f" in source
        assert 'cp -a "$ROOT/medium/lxd-monitoring" "$BUNDLE/observability"' in source
        assert 'rm -rf "$BUNDLE/observability/tests"' in source


def test_the_wrapper_runs_the_medium_bundle_with_this_vms_ports(tmp_path):
    lab = tmp_path / "deploy/lxd-vm"
    lab.mkdir(parents=True)
    shutil.copy(LXD / "monitoring.sh", lab)
    shutil.copy(LXD / "instance-config.sh", lab)
    bundle = tmp_path / "medium/lxd-monitoring"
    bundle.mkdir(parents=True)
    (bundle / "enable.sh").write_text(
        'echo "$* base=$LAB_PORT_BASE ui=$LAB_LXD_UI_PORT grafana=$LAB_GRAFANA_PORT"\n'
    )
    # hermetic: not the lab a caller configured (lab-config.sh, the suite), and a host with
    # no other instance, whether or not it has LXD
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "lxc").write_text('#!/bin/sh\n[ "$1" = list ] && echo "[]"\nexit 0\n')
    (tools / "lxc").chmod(0o755)
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith(("PRPLMESH_", "LAB_", "_PRPL"))}
    environment["PATH"] = f"{tools}:{os.environ['PATH']}"
    expected = subprocess.run(
        ["bash", "-c", '. "$1" && prplmesh_instance_config prpl-1001 && echo "$PRPLMESH_PORT_BASE"',
         "-", str(LXD / "instance-config.sh")], capture_output=True, text=True, check=True, env=environment,
    ).stdout.strip()
    result = subprocess.run(["bash", str(lab / "monitoring.sh"), "enable", "prpl-1001", "192.0.2.1"],
                            capture_output=True, text=True, check=True, env=environment)
    base = int(expected)
    assert result.stdout.strip() == f"prpl-1001 192.0.2.1 base={base} ui={base + 3} grafana={base + 4}"
    refused = subprocess.run(["bash", str(lab / "monitoring.sh"), "setup", "prpl-1001"],
                             capture_output=True, text=True, env=environment)
    assert refused.returncode == 2
