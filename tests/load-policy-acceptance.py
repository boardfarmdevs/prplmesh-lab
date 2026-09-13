import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import re
import signal
import subprocess
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
    args = parser.parse_args()
    if os.geteuid() or not args.yes_change_lab:
        parser.error('requires root and --yes-change-lab')
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
    source_radio = radios[1] if rdk else radios[-2]
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
              'station_macs': station_macs, 'radios': radios, 'actions': [], 'restoration_errors': [],
              'scope': 'two-client native load policy qualification; production pool remains 20',
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

        cleanup.append(('native client roster', verify_native_restoration))
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
            frequencies = '2412 2437'
            require_ok('lxc', 'exec', node, '--', 'wpa_cli', '-i', 'wlan0', 'set_network', '0', 'freq_list', frequencies)
            cleanup.append(('client frequency capability', lambda owner=node, value=prior:
                require_ok('lxc', 'exec', owner, '--', 'wpa_cli', '-i', 'wlan0', 'set_network', '0', 'freq_list', value)))
        updates = []
        for index, station in enumerate(station_radios):
            for radio in radios:
                strength = 55 if radio is source_radio else 53 if index == 0 and radio is radios[-1] else -20
                for frequency in (2412, 2437):
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
        report['target_scan_precondition'] = scan_for_roam(clients[0], radios[-1]['bssid'], 2412)
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
        observer = observer_type(base, candidate_provider=candidate)
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
        provider = NativeLoadProvider(nodes[0])
        configuration = load_policy(args.root / 'optimizer/configs/load-aware-policy.yaml')
        report['production_policy'] = asdict(configuration)
        engine = policy_for(replace(configuration, expected_clients=2))
        policy_state = PolicyState()
        original_level = command('lxc', 'exec', clients[0], '--', 'wpa_cli', '-i', 'wlan0', 'log_level')
        report['original_log_level'] = original_level
        level = re.search(r'Current level:\s*(\w+)', original_level)[1]
        require_ok('lxc', 'exec', clients[0], '--', 'wpa_cli', '-i', 'wlan0', 'log_level', 'DEBUG')
        cleanup.append(('supplicant logging', lambda: require_ok('lxc', 'exec', clients[0], '--', 'wpa_cli', '-i', 'wlan0', 'log_level', level)))
        if not rdk:
            cleanup.append(('supplicant evidence', lambda: (args.output / 'supplicant.log').write_text(command('lxc', 'exec', clients[0], '--', 'tail', '-n', '1800', '/tmp/wpa_supplicant.log'))))
        else:
            cleanup.append(('native steering evidence', lambda: (args.output / 'source-agent.log').write_text(
                command('lxc', 'exec', nodes[1], '--', 'tail', '-n', '3000', '/rdklogs/logs/emAgent.txt'))))
        capture_path = args.output / 'supplicant-events.jsonl'
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
            traffic.append(subprocess.Popen(['nsenter', '-t', str(processes[node]), '-n', 'iperf3', '-c', gateway, '-p', port, '-u', '-b', '12M', '-l', '1200', '-t', '85', '-J', '-i', '1'],
                                            stdout=client_output, stderr=subprocess.STDOUT))
        report['traffic_started_at'] = time.time()
        deadline = time.monotonic() + 65
        verified_monotonic = None
        with (args.output / 'cycles.jsonl').open('w') as journal:
            while time.monotonic() < deadline:
                snapshot = observer.observe()
                snapshot = replace(snapshot, health=replace(snapshot.health, clients=2),
                    clients=tuple(row for row in snapshot.clients if row.sta_mac in station_macs),
                    candidates=tuple(row for row in snapshot.candidates if row.sta_mac in station_macs))
                snapshot = provider.enrich(snapshot, observer.last_raw)
                evaluation = engine.evaluate(snapshot, policy_state)
                policy_state = evaluation.state
                journal.write(json.dumps({'snapshot': snapshot.to_dict(), 'evaluation': evaluation.to_dict(), 'raw': observer.last_raw}) + '\n')
                journal.flush()
                print(json.dumps({'loads': [(row.bssid, row.utilization) for row in snapshot.bss_loads if row.bssid in [source_radio['bssid'], radios[-1]['bssid']]],
                                  'activity': [(row.sta_mac, row.packets_per_second) for row in snapshot.client_activity],
                                  'decisions': [(row.sta_mac, row.reason) for row in evaluation.decisions]}), flush=True)
                actions = [row for row in evaluation.decisions if row.action == 'steer']
                for decision in actions:
                    if report['actions'] or decision.sta_mac != station_macs[0] or decision.target_bssid != radios[-1]['bssid'] or decision.reason != 'native_load_margin_hold_satisfied':
                        raise RuntimeError('unexpected or additional steering decision')
                    bsses = inventory(observer.last_raw)[0]
                    actuator = NativeSteerActuator({bssid: row['channel'] for bssid, row in bsses.items()}, base_url=base) if rdk else SteerActuator(
                        args.root / 'scripts/steer-client.sh', request_only=True, preview_seconds=0, timeout_seconds=20)
                    action = {'decision': decision.to_dict(), 'started_at': time.time()}
                    report['actions'].append(action)
                    result = actuator.execute(decision, snapshot)
                    action['submission'] = result.to_dict()
                    if not result.success:
                        raise RuntimeError('native BTM submission failed')
                    verifier = OutcomeVerifier(observer_type(base))
                    action['verification'] = verifier.verify(decision.sta_mac, decision.target_bssid, timeout_seconds=15, poll_seconds=.1).to_dict()
                    action['verified_at'] = time.time()
                    if not action['verification']['success']:
                        raise RuntimeError('native controller did not verify target association')
                    verified_monotonic = time.monotonic()
                if verified_monotonic is not None:
                    report['settling_observed_seconds'] = time.monotonic() - verified_monotonic
                    if report['settling_observed_seconds'] >= 20:
                        break
                time.sleep(.5)
        if not report['actions']:
            raise RuntimeError('no qualified native load-driven action before deadline')
        if report.get('settling_observed_seconds', 0) < 20:
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
        report['state'] = 'passed'
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
        if report['restoration_errors']:
            report['state'] = 'failed'
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'receiver_results'}), flush=True)
    return 0 if report['state'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
