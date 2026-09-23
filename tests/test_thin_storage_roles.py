import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("thin_roles_guard", ROOT / "deploy/guest/thin-image-guard.py")
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def free_space():
    return {"bytes": 1000 * GUARD.GIB, "inodes": 100000000}


@pytest.fixture
def role_templates(tmp_path, monkeypatch):
    roots = {}
    images = {}
    sanitation_paths = {}
    for role, required in (("mesh", GUARD.REQUIRED_NATIVE), ("client", GUARD.REQUIRED_CLIENT)):
        root = tmp_path / role / "rootfs"
        root.mkdir(parents=True)
        for relative in required:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(relative.encode())
        for relative in GUARD.CLEAN:
            (root / relative).mkdir(parents=True, exist_ok=True)
            (root / relative / "old.log").write_text("history")
        evidence = tmp_path / (role + "-evidence")
        GUARD.sanitize(root, evidence, required=required)
        fingerprint = ("a" if role == "mesh" else "b") * 64
        monkeypatch.setattr(GUARD, "image_fingerprint", lambda alias, value=fingerprint: value)
        images[role] = GUARD.publication_record(root, evidence / "sanitation.json", role, required)
        sanitation_paths[role] = evidence / "sanitation.json"
        roots[role] = root
    monkeypatch.setattr(GUARD, "image_fingerprint", lambda alias: images[alias]["image_fingerprint"])
    return roots, images, sanitation_paths


def role_manifest(images):
    return {"schema_version": 3, "expected_instances": 105, "images": images,
            "preparation_capacity": GUARD.role_capacity(images, free_space())}


def test_weighted_full_copy_budget_and_boundaries(role_templates):
    unused_roots, images, unused_paths = role_templates
    images = copy.deepcopy(images)
    images["mesh"]["measured"]["expanded_bytes"] = 2 * GUARD.GIB
    images["client"]["measured"]["expanded_bytes"] = GUARD.GIB // 2
    result = GUARD.role_capacity(images, free_space())
    assert result["required_bytes"] == (5 * result["images"]["mesh"]["budget_bytes_per_instance"]
                                       + 100 * result["images"]["client"]["budget_bytes_per_instance"]
                                       + GUARD.HEADROOM)
    boundary = {"bytes": result["required_bytes"], "inodes": result["required_inodes"]}
    assert GUARD.role_capacity(images, boundary)["status"] == "PASS"
    assert GUARD.role_capacity(images, {**boundary, "bytes": boundary["bytes"] - 1})["status"] == "FAIL"
    assert GUARD.role_capacity(images, {**boundary, "inodes": boundary["inodes"] - 1})["status"] == "FAIL"
    assert GUARD.role_capacity(images, free_space(), 0, 0)["required_bytes"] == GUARD.HEADROOM


@pytest.mark.parametrize("fault", ["missing-role", "same-image", "fingerprint", "measurement", "protected", "headroom"])
def test_role_manifest_tampering_fails_closed(role_templates, fault):
    unused_roots, images, unused_paths = role_templates
    manifest = role_manifest(copy.deepcopy(images))
    record = manifest["images"]["client"]
    if fault == "missing-role":
        del manifest["images"]["mesh"]
    elif fault == "same-image":
        record["image_fingerprint"] = manifest["images"]["mesh"]["image_fingerprint"]
    elif fault == "fingerprint":
        record["image_fingerprint"] = "c" * 64
    elif fault == "measurement":
        record["measured"]["expanded_bytes"] += 4096
    elif fault == "protected":
        record["publication"]["protected_sha256"] = "d" * 64
    else:
        manifest["preparation_capacity"]["headroom_bytes"] -= 1
    with pytest.raises(ValueError):
        GUARD.validate_role_manifest(manifest)


def test_client_template_refuses_native_installation(role_templates):
    roots, unused_images, unused_paths = role_templates
    (roots["client"] / "opt/prpl-install-nl80211").mkdir(parents=True)
    with pytest.raises(ValueError, match="full mesh installation"):
        GUARD.protected_snapshot(roots["client"], GUARD.REQUIRED_CLIENT)


def test_btrfs_never_credits_du_of_shared_roster_extents(role_templates, monkeypatch):
    roots, unused_images, unused_paths = role_templates
    monkeypatch.setattr(GUARD, "stopped_root", lambda name: (roots["mesh"], roots["mesh"].parent))
    monkeypatch.setattr(GUARD, "filesystem_type", lambda path: "btrfs")
    monkeypatch.setattr(GUARD.subprocess, "check_output", lambda *args, **kwargs: pytest.fail("must not sum shared extents"))
    assert GUARD.reclaim_space([GUARD.TEMPLATE], roots["mesh"].parent) == 0


def test_btrfs_limits_pool_capacity_by_sparse_backing_free_space(tmp_path, monkeypatch):
    pool = tmp_path / "lxd/storage-pools/prpl-lab"
    pool.mkdir(parents=True)
    disks = tmp_path / "lxd/disks"
    disks.mkdir()
    (disks / "prpl-lab.img").touch()
    monkeypatch.setattr(GUARD, "filesystem_type", lambda path: "btrfs")
    monkeypatch.setattr(GUARD.os, "statvfs", lambda path: SimpleNamespace(
        f_bavail=50 if path == disks else 100, f_frsize=4096, f_favail=0, f_files=0))
    assert GUARD.available(pool) == {"bytes": 50 * 4096, "inodes": sys.maxsize}


@pytest.mark.parametrize("fault", [None, "wrong-daemon", "already-entered"])
def test_btrfs_namespace_entry_uses_verified_local_daemon(monkeypatch, fault):
    source = Path("/var/snap/lxd/common/lxd/storage-pools/prpl-lab")
    backing = source.parents[1] / "disks/prpl-lab.img"
    devices = {"root": {"type": "disk", "path": "/", "pool": "prpl-lab"}}
    responses = {"/1.0/storage-pools/prpl-lab": {"driver": "btrfs", "config": {"source": str(backing)}},
                 "/1.0": {"environment": {"server_pid": 1234}}}
    monkeypatch.setattr(GUARD, "query", lambda endpoint: responses[endpoint])
    monkeypatch.setattr(Path, "is_file", lambda path: path == backing)
    monkeypatch.setattr(GUARD.subprocess, "check_output", lambda *args, **kwargs: "ext4\n")
    monkeypatch.setattr(Path, "read_bytes", lambda path: b"unrelated\0--logfile\0" if fault == "wrong-daemon"
                        else b"/snap/lxd/current/bin/lxd\0--logfile\0/var/log/lxd\0")
    monkeypatch.delenv("PRPLMESH_THIN_MOUNT_NAMESPACE", raising=False)
    if fault == "already-entered":
        monkeypatch.setenv("PRPLMESH_THIN_MOUNT_NAMESPACE", "1")
    calls = []

    def execute(command, arguments):
        calls.append((command, arguments))
        raise RuntimeError("namespace reexec")

    monkeypatch.setattr(GUARD.os, "execvp", execute)
    if fault:
        with pytest.raises(ValueError):
            GUARD.pool_path(devices)
        assert calls == []
    else:
        with pytest.raises(RuntimeError, match="namespace reexec"):
            GUARD.pool_path(devices)
        assert calls[0][0] == "nsenter"
        assert calls[0][1][:3] == ["nsenter", "--mount=/proc/1234/ns/mnt", "--"]


def test_trim_uses_inner_filesystem_before_outer_guest_discard(monkeypatch):
    monkeypatch.setattr(GUARD, "query", lambda endpoint: {"devices": {}})
    monkeypatch.setattr(GUARD, "pool_path", lambda devices: Path("/pool"))
    monkeypatch.setattr(GUARD, "filesystem_type", lambda path: "btrfs")
    calls = []
    monkeypatch.setattr(GUARD.subprocess, "run", lambda arguments, **kwargs: calls.append(arguments))
    monkeypatch.setattr(sys, "argv", ["guard", "trim-pool"])
    GUARD.main()
    assert calls == [["btrfs", "filesystem", "sync", "/pool"], ["fstrim", "--", "/pool"]]
    source = (ROOT / "deploy/lxd-vm/package-cleanup.sh").read_text()
    assert source.index('thin-image-guard.py" trim-pool') < source.index("fstrim -av")


def test_packaging_preserves_both_images_and_rechecks_before_export():
    cleanup = (ROOT / "deploy/lxd-vm/package-cleanup.sh").read_text()
    package = (ROOT / "deploy/lxd-vm/package-thin.sh").read_text()
    firstboot = (ROOT / "deploy/guest/prepare-thin-firstboot.sh").read_text()
    assert 'for alias in "$PRESERVE_IMAGE_ALIAS" "$PRESERVE_CLIENT_ALIAS"' in cleanup
    assert '"${preserve_fingerprints[@]}" | grep -Fxq "$fingerprint"' in cleanup
    assert 'PRPLMESH_PRESERVE_CLIENT_ALIAS="$CLIENT_IMAGE"' in package
    assert package.index('--client-image "$CLIENT_IMAGE"') < package.index('lxc export "$NAME"')
    assert firstboot.index('CLIENT_IMAGE=$RUNTIME_IMAGE') < firstboot.index('"$RADIO_LAB" deploy')


def test_two_image_preparation_records_both_bindings_without_reclaim_credit(role_templates, tmp_path, monkeypatch, capsys):
    roots, images, paths = role_templates
    pool = tmp_path
    monkeypatch.setattr(GUARD, "stopped_root", lambda name: (roots["client" if name == GUARD.CLIENT_TEMPLATE else "mesh"], pool))
    monkeypatch.setattr(GUARD, "filesystem_type", lambda path: "btrfs")
    monkeypatch.setattr(GUARD, "available", lambda path: free_space())
    state = tmp_path / "state.json"
    monkeypatch.setattr(sys, "argv", ["guard", "prepare-check", "--image", "mesh", "--client-image", "client",
                                     "--sanitation", str(paths["mesh"]), "--client-sanitation", str(paths["client"]),
                                     "--state", str(state), "--reclaim", GUARD.TEMPLATE, GUARD.CLIENT_TEMPLATE])
    GUARD.main()
    manifest = json.loads(state.read_text())
    assert GUARD.validate_role_manifest(manifest) == images
    assert manifest["preparation_capacity"]["reclaim_bytes"] == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"


@pytest.mark.parametrize("fault", [None, "swapped", "missing-image", "wrong-base", "foreign-instance", "count", "space"])
def test_firstboot_checks_both_images_and_actual_remaining_roles(role_templates, monkeypatch, capsys, fault):
    unused_roots, images, unused_paths = role_templates
    manifest = role_manifest(images)
    instances = [{"name": name, "type": "container", "config": {"volatile.base_image": images[role]["image_fingerprint"]},
                  "expanded_devices": {}} for name, role in (("prpl-controller", "mesh"), ("prpl-client-01", "client"))]
    args = SimpleNamespace(image="mesh", client_image="client", existing=2)
    if fault == "swapped":
        args.client_image = "mesh"
    elif fault == "missing-image":
        monkeypatch.setattr(GUARD, "image_fingerprint", lambda alias: "c" * 64)
    elif fault == "wrong-base":
        instances[1]["config"]["volatile.base_image"] = "a" * 64
    elif fault == "foreign-instance":
        instances[1]["name"] = "other-lab"
    elif fault == "count":
        args.existing = 3
    monkeypatch.setattr(GUARD, "query", lambda endpoint: instances if "instances?" in endpoint else {"devices": {}})
    monkeypatch.setattr(GUARD, "pool_path", lambda devices: Path("/pool"))
    monkeypatch.setattr(GUARD, "available", lambda path: {"bytes": 0, "inodes": 0} if fault == "space" else free_space())
    if fault:
        with pytest.raises(ValueError):
            GUARD.firstboot_roles(args, manifest)
    else:
        GUARD.firstboot_roles(args, manifest)
        report = json.loads(capsys.readouterr().out)
        assert report["remaining_mesh"] == 4
        assert report["remaining_clients"] == 99
        assert report["status"] == "PASS"
