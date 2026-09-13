from pathlib import Path
import subprocess
import sys


def test_assembled_candidate_transaction_faults(tmp_path):
    root = Path(__file__).resolve().parents[1]
    initial = (root / 'patches/prplmesh/0006-nl80211-read-hwsim-candidate-metrics.patch').read_text()
    block = initial.split('--- a/controller/')[0]
    lines = []
    in_hunk = False
    for line in block.splitlines():
        if line.startswith('@@'):
            in_hunk = True
        elif in_hunk and line.startswith(('+', ' ')):
            lines.append(line[1:])
    source = tmp_path / 'common/beerocks/bwl/nl80211/mon_wlan_hal_nl80211.cpp'
    source.parent.mkdir(parents=True)
    source.write_text('\n'.join(lines) + '\n')
    patch = root / 'patches/prplmesh/0015-nl80211-preserve-candidate-transaction-identity.patch'
    subprocess.run(['git', 'apply', str(patch)], cwd=tmp_path, check=True, capture_output=True)
    result = subprocess.run([sys.executable, str(root / 'tests/candidate-transport-test.py'), str(source)],
                            check=True, text=True, capture_output=True, timeout=45)
    assert result.stdout.count('PASS ') == 14
