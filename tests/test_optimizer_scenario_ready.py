import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "optimizer_scenario_ready", Path(__file__).with_name("optimizer-scenario-ready.py")
)
READY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READY)


@pytest.fixture
def scenario(tmp_path):
    plan = {"phases": [{"name": "destination_hold", "start_ms": 40000}],
            "events": [{"time_ms": 40000, "generation": 32, "updates": [1]}]}
    run = tmp_path / "run"
    run.mkdir()
    (run / "event-plan.json").write_text(json.dumps(plan))
    return plan, tmp_path, run


def test_fast_collector_waits_for_crossover(scenario):
    plan, root, run = scenario
    assert not READY.stimulus_ready(plan, root)
    log = run / "medium-events.jsonl"
    log.write_text(json.dumps({"event": "generation", "time_ms": 39000,
                              "plan_generation": 31}) + "\n")
    assert not READY.stimulus_ready(plan, root)
    with log.open("a") as stream:
        stream.write(json.dumps({"event": "generation", "time_ms": 40000,
                                 "plan_generation": 32}) + "\n")
    assert READY.stimulus_ready(plan, root)


def test_partial_or_wrong_generation_cannot_release_collector(scenario):
    plan, root, run = scenario
    log = run / "medium-events.jsonl"
    log.write_text(json.dumps({"event": "generation", "time_ms": 40000,
                              "plan_generation": 31}) + "\n")
    assert not READY.stimulus_ready(plan, root)
    log.write_text(json.dumps({"event": "generation", "time_ms": 40000,
                              "plan_generation": 32}))
    assert not READY.stimulus_ready(plan, root)


@pytest.mark.parametrize("finished", ["summary", "restore"])
def test_restored_stimulus_cannot_qualify(scenario, finished):
    plan, root, run = scenario
    log = run / "medium-events.jsonl"
    log.write_text(json.dumps({"event": "generation", "time_ms": 40000,
                              "plan_generation": 32}) + "\n")
    if finished == "summary":
        (run / "summary.json").write_text('{"outcome":"passed","restored":true}')
    else:
        with log.open("a") as stream:
            stream.write('{"event":"restore"}\n')
    with pytest.raises(RuntimeError):
        READY.stimulus_ready(plan, root)


def test_wrong_plan_fails_closed(scenario):
    plan, root, run = scenario
    (run / "medium-events.jsonl").write_text("")
    (run / "event-plan.json").write_text("{}")
    with pytest.raises(ValueError, match="does not match"):
        READY.stimulus_ready(plan, root)


def test_exited_scenario_fails_without_waiting(scenario, monkeypatch):
    plan, root, run = scenario

    def exited(process_id, signal):
        raise ProcessLookupError

    monkeypatch.setattr(READY.os, "kill", exited)
    with pytest.raises(RuntimeError, match="process exited"):
        READY.wait_for_stimulus(plan, root, 12345, 1)


def test_missing_generation_times_out(scenario, monkeypatch):
    plan, root, run = scenario
    ticks = iter([0, 0.5, 2])
    monkeypatch.setattr(READY.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(READY.time, "sleep", lambda interval: None)
    monkeypatch.setattr(READY.os, "kill", lambda process_id, signal: None)
    with pytest.raises(TimeoutError, match="did not commit"):
        READY.wait_for_stimulus(plan, root, 12345, 1)


def test_phase_without_rf_boundary_fails(scenario):
    plan, root, run = scenario
    plan["events"] = []
    with pytest.raises(ValueError, match="committed RF generation"):
        READY.stimulus_ready(plan, root)
