import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("native_baseline", Path(__file__).with_name("prepare-native-baseline.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_only_wrong_parent_is_roamed_and_observed_before_success(monkeypatch):
    calls = []
    parents = {"prpl-agent-01": "02:00:00:00:01:02", "prpl-agent-02": "old-parent"}

    def command(*arguments):
        calls.append(arguments)
        container = arguments[4]
        if arguments[-1] == "status":
            return "wpa_state=COMPLETED\nid=0\nssid=mesh_backhaul\nbssid=" + parents[container]
        if "set_network" in arguments:
            assert arguments[-4:] == ("set_network", "0", "bssid", "02:00:00:00:01:02")
            return "OK"
        assert arguments[-2] == "roam"
        parents[container] = arguments[-1]
        return "OK"

    monkeypatch.setattr(MODULE, "command", command)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    assert MODULE.restore_parents(2)["agents"] == 2
    roams = [call for call in calls if call[-2] == "roam"]
    assert len(roams) == 1 and roams[0][4] == "prpl-agent-02"
    assert sum(call[-1] == "status" for call in calls) == 3


def test_unavailable_parent_fails_without_weakening_topology_gate(monkeypatch):
    monkeypatch.setattr(MODULE, "command", lambda *_args: "wpa_state=DISCONNECTED")
    with pytest.raises(RuntimeError, match="star baseline not established"):
        MODULE.restore_parents(1, seconds=0)
