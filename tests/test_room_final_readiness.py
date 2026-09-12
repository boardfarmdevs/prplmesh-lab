import datetime as dt
import copy
import importlib.util
from pathlib import Path
import pytest


def readiness():
    specification = importlib.util.spec_from_file_location(
        "readiness", Path(__file__).with_name("room-final-readiness.py"))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def room_state():
    return {
        "fleet": {"converged": True, "clients_with_stronger_ap": 1,
                  "stronger_candidates": [{"sta_mac": "aa", "gain_rcpi": 2}]},
        "client_decisions": [{"sta_mac": "AA", "source_bssid": "BB", "current_rcpi": 104,
                             "current_band": "5", "scores": [{"band": "5", "gain_rcpi": 2}]}],
    }, [{"sta_mac": "aa", "connected_bssid": "bb"}]


def test_margin_held_client_is_policy_converged_not_absolute_best(room_state):
    optimizer, clients = room_state
    result = readiness().convergence_state(optimizer, clients)
    assert result["policy_converged"] is True
    assert result["absolute_best_converged"] is False
    assert result["stronger_candidates"] == optimizer["fleet"]["stronger_candidates"]


def test_actionable_client_is_not_converged(room_state):
    optimizer, clients = room_state
    optimizer["fleet"]["converged"] = False
    assert readiness().convergence_state(optimizer, clients)["policy_converged"] is False


@pytest.mark.parametrize("failure", ["missing", "duplicate", "stale_owner", "nan", "bool"])
def test_invalid_decision_coverage_cannot_pass(room_state, failure):
    optimizer, clients = copy.deepcopy(room_state)
    decisions = optimizer["client_decisions"]
    if failure == "missing":
        decisions.clear()
    elif failure == "duplicate":
        decisions.append(decisions[0])
    elif failure == "stale_owner":
        decisions[0]["source_bssid"] = "cc"
    else:
        decisions[0]["current_rcpi"] = float("nan") if failure == "nan" else True
    result = readiness().convergence_state(optimizer, clients)
    assert result["policy_converged"] is False
    assert result["absolute_best_converged"] is False


def test_absolute_best_requires_consistent_scores_and_fleet(room_state):
    optimizer, clients = room_state
    optimizer["client_decisions"][0]["scores"][0]["gain_rcpi"] = 0
    assert readiness().convergence_state(optimizer, clients)["absolute_best_converged"] is False
    optimizer["fleet"]["clients_with_stronger_ap"] = 0
    assert readiness().convergence_state(optimizer, clients)["absolute_best_converged"] is True
    optimizer["fleet"]["converged"] = False
    assert readiness().convergence_state(optimizer, clients)["absolute_best_converged"] is False


def test_native_nanoseconds_work_on_python_310():
    path = Path(__file__).with_name("room-final-readiness.py")
    specification = importlib.util.spec_from_file_location("readiness", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module.parse_timestamp("2026-09-09T21:33:19.167399448Z") == dt.datetime(
        2026, 9, 9, 21, 33, 19, 167399, tzinfo=dt.timezone.utc)
    assert module.parse_timestamp("2026-09-09T21:33:19Z").microsecond == 0
