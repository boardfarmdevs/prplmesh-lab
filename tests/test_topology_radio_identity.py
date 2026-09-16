import copy
import importlib.util
import itertools
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "topology_acceptance", Path(__file__).with_name("topology-acceptance.py"))
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)


def radios():
    return [{"id": f"02:00:00:00:{6 + offset:02x}:00", "band": band,
             "bsses": [{"ssid": ssid} for ssid in ("private_ssid", "iot_ssid", "mesh_backhaul")]}
            for offset, band in enumerate(("2.4 GHz", "5 GHz", "6 GHz"))]


def test_registration_order_does_not_change_radio_identity():
    for order in itertools.permutations(radios()):
        ACCEPTANCE.validate_radio_inventory(2, order)


@pytest.mark.parametrize("change", ["missing", "duplicate", "band", "id", "ssid"])
def test_inventory_still_rejects_missing_or_wrong_radios(change):
    inventory = copy.deepcopy(radios())
    if change == "missing":
        inventory.pop()
    elif change == "duplicate":
        inventory[1] = inventory[0]
    elif change == "band":
        inventory[1]["band"] = "2.4 GHz"
    elif change == "id":
        inventory[1]["id"] = inventory[0]["id"]
    else:
        inventory[1]["bsses"].pop()
    with pytest.raises(AssertionError):
        ACCEPTANCE.validate_radio_inventory(2, inventory)
