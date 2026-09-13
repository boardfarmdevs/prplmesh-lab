import copy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from room_demo.band_profiles import BandProfileManager, ClientBandSettings, validate_profiles
from room_demo.recovery import RecoveryJournal, load_recovery
from wmdcfg.actuator import ActuatorError


STATION = "02:00:00:10:01:00"
CONTAINER = "prpl-client-01"
VALUES = {"freq_list": "2437", "scan_freq": "2437", "key_mgmt": "WPA-PSK", "ieee80211w": "1", "sae_pwe": "0"}
RECORD = {"container": CONTAINER, "sta_mac": STATION, "network_id": "0", "ssid": "private_ssid", "values": VALUES}
PROFILE = {"allowed_bands": ["2.4", "5", "6"], "initial_band": "2.4"}


def manager(tmp_path):
    plan = {"bindings": {
        "client": {"container": CONTAINER, "station_mac": STATION, "radio_permanent_mac": STATION},
        "gateway": {"fronthaul_frequencies_mhz": {"2.4": 2437, "5": 5180, "6": 5975}}}}
    journal = RecoveryJournal(tmp_path / "recovery.json", "test", "inventory")
    journal.prepare("instance", 0, {})
    settings = Mock()
    settings.capture.return_value = copy.deepcopy(RECORD)
    scanner = Mock()
    scanner.capabilities.return_value = {"sta_mac": STATION, "frequencies_mhz": [2437, 5180, 5975],
                                        "key_management": ["WPA-PSK", "SAE"]}
    return BandProfileManager(plan, journal, settings=settings, scanner=scanner), settings, scanner, journal


def test_profiles_are_explicit_and_default_has_none():
    world = {"roles": {"client": "station"}, "generations": [{"present": {"client": True}}]}
    assert validate_profiles(world) == {}
    world["band_steering"] = {"client": PROFILE}
    assert validate_profiles(world) == {"client": PROFILE}
    for invalid in [{"allowed_bands": ["5", "5"], "initial_band": "5"},
                    {"allowed_bands": ["5"], "initial_band": "6"},
                    {**PROFILE, "force_bssid": "anything"}, {"allowed_bands": [5], "initial_band": "5"}]:
        with pytest.raises(ValueError):
            validate_profiles({**world, "band_steering": {"client": invalid}})
    with pytest.raises(ValueError):
        validate_profiles({**world, "roles": {"client": "fronthaul_ap"}})


def test_band_settings_are_journaled_before_mutation_and_restored_on_default(tmp_path):
    profiles, settings, _scanner, journal = manager(tmp_path)

    def initialize(record, values, frequencies):
        assert journal.client_networks()[CONTAINER] == record
        assert frequencies == [2437]
        assert values == {"freq_list": "2437 5180 5975", "scan_freq": "2437 5180 5975",
                          "key_mgmt": "WPA-PSK SAE", "ieee80211w": "1", "sae_pwe": "2"}

    settings.initialize.side_effect = initialize
    with profiles.transition({"client": PROFILE}):
        assert profiles.snapshot()[STATION]["profile"] == PROFILE
    assert load_recovery(journal.path)["client_networks"][CONTAINER] == RECORD
    with profiles.transition({}):
        assert not profiles.active
    settings.restore.assert_called_once_with(RECORD)
    assert journal.client_networks() == {}


@pytest.mark.parametrize("failure", ["setup", "consumer"])
def test_failed_switch_restores_previous_settings_and_journal(tmp_path, failure):
    profiles, settings, _scanner, journal = manager(tmp_path)
    if failure == "setup":
        settings.initialize.side_effect = ActuatorError("setup")
    with pytest.raises(ActuatorError):
        with profiles.transition({"client": PROFILE}):
            raise ActuatorError("consumer")
    settings.restore.assert_called_once_with(RECORD)
    assert profiles.active == {} and journal.client_networks() == {}


def test_failed_rollback_keeps_recoverable_original_settings(tmp_path):
    profiles, settings, _scanner, journal = manager(tmp_path)
    settings.initialize.side_effect = ActuatorError("setup")
    settings.restore.side_effect = ActuatorError("rollback")
    with pytest.raises(ActuatorError, match="rollback failed"):
        with profiles.transition({"client": PROFILE}):
            pass
    assert journal.client_networks()[CONTAINER] == RECORD
    assert load_recovery(journal.path)["state"] == "failed"


@pytest.mark.parametrize("capability", ["frequencies_mhz", "key_management", "sta_mac"])
def test_unsupported_profile_is_rejected_before_any_mutation(tmp_path, capability):
    profiles, settings, scanner, journal = manager(tmp_path)
    scanner.capabilities.return_value[capability] = [] if capability != "sta_mac" else "02:00:00:00:00:00"
    with pytest.raises(ActuatorError):
        with profiles.transition({"client": PROFILE}):
            pass
    settings.initialize.assert_not_called()
    assert journal.client_networks() == {}


def test_crash_recovery_retains_failed_record_and_removes_only_restored_records(tmp_path):
    _profiles, _settings, _scanner, journal = manager(tmp_path)
    journal.preserve_client_network(CONTAINER, RECORD)
    with patch("room_demo.recovery.restore_client_network", side_effect=ActuatorError("offline")):
        with pytest.raises(ActuatorError):
            journal.restore_client_networks()
    assert journal.client_networks()[CONTAINER] == RECORD
    with patch("room_demo.recovery.restore_client_network") as restore:
        journal.restore_client_networks()
    restore.assert_called_once_with(RECORD)
    assert not journal.client_networks()


def test_network_writer_checks_identity_readback_and_handles_unset_frequency():
    settings = ClientBandSettings()
    record = {**RECORD, "values": {**VALUES, "freq_list": None, "scan_freq": None}}
    settings.capture = Mock(side_effect=[RECORD, copy.deepcopy(record)])
    settings.control = Mock(return_value="OK")
    settings.write(record, record["values"])
    assert settings.control.call_args_list[0].args == (CONTAINER, "set_network", "0", "freq_list", "")
    settings.capture = Mock(return_value={**record, "sta_mac": "02:00:00:00:00:00"})
    with pytest.raises(ActuatorError, match="identity changed"):
        settings.write(record, record["values"])


def test_successful_mutation_with_wrong_readback_is_not_accepted():
    settings = ClientBandSettings()
    settings.capture = Mock(return_value=RECORD)
    settings.control = Mock(return_value="OK")
    with pytest.raises(ActuatorError, match="readback mismatch"):
        settings.write(RECORD, {**VALUES, "freq_list": "5180"})
