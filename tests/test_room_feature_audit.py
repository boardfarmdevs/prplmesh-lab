import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location("room_feature_audit", Path(__file__).with_name("room-feature-guest-audit.py"))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
LINK = "Connected to 02:00:00:00:01:00 (on wlan0)\n\tfreq: 5180.0\n"
INFO = "Interface wlan0\n\taddr 02:00:00:10:01:00\n"


@pytest.mark.parametrize("after,traffic_ok,stable", [
    (LINK, True, True), (LINK, False, True),
    (LINK.replace("01:00", "02:00"), True, False),
    (LINK.replace("5180.0", "2437"), True, False),
    ("Not connected.", True, False), ("\tfreq: 5180\n", True, False),
])
def test_band_probe_checks_native_owner_and_wlan_traffic(monkeypatch, after, traffic_ok, stable):
    calls = []
    outputs = iter([LINK, INFO, "traffic evidence", after])

    def run(arguments, **kwargs):
        calls.append((list(arguments), kwargs))
        return SimpleNamespace(returncode=0 if arguments[0] != "ping" or traffic_ok else 1,
                               stdout=next(outputs), stderr="")

    monkeypatch.setattr(AUDIT.subprocess, "run", run)
    result = AUDIT.band_probe("192.168.77.1")
    assert result == {"link": after.strip(), "station": "02:00:00:10:01:00", "stable_owner": stable,
                      "traffic_ok": traffic_ok, "traffic": "traffic evidence",
                      "transport": "native_client_network_namespace", "link_errors": []}
    assert calls[2][0] == ["ping", "-I", "wlan0", "-c", "1", "-W", "1", "192.168.77.1"]
    assert [kwargs["timeout"] for _, kwargs in calls] == [3, 3, 4, 3]


def test_band_probe_does_not_invent_station_identity(monkeypatch):
    values = iter([LINK, "Interface wlan0", "traffic", LINK])
    monkeypatch.setattr(AUDIT.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=next(values), stderr=""))
    assert AUDIT.band_probe("10.0.0.1")["station"] is None


@pytest.mark.parametrize("stage", [0, 3])
def test_iw_owner_disappearing_during_query_is_an_unconverged_sample(monkeypatch, stage):
    calls = []
    outputs = [LINK, INFO, "traffic evidence", LINK]
    error = "command failed: No such file or directory (-2)"

    def run(arguments, **kwargs):
        index = len(calls)
        calls.append(arguments)
        return SimpleNamespace(returncode=254 if index == stage else 0,
                               stdout=outputs[index], stderr=error if index == stage else "")

    monkeypatch.setattr(AUDIT.subprocess, "run", run)
    result = AUDIT.band_probe("10.0.0.1")
    assert result["stable_owner"] is False
    assert result["traffic_ok"] is True
    assert result["station"] == "02:00:00:10:01:00"
    assert result["link_errors"] == [error]
    assert len(calls) == 4


def test_other_native_link_errors_remain_fatal(monkeypatch):
    monkeypatch.setattr(AUDIT.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout="", stderr="Operation not permitted"))
    with pytest.raises(RuntimeError, match="Operation not permitted"):
        AUDIT.band_probe("10.0.0.1")


@pytest.mark.parametrize("target", ["localhost", "10.0.0.2", "192.168.77.1; true"])
def test_band_probe_refuses_non_lab_targets(target):
    with pytest.raises(ValueError, match="lab gateway"):
        AUDIT.band_probe(target)
    with pytest.raises(ValueError, match="lab gateway"):
        AUDIT.band_links({"target": target, "mapping": {"client": "prpl-client-01"}})


@pytest.mark.parametrize("container", ["prpl-client-01", "wlan-client", "wlan-client-007"])
def test_band_links_enters_bound_native_namespace_once(monkeypatch, container):
    calls = []
    evidence = {"link": LINK, "station": "02:00:00:10:01:00", "stable_owner": True, "traffic_ok": True}

    def command(*arguments, **kwargs):
        calls.append((arguments, kwargs))
        if arguments[0] == "lxc":
            return json.dumps([{"name": container, "state": {"pid": 1234, "status": "Running"}}])
        return json.dumps(evidence)

    monkeypatch.setattr(AUDIT, "command", command)
    assert AUDIT.band_links({"target": "10.0.0.1", "mapping": {"client": container}}) == {"client": evidence}
    assert calls == [(("lxc", "query", "/1.0/instances?recursion=2"), {"timeout": 5}),
                     (("nsenter", "--target", "1234", "--net", "--", AUDIT.sys.executable,
                       str(Path(AUDIT.__file__).resolve()), "band-probe", "10.0.0.1"), {"timeout": 15})]


@pytest.mark.parametrize("mapping", [{}, {"client": "prpl-controller"}, {"client": "prpl-client-01; true"},
                                    {str(index): "prpl-client-01" for index in range(5)}])
def test_band_links_rejects_unbound_or_unbounded_probes(mapping):
    with pytest.raises(ValueError, match="one to four"):
        AUDIT.band_links({"target": "10.0.0.1", "mapping": mapping})


@pytest.mark.parametrize("process,status", [(0, "Stopped"), (1234, "Stopped"), (1, "Running"), (True, "Running"), ("1234", "Running")])
def test_band_links_refuses_missing_native_namespace(monkeypatch, process, status):
    monkeypatch.setattr(AUDIT, "command", lambda *args, **kwargs: json.dumps([
        {"name": "prpl-client-01", "state": {"pid": process, "status": status}}]))
    with pytest.raises(RuntimeError, match="namespace is unavailable"):
        AUDIT.band_links({"target": "10.0.0.1", "mapping": {"client": "prpl-client-01"}})


def test_command_preserves_failures_and_timeouts(monkeypatch):
    monkeypatch.setattr(AUDIT.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stderr="native failure", stdout=""))
    with pytest.raises(RuntimeError, match="native failure"):
        AUDIT.command("iw", timeout=3)

    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(AUDIT.subprocess, "run", expired)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        AUDIT.command("iw", timeout=3)
    assert caught.value.timeout == 3


def test_full_pool_links_uses_one_inventory_and_native_network_namespaces(monkeypatch):
    calls = []
    mapping = {f"client_{index}": f"prpl-client-{index:02d}" for index in range(1, 101)}
    instances = [{"name": container, "state": {"pid": index + 100, "status": "Running"}}
                 for index, container in enumerate(mapping.values())]

    def command(*arguments, **kwargs):
        calls.append((arguments, kwargs))
        return json.dumps(instances) if arguments[0] == "lxc" else LINK

    monkeypatch.setattr(AUDIT, "command", command)
    assert AUDIT.links(mapping) == dict.fromkeys(mapping, LINK)
    assert calls[0] == (("lxc", "query", "/1.0/instances?recursion=2"), {"timeout": 5})
    assert len(calls) == 101
    assert all(arguments[0] == "nsenter" and arguments[3:] == ("--net", "--", "iw", "dev", "wlan0", "link")
               and options == {"timeout": 3} for arguments, options in calls[1:])


@pytest.mark.parametrize("mapping", [{}, {"client": "prpl-controller"},
                                   {str(index): "wlan-client" for index in range(101)}])
def test_full_pool_links_rejects_unbound_or_oversized_inventory(mapping):
    with pytest.raises(ValueError, match="one to 100"):
        AUDIT.links(mapping)


@pytest.mark.parametrize("process,status", [(0, "Stopped"), (1, "Running"), (True, "Running")])
def test_full_pool_links_preserves_missing_namespace_failure(monkeypatch, process, status):
    monkeypatch.setattr(AUDIT, "command", lambda *args, **kwargs: json.dumps([
        {"name": "wlan-client", "state": {"pid": process, "status": status}}]))
    with pytest.raises(RuntimeError, match="namespace is unavailable"):
        AUDIT.links({"client": "wlan-client"})
