#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PHASES = ('static', 'webui', 'browser', 'rf', 'rf-actions', 'rooms', 'live', 'soak')


def main():
    parser = argparse.ArgumentParser(description='Host-side prplMesh suite; defaults to offline static tests. Mutating tiers require --yes-act.')
    parser.add_argument('sections', nargs='*', metavar='SECTION', help='static, webui, browser, rf, rf-actions, rooms, live, soak or all')
    parser.add_argument('--yes-act', action='store_true')
    parser.add_argument('--install-browser-deps', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--churn-iterations', type=int, default=3)
    parser.add_argument('--list', action='store_true', help='show tiers without running commands')
    args = parser.parse_args()
    if set(args.sections) - set((*PHASES, 'all')):
        parser.error('unknown section; choose ' + ', '.join((*PHASES, 'all')))
    def interrupt(_signum, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupt)
    chosen = set(PHASES if 'all' in args.sections else (args.sections or ['static']))
    if args.list:
        print('\n'.join(section for section in PHASES if section in chosen))
        return 0
    if chosen & {'rf', 'rf-actions', 'rooms', 'live', 'soak'} and not args.yes_act:
        parser.error('rf/rf-actions/rooms/live/soak change RF; use --yes-act on an idle test VM')
    if not 1 <= args.churn_iterations <= 100:
        parser.error('--churn-iterations must be between 1 and 100')
    vm = os.environ.get('PRPLMESH_VM_NAME', 'prplmesh')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = args.output or ROOT / 'test-results' / f'{stamp}-{vm}'
    output.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ)
    for variable in ('DISPLAY', 'WAYLAND_DISPLAY'):
        environment.pop(variable, None)
    environment['PYTHONPATH'] = ':'.join(str(ROOT / entry) for entry in (
        'optimizer', 'demo', 'demo/tests', 'wmediumd/configurator', 'tests'))
    environment['PLAYWRIGHT_MODULE'] = 'playwright-core'
    records = []
    room_restore = False
    room_masked = False
    topology = ROOT / 'controller-ui/web/static'
    room_url = f"http://127.0.0.1:{environment['PRPLMESH_ROOM_DEMO_HOST_PORT']}/"
    topology_url = f"http://127.0.0.1:{environment['PRPLMESH_UI_HOST_PORT']}/"
    console_url = f"http://127.0.0.1:{environment['PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT']}/"

    def record(name, status, elapsed=0, detail=''):
        records.append(dict(name=name, status=status, seconds=round(elapsed, 3), detail=detail))
        print(f'[{status}] {name} ({elapsed:.1f}s) {detail}', flush=True)
        totals = {state: sum(row['status'] == state for row in records) for state in ('passed', 'failed', 'blocked')}
        (output / 'summary.json').write_text(json.dumps(dict(vm=vm, totals=totals, results=records), indent=2) + '\n')
        (output / 'results.tsv').write_text('name\tstatus\tseconds\tdetail\n' + ''.join(
            f"{row['name']}\t{row['status']}\t{row['seconds']}\t{row['detail']}\n" for row in records))

    def step(name, command, timeout=300, cwd=ROOT):
        print(f'\n===== {name} =====\n{shlex.join(map(str, command))}', flush=True)
        started = time.monotonic()
        logfile = output / (name.replace('/', '-') + '.log')
        with logfile.open('w') as stream:
            process = None
            try:
                process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=stream,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                code = process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                if process is not None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                record(name, 'failed', time.monotonic() - started, 'interrupted or timed out')
                raise
            except OSError as error:
                stream.write(str(error) + '\n')
                code = 127
        print(logfile.read_text()[-6000:], end='', flush=True)
        record(name, 'passed' if code == 0 else 'failed', time.monotonic() - started, str(logfile))
        return code == 0

    def guest(*command):
        return ['lxc', 'exec', vm, '--', *command]

    def install_helper(name):
        command = ['lxc', 'exec', '--mode', 'non-interactive', vm, '--',
                   'install', '-m', '0644', '/dev/stdin', '/tmp/' + name]
        return ['bash', '-c', shlex.join(command) + ' < ' + shlex.quote(str(ROOT / 'tests' / name))]

    def native(script, *extra):
        return guest('env', 'PRPL_AGENT_COUNT=4', 'PRPL_CLIENT_COUNT=100', 'PRPL_TOPOLOGY=star',
                     'PROVISIONED_CLIENT_COUNT=100', 'HWSIM_RADIOS=120',
                     f'PRPL_CHURN_ITERATIONS={args.churn_iterations}',
                     'bash', '/opt/prplmesh-lab/' + script, *extra)

    def browser_ready():
        tools = ROOT / 'browser-tools'
        environment['NODE_PATH'] = str(tools / 'node_modules') + ':' + environment.get('NODE_PATH', '')
        if args.install_browser_deps:
            if not step('deps/playwright', ['npm', 'install', '--prefix', str(tools), '--save-exact', 'playwright-core']):
                return False
            if not step('deps/chromium', ['node', str(tools / 'node_modules/playwright-core/cli.js'), 'install', 'chromium'], 600):
                return False
        return step('deps/browser-ready', ['node', '-e',
            "const fs=require('fs');const browser=require('playwright-core').chromium;"
            "if(Number(process.versions.node.split('.')[0])<22)throw Error('Node 22+ required');"
            "if(!fs.existsSync(process.env.CHROMIUM_PATH||browser.executablePath()))throw Error('Install Chromium or set CHROMIUM_PATH');"])

    def stop_room():
        nonlocal room_restore, room_masked
        result = subprocess.run(guest('systemctl', 'show', 'prplmesh-room-demo.service', '-p', 'ActiveState', '--value'),
                                capture_output=True, text=True, timeout=30)
        if result.returncode or result.stdout.strip() not in ('active', 'inactive'):
            record('live/room-state', 'failed', detail='room must be active or cleanly stopped')
            return False
        was_active = result.stdout.strip() == 'active'
        mask_state = subprocess.run(guest('systemctl', 'is-enabled', 'prplmesh-room-demo.service'),
                                    capture_output=True, text=True, timeout=30).stdout.strip()
        if mask_state.startswith('masked'):
            record('live/room-state', 'failed', detail='room was already masked; resolve this before testing')
            return False
        if not step('live/install-room-guard', install_helper('suite-room-guard.sh')):
            return False
        if not step('live/guard-room', guest('bash', '/tmp/suite-room-guard.sh', 'acquire'), 60):
            return False
        room_masked = True
        room_restore = was_active
        if not step('live/stop-room', guest('systemctl', 'stop', 'prplmesh-room-demo.service'), 180):
            return False
        if not step('live/prepare-backhaul', guest('python3', '/opt/prplmesh-lab/tests/prepare-native-baseline.py',
                                                 '--yes-act', '--agents', '4'), 120):
            return False
        return step('live/full-roster', guest('bash', '-c',
            'for attempt in $(seq 1 36); do '
            'python3 /opt/prplmesh-lab/tests/topology-acceptance.py --agents 4 --clients 100 --topology star && exit 0; '
            'sleep 5; done; exit 1'), 300)

    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
        (output / 'source.json').write_text(json.dumps(dict(commit=revision, dirty=dirty, sections=sorted(chosen)), indent=2))
        if 'static' in chosen:
            step('static/documentation', [sys.executable, 'tests/test_documentation.py'])
            step('static/unattended-lxd', [sys.executable, 'tests/unattended-lxd.py'])
            step('static/thin-firstboot', ['bash', 'tests/thin-firstboot.sh'])
            step('static/python', [sys.executable, '-m', 'pytest', '--import-mode=importlib', '-q',
                                  'wmediumd/configurator/tests', 'optimizer/tests', 'demo/tests', 'tests'], 1200)
            step('static/console-go', ['go', 'test', './...'], cwd=ROOT / 'wmediumd/observer')
            if step('static/topology-assets', ['bash', 'controller-ui/prepare-web-assets.sh']):
                step('static/topology-go', ['go', 'test', './...'], cwd=ROOT / 'controller-ui')
        if 'webui' in chosen:
            for filename in sorted((ROOT / 'tests').glob('*-test.js')):
                if 'browser' in filename.name or filename.name == 'viewer-sidebar-layout-test.js':
                    continue
                command = ['node', str(filename)]
                if filename.name == 'webui-rf-hover-test.js':
                    command.append(str(topology / 'room-topology.js'))
                elif filename.name.startswith('webui-'):
                    command.append(str(topology / 'script.js'))
                elif filename.name == 'steering-cues-test.js':
                    command.append(str(topology / 'steering-cues.js'))
                step('webui/' + filename.stem, command)
            for filename in sorted((ROOT / 'tests').glob('test-*.js')):
                step('webui/' + filename.stem, ['node', str(filename)])
            step('webui/console-ng', ['node', '--test', 'wmediumd/observer/web/ng/model.test.mjs'])
        needs_browser = bool(chosen & {'browser', 'rooms'})
        browser_ok = browser_ready() if needs_browser else False
        if 'browser' in chosen:
            if browser_ok and step('browser/assets', ['bash', 'controller-ui/prepare-web-assets.sh']):
                files = sorted((ROOT / 'tests').glob('*browser-test.js')) + [ROOT / 'tests/viewer-sidebar-layout-test.js']
                for filename in files:
                    if filename.name == 'webui-rf-hover-browser-test.js':
                        continue
                    command = ['node', str(filename)]
                    if filename.name == 'steering-cues-browser-test.js':
                        command += [str(topology / 'steering-cues.js'), str(topology / 'vendor/d3-7.9.0.min.js')]
                    if filename.name == 'webui-room-follow-browser-test.js':
                        command.append(str(topology))
                    step('browser/' + filename.stem, command)
            else:
                record('browser/tests', 'blocked', detail='browser dependencies unavailable')
        live_ok = True
        if chosen & {'rf', 'rf-actions', 'rooms', 'live', 'soak'}:
            live_ok = not dirty and step('live/source-match', guest('bash', '-c',
                'test "$(git -C /opt/prplmesh-lab rev-parse HEAD)" = "$1" && '
                'test -z "$(git -C /opt/prplmesh-lab status --porcelain)"', 'source-check', revision))
            if not live_ok:
                record('live/prerequisites', 'blocked', detail='host and guest must be clean, matching checkouts')
            else:
                config = json.loads(subprocess.check_output(['lxc', 'query', '/1.0/instances/' + vm], text=True, timeout=30))
                def endpoint(name):
                    address = config['expanded_devices'][name]['listen'].removeprefix('tcp:')
                    if address.startswith('0.0.0.0:'):
                        address = '127.0.0.1:' + address.rsplit(':', 1)[1]
                    return 'http://' + address + '/'
                room_url = endpoint('room-demo-viewer')
                topology_url = endpoint('controller-ui')
                console_url = endpoint('wmediumd-console')
        if 'rf-actions' in chosen:
            actions_ok = step('rf-actions/contracts', [sys.executable, '-m', 'pytest', '-q',
                                                     'tests/test_load_acceptance.py'])
            scenarios = ('clear', 'pressure', 'rescue')
            if live_ok and actions_ok:
                for index, scenario in enumerate(scenarios):
                    workload = ['--payload-bytes', '1400'] if scenario == 'clear' else [
                        '--payload-bytes', '1200', '--pressure-payload-bytes', '512',
                        '--pressure-access-category', 'voice', '--pressure-snr', '2',
                        '--rescue-snr', '32', '--background-packets-per-second', '300']
                    if not step('rf-actions/' + scenario, guest('env',
                        'PYTHONPATH=/opt/prplmesh-lab/optimizer:/opt/prplmesh-lab/wmediumd/configurator',
                        'python3', '/opt/prplmesh-lab/tests/load-policy-acceptance.py', '--stack', 'prpl',
                        '--root', '/opt/prplmesh-lab', '--policy',
                        '/opt/prplmesh-lab/optimizer/configs/load-counter-guard-policy.yaml',
                        *workload, '--counter-case', scenario, '--yes-change-lab', '--output',
                        '/opt/prplmesh-lab/test-results/rf-actions-' + stamp + '-' + scenario), 600):
                        for pending in scenarios[index + 1:]:
                            record('rf-actions/' + pending, 'blocked',
                                   detail=scenario + ' failed; subsequent RF mutations were not attempted')
                        break
            else:
                for scenario in scenarios:
                    record('rf-actions/' + scenario, 'blocked',
                           detail='contracts or clean matching checkouts required')
        if 'rf' in chosen:
            contracts_ok = step('rf/contracts', [sys.executable, '-m', 'pytest', '--import-mode=importlib', '-o', 'addopts=', '-q',
                'optimizer/tests/test_counter_guard.py', 'optimizer/tests/test_counter_shadow.py',
                'optimizer/tests/test_load_policy.py', 'optimizer/tests/test_policy.py',
                'optimizer/tests/test_owner_observation.py', 'optimizer/tests/test_rf_observations.py',
                'demo/tests/test_rf_property_coverage.py', 'demo/tests/test_rf_rooms.py', 'demo/tests/test_world_switch.py',
                'demo/tests/test_traffic_experiment.py', 'demo/tests/test_rf_observation.py',
                'tests/test_rf_property_rooms_smoke.py', 'tests/test_counter_guard_room_smoke.py',
                'tests/test_native_retry_counters.py', 'tests/test_connected_model_repair.py',
                'tests/test_candidate_event_memory.py', 'tests/test_neighbor_cache_memory.py',
                'tests/test_frequency_slot_allocation.py',
                'tests/test_console_ng_contract.py',
                'wmediumd/configurator/tests/test_rf_contract.py'])
            contracts_ok = step('rf/viewer', ['node', 'tests/viewer-room-guide-test.js']) and contracts_ok
            contracts_ok = step('rf/inspector', ['node', 'tests/viewer-rf-inspector-test.js']) and contracts_ok
            contracts_ok = step('rf/documentation', [sys.executable, 'tests/test_documentation.py']) and contracts_ok
            if live_ok and contracts_ok:
                rooms_ok = step('rf/rooms', [sys.executable, 'tests/rf-property-rooms-smoke.py', '--yes-act',
                    '--host', 'local', '--vm', vm, '--room-url', room_url, '--output', str(output / 'rf-properties.json')], 240)
                if rooms_ok:
                    manifest_ok = step('rf/counter-manifest', guest('python3', '/opt/prplmesh-lab/tests/counter-guard-room-smoke.py',
                        '--stack', 'prpl', '--yes-change-lab', '--output', f'/var/lib/prplmesh-lab/test-results/{stamp}-counter-manifest'), 1200)
                    if manifest_ok:
                        step('rf/counter-shadow', guest('env', 'PYTHONPATH=/opt/prplmesh-lab/optimizer:/opt/prplmesh-lab/wmediumd/configurator',
                            'python3', '/opt/prplmesh-lab/tests/native-retry-counter-acceptance.py', '--stack', 'prpl',
                            '--yes-change-lab', '--seconds', '8', '--shadow-counter-policy',
                            '/opt/prplmesh-lab/optimizer/configs/load-counter-guard-policy.yaml', '--output',
                            f'/var/lib/prplmesh-lab/test-results/{stamp}-counter-shadow'), 240)
                    else:
                        record('rf/counter-shadow', 'blocked', detail='manifest/restoration failed')
                else:
                    record('rf/counter-checks', 'blocked', detail='room/restoration failed')
            else:
                record('rf/live', 'blocked', detail='contracts or clean matching checkouts required; use direct helpers for diagnostics')
        if 'rooms' in chosen:
            if live_ok and browser_ok:
                helpers_ok = all([step('rooms/install-' + name, install_helper(name))
                                  for name in ('room-feature-guest-audit.py', 'backhaul-native-probe.py')])
                if helpers_ok:
                    common = ['--host', 'local', '--vm', vm, '--flavor', 'prpl', '--room-url', room_url, '--topology-url', topology_url]
                    step('rooms/catalog-play', ['node', 'tests/room-feature-acceptance.js', *common,
                         '--yes-act', '--worlds', str(ROOT / 'wmediumd/configurator/worlds/golden'), '--output', str(output / 'rooms')], 14400)
                    step('rooms/geometry-play', ['node', 'tests/room-backhaul-features.js', *common,
                         '--yes-act', 'true', '--output', str(output / 'backhaul')], 3600)
            else:
                record('rooms/playback', 'blocked', detail='browser or matching-VM prerequisites unavailable')
        if chosen & {'live', 'soak'}:
            if live_ok:
                step('live/console-ng', [sys.executable, 'wmediumd/observer/check-ready.py', '--url', console_url], 90)
                if browser_ok:
                    step('live/rf-hover', ['node', 'tests/webui-rf-hover-browser-test.js', topology_url, str(output / 'rf-hover.json')])
            if live_ok and stop_room():
                acceptance_ok = True
                if 'live' in chosen:
                    acceptance_ok = step('live/native-acceptance', native('tests/run-acceptance.sh'), 3600)
                    if acceptance_ok:
                        acceptance_ok = step('live/controller-memory', guest(
                            'python3', '/opt/prplmesh-lab/tests/controller-memory.py', '--expected-clients', '100',
                            '--traffic', '--include-fronthaul', '--output',
                            f'/var/lib/prplmesh-lab/test-results/{stamp}-controller-memory.json'), 180)
                    else:
                        record('live/controller-memory', 'blocked', detail='native acceptance failed')
                if 'soak' in chosen:
                    if acceptance_ok:
                        step('soak/churn', native('tests/churn-soak.sh'), 3600)
                    else:
                        record('soak/churn', 'blocked', detail='native acceptance failed')
            else:
                record('live/native-tests', 'blocked', detail='full-roster prerequisite failed; no weakened headcount gate')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        record('suite/interrupted', 'failed', detail=str(error).replace('\n', ' '))
    finally:
        for needed, name, command, timeout in (
            (room_masked, 'release-room-guard', guest('bash', '/tmp/suite-room-guard.sh', 'release'), 60),
            (room_restore, 'start-room', guest('systemctl', 'start', 'prplmesh-room-demo.service'), 180),
        ):
            if needed:
                try:
                    step('restore/' + name, command, timeout)
                except (OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
                    record('restore/' + name + '-error', 'failed', detail=str(error).replace('\n', ' '))
        print(f'\nResults: {output / "summary.json"}', flush=True)
    return int(any(row['status'] != 'passed' for row in records))


if __name__ == '__main__':
    raise SystemExit(main())
