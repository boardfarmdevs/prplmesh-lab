from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "name", ("hostapd-wlan0.conf", "hostapd-wlan2.conf", "hostapd-wlan4.conf")
)
def test_every_lab_bss_has_stress_profile_inactivity_margin(name):
    text = (ROOT / "manifests" / name).read_text(encoding="utf-8")
    blocks = text.split("\nbss=")
    assert len(blocks) == 3
    assert all(block.count("ap_max_inactivity=1200") == 1 for block in blocks)


def test_inactivity_margin_exceeds_longest_optimizer_profile_hold():
    helper = (ROOT / "tests" / "optimizer-profile-scenario.py").read_text(
        encoding="utf-8"
    )
    assert "max(90, 6 * client_count)" in helper
    assert 1200 > 6 * 100
