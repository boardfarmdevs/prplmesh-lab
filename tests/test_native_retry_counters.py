import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "retry_acceptance", Path(__file__).with_name("native-retry-counter-acceptance.py"))
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


def trial(name="ack_loss", unit=1):
    driver = {"packets_sent": 1000, "bytes_sent": 1024000,
              "retransmissions": 900, "tx_packet_errors": 45, "rx_packet_errors": 0}
    return {"name": name, "kernel_deltas": driver,
            "native_deltas": {**driver, "bytes_sent": driver["bytes_sent"] // unit},
            "sender": {"packets": 1000}, "receiver": {"unique_packets": 1000}}


@pytest.mark.parametrize("unit", [1, 1024])
def test_ack_loss_allows_delivered_data_despite_tx_failure(unit):
    DRIVER.qualify_trial(trial(unit=unit), unit)


def test_missing_native_tx_errors_fails_even_when_retries_are_reported():
    value = trial()
    value["native_deltas"]["tx_packet_errors"] = 0
    with pytest.raises(RuntimeError, match="native tx_packet_errors"):
        DRIVER.qualify_trial(value, 1)


def test_wrong_byte_units_cannot_qualify():
    with pytest.raises(RuntimeError, match="byte units"):
        DRIVER.qualify_trial(trial(unit=1024), 1)


def test_data_loss_requires_actual_endpoint_loss():
    with pytest.raises(RuntimeError, match="did not lose data"):
        DRIVER.qualify_trial(trial("data_loss"), 1)
    value = trial("data_loss")
    value["receiver"]["unique_packets"] = 950
    DRIVER.qualify_trial(value, 1)


def test_counter_reset_cannot_qualify():
    value = trial()
    value["native_deltas"]["rx_packet_errors"] = -1
    with pytest.raises(RuntimeError, match="counter reset"):
        DRIVER.qualify_trial(value, 1)


def test_kernel_counter_parser_keeps_missing_distinct_from_zero():
    values = DRIVER.kernel_counters("  tx packets: 100\n  tx retries: 9\n  tx failed: 2\n  rx drop misc: 0\n")
    assert values == {"packets_sent": 100, "retransmissions": 9, "tx_packet_errors": 2, "rx_packet_errors": 0}
    assert "bytes_sent" not in values
