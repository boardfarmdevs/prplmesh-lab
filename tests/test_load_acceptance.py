import importlib.util
from copy import deepcopy
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "load_acceptance", Path(__file__).with_name("load-policy-acceptance.py"))
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


@pytest.mark.parametrize("response", ["FAIL\n", "", "UNKNOWN COMMAND\n"])
def test_restore_requires_supplicant_ack_not_just_process_success(monkeypatch, response):
    monkeypatch.setattr(DRIVER, "command", lambda *arguments: response)
    with pytest.raises(RuntimeError, match="supplicant command rejected"):
        DRIVER.require_ok("wpa_cli", "set_network", "0", "freq_list", "")


def test_restore_accepts_acknowledged_empty_frequency_list(monkeypatch):
    calls = []

    def command(*arguments):
        calls.append(arguments)
        return "OK\n"

    monkeypatch.setattr(DRIVER, "command", command)
    DRIVER.require_ok("wpa_cli", "set_network", "0", "freq_list", "")
    assert calls == [("wpa_cli", "set_network", "0", "freq_list", "")]


def test_single_radio_update_preserves_other_bands_and_restores_exact_configuration():
    document = {'Version': '1.0', 'WifiRadioConfig': [
        {'RadioName': 'radio1', 'FreqBand': 1, 'Channel': 6, 'AutoChannelEnabled': True,
         'CurrentOperatingClasses': [{'Class': 81, 'Channel': 6}], 'TransmitPower': 85},
        {'RadioName': 'radio2', 'FreqBand': 2, 'Channel': 36},
        {'RadioName': 'radio3', 'FreqBand': 16, 'Channel': 37}]}
    before = deepcopy(document)
    payload = DRIVER.radio_subdoc(document, 1)
    assert payload['SubDocName'] == 'radio_2.4G'
    assert len(payload['WifiRadioConfig']) == 1
    assert payload['WifiRadioConfig'][0] == {**before['WifiRadioConfig'][0],
        'Channel': 1, 'AutoChannelEnabled': False, 'CurrentOperatingClasses': [{'Class': 81, 'Channel': 1}]}
    assert DRIVER.radio_subdoc(document)['WifiRadioConfig'] == [before['WifiRadioConfig'][0]]
    assert document == before


@pytest.mark.parametrize('radios', [[], [{'RadioName': 'radio1', 'FreqBand': 16}],
    [{'RadioName': 'radio1', 'FreqBand': 1}, {'RadioName': 'radio1', 'FreqBand': 1}]])
def test_single_radio_update_rejects_ambiguous_identity(radios):
    with pytest.raises(RuntimeError, match='exactly one'):
        DRIVER.radio_subdoc({'Version': '1.0', 'WifiRadioConfig': radios}, 1)


def test_single_radio_update_never_applies_global_settings_or_restarts_agent(monkeypatch):
    calls = []

    def command(*arguments):
        calls.append(arguments)
        return 'setvalues succeeded..\n'

    monkeypatch.setattr(DRIVER, 'command', command)
    payload = {'Version': '1.0', 'SubDocName': 'radio_2.4G', 'WifiRadioConfig': []}
    DRIVER.apply_radio_subdoc('bpiap-003', payload)
    assert calls == [('lxc', 'exec', 'bpiap-003', '--', 'rbuscli', 'set',
        'Device.WiFi.WebConfig.Data.Subdoc.South', 'string', json.dumps(payload))]


def test_single_radio_update_rejects_failed_rbus_ack(monkeypatch):
    monkeypatch.setattr(DRIVER, 'command', lambda *arguments: 'setvalues failed\n')
    with pytest.raises(RuntimeError, match='configuration rejected'):
        DRIVER.apply_radio_subdoc('bpiap-003', {})
