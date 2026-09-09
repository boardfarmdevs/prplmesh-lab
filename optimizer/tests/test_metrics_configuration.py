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
                "AssocSTALinkMetricsInclusionPolicy": True,
                "AssocSTATrafficStatsInclusionPolicy": True}
    with patch.object(metrics, "call", side_effect=[{}, {metrics.OBJECT + ".": expected}]) as native:
        assert metrics.configure() == expected
    assert native.call_args_list[0].args == ("_set", {"parameters": expected})
    assert native.call_args_list[1].args == ("_get", {"rel_path": "", "depth": 0})


def test_native_rejection_is_not_success():
    with patch.object(metrics, "call", return_value={}):
        with pytest.raises(RuntimeError, match="did not apply"):
            metrics.configure()


def test_metrics_policy_precedes_root_and_extender_configuration():
    source = (path.parents[2] / "scripts/radio-lab.sh").read_text()
    start = source.index("configure_credentials()")
    end = source.index("\nclient_cohort()", start)
    body = source[start:end]
    assert body.index("configure-metrics.py") < body.index('set_device_credentials "$CONTROLLER_AL_MAC"')
    assert metrics.policy(2)["LinkMetricsRequestIntervalSec"] == 2


@pytest.mark.parametrize("interval", [0, 61, -1, 0.5, True])
def test_invalid_interval_never_mutates_native_controller(interval):
    with patch.object(metrics, "call") as native:
        with pytest.raises(ValueError):
            metrics.configure(interval)
        native.assert_not_called()
