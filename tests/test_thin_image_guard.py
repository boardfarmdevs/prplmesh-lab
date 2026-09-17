import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("thin_image_guard", ROOT / "deploy/guest/thin-image-guard.py")
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
FINGERPRINT = "a" * 64


@pytest.fixture
def template(tmp_path):
    root = tmp_path / "rootfs"
    for relative in GUARD.CLEAN:
        (root / relative).mkdir(parents=True, exist_ok=True)
        (root / relative / "history").write_bytes(b"old history" * 8192)
    for relative in (*GUARD.REQUIRED_NATIVE, "etc/startup.conf", "var/lib/lease.db", "var/cache/keep"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    (root / "tmp").chmod(0o1777)
    return root


def generous_free():
    return {"bytes": 1000 * GUARD.GIB, "inodes": 10000000}


def test_sanitize_only_history_preserves_all_native_and_startup_bytes(template, tmp_path):
    before = GUARD.protected_snapshot(template)
    report = GUARD.sanitize(template, tmp_path / "evidence")
    assert GUARD.protected_snapshot(template) == before
    assert report["before"]["expanded_bytes"] > report["after"]["expanded_bytes"]
    assert report["protected_before_sha256"] == report["protected_after_sha256"]
    for relative in GUARD.CLEAN:
        assert list((template / relative).iterdir()) == []
    assert (template / "tmp").stat().st_mode & 0o7777 == 0o1777


def test_symlink_and_hardlink_in_history_never_modify_native_or_external_target(template, tmp_path):
    native = template / GUARD.REQUIRED_NATIVE[0]
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep").write_text("untouched")
    (template / "tmp/external").symlink_to(external, target_is_directory=True)
    os.link(native, template / "tmp/native-hardlink")
    expected = native.read_bytes()
    GUARD.sanitize(template, tmp_path / "evidence")
    assert native.read_bytes() == expected
    assert (external / "keep").read_text() == "untouched"


@pytest.mark.parametrize("relative", ["tmp", "var/log", "var", "var/crash", "var/tmp"])
def test_symlinked_cleanup_roots_fail_before_mutation(template, tmp_path, relative):
    path = template / relative
    moved = tmp_path / "outside"
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked cleanup"):
        GUARD.sanitize(template, tmp_path / "evidence")
    assert not (tmp_path / "evidence").exists()
    assert (moved / ("log/history" if relative == "var" else "history")).exists()


def test_mounts_inside_template_fail_closed(template, monkeypatch):
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs:
                        f"1 2 0:1 / {template}/tmp rw - tmpfs tmpfs rw\n"
                        if str(path) == "/proc/self/mountinfo" else original(path, *args, **kwargs))
    with pytest.raises(ValueError, match="mounted rootfs content"):
        GUARD.validate_root(template)


def test_missing_native_and_existing_evidence_fail_closed(template, tmp_path):
    (template / GUARD.REQUIRED_NATIVE[0]).unlink()
    with pytest.raises(ValueError, match="missing native"):
        GUARD.sanitize(template, tmp_path / "missing-native")
    assert (template / "var/log/history").exists()
    with pytest.raises(FileExistsError):
        GUARD.sanitize(template, tmp_path / "missing-native")


def test_source_native_mismatch_leaves_copy_unsanitized(template, tmp_path):
    source = tmp_path / "source"
    shutil.copytree(template, source)
    (source / GUARD.REQUIRED_NATIVE[0]).write_text("different native bytes")
    with pytest.raises(ValueError, match="source/copy native"):
        GUARD.sanitize(template, tmp_path / "evidence", source)
    assert (template / "var/log/history").exists()


def test_source_copy_matches_and_source_history_is_untouched(template, tmp_path):
    source = tmp_path / "source"
    shutil.copytree(template, source)
    before = GUARD.protected_snapshot(source)
    GUARD.sanitize(template, tmp_path / "evidence", source)
    assert GUARD.protected_snapshot(source) == before
    assert (source / "var/log/history").exists()
    assert not (template / "var/log/history").exists()


def test_preservation_failure_retains_before_and_after_not_pass(template, tmp_path, monkeypatch):
    original = GUARD.protected_snapshot
    calls = []

    def tampered(root):
        calls.append(root)
        if len(calls) == 2:
            (root / GUARD.REQUIRED_NATIVE[0]).write_text("corrupted")
        return original(root)

    monkeypatch.setattr(GUARD, "protected_snapshot", tampered)
    evidence = tmp_path / "evidence"
    with pytest.raises(ValueError, match="protected files/native hashes"):
        GUARD.sanitize(template, evidence)
    assert (evidence / "protected-before.json").exists()
    assert (evidence / "protected-after.json").exists()
    assert not (evidence / "sanitation.json").exists()


def test_sparse_and_hardlinked_files_budget_full_expansion(template):
    sparse = template / "tmp/sparse"
    with sparse.open("wb") as stream:
        stream.truncate(1024 * 1024)
    os.link(sparse, template / "tmp/sparse-hardlink")
    assert GUARD.footprint(template)["expanded_bytes"] >= 2 * 1024 * 1024


def test_observed_bloated_105_pool_rejected_clean_estimate_fits():
    available = {"bytes": 154 * GUARD.GIB - 10 * GUARD.GIB, "inodes": 17000000}
    dirty = {"expanded_bytes": 1948921856, "entries": 50000}
    cleaned_estimate = {"expanded_bytes": 1204039680, "entries": 50000}
    assert GUARD.capacity(dirty, available)["status"] == "FAIL"
    assert GUARD.capacity(cleaned_estimate, available)["status"] == "PASS"


def test_byte_inode_boundaries_and_existing_roster():
    measured = {"expanded_bytes": 1000000, "entries": 30000}
    result = GUARD.capacity(measured, generous_free())
    boundary = {"bytes": result["required_bytes"], "inodes": result["required_inodes"]}
    assert GUARD.capacity(measured, boundary)["status"] == "PASS"
    assert GUARD.capacity(measured, {**boundary, "bytes": boundary["bytes"] - 1})["status"] == "FAIL"
    assert GUARD.capacity(measured, {**boundary, "inodes": boundary["inodes"] - 1})["status"] == "FAIL"
    resumed = GUARD.capacity(measured, generous_free(), 26)
    assert resumed["required_bytes"] == 26 * result["budget_bytes_per_instance"] + GUARD.HEADROOM
    for remaining in (-1, 106):
        with pytest.raises(ValueError, match="invalid remaining roster"):
            GUARD.capacity(measured, generous_free(), remaining)


@pytest.mark.parametrize("value", [0, -1, True, "123"])
def test_invalid_measurement_rejected(value):
    with pytest.raises(ValueError, match="invalid measured"):
        GUARD.capacity({"expanded_bytes": value, "entries": 100}, generous_free())


@pytest.mark.parametrize("state,type_name", [("Running", "container"), ("Stopped", "virtual-machine")])
def test_only_stopped_containers_allowed(monkeypatch, state, type_name):
    monkeypatch.setattr(GUARD, "query", lambda endpoint: {"status": state, "type": type_name})
    with pytest.raises(ValueError, match="stopped container"):
        GUARD.stopped_root(GUARD.TEMPLATE)


def test_unsupported_pool_and_root_quotas_rejected(monkeypatch):
    devices = {"root": {"type": "disk", "path": "/", "pool": "default"}}
    monkeypatch.setattr(GUARD, "query", lambda endpoint: {"driver": "zfs"})
    with pytest.raises(ValueError, match="requires nested dir"):
        GUARD.pool_path(devices)
    devices["root"]["size"] = "1GiB"
    with pytest.raises(ValueError, match="root quotas"):
        GUARD.pool_path(devices)


@pytest.fixture
def prepared(template, tmp_path, monkeypatch):
    sanitation = tmp_path / "sanitation"
    GUARD.sanitize(template, sanitation)
    monkeypatch.setattr(GUARD, "stopped_root", lambda name: (template, template.parent))
    monkeypatch.setattr(GUARD, "available", lambda path: generous_free())
    monkeypatch.setattr(GUARD, "query", lambda endpoint:
                        {"target": FINGERPRINT} if "/aliases/" in endpoint else {"type": "container"})
    state = tmp_path / "capacity.json"
    arguments = ["guard", "prepare-check", "--image", "candidate", "--state", str(state),
                 "--sanitation", str(sanitation / "sanitation.json"), "--reclaim", GUARD.TEMPLATE]
    monkeypatch.setattr(sys, "argv", arguments)
    return state, sanitation


def test_preparation_writes_image_bound_measurement_only_after_success(prepared, capsys):
    state, sanitation = prepared
    GUARD.main()
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    manifest = json.loads(state.read_text())
    assert manifest["image_fingerprint"] == FINGERPRINT
    assert manifest["measured"] == json.loads((sanitation / "sanitation.json").read_text())["after"]
    assert manifest["preparation_capacity"]["reclaim_instances"] == [GUARD.TEMPLATE]


@pytest.mark.parametrize("problem", ["enospc", "native-changed", "proof-changed", "scope", "duplicate-reclaim"])
def test_preparation_failure_never_creates_capacity_manifest(prepared, template, monkeypatch, problem):
    state, sanitation = prepared
    if problem == "enospc":
        monkeypatch.setattr(GUARD, "available", lambda path: {"bytes": 0, "inodes": 0})
    elif problem == "native-changed":
        (template / GUARD.REQUIRED_NATIVE[0]).write_text("changed after sanitation")
    elif problem == "proof-changed":
        (sanitation / "protected-before.json").write_text("{}")
    elif problem == "scope":
        path = sanitation / "sanitation.json"
        contents = json.loads(path.read_text())
        contents["cleaned_paths"] = ["usr"]
        path.write_text(json.dumps(contents))
    else:
        monkeypatch.setattr(sys, "argv", [*sys.argv, GUARD.TEMPLATE])
    with pytest.raises(ValueError):
        GUARD.main()
    assert not state.exists()


@pytest.mark.parametrize("free", [{"bytes": 0, "inodes": 1000000}, {"bytes": 100 * GUARD.GIB, "inodes": 0}])
def test_insufficient_copy_workspace_does_not_touch_source(template, monkeypatch, free):
    monkeypatch.setattr(sys, "argv", ["guard", "copy-check"])
    monkeypatch.setattr(GUARD, "stopped_root", lambda name: (template, template.parent))
    monkeypatch.setattr(GUARD, "available", lambda path: free)
    with pytest.raises(ValueError, match="workspace"):
        GUARD.main()
    assert (template / "var/log/history").exists()


def test_native_xattrs_preserved(template, tmp_path):
    native = template / GUARD.REQUIRED_NATIVE[0]
    os.setxattr(native, "user.test", b"preserve this metadata")
    GUARD.sanitize(template, tmp_path / "evidence")
    assert os.getxattr(native, "user.test") == b"preserve this metadata"


@pytest.fixture
def firstboot(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()
    manifest = tmp_path / "capacity.json"
    measured = {"expanded_bytes": 4096, "entries": 10}
    manifest.write_text(json.dumps({"schema_version": 1, "expected_instances": 105,
                                    "image_fingerprint": FINGERPRINT, "measured": measured,
                                    "sanitation": {"status": "PASS", "after": measured,
                                                   "cleaned_paths": list(GUARD.CLEAN),
                                                   "protected_before_sha256": "c" * 64,
                                                   "protected_after_sha256": "c" * 64}}))
    marker = tmp_path / "pending"
    marker.touch()
    calls = tmp_path / "calls"
    calls.touch()
    query_data = {
        "/1.0/images/aliases/prpl-runtime-local": {"target": FINGERPRINT},
        "/1.0/images/" + FINGERPRINT: {"type": "container"},
        "/1.0/profiles/default": {"devices": {"root": {"type": "disk", "path": "/", "pool": "default"}}},
        "/1.0/storage-pools/default": {"driver": "dir", "config": {"source": str(pool)}},
    }
    fake = commands / "lxc"
    fake.write_text("#!/usr/bin/env python3\nimport json, sys\n"
                    f"queries = {query_data!r}\n"
                    "if sys.argv[1] == 'query': print(json.dumps(queries[sys.argv[2]]))\n"
                    "elif sys.argv[1:3] == ['image', 'info']: print('Fingerprint: ' + 'a' * 64)\n"
                    "elif sys.argv[1] != 'list': sys.exit(2)\n")
    fake.chmod(0o755)
    radio = commands / "radio"
    radio.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALLS"\nexit 99\n')
    radio.chmod(0o755)
    environment = {**os.environ, "PRPLMESH_ROOT": str(ROOT), "PROVISIONED_AGENT_COUNT": "4",
                   "PROVISIONED_CLIENT_COUNT": "100", "PRPLMESH_THIN_ALLOW_UNPRIVILEGED": "1",
                   "PRPLMESH_THIN_MARKER": str(marker), "PRPLMESH_THIN_REPORT": str(tmp_path / "report"),
                   "PRPLMESH_THIN_CAPACITY_STATE": str(manifest), "PRPLMESH_LXC_BIN": str(fake),
                   "PRPLMESH_RADIO_LAB": str(radio), "CALLS": str(calls)}
    return environment, manifest, calls


@pytest.mark.parametrize("problem", ["enospc", "fingerprint", "missing", "corrupt", "cardinality", "preservation"])
def test_firstboot_fails_before_any_radio_or_instance_action(firstboot, problem):
    environment, manifest, calls = firstboot
    data = json.loads(manifest.read_text())
    if problem == "enospc":
        data["measured"]["expanded_bytes"] = 1000 * GUARD.GIB
        data["sanitation"]["after"] = data["measured"]
    elif problem == "fingerprint":
        data["image_fingerprint"] = "b" * 64
    elif problem == "cardinality":
        data["expected_instances"] = 25
    elif problem == "preservation":
        data["sanitation"]["protected_after_sha256"] = "d" * 64
    manifest.write_text(json.dumps(data))
    if problem == "missing":
        manifest.unlink()
    elif problem == "corrupt":
        manifest.write_text("not JSON")
    result = subprocess.run(["bash", str(ROOT / "deploy/guest/prepare-thin-firstboot.sh")],
                            env=environment, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "thin image guard:" in result.stderr
    assert not Path(environment["PRPLMESH_THIN_REPORT"]).exists()
    assert Path(environment["PRPLMESH_THIN_MARKER"]).exists()
    assert calls.read_text() == ""
    reports = list(manifest.parent.glob("report.capacity.*.json"))
    assert len(reports) == 1
    if problem == "enospc":
        assert json.loads(reports[0].read_text())["status"] == "FAIL"


def test_firstboot_success_checks_actual_image_and_default_pool(firstboot, monkeypatch, capsys):
    environment, manifest, unused_calls = firstboot
    monkeypatch.setenv("PRPLMESH_LXC_BIN", environment["PRPLMESH_LXC_BIN"])
    monkeypatch.setattr(sys, "argv", ["guard", "firstboot-check", "--state", str(manifest),
                                     "--image", "prpl-runtime-local", "--expected", "105", "--existing", "0"])
    monkeypatch.setattr(GUARD, "available", lambda path: generous_free())
    GUARD.main()
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["remaining_instances"] == 105
    assert report["image_fingerprint"] == FINGERPRINT


def test_prepare_publishes_only_clean_copy_before_alias_switch_or_roster_removal():
    source = (ROOT / "deploy/guest/prepare-thin-image.sh").read_text()
    ordered = ["copy-check", 'lxc copy prpl-controller "$SANITIZED_TEMPLATE"',
               '"$GUARD" sanitize', 'lxc publish "$SANITIZED_TEMPLATE"',
               '"$GUARD" prepare-check', 'lxc image alias delete "$RUNTIME_IMAGE"',
               'lxc delete "$name"', 'lxc delete "$SANITIZED_TEMPLATE"']
    positions = [source.index(fragment) for fragment in ordered]
    assert positions == sorted(positions)
    assert "lxc publish prpl-controller" not in source
    assert "lxc start" not in source


def test_already_thin_exports_cannot_bypass_capacity_or_fingerprint_guard():
    source = (ROOT / "deploy/lxd-vm/package-thin.sh").read_text()
    gate = source.index("thin-image-guard.py firstboot-check")
    assert source.index("thin_repackaged=true") < gate < source.index('lxc export "$NAME"')
    assert source.index("nested_instances_before_export") < gate
    assert "thin-capacity-check.json thin-image-capacity.json" in source
