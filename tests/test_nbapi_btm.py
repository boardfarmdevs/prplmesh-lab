import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NETWORK = "Device.WiFi.DataElements.Network"
STATION = NETWORK + ".Device.6.Radio.2.BSS.1.STA.2"
TARGET = "02:00:00:00:03:00"
pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="jq is required by the lab scripts")


def submit(tmp_path, reply='{}\n{}\n{"amxd-error-code":0}', status=0, station=STATION):
    request = {"DisassociationImminent": False, "DisassociationTimer": 0,
               "BSSTerminationDuration": 0, "ValidityInterval": 10,
               "SteeringTimer": 50, "TargetBSS": TARGET}
    command = r'''
set -euo pipefail
source "$1/scripts/lib/nbapi-btm.sh"
CONTROLLER=prpl-controller
lxc()
{
    printf '%s\n' "$@" >> calls
    if read -r line; then
        echo "native call inherited stdin" >&2
        return 99
    fi
    printf '%s' "$REPLY"
    return "$STATUS"
}
nbapi_btm_request "$2" "$3"
'''
    result = subprocess.run(["bash", "-c", command, "test", str(ROOT), station, json.dumps(request)],
                            cwd=tmp_path, input="do not forward\n", text=True, capture_output=True,
                            env={**os.environ, "REPLY": reply, "STATUS": str(status)}, timeout=5)
    calls = (tmp_path / "calls").read_text().splitlines() if (tmp_path / "calls").exists() else []
    return result, calls, request


def test_root_dispatch_does_not_require_station_bus_registration(tmp_path):
    result, calls, request = submit(tmp_path)
    assert result.returncode == 0, result.stderr
    assert calls[:-1] == ["exec", "--mode", "non-interactive", "prpl-controller", "--",
                          "timeout", "-k", "1", "8", "ubus", "-t", "5", "call", NETWORK, "_exec"]
    assert json.loads(calls[-1]) == {"rel_path": "Device.6.Radio.2.BSS.1.STA.2.MultiAPSTA.",
                                    "method": "BTMRequest", "args": request}


@pytest.mark.parametrize("reply", ["", "garbage", "{}", '{"amxd-error-code":4}',
                                  '{"amxd-error-code":false}', '{"amxd-error-code":"0"}',
                                  '{"amxd-error-code":0}\n{"amxd-error-code":4}',
                                  '{"amxd-error-code":0}\n{"amxd-error-code":0}',
                                  'null\n{"amxd-error-code":0}'])
def test_native_acknowledgement_required(tmp_path, reply):
    result, calls, _ = submit(tmp_path, reply=reply)
    assert result.returncode != 0
    assert calls.count("_exec") == 1


@pytest.mark.parametrize("status", [4, 7, 124])
def test_failure_or_timeout_is_not_retried(tmp_path, status):
    result, calls, _ = submit(tmp_path, status=status)
    assert result.returncode == status
    assert calls.count("_exec") == 1


@pytest.mark.parametrize("station", ["", NETWORK, STATION + ".MultiAPSTA", "Device.6.Radio.2"])
def test_invalid_station_path_does_not_submit(tmp_path, station):
    result, calls, _ = submit(tmp_path, station=station)
    assert result.returncode == 2
    assert not calls


def test_both_steering_entrypoints_use_checked_root_dispatch():
    for name in ("steer-client.sh", "test-steering.sh"):
        script = (ROOT / "scripts" / name).read_text()
        assert 'source "$ROOT/scripts/lib/nbapi-btm.sh"' in script
        assert 'nbapi_btm_request "$object" "$request"' in script
        assert 'ubus call "${object}.MultiAPSTA"' not in script
