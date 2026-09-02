import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests" / "optimizer-profile-scenario.py"
SPEC = importlib.util.spec_from_file_location("optimizer_profile_scenario", HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "clients, expected",
    ((10, 90), (20, 120), (50, 300), (100, 600)),
)
def test_hold_scales_with_serialized_profile_collection(clients, expected):
    assert MODULE.hold_seconds(clients) == expected


def test_render_changes_only_the_destination_hold_duration():
    source = """scenario sample {
    phase baseline for 10s {
        hold
    }
    phase destination_hold for 90s {
        hold
    }
}
"""
    assert MODULE.render(source, 50) == """scenario sample {
    phase baseline for 10s {
        hold
    }
    phase destination_hold for 300s {
        hold
    }
}
"""


@pytest.mark.parametrize(
    "source",
    (
        "scenario sample { phase baseline for 10s { hold } }",
        """phase destination_hold for 90s { hold }
phase destination_hold for 90s { hold }
""",
    ),
)
def test_render_rejects_missing_or_ambiguous_hold(source):
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.render(source, 20)


def test_non_positive_profile_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        MODULE.hold_seconds(0)
