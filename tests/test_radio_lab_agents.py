from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts/radio-lab.sh").read_text()


def function(name):
    match = re.search(rf"^{name}\(\)\n\{{\n.*?^\}}\n", SCRIPT, re.S | re.M)
    assert match, name
    return match.group(0)


# the Agent functions as the script has them; the containers and the controller stubbed
FUNCTIONS = "\n".join(function(name) for name in (
    "require_count", "agent_name", "wired_agent_ordinals", "is_wired_agent",
    "start_agent", "start_wired_agent", "start_mesh_agent", "stop_agent"))
STUBS = """
PROVISIONED_AGENT_COUNT=4
PROVISIONED_WIRED_AGENT_COUNT=1
MESH_AGENT_COUNT=5
TOPOLOGY=star
parent_backhaul_bssid() { echo parent-bssid; }
start_container() { :; }
configure_control_priority() { :; }
agent_al() { echo "al-$1"; }
wait_for_model() { :; }
wait_for_agent_controller() { :; }
instance_state() { echo RUNNING; }
# the container commands, recorded apart from what the functions redirect
exec 3>&1
lxc() { echo "lxc $*" >&3; }
"""


def run(command):
    return subprocess.run(["bash", "-euc", STUBS + FUNCTIONS + command],
                          capture_output=True, text=True)


@pytest.mark.parametrize(("ordinal", "setup"), [
    (1, "agent 1 wireless parent-bssid"), (4, "agent 4 wireless parent-bssid"), (5, "agent 5 wired"),
])
def test_an_agent_starts_as_it_was_provisioned(ordinal, setup):
    result = run(f"start_mesh_agent {ordinal}")
    assert result.returncode == 0, result.stderr
    assert f"setup-nl80211-node.sh {setup}" in result.stdout


def test_the_wired_agent_can_be_stopped_and_an_ordinal_beyond_the_agents_cannot():
    stopped = run("stop_agent 5")
    assert stopped.returncode == 0, stopped.stderr
    assert "lxc stop prpl-agent-05" in stopped.stdout
    for command in ("stop_agent 6", "start_mesh_agent 6"):
        refused = run(command)
        assert refused.returncode == 2
        assert "exceeds provisioned maximum" in refused.stderr


def test_a_wifi_agent_is_never_started_as_a_wired_one():
    refused = run("start_wired_agent 2")
    assert refused.returncode == 2
    assert "not a wired Agent" in refused.stderr


def test_the_agent_commands_start_each_agent_as_it_was_provisioned():
    for action in ("start-agent", "restart-agent"):
        arm = SCRIPT.split(f"    {action})\n", 1)[1].split(";;", 1)[0]
        assert "start_mesh_agent" in arm and "start_agent " not in arm
