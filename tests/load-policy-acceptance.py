import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from optimizer.actuator import NativeSteerActuator, SteerActuator
from optimizer.candidates import ControllerCandidateProvider
from optimizer.config import load_policy
from optimizer.load_observer import NativeLoadProvider, inventory
from optimizer.load_policy import policy_for
from optimizer.model import parse_time
from optimizer.observer import ControllerObserver
from optimizer.state import PolicyState
from optimizer.verifier import OutcomeVerifier
from wmdcfg.actuator import ControlClient
from wmdcfg.rf_qualify import association_identity
from wmdcfg.rf_spatial import private_channels, private_radio, registered_radio, roam_client, net_command
from wmdcfg.rf_validate import command, stop_process, scan_for_roam


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def require_ok(*arguments):
    result = command(*arguments).strip()
    if result != 'OK':
        raise RuntimeError('supplicant command rejected: ' + result)


def native_identity(root, stack):
    identity = json.loads(command(sys.executable, str(root / 'tests/room-feature-guest-audit.py'), 'identity', stack))
    if not isinstance(identity, dict) or not identity.get('medium') or len(identity) < 6:
        raise RuntimeError('incomplete native process identity audit')
    return identity


def verify_native_identity(before, after):
    if not before or before != after:
        raise RuntimeError('native/container/medium process identity changed during qualification')


def radio_subdoc(document, channel=None):
    radios = document.get('WifiRadioConfig', [])
    selected = [radio for radio in radios if radio.get('RadioName') == 'radio1']
    if len(selected) != 1 or selected[0].get('FreqBand') != 1:
        raise RuntimeError('requires exactly one 2.4 GHz radio1 configuration')
    radio = deepcopy(selected[0])
    if channel is not None:
        if channel not in (1, 6):
            raise ValueError('qualification supports only 2.4 GHz channels 1 and 6')
        radio.update(Channel=channel, AutoChannelEnabled=False)
        for current in radio.get('CurrentOperatingClasses', []):
            current['Channel'] = channel
    return {'Version': document['Version'], 'SubDocName': 'radio_2.4G', 'WifiRadioConfig': [radio]}


def apply_radio_subdoc(node, document):
    result = command('lxc', 'exec', node, '--', 'rbuscli', 'set',
                     'Device.WiFi.WebConfig.Data.Subdoc.South', 'string', json.dumps(document)).strip()
    if result != 'setvalues succeeded..':
        raise RuntimeError('single-radio configuration rejected: ' + result)


def require_traffic_tools():
    missing = [name for name in ('lxc', 'nsenter', 'iperf3') if shutil.which(name) is None]
    if missing:
        raise RuntimeError('install required outer-VM tools before changing the lab: ' + ', '.join(missing))


def require_running_traffic(processes):
    for process in processes:
        status = process.poll()
        if status is not None:
            raise RuntimeError('traffic process exited before qualification completed: status ' + str(status))


def select_source_radio(radios, bsses, hops, preferred):
    radio_hops = [hops.get(bsses.get(radio['bssid'], {}).get('device_id')) for radio in radios]
    target_hops = radio_hops[-1]
    eligible = [index for index in range(1, len(radios) - 1)
                if radio_hops[index] is not None and target_hops is not None
                and radio_hops[index] >= target_hops]
    if not eligible:
        raise RuntimeError('prepare a target with no additional backhaul hop before qualification')
    return min(eligible, key=lambda index: (index != preferred, radio_hops[index] - target_hops, index))


def same_channel_negative(snapshot, evaluation, configuration, station, source_bssid, target_bssid):
    if any(decision.action != 'none' for decision in evaluation.decisions):
        raise RuntimeError('same-channel negative produced a steering action')
    now = parse_time(snapshot.observed_at)
    def fresh(row):
        return row.observed_at is not None and 0 <= (now - parse_time(row.observed_at)).total_seconds() <= configuration.load_maximum_age_seconds
    loads = {row.bssid: row for row in snapshot.bss_loads if row.source == 'native_ap_metrics' and fresh(row)}
    source, target = loads.get(source_bssid), loads.get(target_bssid)
    client = snapshot.client(station)
    result = {'qualified': False, 'overloaded': bool(source and source.utilization >= configuration.load_high_utilization),
              'source': asdict(source) if source else None, 'target': asdict(target) if target else None}
    if not result['overloaded'] or target is None or client is None:
        return result
    decision = next((row for row in evaluation.decisions if row.sta_mac == station), None)
    evidence = decision.load_evidence if decision else None
    if (client.connected_bssid != source_bssid or client.connected_device_id != source.device_id
            or source.channel != 6 or target.channel != 6 or source.radio_id == target.radio_id
            or source.epoch != target.epoch or evidence is None
            or evidence.get('current_utilization') != source.utilization
            or evidence.get('current_epoch') != source.epoch
            or decision.reason != 'native_load_no_safe_quieter_target'):
        return result
    activity = next((row for row in snapshot.client_activity if row.sta_mac == station
        and row.bssid == source_bssid and row.source == 'native_sta_traffic' and row.epoch == source.epoch
        and fresh(row) and row.packets_per_second >= configuration.load_minimum_activity_packets_per_second), None)
    candidate = next((row for row in snapshot.candidates_for(station) if row.bssid == target_bssid
        and row.device_id == target.device_id and row.band == client.band and row.eligible
        and row.rcpi is not None and row.rcpi >= configuration.load_minimum_target_rcpi), None)
    assessment = next((row for row in evidence.get('candidate_assessments', []) if row.get('bssid') == target_bssid), None)
    if (activity is None or candidate is None or assessment is None or assessment.get('state') != 'excluded'
            or 'same_channel' not in assessment.get('reasons', [])
            or abs((parse_time(source.observed_at) - parse_time(target.observed_at)).total_seconds()) > configuration.load_maximum_report_skew_seconds):
        return result
    return {**result, 'qualified': True, 'activity': asdict(activity), 'decision': decision.to_dict(),
            'assessment': assessment, 'other_exclusions': [reason for reason in assessment['reasons'] if reason != 'same_channel']}


def negative_summary(observations, hold_seconds):
    qualified = [row for row in observations if row['qualified']]
    grouped = {}
    for row in qualified:
        source = row['source']
        key = (source['epoch'], source['radio_id'], row['target']['radio_id'])
        grouped.setdefault(key, set()).add(parse_time(source['observed_at']).timestamp())
    sustained = any(len(stamps) >= 2 and max(stamps) - min(stamps) >= hold_seconds for stamps in grouped.values())
    overloaded = any(row['overloaded'] for row in observations)
    measured = any(row['source'] is not None for row in observations)
    return {'state': 'passed' if sustained else 'failed' if overloaded or not measured else 'unsupported_workload',
            'passed': sustained, 'native_overload_observed': overloaded, 'qualified_samples': len(qualified),
            'required_hold_seconds': hold_seconds,
            'maximum_native_source_utilization': max((row['source']['utilization'] for row in observations if row['source']), default=None),
            'reason': None if sustained else 'no fresh native source metrics' if not measured
                else 'native overload occurred without sustained same-channel exclusion' if overloaded
                else 'two real 12 Mbps clients did not produce native source utilization at the production threshold',
            'scope': 'same-channel exclusion under real native overload; other exclusions are retained, not claimed absent'}


def timing_mark():
    return {'at': time.time(), 'monotonic_ns': time.monotonic_ns()}


def timed_call(timings, stage, operation, *arguments, **keywords):
    timing = timings[stage] = {'started': timing_mark()}
    try:
        return operation(*arguments, **keywords)
    except Exception as error:
        timing['error'] = str(error)
        raise
    finally:
        timing['finished'] = timing_mark()
        timing['elapsed_ms'] = (timing['finished']['monotonic_ns'] - timing['started']['monotonic_ns']) / 1e6


class TimedCandidates:
    def __init__(self, provider):
        self.provider = provider
        self.timings = {}

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def __call__(self, *arguments, **keywords):
        return timed_call(self.timings, 'candidates', lambda: list(self.provider(*arguments, **keywords)))


def measured_cycle(observer, provider, engine, policy_state, station_macs, journal, cycle_index):
    cycle = {'cycle_index': cycle_index, 'timings': {}}
    observer.candidate_provider.timings = cycle['timings']

    def collect():
        snapshot = timed_call(cycle['timings'], 'observer', observer.observe)
        snapshot = replace(snapshot, health=replace(snapshot.health, clients=2),
            clients=tuple(row for row in snapshot.clients if row.sta_mac in station_macs),
            candidates=tuple(row for row in snapshot.candidates if row.sta_mac in station_macs))
        snapshot = timed_call(cycle['timings'], 'load', provider.enrich, snapshot, observer.last_raw)
        cycle['snapshot'] = snapshot.to_dict()
        evaluation = timed_call(cycle['timings'], 'evaluate', engine.evaluate, snapshot, policy_state)
        cycle['evaluation'] = evaluation.to_dict()
        return snapshot, evaluation, cycle

    try:
        return timed_call(cycle['timings'], 'cycle', collect)
    except Exception as error:
        cycle['error'] = str(error)
        raise
    finally:
        cycle['raw'] = observer.last_raw
        cycle['candidate_transactions'] = observer.candidate_provider.last_raw
        observer_ms = cycle['timings']['observer']['elapsed_ms']
        candidate_ms = cycle['timings'].get('candidates', {}).get('elapsed_ms', 0)
        cycle['observer_excluding_candidates_ms'] = observer_ms - candidate_ms
        journal.write(json.dumps(cycle) + '\n')
        journal.flush()


def freshness_requirements(decision, snapshot):
    identities = {row.bssid: {'bssid': row.bssid, 'device_id': row.device_id, 'band': row.band}
                  for row in snapshot.candidates_for(decision.sta_mac) if row.band == decision.target_band}
    client = snapshot.client(decision.sta_mac)
    identities[client.connected_bssid] = {'bssid': client.connected_bssid,
        'device_id': client.connected_device_id, 'band': client.band}
    return {'target': identities[decision.target_bssid],
        'candidates': [identity for bssid, identity in sorted(identities.items()) if bssid != decision.target_bssid],
        'loads': [asdict(row) for row in snapshot.bss_loads
                  if row.bssid in (decision.source_bssid, decision.target_bssid)]}


def record_post_verify_freshness(action, snapshot, cycle, configuration):
    milestones = action.setdefault('post_verify_freshness', dict.fromkeys((
        'target_metrics', 'candidates', 'target_load', 'source_load', 'target_activity', 'complete_snapshot')))
    boundary = action['timings']['verification']['finished']
    detected = cycle['timings']['cycle']['finished']
    if cycle['timings']['cycle']['started']['monotonic_ns'] <= boundary['monotonic_ns']:
        return
    requirements = action['freshness_requirements']
    target = requirements['target']
    station = action['decision']['sta_mac']
    client = snapshot.client(station)
    if (client is None or client.connected_bssid != target['bssid']
            or client.connected_device_id != target['device_id'] or client.band != target['band']):
        return

    metric_sample = cycle['timings'].get('candidates', cycle['timings']['observer'])['started']
    candidate_sample = cycle['timings']['observer']['finished']
    load_sample = cycle['timings']['load']['finished']

    def fresh(timestamp, maximum_age, sampled):
        if timestamp is None:
            return False
        reported_at = parse_time(timestamp).timestamp()
        return boundary['at'] < reported_at <= sampled['at'] and sampled['at'] - reported_at <= maximum_age

    def record(name, rows, sampled=detected):
        if rows and milestones[name] is None:
            milestones[name] = {'cycle_index': cycle['cycle_index'], 'detected': sampled,
                'after_verification_seconds': (sampled['monotonic_ns'] - boundary['monotonic_ns']) / 1e9,
                'reports': [asdict(row) for row in rows]}
        return bool(rows)

    metrics = record('target_metrics', [client] if client.rcpi is not None and client.rcpi > 0
        and client.measurement_source in ('associated_sta_link_metrics', 'prplmesh_associated_sta_link_metrics')
        and fresh(client.metric_observed_at, configuration.reject_stale_metrics_after_seconds, metric_sample) else [], metric_sample)
    candidates = [row for row in snapshot.candidates_for(station)
        if {'bssid': row.bssid, 'device_id': row.device_id, 'band': row.band} in requirements['candidates']
        and row.rcpi is not None and row.measurement_source.startswith('easy_mesh_unassociated_sta_link_metrics:')
        and fresh(row.metric_observed_at, configuration.reject_stale_metrics_after_seconds, candidate_sample)]
    candidate_complete = record('candidates', candidates if requirements['candidates']
        and len(candidates) == len(requirements['candidates'])
        and len({row.bssid for row in candidates}) == len(candidates) else [], candidate_sample)
    loads = [row for row in snapshot.bss_loads if row.source == 'native_ap_metrics'
        and fresh(row.observed_at, configuration.load_maximum_age_seconds, load_sample)
        and any(all(getattr(row, field) == expected[field]
                    for field in ('bssid', 'device_id', 'radio_id', 'channel', 'epoch', 'transport'))
                for expected in requirements['loads'])]
    target_loads = [row for row in loads if row.bssid == target['bssid']]
    target_load = record('target_load', target_loads, load_sample)
    source_load = record('source_load', [row for row in loads if row.bssid == action['decision']['source_bssid']], load_sample)
    activities = [row for row in snapshot.client_activity
        if row.sta_mac == station and row.bssid == target['bssid'] and row.source == 'native_sta_traffic'
        and fresh(row.observed_at, configuration.load_maximum_age_seconds, load_sample)
        and parse_time(row.observed_at).timestamp() - row.interval_seconds > boundary['at']
        and any(row.epoch == load.epoch and row.transport == load.transport for load in target_loads)]
    activity = record('target_activity', activities, load_sample)
    if metrics and candidate_complete and target_load and source_load and activity:
        timestamps = [parse_time(row.observed_at).timestamp() for row in loads]
        if max(timestamps) - min(timestamps) <= configuration.load_maximum_report_skew_seconds:
            record('complete_snapshot', [client, *candidates, *loads, *activities])


def main():
    def interrupted(_signal, _frame):
        raise InterruptedError('qualification interrupted; restoring owned changes')

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser()
    parser.add_argument('--stack', choices=('rdk', 'prpl'), required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--yes-change-lab', action='store_true')
    parser.add_argument('--same-channel-negative', action='store_true',
                        help='keep all APs on channel 6; require real native overload, same_channel exclusion and no actions')
    args = parser.parse_args()
    if os.geteuid() or not args.yes_change_lab:
        parser.error('requires root and --yes-change-lab')
    require_traffic_tools()
    state_room = fetch('http://127.0.0.1:8891/api/demo/interactions')
    if (state_room['lease']['held'] or state_room['recording']['active']
            or state_room['playback']['status'] != 'paused' or state_room['playback']['time_ms'] != 0
            or state_room['playback']['manual_roles']
            or state_room['expected_online_clients'] != 20
            or state_room['selected_world'] != 'home-five-agent--private-client-room-walk'):
        raise RuntimeError('requires idle default 20-client room')
    rdk = args.stack == 'rdk'
    if not rdk:
        from optimizer.prplmesh import PrplMeshCandidateProvider, PrplMeshObserver
    nodes = ['bpibroadband', 'bpiap', 'bpiap-001', 'bpiap-002', 'bpiap-003'] if rdk else [
        'prpl-controller', 'prpl-agent-01', 'prpl-agent-02', 'prpl-agent-03', 'prpl-agent-04']
    clients = ['wlan-client', 'wlan-client-001'] if rdk else ['prpl-client-01', 'prpl-client-03']
    room = 'easymesh-room-demo' if rdk else 'prplmesh-room-demo'
    control_path = '/run/wmediumd-control.sock' if rdk else '/run/prpl-wmediumd/control.sock'
    base = 'http://127.0.0.1:8888' if rdk else 'http://127.0.0.1:8092'
    gateway = '10.0.0.1' if rdk else '192.168.77.1'
    observer_type = ControllerObserver if rdk else PrplMeshObserver
    observer = observer_type(base)
    inventory_observer = observer_type(base)
    original_roster = {row.sta_mac for row in inventory_observer.observe().clients}
    if len(original_roster) != 20:
        raise RuntimeError('requires complete native twenty-client roster')
    radios = [private_radio(command('lxc', 'exec', node, '--', 'iw', 'dev')) for node in nodes]
    bsses, hops = inventory(inventory_observer.last_raw)
    source_index = select_source_radio(radios, bsses, hops, 1 if rdk else len(radios) - 2)
    source_radio = radios[source_index]
    if any(radio['frequency'] != 2437 for radio in radios):
        raise RuntimeError('requires default channel 6 on all private 2.4 GHz radios')
    processes = {node: json.loads(command('lxc', 'query', f'/1.0/instances/{node}/state'))['pid']
                 for node in nodes + clients}
    originals = [association_identity(net_command(processes[node], 'iw', 'dev', 'wlan0', 'link')) for node in clients]
    if any(value is None for value in originals):
        raise RuntimeError('test clients must be associated')
    station_macs = [json.loads(net_command(processes[node], 'ip', '-j', 'link', 'show', 'wlan0'))[0]['address'] for node in clients]
    addresses = [next(row['local'] for row in json.loads(net_command(processes[node], 'ip', '-j', '-4', 'addr', 'show', 'wlan0'))[0]['addr_info']
                      if row['scope'] == 'global') for node in clients]
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'stack': args.stack, 'state': 'failed', 'original_associations': originals,
              'same_channel_negative': args.same_channel_negative,
              'workload': {'clients': 2, 'offered_mbps_each': 12, 'seconds': 85, 'native_metrics_injected': False},
              'timing_schema': 'native-load-stage-timings.v1', 'observation_gate_seconds': 20,
              'freshness_timing_scope': 'first sampled evidence after verification; not native arrival or convergence latency',
              'station_macs': station_macs, 'radios': radios, 'actions': [], 'restoration_errors': [],
              'source_node': nodes[source_index], 'source_bssid': source_radio['bssid'],
              'source_backhaul_hops': hops[bsses[source_radio['bssid']]['device_id']],
              'target_backhaul_hops': hops[bsses[radios[-1]['bssid']]['device_id']],
              'scope': 'two-client native load policy qualification; default 20 active, provisioned pool unchanged',
              'rf_candidates': 'native controller query using explicitly enabled idealized hwsim measurements'}
    cleanup, traffic, servers, handles = [], [], [], []
    provider = None
    capture = None

    def retune(frequency, restore=False):
        node, radio = nodes[-1], radios[-1]
        started = time.monotonic()
        if rdk:
            channel = 1 if frequency == 2412 else 6
            apply_radio_subdoc(node, radio_subdoc(original_radio_document, None if restore else channel))
        else:
            result = command('lxc', 'exec', node, '--', 'hostapd_cli', '-i', radio['interface'],
                             'chan_switch', '3', str(frequency), 'bandwidth=20', 'ht')
            if 'OK' not in result:
                raise RuntimeError('native channel switch rejected: ' + result)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            local = net_command(processes[node], 'iw', 'dev', radio['interface'], 'info')
            inventory_observer.observe()
            bsses = inventory(inventory_observer.last_raw)[0]
            if f'({frequency} MHz)' in local and bsses.get(radio['bssid'], {}).get('channel') == (1 if frequency == 2412 else 6):
                if rdk:
                    actual = private_channels(net_command(processes[node], 'iw', 'dev'))
                    expected = {name: dict(value) for name, value in report['original_live_radios'].items()}
                    expected['wifi0'].update(frequency=frequency, channel=1 if frequency == 2412 else 6)
                    if actual != expected:
                        raise RuntimeError('retune changed an unrelated radio: ' + json.dumps(actual))
                    if any(bsses.get(value['bssid'], {}).get('channel') != value['channel'] for value in expected.values()):
                        time.sleep(1)
                        continue
                    agent_pid = command('lxc', 'exec', node, '--', 'systemctl', 'show', 'em_agent', '-p', 'MainPID', '--value').strip()
                    if agent_pid != report['original_agent_pid']:
                        raise RuntimeError('agent restarted during single-radio retuning')
                    report.setdefault('retunes', []).append({'frequency': frequency, 'restore': restore,
                        'elapsed_seconds': time.monotonic() - started, 'live_radios': actual, 'agent_pid': agent_pid})
                return
            time.sleep(1)
        raise RuntimeError('kernel and native inventory did not confirm channel ' + str(frequency))

    try:
        report['native_identity_before'] = native_identity(args.root, args.stack)
        command('systemctl', 'stop', room, timeout=180)
        cleanup.append(('room service', lambda: command('systemctl', 'start', room, timeout=180)))

        def verify_native_restoration():
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                restored = inventory_observer.observe()
                if ({row.sta_mac for row in restored.clients} == original_roster and all(
                        row.rcpi is not None and row.rcpi > 0 and row.metric_observed_at is not None
                        and 0 <= time.time() - parse_time(row.metric_observed_at).timestamp() <= 30
                        for row in restored.clients)):
                    report['native_roster_restored'] = True
                    report['native_metrics_restored'] = True
                    return
                time.sleep(1)
            raise RuntimeError('fresh native twenty-client roster was not restored; operator recovery required')

        cleanup.insert(0, ('native client roster', verify_native_restoration))
        with ControlClient(control_path) as control:
            original_frequencies = control.dump_frequency_links()[1]
            links = control.dump_links()[1]
        registered = {row[field] for row in links + original_frequencies for field in ('source', 'destination')}
        for node, radio in zip(nodes, radios):
            radio['radio'] = registered_radio(node, radio['interface'], registered)
        station_radios = [registered_radio(node, 'wlan0', registered) for node in clients]
        if rdk:
            document_text = command('lxc', 'exec', nodes[-1], '--', 'rbuscli', 'get', 'Device.WiFi.WebConfig.Data.Init_dml')
            original_radio_document = json.loads(re.search(r'Value\s*:\s*([\s\S]*)', document_text)[1])
            radio_subdoc(original_radio_document)
            report['original_agent_pid'] = command('lxc', 'exec', nodes[-1], '--', 'systemctl', 'show', 'em_agent', '-p', 'MainPID', '--value').strip()
            if not report['original_agent_pid'].isdigit() or int(report['original_agent_pid']) <= 0:
                raise RuntimeError('requires a running native RDK agent')
            report['original_live_radios'] = private_channels(command('lxc', 'exec', nodes[-1], '--', 'iw', 'dev'))
            if (set(report['original_live_radios']) != {'wifi0', 'wifi1', 'wifi2'}
                    or any(value['width'] != 20 for value in report['original_live_radios'].values())):
                raise RuntimeError('requires three 20 MHz private radios before local RDK retuning')
            configured = {radio['RadioName']: radio['Channel'] for radio in original_radio_document['WifiRadioConfig']}
            if any(configured.get('radio' + str(int(name.removeprefix('wifi')) + 1)) != value['channel']
                   for name, value in report['original_live_radios'].items()):
                raise RuntimeError('RDK configured/live radio channels differ; restore before testing')
        cleanup.append(('client associations', lambda: [roam_client(node, *identity) for node, identity in zip(clients, originals)]))
        if not args.same_channel_negative:
            cleanup.append(('channel and native report', lambda: retune(2437, restore=True)))
            retune(2412)
        report['original_client_frequencies'] = {}
        for node in clients:
            prior = command('lxc', 'exec', node, '--', 'wpa_cli', '-i', 'wlan0', 'get_network', '0', 'freq_list').strip()
            if prior == 'FAIL':
                prior = ''
            if prior and not all(value.isdigit() for value in prior.split()):
                raise RuntimeError('requires explicit restorable client frequency list')
            report['original_client_frequencies'][node] = prior
            frequencies = '2437' if args.same_channel_negative else '2412 2437'
            require_ok('lxc', 'exec', node, '--', 'wpa_cli', '-i', 'wlan0', 'set_network', '0', 'freq_list', frequencies)
            cleanup.append(('client frequency capability', lambda owner=node, value=prior:
                require_ok('lxc', 'exec', owner, '--', 'wpa_cli', '-i', 'wlan0', 'set_network', '0', 'freq_list', value)))
        updates = []
        for index, station in enumerate(station_radios):
            for radio in radios:
                strength = 55 if radio is source_radio else 53 if index == 0 and radio is radios[-1] else -20
                for frequency in ((2437,) if args.same_channel_negative else (2412, 2437)):
                    for source, destination in ((station, radio['radio']), (radio['radio'], station)):
                        updates.append({'source': source, 'destination': destination, 'frequency_mhz': frequency, 'value': strength})
        key = lambda row: (row['source'], row['destination'], row['frequency_mhz'])
        original_by_key = {key(row): row for row in original_frequencies}
        restoration = [original_by_key.get(key(row), {**row, 'override': False, 'value': 0}) for row in updates]

        def restore_rf():
            with ControlClient(control_path) as control:
                control.apply_frequency(control.status().generation + 1, restoration)
                if sorted(control.dump_frequency_links()[1], key=key) != sorted(original_frequencies, key=key):
                    raise RuntimeError('frequency RF restoration mismatch')

        cleanup.append(('RF overrides', restore_rf))
        with ControlClient(control_path) as control:
            control.apply_frequency(control.status().generation + 1, updates)
            report['rf_readback'] = all(control.get_frequency_link(row['source'], row['destination'], row['frequency_mhz'])[1] == row['value'] for row in updates)
            if not report['rf_readback']:
                raise RuntimeError('test RF readback differs from requested links')
        for node in clients:
            print(json.dumps({'phase': 'source-roam', 'client': node}), flush=True)
            roam_client(node, source_radio['bssid'], 2437)
        report['target_scan_precondition'] = scan_for_roam(clients[0], radios[-1]['bssid'], 2437 if args.same_channel_negative else 2412)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            initial = inventory_observer.observe()
            (args.output / 'precondition-snapshot.json').write_text(json.dumps(initial.to_dict(), indent=2) + '\n')
            if all(initial.client(station) is not None and initial.client(station).connected_bssid == source_radio['bssid']
                   and initial.client(station).band == '2.4' and initial.client(station).rcpi is not None
                   and initial.client(station).rcpi > 0 and initial.client(station).metric_observed_at is not None
                   and 0 <= time.time() - parse_time(initial.client(station).metric_observed_at).timestamp() <= 30
                   for station in station_macs):
                break
            time.sleep(.5)
        else:
            raise RuntimeError('native controller did not confirm preconditioned source associations')
        selected = lambda client, _timestamp: client.sta_mac in station_macs
        candidate = ControllerCandidateProvider(base, allow_simulated=True, client_selector=selected) if rdk else PrplMeshCandidateProvider(
            allow_simulated=True, client_selector=selected, timeout_seconds=10)
        observer = observer_type(base, candidate_provider=TimedCandidates(candidate))
        for attempt in range(3):
            try:
                qualification = observer.observe()
                (args.output / 'candidate-precondition.json').write_text(json.dumps(qualification.to_dict(), indent=2) + '\n')
                break
            except Exception as error:
                detail = {'attempt': attempt + 1, 'error': str(error)}
                report.setdefault('candidate_precondition_retries', []).append(detail)
                print(json.dumps({'phase': 'candidate-precondition-retry', **detail}), flush=True)
                if attempt == 2:
                    raise
                time.sleep(2)
        provider = NativeLoadProvider(nodes[0], byte_counter_unit_bytes=1 if rdk else 1024)
        observer.ownership_observer = provider.observe_owners
        configuration = load_policy(args.root / 'optimizer/configs/load-aware-policy.yaml')
        report['production_policy'] = asdict(configuration)
        engine = policy_for(replace(configuration, expected_clients=2))
        policy_state = PolicyState()
        original_level = command('lxc', 'exec', clients[0], '--', 'wpa_cli', '-i', 'wlan0', 'log_level')
        report['original_log_level'] = original_level
        level = re.search(r'Current level:\s*(\w+)', original_level)[1]
        require_ok('lxc', 'exec', clients[0], '--', 'wpa_cli', '-i', 'wlan0', 'log_level', 'DEBUG')
        cleanup.append(('supplicant logging', lambda: require_ok('lxc', 'exec', clients[0], '--', 'wpa_cli', '-i', 'wlan0', 'log_level', level)))
        if rdk:
            cleanup.append(('native steering evidence', lambda: (args.output / 'source-agent.log').write_text(
                command('lxc', 'exec', nodes[source_index], '--', 'tail', '-n', '3000', '/rdklogs/logs/emAgent.txt'))))
        capture_path = args.output / 'supplicant-events.jsonl'
        report['supplicant_evidence'] = capture_path.name
        capture_output = capture_path.open('w')
        handles.append(capture_output)
        capture = subprocess.Popen(['nsenter', '-t', str(processes[clients[0]]), '-n', 'python3',
                                    str(args.root / 'tests/supplicant-event-capture.py'), '--socket',
                                    f'/proc/{processes[clients[0]]}/root/run/wpa_supplicant/wlan0',
                                    '--seconds', '180', '--watch-stdin'], stdin=subprocess.PIPE,
                                   stdout=capture_output, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 5
        while not capture_path.read_text().startswith('{"kind": "ready"}'):
            if capture.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('supplicant event capture did not become ready')
            time.sleep(.05)
        for index, node in enumerate(clients):
            port = str(59991 + index)
            if net_command(processes[nodes[0]], 'ss', '-H', '-lnt', 'sport = :' + port).strip():
                raise RuntimeError('traffic port already occupied')
            if rdk:
                for protocol in ('tcp', 'udp'):
                    rule = ['-s', addresses[index] + '/32', '-d', gateway + '/32', '-p', protocol, '--dport', port, '-j', 'ACCEPT']
                    command('lxc', 'exec', nodes[0], '--', 'iptables', '-I', 'INPUT', *rule)
                    cleanup.append(('traffic firewall', lambda specification=rule: command('lxc', 'exec', nodes[0], '--', 'iptables', '-D', 'INPUT', *specification)))
            server_output = (args.output / f'receiver-{index}.json').open('w')
            client_output = (args.output / f'sender-{index}.json').open('w')
            handles.extend([server_output, client_output])
            servers.append(subprocess.Popen(['nsenter', '-t', str(processes[nodes[0]]), '-n', 'iperf3', '-s', '-1', '-B', gateway, '-p', port, '-J', '-i', '1'],
                                            stdout=server_output, stderr=subprocess.STDOUT))
            time.sleep(.3)
            traffic.append(subprocess.Popen(['nsenter', '-t', str(processes[node]), '-n', 'iperf3', '-c', gateway, '-B', addresses[index], '-p', port, '-u', '-b', '12M', '-l', '1200', '-t', '85', '-J', '-i', '1'],
                                            stdout=client_output, stderr=subprocess.STDOUT))
        report['traffic_started_at'] = time.time()
        deadline = time.monotonic() + 65
        verified_monotonic = None
        negative_observations = []
        with (args.output / 'cycles.jsonl').open('w') as journal:
            cycle_index = 0
            while time.monotonic() < deadline:
                require_running_traffic(traffic + servers)
                cycle_index += 1
                snapshot, evaluation, cycle = measured_cycle(
                    observer, provider, engine, policy_state, station_macs, journal, cycle_index)
                policy_state = evaluation.state
                for prior_action in report['actions']:
                    record_post_verify_freshness(prior_action, snapshot, cycle, configuration)
                print(json.dumps({'loads': [(row.bssid, row.utilization) for row in snapshot.bss_loads if row.bssid in [source_radio['bssid'], radios[-1]['bssid']]],
                                  'activity': [(row.sta_mac, row.packets_per_second) for row in snapshot.client_activity],
                                  'decisions': [(row.sta_mac, row.reason) for row in evaluation.decisions]}), flush=True)
                actions = [row for row in evaluation.decisions if row.action == 'steer']
                if args.same_channel_negative:
                    if any(snapshot.client(station) is None or snapshot.client(station).connected_bssid != source_radio['bssid']
                           for station in station_macs):
                        raise RuntimeError('negative workload subject left the source AP')
                    channels = inventory(observer.last_raw)[0]
                    if any(channels.get(radio['bssid'], {}).get('channel') != 6 for radio in radios):
                        raise RuntimeError('negative workload requires native channel 6 on every AP')
                    observation = same_channel_negative(snapshot, evaluation, configuration,
                        station_macs[0], source_radio['bssid'], radios[-1]['bssid'])
                    negative_observations.append({'cycle_index': cycle_index, **observation})
                    if observation['qualified'] and verified_monotonic is None:
                        verified_monotonic = time.monotonic()
                for decision in actions:
                    if report['actions'] or decision.sta_mac != station_macs[0] or decision.target_bssid != radios[-1]['bssid'] or decision.reason != 'native_load_margin_hold_satisfied':
                        raise RuntimeError('unexpected or additional steering decision')
                    bsses = inventory(observer.last_raw)[0]
                    actuator = NativeSteerActuator({bssid: row['channel'] for bssid, row in bsses.items()}, base_url=base) if rdk else SteerActuator(
                        args.root / 'scripts/steer-client.sh', request_only=True, preview_seconds=0, timeout_seconds=20)
                    action = {'decision': decision.to_dict(), 'started_at': time.time(),
                              'cycle_index': cycle_index, 'timings': {},
                              'freshness_requirements': freshness_requirements(decision, snapshot)}
                    report['actions'].append(action)
                    result = timed_call(action['timings'], 'submission', actuator.execute, decision, snapshot)
                    action['submission'] = result.to_dict()
                    if not result.success:
                        raise RuntimeError('native BTM submission failed')
                    verifier = OutcomeVerifier(observer_type(base))
                    action['verification'] = timed_call(action['timings'], 'verification', verifier.verify,
                        decision.sta_mac, decision.target_bssid, timeout_seconds=15, poll_seconds=.1).to_dict()
                    action['verified_at'] = time.time()
                    if not action['verification']['success']:
                        raise RuntimeError('native controller did not verify target association')
                    verified_monotonic = time.monotonic()
                    record_post_verify_freshness(action, snapshot, cycle, configuration)
                if verified_monotonic is not None:
                    report['settling_observed_seconds'] = time.monotonic() - verified_monotonic
                    if report['settling_observed_seconds'] >= 20:
                        break
                time.sleep(.5)
        if args.same_channel_negative:
            report['negative_observations'] = negative_observations
            report['negative_result'] = negative_summary(negative_observations, configuration.load_condition_hold_seconds)
        elif not report['actions']:
            raise RuntimeError('no qualified native load-driven action before deadline')
        if (not args.same_channel_negative or report['negative_result']['passed']) and report.get('settling_observed_seconds', 0) < 20:
            raise RuntimeError('full post-steer settling window was not observed')
        for process in traffic + servers:
            process.wait(timeout=95)
            if process.returncode:
                raise RuntimeError('traffic process failed')
        for handle in handles:
            handle.flush()
        report['receiver_results'] = [json.loads((args.output / f'receiver-{index}.json').read_text()) for index in range(2)]
        if any(not row.get('end', {}).get('sum_received', row.get('end', {}).get('sum', {})).get('bits_per_second', 0) > 0 for row in report['receiver_results']):
            raise RuntimeError('no measured receiver goodput')
        report['state'] = report['negative_result']['state'] if args.same_channel_negative else 'passed'
    except Exception as error:
        report['error'] = str(error)
        print(json.dumps({'phase': 'failed-restoring', 'error': str(error)}), flush=True)
    finally:
        if provider is not None:
            provider.close()
        if capture is not None:
            capture.stdin.close()
            try:
                capture.wait(timeout=3)
            except subprocess.TimeoutExpired:
                stop_process(capture)
            if capture.returncode != 0 or '"kind": "end"' not in capture_path.read_text():
                report['restoration_errors'].append({'step': 'supplicant capture', 'error': 'incomplete event capture'})
        for process in traffic + servers:
            stop_process(process)
        for handle in handles:
            handle.close()
        for name, action in reversed(cleanup):
            try:
                action()
            except Exception as error:
                report['restoration_errors'].append({'step': name, 'error': str(error)})
        if 'native_identity_before' in report:
            try:
                report['native_identity_after'] = native_identity(args.root, args.stack)
                verify_native_identity(report['native_identity_before'], report['native_identity_after'])
                report['native_identities_unchanged'] = True
            except Exception as error:
                report['native_identities_unchanged'] = False
                report['restoration_errors'].append({'step': 'native process identity', 'error': str(error)})
        if args.same_channel_negative:
            try:
                report['final_private_radios'] = [private_radio(command('lxc', 'exec', node, '--', 'iw', 'dev')) for node in nodes]
                if any(radio['frequency'] != 2437 for radio in report['final_private_radios']):
                    raise RuntimeError('same-channel negative changed an AP channel')
                if report['actions'] or (capture is not None and 'BSS-TM-REQ' in capture_path.read_text()):
                    raise RuntimeError('same-channel negative observed a steering request')
            except Exception as error:
                report['restoration_errors'].append({'step': 'same-channel no-action audit', 'error': str(error)})
        if report['restoration_errors']:
            report['state'] = 'failed'
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'receiver_results'}), flush=True)
    return 0 if report['state'] == 'passed' else 2 if report['state'] == 'unsupported_workload' else 1


if __name__ == '__main__':
    raise SystemExit(main())
