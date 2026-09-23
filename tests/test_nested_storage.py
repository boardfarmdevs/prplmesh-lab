import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def storage_commands(tmp_path):
    log = tmp_path / "calls"
    mock = tmp_path / "lxc"
    mock.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["CALLS"], "a") as stream:
    stream.write(" ".join(sys.argv[1:]) + "\\n")
arguments = sys.argv[1:]
if arguments == ["query", "/1.0/profiles/default"]:
    print(json.dumps({"devices": {"root": {"type": "disk", "path": "/", "pool": os.environ.get("CURRENT_POOL", "default")}}}))
elif arguments == ["list", "--format", "json"]:
    print(json.dumps([{}] * int(os.environ.get("INSTANCES", "0"))))
elif arguments[:2] == ["storage", "show"]:
    sys.exit(0 if os.environ.get("EXISTING_DRIVER") else 1)
elif arguments[:1] == ["query"]:
    print(json.dumps({"driver": os.environ["EXISTING_DRIVER"]}))
''')
    mock.chmod(0o755)
    for name in ("modprobe", "btrfs"):
        command = tmp_path / name
        command.write_text('#!/bin/bash\necho "' + name + ' $*" >> "$CALLS"\n')
        command.chmod(0o755)
    environment = {**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "CALLS": str(log)}
    for name in ("PRPLMESH_NESTED_STORAGE_POOL", "PRPLMESH_NESTED_STORAGE_DRIVER", "PRPLMESH_NESTED_STORAGE_SIZE"):
        environment.pop(name, None)
    return environment, log


def run_storage(fixture, **overrides):
    environment, log = fixture
    result = subprocess.run(["bash", str(ROOT / "deploy/guest/setup-nested-storage.sh")],
                            env={**environment, **overrides}, capture_output=True, text=True)
    return result, log.read_text() if log.exists() else ""


def test_fresh_guest_selects_named_btrfs_before_provisioning(storage_commands):
    result, calls = run_storage(storage_commands)
    assert result.returncode == 0, result.stderr
    assert "storage create prpl-lab btrfs size=120GiB" in calls
    assert "profile device set default root pool=prpl-lab" in calls
    source = (ROOT / "deploy/lxd-vm/build.sh").read_text()
    assert source.index("bash /opt/prplmesh-lab/deploy/guest/setup-nested-storage.sh") < source.index("run bash /opt/prplmesh-lab/scripts/install-from-artifacts.sh")


def test_existing_matching_pool_is_reused_without_resize(storage_commands):
    result, calls = run_storage(storage_commands, CURRENT_POOL="prpl-lab", EXISTING_DRIVER="btrfs", INSTANCES="105")
    assert result.returncode == 0, result.stderr
    assert "storage create" not in calls
    assert "size=" not in calls


@pytest.mark.parametrize("overrides", [
    {"INSTANCES": "105"}, {"EXISTING_DRIVER": "dir"},
    {"PRPLMESH_NESTED_STORAGE_DRIVER": "zfs"}, {"PRPLMESH_NESTED_STORAGE_SIZE": "0GiB"},
    {"PRPLMESH_NESTED_STORAGE_POOL": "../existing"},
])
def test_refuses_existing_roster_migration_or_incompatible_pool(storage_commands, overrides):
    result, calls = run_storage(storage_commands, **overrides)
    assert result.returncode != 0
    assert "storage create" not in calls
    assert "profile device set" not in calls


def test_explicit_directory_backend_is_available(storage_commands):
    result, calls = run_storage(storage_commands, PRPLMESH_NESTED_STORAGE_DRIVER="dir")
    assert result.returncode == 0, result.stderr
    assert "storage create prpl-lab dir" in calls
    assert "modprobe" not in calls


def test_clients_keep_pinned_supplicant_without_mesh_stack_or_ap_daemon():
    image = (ROOT / "scripts/container/setup-client-base.sh").read_text()
    setup = (ROOT / "scripts/container/setup-client.sh").read_text()
    assert "prpl-install-nl80211-6.0.0.tar.gz" not in image
    assert "prpl-runtime-deps-6.0.0.tar.gz" not in image
    for source in (image, setup):
        assert "hostap-runtime-2.10.tar.gz" in source
        assert "./sbin/wpa_supplicant ./bin/wpa_cli" in source
    for dependency in ("iperf3", "tcpdump", "python3", "libssl3", "libnl-genl-3-200"):
        assert dependency in image
    assert "--no-install-recommends" in image
    assert "apt-get clean" in image
    assert "apt-daily.timer" in image
