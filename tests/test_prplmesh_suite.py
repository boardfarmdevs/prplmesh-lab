import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('prpl_suite', ROOT / 'tests/run-prplmesh-suite.py')
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


def run_fixture(tmp_path, *, fail='', state='active', dirty=False):
    calls = []
    def spawn(command, **_options):
        calls.append(command)
        code = int(bool(fail and any(fail in str(item) for item in command)))
        return SimpleNamespace(wait=lambda timeout: code)

    def output(command, **_options):
        if command[:2] == ['lxc', 'query']:
            return json.dumps({'expanded_devices': {
                name: {'listen': 'tcp:192.0.2.1:' + str(port)} for name, port in
                [('room-demo-viewer', 42002), ('controller-ui', 42000), ('wmediumd-console', 42001)]}})
        return ('dirty' if dirty else '') if 'status' in command else 'abc123\n'

    def execute(command, **_options):
        return SimpleNamespace(returncode=0, stdout=state if 'show' in command else 'enabled')

    environment = {'PRPLMESH_VM_NAME': 'fixture', 'PRPLMESH_ROOM_DEMO_HOST_PORT': '42002',
                   'PRPLMESH_UI_HOST_PORT': '42000', 'PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT': '42001'}
    with patch.object(suite.sys, 'argv', ['suite', 'live', 'soak', '--yes-act', '--output', str(tmp_path / 'run')]), \
         patch.dict(suite.os.environ, environment), \
         patch.object(suite.subprocess, 'Popen', side_effect=spawn), \
         patch.object(suite.subprocess, 'check_output', side_effect=output), \
         patch.object(suite.subprocess, 'run', side_effect=execute), \
         patch.object(suite.signal, 'signal'), contextlib.redirect_stdout(io.StringIO()):
        result = suite.main()
    report = json.loads((tmp_path / 'run/summary.json').read_text())
    return result, calls, report


def test_native_steps_hold_room_stopped_until_after_churn(tmp_path):
    result, calls, report = run_fixture(tmp_path)
    assert result == 0
    names = [row['name'] for row in report['results']]
    assert names.index('live/stop-room') < names.index('live/native-acceptance') < names.index('soak/churn')
    assert names.index('soak/churn') < names.index('restore/release-room-guard') < names.index('restore/start-room')
    assert sum('acquire' in command for command in calls) == 1
    assert sum('start' in command for command in calls) == 1
    readiness = next(command for command in calls if 'wmediumd/observer/check-ready.py' in command)
    assert 'http://192.0.2.1:42001/' in readiness


def test_acceptance_failure_blocks_churn_but_restores_service(tmp_path):
    result, calls, report = run_fixture(tmp_path, fail='run-acceptance.sh')
    assert result == 1
    assert not any('churn-soak.sh' in str(command) for command in calls)
    assert report['results'][-1]['name'] == 'restore/start-room'
    assert report['totals']['blocked'] == 1


def test_inactive_room_is_not_started_by_cleanup(tmp_path):
    result, calls, _report = run_fixture(tmp_path, state='inactive')
    assert result == 0
    assert not any('start' in command for command in calls)
    assert any('release' in command for command in calls)


def test_roster_gate_failure_never_runs_native_checks(tmp_path):
    result, calls, _report = run_fixture(tmp_path, fail='topology-acceptance.py')
    assert result == 1
    assert not any('run-acceptance.sh' in str(command) for command in calls)
    assert any('start' in command for command in calls)


def test_dirty_checkout_does_not_touch_guest_services(tmp_path):
    result, calls, _report = run_fixture(tmp_path, dirty=True)
    assert result == 1
    assert not calls


def test_restore_failure_is_a_suite_failure(tmp_path):
    result, _calls, report = run_fixture(tmp_path, fail='start')
    assert result == 1
    assert report['results'][-1]['status'] == 'failed'


def test_failed_guard_acquisition_never_changes_another_suites_room(tmp_path):
    result, calls, report = run_fixture(tmp_path, fail='acquire')
    assert result == 1
    assert not any(any(operation in command for operation in ('start', 'stop', 'release')) for command in calls)
    assert not any(row['name'].startswith('restore/') for row in report['results'])


def test_guard_installation_can_replace_an_operator_owned_tmp_file(tmp_path):
    result, calls, _report = run_fixture(tmp_path)
    assert result == 0
    installation = next(command for command in calls if command[:2] == ['bash', '-c'])
    assert 'exec --mode non-interactive fixture -- install -m 0644 /dev/stdin /tmp/suite-room-guard.sh' in installation[2]
    assert not any(command[:3] == ['lxc', 'file', 'push'] for command in calls)
