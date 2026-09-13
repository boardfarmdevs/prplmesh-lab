import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--seconds', type=int, default=720)
args = parser.parse_args()
if not 5 <= args.seconds <= 2400:
    parser.error('--seconds must be between 5 and 2400')
if os.geteuid() != 0:
    parser.error('run inside the lab VM as root')
args.output.mkdir(parents=True, exist_ok=False)
owned = []
streams = []
readers = []
started = time.time()
nodes = ['prpl-controller', 'prpl-agent-01', 'prpl-agent-02', 'prpl-agent-03', 'prpl-agent-04']
capture_id = uuid.uuid4().hex

def stop_requested(signum, _frame):
    raise SystemExit(128 + signum)

signal.signal(signal.SIGTERM, stop_requested)

def copy_measurements(stream, output):
    for line in stream:
        lowered = line.lower()
        if any(marker in lowered for marker in (b'unassoc', b'candidate metric', b'signal_strength', b'time_stamp', b'error', b'failed')):
            output.write(line)
    output.flush()

try:
    for node in nodes:
        commands = [('pcap', ['tcpdump', '-i', 'br-lan', '-U', '-s', '0', '-B', '2048', '-w', '-', 'ether', 'proto', '0x893a'])]
        logs = ['/tmp/beerocks/logs/beerocks_agent.log', '/tmp/beerocks/logs/beerocks_ap_manager_wlan2.log',
                '/tmp/beerocks/logs/beerocks_monitor_wlan2.log']
        if node == 'prpl-controller':
            logs.append('/tmp/beerocks/logs/beerocks_controller.log')
        commands.append(('log', ['tail', '-n', '0', '-F', *logs]))
        for kind, command in commands:
            pidfile = f'/tmp/prpl-candidate-{capture_id}-{kind}.pid'
            output = (args.output / f'{node}.{kind}').open('wb')
            errors = (args.output / f'{node}.{kind}.stderr').open('wb')
            streams.extend([output, errors])
            process = subprocess.Popen(['lxc', 'exec', node, '--', 'sh', '-c',
                                        'echo $$ > "$1"; shift; exec "$@"', 'capture', pidfile, *command],
                                       stdout=subprocess.PIPE if kind == 'log' else output, stderr=errors)
            owned.append((node, pidfile, process))
            if kind == 'log':
                reader = threading.Thread(target=copy_measurements, args=(process.stdout, output))
                reader.start()
                readers.append(reader)
    time.sleep(2)
    assert all(process.poll() is None for _, _, process in owned), 'capture startup failed'
    (args.output / 'ready').touch()
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline and not (args.output / 'stop').exists():
        assert all(process.poll() is None for _, _, process in owned), 'capture exited early'
        assert sum(path.stat().st_size for path in args.output.iterdir()) < 256 * 1024 * 1024, 'capture budget exceeded'
        time.sleep(1)
finally:
    results = []
    for node, pidfile, process in owned:
        subprocess.run(['lxc', 'exec', node, '--', 'sh', '-c',
                        'if test -f "$1"; then kill -INT "$(cat "$1")"; fi', 'stop', pidfile], check=False)
        try:
            status = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            subprocess.run(['lxc', 'exec', node, '--', 'sh', '-c',
                            'if test -f "$1"; then kill -TERM "$(cat "$1")"; fi', 'stop', pidfile], check=False)
            status = process.wait(timeout=10)
        subprocess.run(['lxc', 'exec', node, '--', 'rm', '-f', pidfile], check=False)
        results.append({'node': node, 'pidfile': pidfile, 'exit': status})
    for reader in readers:
        reader.join(timeout=10)
        assert not reader.is_alive(), 'log reader did not stop'
    for stream in streams:
        stream.close()
    (args.output / 'capture.json').write_text(json.dumps({'started': started, 'finished': time.time(), 'processes': results}, indent=2))
