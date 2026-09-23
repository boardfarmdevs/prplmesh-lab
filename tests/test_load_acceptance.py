import importlib.util
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimizer.model import (BssLoadObservation, CandidateObservation, ClientActivityObservation,
                             ClientObservation, MeshHealth, Snapshot, format_time)


SPEC = importlib.util.spec_from_file_location(
    "load_acceptance", Path(__file__).with_name("load-policy-acceptance.py"))
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


@pytest.mark.parametrize('missing', ['lxc', 'nsenter', 'iperf3'])
def test_missing_traffic_tool_fails_before_lab_changes(monkeypatch, missing):
    monkeypatch.setattr(DRIVER.shutil, 'which', lambda name: None if name == missing else '/usr/bin/' + name)
    with pytest.raises(RuntimeError, match='before changing the lab: ' + missing):
        DRIVER.require_traffic_tools()


def test_available_traffic_tools_pass(monkeypatch):
    monkeypatch.setattr(DRIVER.shutil, 'which', lambda name: '/usr/bin/' + name)
    DRIVER.require_traffic_tools()


@pytest.mark.parametrize('failure', ['missing', 'disabled', 'pressure', 'incomplete', 'duplicate'])
def test_guarded_action_requires_complete_clear_counters(failure):
    evidence = {'counter_guard_enabled': True, 'counter_checks': [
        {'property': name, 'state': 'within_limit'}
        for name in ('retries_per_second', 'tx_errors_per_second', 'rx_errors_per_second')]}
    configuration = SimpleNamespace(load_counter_guard_enabled=True)
    DRIVER.require_clear_counter_action(SimpleNamespace(load_evidence=deepcopy(evidence)), configuration)
    if failure == 'missing':
        evidence = None
    elif failure == 'disabled':
        evidence['counter_guard_enabled'] = False
    elif failure == 'pressure':
        evidence['counter_checks'][0]['state'] = 'exceeded'
    elif failure == 'incomplete':
        evidence['counter_checks'].pop()
    else:
        evidence['counter_checks'].append(evidence['counter_checks'][0])
    with pytest.raises(RuntimeError, match='clear native counter evidence'):
        DRIVER.require_clear_counter_action(SimpleNamespace(load_evidence=evidence), configuration)


def test_original_load_policy_does_not_require_optional_guard():
    DRIVER.require_clear_counter_action(SimpleNamespace(load_evidence=None),
                                       SimpleNamespace(load_counter_guard_enabled=False))


def test_btm_capture_matches_actual_transition_owner_target_and_action_window():
    action = {'decision': {'source_bssid': '02:00:00:00:00:01', 'target_bssid': '02:00:00:00:00:02'},
              'started_at': 10, 'verified_at': 12}
    row = {'received_at': 11, 'event': '<2>WNM: Transition to BSS 02:00:00:00:00:02 based on BSS Transition Management Request (old BSSID 02:00:00:00:00:01 after_new_scan=1)'}
    assert DRIVER.btm_events(json.dumps(row), action) == [row]
    assert DRIVER.btm_events(json.dumps(row)) == [row]
    for bad in ({**row, 'received_at': 9}, {**row, 'received_at': 13},
                {**row, 'event': row['event'].replace('00:01', '00:03')},
                {**row, 'event': row['event'].replace('00:02', '00:03')},
                {**row, 'event': '<3>CTRL-EVENT-CONNECTED - Connection to 02:00:00:00:00:02 completed'}):
        assert not DRIVER.btm_events(json.dumps(bad), action)
    explicit = {'event': '<3>BSS-TM-REQ dialog_token=1'}
    assert DRIVER.btm_events(json.dumps(explicit)) == [explicit]
    assert not DRIVER.btm_events(json.dumps(explicit), action)


def test_post_steer_delivery_requires_receiver_data_after_verified_boundary():
    interval = {'start': 4, 'bytes': 1200, 'packets': 1, 'sender': False, 'omitted': False}
    receiver = {'start': {'timestamp': {'timesecs': 10}}, 'intervals': [{'sum': interval}]}
    assert DRIVER.post_steer_delivery(receiver, 12) == [interval]
    for field, value in (('start', 2), ('start', 3), ('bytes', 0), ('packets', 0),
                         ('sender', True), ('omitted', True)):
        changed = {**receiver, 'intervals': [{'sum': {**interval, field: value}}]}
        assert not DRIVER.post_steer_delivery(changed, 12)
    assert not DRIVER.post_steer_delivery({'intervals': receiver['intervals']}, 12)


@pytest.mark.parametrize('failure', [None, 'instance', 'readback'])
def test_counter_pulse_verifies_daemon_and_readback_and_stops(monkeypatch, failure):
    writes = []
    state = {'value': 55, 'generation': 1}
    strong = [{'source': 'station', 'destination': 'ap', 'frequency_mhz': 2437, 'value': 55}]
    impaired = [{**strong[0], 'value': -20}]

    class Control:
        def __init__(self, path):
            assert path == '/test/control'

        def __enter__(self):
            return self

        def __exit__(self, *arguments):
            return False

        def status(self):
            return SimpleNamespace(instance_id='new' if failure == 'instance' and writes else 'old',
                                   generation=state['generation'])

        def apply_frequency(self, generation, rows):
            assert generation > state['generation']
            state.update(generation=generation, value=rows[0]['value'])
            writes.append(deepcopy(rows))

        def get_frequency_link(self, *arguments):
            return state['generation'], 0 if failure == 'readback' else state['value'], True

    monkeypatch.setattr(DRIVER, 'ControlClient', Control)
    pulse = DRIVER.CounterPulse('/test/control', strong, impaired)
    monkeypatch.setattr(pulse.stopped, 'wait', lambda seconds: len(writes) >= 2)
    pulse.thread.start()
    pulse.thread.join(timeout=1)
    assert not pulse.thread.is_alive()
    if failure:
        with pytest.raises(RuntimeError, match='counter impairment failed'):
            pulse.close()
        assert pulse.error
    else:
        pulse.close()
        assert writes == [impaired, strong, strong]
        assert pulse.generations == 2


@pytest.fixture
def same_channel_case(freshness_case):
    from optimizer.policy import PolicyConfig
    action, snapshot, _cycle, _configuration = freshness_case
    station = action['decision']['sta_mac']
    source, target = action['decision']['source_bssid'], action['decision']['target_bssid']
    source_load, target_load = snapshot.bss_loads
    snapshot = replace(snapshot,
        clients=(replace(snapshot.clients[0], connected_bssid=source, connected_device_id=source_load.device_id,
                         association_uptime_seconds=100),),
        candidates=(replace(snapshot.candidates[0], bssid=target, device_id=target_load.device_id),),
        bss_loads=(replace(source_load, utilization=230, channel=6), replace(target_load, utilization=70, channel=6)),
        client_activity=(replace(snapshot.client_activity[0], bssid=source),))
    configuration = PolicyConfig(load_aware_enabled=True, expected_devices=5, expected_clients=2)
    return snapshot, configuration, station, source, target


def negative_observation(case):
    snapshot, configuration, station, source, target = case
    evaluation = DRIVER.policy_for(configuration).evaluate(snapshot)
    return DRIVER.same_channel_negative(snapshot, evaluation, configuration, station, source, target)


def test_same_channel_negative_requires_real_overload_and_explicit_exclusion(same_channel_case):
    result = negative_observation(same_channel_case)
    assert result['qualified'] and result['overloaded']
    assert result['decision']['action'] == 'none'
    assert result['assessment']['reasons'] == ['same_channel']
    assert result['other_exclusions'] == []


@pytest.mark.parametrize('field,value', [('utilization', 191), ('source', 'fixture'),
    ('observed_at', '1970-01-01T00:01:30Z'), ('observed_at', '1970-01-01T00:02:00Z')])
def test_unloaded_synthetic_stale_or_future_reports_cannot_qualify(same_channel_case, field, value):
    snapshot, *settings = same_channel_case
    snapshot = replace(snapshot, bss_loads=(replace(snapshot.bss_loads[0], **{field: value}), snapshot.bss_loads[1]))
    result = negative_observation((snapshot, *settings))
    assert not result['qualified'] and not result['overloaded']


@pytest.mark.parametrize('change', ['idle', 'missing_target', 'different_channel', 'missing_exclusion'])
def test_native_overload_alone_is_not_a_same_channel_pass(same_channel_case, change):
    snapshot, configuration, station, source, target = same_channel_case
    if change == 'idle':
        snapshot = replace(snapshot, client_activity=())
    elif change == 'missing_target':
        snapshot = replace(snapshot, bss_loads=snapshot.bss_loads[:1])
    elif change == 'different_channel':
        snapshot = replace(snapshot, bss_loads=(snapshot.bss_loads[0], replace(snapshot.bss_loads[1], channel=1)))
    evaluation = DRIVER.policy_for(configuration).evaluate(snapshot)
    if change == 'missing_exclusion':
        evidence = {**evaluation.decisions[0].load_evidence, 'candidate_assessments': []}
        evaluation = replace(evaluation, decisions=(replace(evaluation.decisions[0], load_evidence=evidence),))
    result = DRIVER.same_channel_negative(snapshot, evaluation, configuration, station, source, target)
    assert result['overloaded'] and not result['qualified']
    assert DRIVER.negative_summary([result], 5)['state'] == 'failed'


def test_negative_refuses_actions_for_either_subject_before_actuator(same_channel_case):
    snapshot, configuration, station, source, target = same_channel_case
    evaluation = DRIVER.policy_for(configuration).evaluate(snapshot)
    evaluation = replace(evaluation, decisions=(*evaluation.decisions, replace(evaluation.decisions[0], action='steer')))
    with pytest.raises(RuntimeError, match='steering action'):
        DRIVER.same_channel_negative(snapshot, evaluation, configuration, station, source, target)


def test_duplicate_or_different_epoch_reports_cannot_claim_sustained_exclusion(same_channel_case):
    first = negative_observation(same_channel_case)
    assert DRIVER.negative_summary([first] * 20, 5)['passed'] is False
    later = deepcopy(first)
    later['source']['observed_at'] = '1970-01-01T00:01:47Z'
    assert DRIVER.negative_summary([first, later], 5)['passed'] is True
    later['source']['epoch'] = 'new-provider'
    assert DRIVER.negative_summary([first, later], 5)['passed'] is False


def test_no_overload_is_explicit_unsupported_workload_not_pass(same_channel_case):
    snapshot, *settings = same_channel_case
    snapshot = replace(snapshot, bss_loads=(replace(snapshot.bss_loads[0], utilization=10), snapshot.bss_loads[1]))
    report = DRIVER.negative_summary([negative_observation((snapshot, *settings))], 5)
    assert report['state'] == 'unsupported_workload' and report['passed'] is False
    assert report['maximum_native_source_utilization'] == 10


@pytest.fixture
def pressure_case(same_channel_case):
    snapshot, configuration, station, source, target = same_channel_case
    configuration = replace(configuration, load_counter_guard_enabled=True)
    snapshot = replace(snapshot,
        bss_loads=(snapshot.bss_loads[0], replace(snapshot.bss_loads[1], channel=1)),
        client_activity=(replace(snapshot.client_activity[0], retries_per_second=101,
                                 tx_errors_per_second=0, rx_errors_per_second=0),))
    return snapshot, configuration, station, source, target


def test_live_pressure_requires_an_otherwise_safe_quieter_target(pressure_case):
    snapshot, configuration, station, source, target = pressure_case
    evaluation = DRIVER.policy_for(configuration).evaluate(snapshot)
    result = DRIVER.pressure_observation(snapshot, evaluation, configuration, station, source, target)
    assert result['qualified']
    assert result['counter_guard']['state'] == 'pressure'
    assert result['unguarded_selection']['target_bssid'] == target
    assert result['decision']['reason'] == 'native_load_counter_pressure'


@pytest.mark.parametrize('change', ['same_channel', 'no_load', 'clear', 'stale', 'wrong_owner', 'missing_signal'])
def test_other_reasons_for_no_action_do_not_prove_counter_veto(pressure_case, change):
    snapshot, configuration, station, source, target = pressure_case
    if change == 'same_channel':
        snapshot = replace(snapshot, bss_loads=(snapshot.bss_loads[0], replace(snapshot.bss_loads[1], channel=6)))
    elif change == 'no_load':
        snapshot = replace(snapshot, bss_loads=(replace(snapshot.bss_loads[0], utilization=10), snapshot.bss_loads[1]))
    elif change == 'missing_signal':
        snapshot = replace(snapshot, clients=(replace(snapshot.clients[0], rcpi=None),))
    else:
        fields = {'clear': {'retries_per_second': 0}, 'stale': {'observed_at': '1970-01-01T00:00:00Z'},
                  'wrong_owner': {'bssid': '02:00:00:00:00:99'}}[change]
        snapshot = replace(snapshot, client_activity=(replace(snapshot.client_activity[0], **fields),))
    evaluation = DRIVER.policy_for(configuration).evaluate(snapshot)
    assert not DRIVER.pressure_observation(snapshot, evaluation, configuration, station, source, target)['qualified']


def test_missing_native_telemetry_is_failure_not_unsupported_workload():
    result = DRIVER.negative_summary([{'qualified': False, 'overloaded': False, 'source': None, 'target': None}], 5)
    assert result['state'] == 'failed' and result['reason'] == 'no fresh native source metrics'


@pytest.mark.parametrize('status', [0, 1, 127, -15])
def test_early_traffic_exit_is_not_misreported_as_no_overload(status):
    with pytest.raises(RuntimeError, match='traffic process exited'):
        DRIVER.require_running_traffic([SimpleNamespace(poll=lambda: status)])


def test_running_traffic_continues():
    DRIVER.require_running_traffic([SimpleNamespace(poll=lambda: None)])


def test_native_identity_requires_unchanged_processes_even_after_recovery():
    baseline = {'medium': '123 wmediumd', 'gateway': {'pid': 456, 'restarts': 0}}
    DRIVER.verify_native_identity(baseline, deepcopy(baseline))
    for changed in ({}, {**baseline, 'medium': '124 wmediumd'},
                    {**baseline, 'gateway': {'pid': 789, 'restarts': 1}}):
        with pytest.raises(RuntimeError, match='process identity changed'):
            DRIVER.verify_native_identity(baseline, changed)
    with pytest.raises(RuntimeError, match='process identity changed'):
        DRIVER.verify_native_identity({}, {})


@pytest.mark.parametrize('identity', [{}, [], {'medium': '123 wmediumd'}, {'node': 123}])
def test_incomplete_native_identity_cannot_qualify(monkeypatch, identity):
    monkeypatch.setattr(DRIVER, 'command', lambda *arguments: json.dumps(identity))
    with pytest.raises(RuntimeError, match='incomplete native process identity'):
        DRIVER.native_identity(Path('/lab'), 'rdk')


@pytest.mark.parametrize('hop_counts, preferred, expected', [
    ([0, 1, 1, 1, 1], 1, 1),
    ([0, 1, 1, 2, 2], 1, 3),
    ([0, 1, 1, 2, 2], 3, 3),
    ([0, 3, 1, 2, 2], 2, 3),
])
def test_positive_load_setup_respects_actual_backhaul(hop_counts, preferred, expected):
    radios = [{'bssid': 'bss-' + str(index)} for index in range(5)]
    bsses = {radio['bssid']: {'device_id': 'node-' + str(index)} for index, radio in enumerate(radios)}
    hops = {'node-' + str(index): count for index, count in enumerate(hop_counts)}
    assert DRIVER.select_source_radio(radios, bsses, hops, preferred) == expected


@pytest.mark.parametrize('hop_counts', [[0, 1, 1, 1, 2], [0, 1, 1, 1, None]])
def test_positive_load_setup_rejects_missing_or_additional_hop(hop_counts):
    radios = [{'bssid': 'bss-' + str(index)} for index in range(5)]
    bsses = {radio['bssid']: {'device_id': 'node-' + str(index)} for index, radio in enumerate(radios)}
    hops = {'node-' + str(index): count for index, count in enumerate(hop_counts)}
    with pytest.raises(RuntimeError, match='no additional backhaul hop'):
        DRIVER.select_source_radio(radios, bsses, hops, 1)


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


@pytest.fixture
def freshness_case():
    station, source, target, source_device, target_device = [
        '02:00:00:00:00:' + suffix for suffix in ('01', '02', '03', '04', '05')]
    stamp = lambda seconds: format_time(datetime.fromtimestamp(seconds, timezone.utc))
    client = ClientObservation(station, source_device, '', source, 140, 10, stamp(99),
                               'associated_sta_link_metrics', band='2.4')
    candidate = CandidateObservation(station, target, target_device, '', 136, stamp(99),
                                    'easy_mesh_unassociated_sta_link_metrics:hwsim:simulated', band='2.4')
    loads = tuple(BssLoadObservation(bssid, device, bssid, channel, 100, 1, stamp(99), 'epoch', 1)
                  for bssid, device, channel in ((source, source_device, 6), (target, target_device, 1)))
    before = Snapshot(2, 0, stamp(99), 'http://controller', MeshHealth(5, 2), (client,), (candidate,), loads)
    decision = SimpleNamespace(sta_mac=station, source_bssid=source, target_bssid=target, target_band='2.4')
    action = {'decision': vars(decision), 'freshness_requirements': DRIVER.freshness_requirements(decision, before),
              'timings': {'verification': {'finished': {'at': 100, 'monotonic_ns': 100000000000}}}}
    after = replace(before, sequence=1, observed_at=stamp(103),
        clients=(replace(client, connected_bssid=target, connected_device_id=target_device,
                         metric_observed_at=stamp(101)),),
        candidates=(replace(candidate, bssid=source, device_id=source_device, metric_observed_at=stamp(101)),),
        bss_loads=tuple(replace(row, observed_at=stamp(102)) for row in loads),
        client_activity=(ClientActivityObservation(station, target, 50, 1, stamp(102), 'epoch'),))
    mark = lambda seconds: {'at': seconds, 'monotonic_ns': int(seconds * 1e9)}
    cycle = {'cycle_index': 2, 'timings': {
        'cycle': {'started': mark(100.5), 'finished': mark(103)},
        'observer': {'started': mark(100.5), 'finished': mark(102)},
        'candidates': {'started': mark(101.5), 'finished': mark(102)},
        'load': {'started': mark(102), 'finished': mark(102.5)}}}
    configuration = SimpleNamespace(reject_stale_metrics_after_seconds=15, load_maximum_age_seconds=5,
                                    load_maximum_report_skew_seconds=1)
    return action, after, cycle, configuration


def test_freshness_records_stage_detection_and_preserves_first_observation(freshness_case):
    action, snapshot, cycle, configuration = freshness_case
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    first = deepcopy(action['post_verify_freshness'])
    assert all(first.values())
    assert first['target_metrics']['after_verification_seconds'] == 1.5
    assert first['candidates']['after_verification_seconds'] == 2
    assert first['target_load']['after_verification_seconds'] == 2.5
    assert first['complete_snapshot']['after_verification_seconds'] == 3
    assert first['target_metrics']['reports'][0]['metric_observed_at'].endswith('01:41.000Z')
    DRIVER.record_post_verify_freshness(action, snapshot, {**cycle, 'cycle_index': 3}, configuration)
    assert action['post_verify_freshness'] == first


@pytest.mark.parametrize('timestamp', [None, '1970-01-01T00:01:39Z', '1970-01-01T00:01:40Z',
                                       '1970-01-01T00:01:42Z'])
def test_target_metric_requires_report_after_verify_before_its_sample(freshness_case, timestamp):
    action, snapshot, cycle, configuration = freshness_case
    snapshot = replace(snapshot, clients=(replace(snapshot.clients[0], metric_observed_at=timestamp),))
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert action['post_verify_freshness']['target_metrics'] is None
    assert action['post_verify_freshness']['complete_snapshot'] is None


@pytest.mark.parametrize('field,value', [
    ('connected_bssid', '02:00:00:00:00:09'), ('connected_device_id', '02:00:00:00:00:09'),
    ('sta_mac', '02:00:00:00:00:09'), ('band', '5')])
def test_post_verify_reports_require_matching_serving_identity(freshness_case, field, value):
    action, snapshot, cycle, configuration = freshness_case
    snapshot = replace(snapshot, clients=(replace(snapshot.clients[0], **{field: value}),))
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert not any(action['post_verify_freshness'].values())


@pytest.mark.parametrize('field,value', [
    ('sta_mac', '02:00:00:00:00:09'), ('bssid', '02:00:00:00:00:09'),
    ('device_id', '02:00:00:00:00:09'), ('band', '5'), ('rcpi', None),
    ('metric_observed_at', '1970-01-01T00:01:40Z'), ('measurement_source', 'controller_bss_inventory_only')])
def test_candidates_require_fresh_measured_matching_identities(freshness_case, field, value):
    action, snapshot, cycle, configuration = freshness_case
    snapshot = replace(snapshot, candidates=(replace(snapshot.candidates[0], **{field: value}),))
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert action['post_verify_freshness']['candidates'] is None
    assert action['post_verify_freshness']['complete_snapshot'] is None


@pytest.mark.parametrize('field,value', [
    ('device_id', '02:00:00:00:00:09'), ('radio_id', '02:00:00:00:00:09'),
    ('channel', 11), ('epoch', 'restarted'), ('source', 'fixture'),
    ('transport', 'prpl-local-broker'), ('observed_at', '1970-01-01T00:01:40Z')])
def test_load_requires_post_verify_timestamp_and_original_radio_epoch(freshness_case, field, value):
    action, snapshot, cycle, configuration = freshness_case
    snapshot = replace(snapshot, bss_loads=tuple(replace(row, **{field: value}) for row in snapshot.bss_loads))
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert action['post_verify_freshness']['target_load'] is None
    assert action['post_verify_freshness']['source_load'] is None
    assert action['post_verify_freshness']['complete_snapshot'] is None


def test_activity_interval_must_start_after_verification(freshness_case):
    action, snapshot, cycle, configuration = freshness_case
    snapshot = replace(snapshot, client_activity=(replace(snapshot.client_activity[0], interval_seconds=2),))
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert action['post_verify_freshness']['target_activity'] is None
    assert action['post_verify_freshness']['complete_snapshot'] is None


def test_action_cycle_and_expired_reports_do_not_qualify(freshness_case):
    action, snapshot, cycle, configuration = freshness_case
    cycle['timings']['cycle']['started']['monotonic_ns'] = 100000000000
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert not any(action['post_verify_freshness'].values())
    cycle['timings']['cycle']['started']['monotonic_ns'] += 1
    configuration.reject_stale_metrics_after_seconds = 0.1
    configuration.load_maximum_age_seconds = 0.1
    DRIVER.record_post_verify_freshness(action, snapshot, cycle, configuration)
    assert not any(action['post_verify_freshness'].values())


def test_measured_cycle_accounts_for_lazy_candidates_and_retains_failure(monkeypatch, freshness_case):
    _, snapshot, _, _ = freshness_case
    clock = {'ns': 0, 'fail': False}
    monkeypatch.setattr(DRIVER.time, 'monotonic_ns', lambda: clock['ns'])
    monkeypatch.setattr(DRIVER.time, 'time', lambda: 100 + clock['ns'] / 1e9)

    class Candidates:
        last_raw = [{'operation': 'query', 'elapsed_ms': 7}]

        def __call__(self, *arguments):
            clock['ns'] += 7000000
            if clock['fail']:
                raise RuntimeError('candidate timeout')
            yield snapshot.candidates[0]

    candidates = DRIVER.TimedCandidates(Candidates())
    observer = SimpleNamespace(candidate_provider=candidates, last_raw={'topology': {}})

    def observe():
        clock['ns'] += 2000000
        list(observer.candidate_provider())
        return snapshot

    def enrich(value, raw):
        clock['ns'] += 3000000
        return value

    evaluation = SimpleNamespace(state='unchanged', to_dict=lambda: {'decisions': []})

    def evaluate(value, state):
        clock['ns'] += 1000000
        return evaluation

    observer.observe = observe
    journal = io.StringIO()
    result, decisions, cycle = DRIVER.measured_cycle(observer, SimpleNamespace(enrich=enrich),
        SimpleNamespace(evaluate=evaluate), None, [snapshot.clients[0].sta_mac], journal, 1)
    assert result.clients == snapshot.clients
    assert decisions is evaluation
    assert {key: value['elapsed_ms'] for key, value in cycle['timings'].items()} == {
        'observer': 9, 'candidates': 7, 'load': 3, 'evaluate': 1, 'cycle': 13}
    assert cycle['observer_excluding_candidates_ms'] == 2
    assert cycle['candidate_transactions'] == candidates.provider.last_raw
    clock['fail'] = True
    with pytest.raises(RuntimeError, match='candidate timeout'):
        DRIVER.measured_cycle(observer, SimpleNamespace(enrich=enrich), SimpleNamespace(evaluate=evaluate),
                              None, [snapshot.clients[0].sta_mac], journal, 2)
    failed = json.loads(journal.getvalue().splitlines()[-1])
    assert failed['error'] == 'candidate timeout'
    assert failed['timings']['candidates']['elapsed_ms'] == 7
    assert failed['timings']['observer']['elapsed_ms'] == 9
    assert 'snapshot' not in failed
