from dataclasses import dataclass, replace
from unittest.mock import Mock, patch

import pytest

from room_demo.conductor import LiveConductor


@dataclass(frozen=True)
class Observation:
    observed_at: str = "before"
    bss_loads: tuple = ()
    client_activity: tuple = ()


def conductor(interactive=True):
    result = object.__new__(LiveConductor)
    result.interactive = interactive
    result._load_provider = None
    result._load_error = None
    return result


def test_interactive_collection_does_not_require_load_policy():
    observer = conductor()
    with patch("room_demo.conductor.NativeLoadProvider") as provider:
        observer._start_rf_observation(False)
    provider.assert_called_once()
    assert observer._load_provider is provider.return_value


def test_noninteractive_signal_session_keeps_collection_opt_in():
    observer = conductor(False)
    with patch("room_demo.conductor.NativeLoadProvider") as provider:
        observer._start_rf_observation(False)
    provider.assert_not_called()


def test_optional_receiver_failure_does_not_stop_signal_steering():
    observer = conductor()
    with patch("room_demo.conductor.NativeLoadProvider", side_effect=RuntimeError("receiver unavailable")):
        observer._start_rf_observation(False)
        with pytest.raises(RuntimeError, match="receiver unavailable"):
            observer._start_rf_observation(True)
    assert observer._load_provider is None
    assert observer._load_error == "receiver unavailable"


def test_observation_snapshot_does_not_replace_policy_measurement_time():
    observer = conductor()
    original = Observation()
    enriched = replace(original, observed_at="after", bss_loads=("native",))
    observer._load_provider = Mock(error=None, enrich=Mock(return_value=enriched))
    assert observer._observe_rf(original, {}, False) is enriched
    assert original.observed_at == "before" and original.bss_loads == ()
    observer._load_provider.enrich.side_effect = ValueError("malformed report")
    assert observer._observe_rf(original, {}, False) == original
    assert observer._load_error == "malformed report"
    with pytest.raises(ValueError, match="malformed report"):
        observer._observe_rf(original, {}, True)
