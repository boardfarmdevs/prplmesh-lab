#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import urllib.request


flavor = sys.argv[1]
root = Path('/home/easymesh/git/meta-cmf-bananapi-vcpe' if flavor == 'rdk' else '/opt/prplmesh-lab')
configurator = root / ('gen/wmediumd/configurator' if flavor == 'rdk' else 'wmediumd/configurator')
sys.path.insert(0, str(configurator))
from wmdcfg.actuator import ControlClient


def request(suffix):
    with urllib.request.urlopen('http://127.0.0.1:8891/api/demo/' + suffix, timeout=10) as response:
        return json.load(response)


current = request('current')
before = request('interactions')
evidence = Path('/home/easymesh/easymesh-evidence/room-runs' if flavor == 'rdk' else '/var/lib/prplmesh-lab/room-runs') / current['run_id']
bindings = json.loads((evidence / 'bindings.json').read_text())['roles']
inventory = json.loads((evidence / 'inventory.json').read_text())['radios']
radios = {radio['container']: radio for radio in inventory}
station = radios[bindings['sta_mobile_01']]['tx_mac']
rows = []
socket_path = '/run/wmediumd-control.sock' if flavor == 'rdk' else '/run/prpl-wmediumd/control.sock'
with ControlClient(socket_path) as client:
    for role in ['gateway', 'extender_1', 'extender_2', 'extender_3', 'extender_4']:
        for band, radio in radios[bindings[role]]['band_radios'].items():
            frequency = radio['frequency_mhz']
            down = client.get_frequency_link(radio['tx_mac'], station, frequency)
            up = client.get_frequency_link(station, radio['tx_mac'], frequency)
            rows.append({'ap': role, 'band': band, 'frequency_mhz': frequency,
                         'down': down, 'up': up, 'uplink_minus_downlink_db': up[1] - down[1]})
after = request('interactions')
print(json.dumps({'world': before['selected_world'], 'playback': before['playback'],
                  'epoch': before['environment_epoch'], 'epoch_stable': before['environment_epoch'] == after['environment_epoch'],
                  'roles': before['roles'], 'links': rows}, indent=2))
