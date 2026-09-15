import copy
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from room_demo.traffic_experiment import TrafficCancelled, TrafficExperiment, namespace_ping, packet_counts, phase_at
from wmdcfg.traffic_profile import validate_traffic


PHASE = {"role": "client", "start_ms": 5000, "end_ms": 10000,
         "packets_per_second": 10, "payload_bytes": 1200}
WORLD = {"roles": {"client": "station"}, "generations": [{"present": {"client": True}}],
         "duration_ms": 30000,
         "traffic_experiment": {"schema": "easymesh.room-traffic.v1", "phases": [PHASE]}}


def test_ordinary_worlds_have_no_traffic_and_no_worker():
    assert validate_traffic({"roles": {}}) is None
    experiment = TrafficExperiment("192.168.77.1", Mock())
    experiment.sync(None)
    assert experiment.snapshot() == {"state": "idle", "history": []}
    assert experiment._thread is None
    experiment.close()


@pytest.mark.parametrize("change", [
    {"packets_per_second": True}, {"packets_per_second": 201}, {"payload_bytes": 1201},
    {"payload_bytes": 0}, {"end_ms": 28000}, {"role": "gateway"},
    {"target": "8.8.8.8"}, {"start_ms": -1}, {"end_ms": 5000},
])
def test_traffic_profile_rejects_unbounded_or_unbound_input(change):
    world = copy.deepcopy(WORLD)
    world["traffic_experiment"]["phases"] = [{**PHASE, **change}]
    with pytest.raises(ValueError):
        validate_traffic(world)


def test_phases_are_ordered_nonoverlapping_and_have_explicit_off_intervals():
    profile = validate_traffic(WORLD)
    assert phase_at(profile, 4999) is None
    assert phase_at(profile, 5000) == (0, PHASE)
    assert phase_at(profile, 10000) is None
    with pytest.raises(ValueError):
        validate_traffic({**WORLD, "traffic_experiment": {**profile, "phases": [PHASE, PHASE]}})


def test_generated_and_delivered_are_not_copied_from_requested_load():
    assert packet_counts("100 packets transmitted, 0 received, 100% packet loss") == {
        "transmitted_packets": 100, "received_echo_replies": 0}
    assert packet_counts("20 packets transmitted, 19 packets received")["received_echo_replies"] == 19
    assert packet_counts("ping: failed")["transmitted_packets"] is None


@pytest.mark.parametrize("target", ["8.8.8.8", "127.0.0.1", "224.0.0.1", "::1", "0.0.0.0",
                                   "169.254.1.1", "192.0.2.1", "255.255.255.255"])
def test_namespace_traffic_refuses_non_lab_destinations(target):
    with patch("room_demo.traffic_experiment.subprocess.run") as run:
        with pytest.raises(ValueError):
            namespace_ping("wlan-client", target, PHASE, 5000)
        run.assert_not_called()


def test_ping_binds_wireless_and_pins_network_namespace():
    with patch("room_demo.traffic_experiment.subprocess.run",
               return_value=SimpleNamespace(stdout='{"pid":42}')), \
         patch("room_demo.traffic_experiment.os.open", return_value=9) as opened, \
         patch("room_demo.traffic_experiment.os.close") as closed, \
         patch("room_demo.traffic_experiment.subprocess.Popen") as launch:
        _process, count = namespace_ping("wlan-client", "192.168.77.1", PHASE, 5000)
        command = launch.call_args.args[0]
        assert "--net=/proc/self/fd/9" in command
        assert command[command.index("-I") + 1] == "wlan0"
        assert command[-1] == "192.168.77.1" and 0 < count <= 50
        assert launch.call_args.kwargs["pass_fds"] == (9,)
        opened.assert_called_once()
        closed.assert_called_once_with(9)


def test_stale_admission_cannot_launch_after_pause_or_world_switch():
    experiment = TrafficExperiment("192.168.77.1", Mock())
    with pytest.raises(TrafficCancelled), experiment._admit(-1, float("inf")):
        pytest.fail("obsolete job admitted")
    experiment.close()


def test_phase_is_launched_once_and_cancellation_reaps_the_owned_process():
    running, finished = Event(), Event()
    process = Mock(pid=999999, returncode=None)
    process.poll.side_effect = lambda: process.returncode
    process.communicate.return_value = ("3 packets transmitted, 2 received", None)
    launches = []
    def launch(container, target, phase, remaining_ms, *, admit):
        with admit():
            launches.append((container, phase, remaining_ms))
            return process, 50
    def publish(value):
        if value["state"] == "running":
            running.set()
        if value["history"]:
            finished.set()
    def signal_process(_process, _signal):
        process.returncode = 130
    experiment = TrafficExperiment("192.168.77.1", publish, launcher=launch)
    experiment._signal = signal_process
    try:
        experiment.sync(("room", 1, 0), PHASE, "wlan-client", 5000)
        assert running.wait(2)
        experiment.sync(("room", 1, 0), PHASE, "wlan-client", 4000)
        experiment.sync(None)
        assert finished.wait(2)
        result = experiment.snapshot()["history"][-1]
        assert result["state"] == "cancelled"
        assert result["transmitted_packets"] == 3
        assert result["received_echo_replies"] == 2
        assert len(launches) == 1
    finally:
        experiment.close()
    process.communicate.assert_called_once()

@pytest.mark.parametrize("change", [
    {"_closing": True}, {"_faulted": "medium changed"}, {"_lease": None},
    {"_playback_status": "paused"}, {"_playback_status": "completed"},
    {"_roles": {"client": {"present": False}}}, {"_playback_time_ms": 10000},
])
def test_session_traffic_gate_cancels_for_pause_expiry_fault_offline_or_phase_end(change):
    from room_demo.interactions import InteractiveMediumSession
    actor = Mock()
    session = SimpleNamespace(_traffic_experiment=actor, _playback_world={**WORLD, "golden_sha256": "world"},
                              _playback_time_ms=6000, _closing=False, _faulted=None, _lease={},
                              _playback_status="playing", _roles={"client": {"present": True}},
                              _traffic_run=1, plan={"bindings": {"client": {"container": "wlan-client"}}})
    InteractiveMediumSession._sync_traffic(session)
    actor.sync.assert_called_once_with(("world", 1, 0), PHASE, "wlan-client", 4000)
    actor.reset_mock()
    for field, value in change.items():
        setattr(session, field, value)
    InteractiveMediumSession._sync_traffic(session)
    actor.sync.assert_called_once_with(None)


def test_cancel_during_namespace_resolution_revokes_launch_admission():
    resolving, release, cancelled = Event(), Event(), Event()
    launched = []
    def launch(container, target, phase, remaining_ms, *, admit):
        resolving.set()
        assert release.wait(2)
        with admit():
            launched.append(True)
            raise AssertionError("cancelled phase must not start a process")
    def publish(value):
        if value["state"] == "cancelled":
            cancelled.set()
    actor = TrafficExperiment("192.168.77.1", publish, launcher=launch)
    try:
        actor.sync(("room", 1, 0), PHASE, "wlan-client", 5000)
        assert resolving.wait(2)
        actor.sync(None)
        release.set()
        assert cancelled.wait(2)
        assert not launched
    finally:
        release.set()
        actor.close()

def test_traffic_cleanup_failure_cannot_skip_rf_restoration():
    from room_demo.interactions import InteractiveMediumSession
    actor = Mock()
    actor.close.side_effect = RuntimeError("traffic worker failed to stop")
    client = Mock()
    session = SimpleNamespace(_lock=RLock(), _closing=False, _pause_playback=Mock(), _movements={},
                              _recording=None, _movement_threads={}, _playback_thread=None, _restored=False,
                              _traffic_experiment=actor, _client=client, restore=Mock(return_value=True))
    with pytest.raises(RuntimeError, match="failed to stop"):
        InteractiveMediumSession.close(session)
    session.restore.assert_called_once()
    client.close.assert_called_once()
    assert session._client is None
