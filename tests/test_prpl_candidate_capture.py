import io
import json
from pathlib import Path
import runpy
import signal
import subprocess
import sys

SCRIPT = Path(__file__).with_name('prpl-candidate-capture.py')


def test_capture_bounds_are_checked_before_creating_output(tmp_path):
    target = tmp_path / 'capture'
    result = subprocess.run([sys.executable, str(SCRIPT), str(target), '--seconds', '2401'], capture_output=True)
    assert result.returncode != 0
    assert not target.exists()


def test_capture_reaps_only_owned_processes_and_preserves_radio_state(tmp_path, monkeypatch):
    target = tmp_path / 'capture'
    calls = []
    processes = []

    class Process:
        def __init__(self, command, **kwargs):
            calls.append(command)
            self.stdout = io.BytesIO(b'irrelevant line\nunassociated measurement\nNo wmediumd candidate metric\n')
            self.reaped = False
            processes.append(self)

        def poll(self):
            return None

        def wait(self, timeout):
            self.reaped = True
            return 0

    monkeypatch.setattr('os.geteuid', lambda: 0)
    monkeypatch.setattr(subprocess, 'Popen', Process)
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: calls.append(command))
    monkeypatch.setattr('time.sleep', lambda seconds: (target / 'stop').touch())
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), str(target), '--seconds', '5'])
    previous = signal.getsignal(signal.SIGTERM)
    try:
        runpy.run_path(str(SCRIPT), run_name='__main__')
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert len(processes) == 10
    assert all(process.reaped for process in processes)
    assert len(json.loads((target / 'capture.json').read_text())['processes']) == 10
    assert (target / 'prpl-agent-01.log').read_text() == 'unassociated measurement\nNo wmediumd candidate metric\n'
    assert not any('hwsim0' in ' '.join(command) or 'systemctl' in command for command in calls)
    assert sum('kill -INT' in ' '.join(command) for command in calls) == 10
    assert sum(command[-3:-1] == ['rm', '-f'] for command in calls) == 10
