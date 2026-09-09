import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


path = Path(__file__).resolve().parents[2] / "scripts/container/configure-metrics.py"
spec = importlib.util.spec_from_file_location("configure_metrics", path)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def test_configures_native_metrics_and_checks_readback():
    expected = {"LinkMetricsRequestIntervalSec": 1, "StatisticsPollingRateSec": 1,
                "AssocSTALinkMetricsInclusionPolicy": True}
    with patch.object(metrics, "call", side_effect=[{}, {metrics.OBJECT + ".": expected}]) as native:
        assert metrics.configure() == expected
    assert native.call_args_list[0].args == ("_set", {"parameters": expected})
    assert native.call_args_list[1].args == ("_get", {"rel_path": "", "depth": 0})


def test_native_rejection_is_not_success():
    with patch.object(metrics, "call", return_value={}):
        with pytest.raises(RuntimeError, match="did not apply"):
            metrics.configure()


def test_boot_defaults_precede_native_task_creation(tmp_path):
    path = tmp_path / "99_lab_metrics.odl"
    metrics.write_defaults(path, 2)
    source = path.read_text()
    assert "object 'X_PRPLWARE-COM_Controller.Configuration'" in source
    assert "parameter 'LinkMetricsRequestIntervalSec' = 2;" in source
    assert "parameter 'StatisticsPollingRateSec' = 2;" in source
    assert "parameter 'AssocSTALinkMetricsInclusionPolicy' = true;" in source


@pytest.mark.parametrize("interval", [0, 61, -1, 0.5, True])
def test_invalid_interval_never_mutates_native_controller(interval):
    with patch.object(metrics, "call") as native:
        with pytest.raises(ValueError):
            metrics.configure(interval)
        native.assert_not_called()
