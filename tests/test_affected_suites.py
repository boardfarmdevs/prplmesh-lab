"""affected-suites.py: what a change needs (the lab VM's step, the suite sections)."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "affected_suites", Path(__file__).resolve().parent / "affected-suites.py")
affected = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(affected)


def test_documents_and_the_site_need_nothing():
    result = affected.plan(["docs/guides/build-vm.md", "README.md", "explorer/app.js",
                            "medium/docs/x.md"])
    assert result["step"] == "none"
    assert result["sections"] == []


def test_native_patches_need_new_archives_and_every_section():
    result = affected.plan(["patches/prplmesh/0001-x.patch"])
    assert result["step"] == "artifacts"
    assert result["sections"] == affected.SECTIONS


def test_the_client_build_is_an_archive_input():
    assert affected.plan(["scripts/container/build-hostap-client-inside.sh"])["step"] == "artifacts"


def test_the_container_images_need_a_build():
    assert affected.plan(["scripts/container/setup-client-base.sh"])["step"] == "build"
    assert affected.plan(["deploy/lxd-vm/build.sh"])["step"] == "build"


def test_the_medium_and_the_containers_scripts_are_an_update():
    for path in ("medium/wmediumd/patches/0040-x.patch", "medium/hwsim/patch.diff",
                 "scripts/container/setup-client.sh", "deploy/guest/prplmesh-lab-start"):
        assert affected.plan([path])["step"] == "update", path
    assert {"rf", "rooms"} <= set(affected.plan(["medium/wmediumd/x.c"])["sections"])


def test_the_controller_ui_runs_the_browser_sections():
    result = affected.plan(["controller-ui/web/app.js"])
    assert result["step"] == "update"
    assert {"webui", "browser"} <= set(result["sections"])


def test_an_unknown_path_runs_everything_and_the_highest_step_wins():
    result = affected.plan(["docs/a.md", "something/new.bin", "tests/x.sh"])
    assert result["step"] == "build"
    assert result["sections"] == affected.SECTIONS


def test_the_soak_is_never_chosen():
    every = [p for p, _, _ in affected.RULES] + ["unknown/path"]
    assert "soak" not in affected.plan(every)["sections"]
