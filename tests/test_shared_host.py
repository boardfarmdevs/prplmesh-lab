from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HOST = r"""
lxc() {
    test "$*" = 'list --format json'
    cat <<'JSON'
[{"name": "prpl-1001", "status": "Running", "expanded_devices": {"wmediumd-console": {}}},
 {"name": "rdk-1001", "status": "Running", "expanded_devices": {"wmediumd-console": {}}},
 {"name": "prpl-0930", "status": "Stopped", "expanded_devices": {"wmediumd-console": {}}},
 {"name": "prpl-1001-builder", "status": "Running", "expanded_devices": {"eth0": {}}}]
JSON
}
"""


def run(script, **environment):
    functions = subprocess.run(
        ["sed", "-n", "/^other_running_labs()/,/^}/p;/^require_host_to_itself()/,/^}/p",
         str(ROOT / "deploy/lxd-vm/build.sh")], check=True, capture_output=True, text=True).stdout
    return subprocess.run(["bash", "-c", HOST + functions + script], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", **environment})


def test_other_running_lab_vms_are_named():
    assert run("NAME=prpl-1001; other_running_labs").stdout == "rdk-1001\n"
    assert run("NAME=prpl-2000; other_running_labs").stdout == "prpl-1001 rdk-1001\n"


def test_build_and_check_refuse_next_to_another_lab_unless_shared():
    refused = run("NAME=prpl-1001; require_host_to_itself; echo continued")
    assert refused.returncode == 1 and "continued" not in refused.stdout
    assert "rdk-1001" in refused.stderr
    shared = run("NAME=prpl-1001; require_host_to_itself; echo continued", PRPLMESH_SHARED_HOST="1")
    assert shared.returncode == 0 and shared.stdout == "continued\n"


def test_build_and_check_call_the_guard():
    script = (ROOT / "deploy/lxd-vm/build.sh").read_text()
    for function in ("build_vm()", "check_vm()"):
        body = script[script.index(function):]
        body = body[:body.index("\n)\n")]
        assert "require_host_to_itself" in body, function
