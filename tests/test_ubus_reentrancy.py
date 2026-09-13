from pathlib import Path
import hashlib
import os
import subprocess
import sys

import pytest


def test_assembled_ubus_dispatch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fixture = (root / 'tests/fixtures/ubus-message-dispatch.c').read_text()
    message, dispatch = fixture.split('void __hidden ubus_handle_data(', 1)
    (tmp_path / 'libubus.c').write_text(message)
    (tmp_path / 'libubus-io.c').write_text('void __hidden ubus_handle_data(' + dispatch)
    command = [sys.executable, str(root / 'tests/ubus-reentrancy-test.py'), str(tmp_path)]
    baseline = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert baseline.returncode != 0 and 'processed[message->hdr.seq] == 1' in baseline.stderr
    patch = root / 'patches/ubus/0001-libubus-guard-reentrant-message-dispatch.patch'
    subprocess.run(['git', 'apply', str(patch)], cwd=tmp_path, check=True, capture_output=True)
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    assert result.stdout.count('PASS ') == 5


def test_ubus_build_and_provenance():
    root = Path(__file__).resolve().parents[1]
    assert 'patches/ubus/*.patch' in (root / 'scripts/build-prplmesh.sh').read_text()
    assert '/root/ubus-patches/*.patch' in (root / 'scripts/container/build-inside.sh').read_text()
    assert 'UBUS_PATCHSET_SHA256=' in (root / 'scripts/package-build-artifacts.sh').read_text()
    assert 'usr/share/prplmesh-lab/ubus-provenance.env' in (root / 'scripts/container/package-artifacts-inside.sh').read_text()
    startup = (root / 'scripts/container/setup-nl80211-node.sh').read_text()
    assert startup.index('pkill -x ubusd') < startup.index('tar --unlink-first -C /')
    assert startup.index('tar --unlink-first -C /') < startup.index('/usr/sbin/ubusd >')
    acceptance = (root / 'tests/run-acceptance.sh').read_text()
    assert 'EXPECTED_UBUS_PATCHSET="$expected_ubus_patchset"' in acceptance
    assert 'UBUS_LIBRARY_SHA256=${digest%% *}' in acceptance


@pytest.mark.parametrize('fault', ['', 'patchset', 'library', 'missing'])
def test_ubus_packaging_rejects_stale_provenance(tmp_path, fault):
    root = Path(__file__).resolve().parents[1]
    package = (root / 'scripts/container/package-artifacts-inside.sh').read_text()
    guard = package[package.index('ubus_provenance='):package.index('HOSTAP_COMMIT="$HOSTAP_COMMIT"')]
    library = tmp_path / 'libubus.so'
    library.write_bytes(b'qualified dependency fixture')
    provenance = tmp_path / 'ubus-provenance.env'
    if fault != 'missing':
        provenance.write_text('UBUS_COMMIT=13a4438b4ebdf85d301999e0a615640ac4c9b0a8\n'
                              f'UBUS_PATCHSET_SHA256={"old" if fault == "patchset" else "expected"}\n'
                              f'UBUS_LIBRARY_SHA256={hashlib.sha256(library.read_bytes()).hexdigest()}\n')
    if fault == 'library':
        library.write_bytes(b'older installed library')
    guard = guard.replace('/usr/share/prplmesh-lab/ubus-provenance.env', str(provenance))
    guard = guard.replace('/usr/lib/libubus.so', str(library))
    result = subprocess.run(['bash', '-eu', '-c', guard], capture_output=True,
                            env=dict(os.environ, UBUS_PATCHSET_SHA256='expected'))
    assert (result.returncode == 0) == (not fault)
