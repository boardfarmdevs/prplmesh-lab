import os
from pathlib import Path
import re
import subprocess

import pytest

from optimizer.load_capture import PrplBrokerDecoder


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0032-size-metrics-messages-for-client-pool.patch"


def test_native_and_observer_limits_match():
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True,
                   capture_output=True, text=True)
    capacities = re.findall(r"^\+\s*(?:MESSAGE_BUFFER_LENGTH|static constexpr uint32_t kMaxFrameLength)"
                            r"\s*=\s*(\d+)", PATCH.read_text(), re.MULTILINE)
    assert [int(value) for value in capacities] == [PrplBrokerDecoder.MAX_MESSAGE_SIZE] * 2
    assert 8192 < PrplBrokerDecoder.MAX_MESSAGE_SIZE < 65536


def test_production_tlvf_full_roster(tmp_path):
    install = os.environ.get("PRPL_NATIVE_INSTALL")
    if not install:
        pytest.skip("set PRPL_NATIVE_INSTALL to a built native install for TLVF round trips")
    install = Path(install)
    binary = tmp_path / "native-ap-metrics-capacity"
    subprocess.run([
        os.environ.get("CXX", "c++"), "-std=c++17",
        str(ROOT / "tests/native-ap-metrics-capacity.cpp"),
        f"-I{install / 'include'}", f"-L{install / 'lib'}",
        f"-Wl,-rpath,{install / 'lib'}", "-ltlvf", "-lelpp", "-o", str(binary),
    ], check=True, timeout=60)
    subprocess.run([str(binary)], check=True, timeout=30)
