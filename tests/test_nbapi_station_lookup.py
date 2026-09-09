import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/lib/nbapi-station.py"
SPEC = importlib.util.spec_from_file_location("nbapi_station", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
STATION = "02:00:00:10:01:00"
OBJECT = "Device.WiFi.DataElements.Network.Device.1.Radio.1.BSS.1.STA.3."


def test_bulk_lookup_ignores_tables_and_accepts_ubus_status_trailer():
    payload = {OBJECT: {"MACAddress": STATION},
               OBJECT.rsplit("3.", 1)[0]: {}, "unrelated": {"MACAddress": STATION}}
    assert MODULE.station_object(json.dumps(payload) + "\n0\n", STATION.upper()) == OBJECT.rstrip(".")


@pytest.mark.parametrize("payload", [{}, {OBJECT: {"MACAddress": STATION},
    OBJECT.replace("STA.3.", "STA.4."): {"MACAddress": STATION}}])
def test_missing_or_duplicate_native_ownership_fails_closed(payload):
    with pytest.raises(ValueError, match="expected one NBAPI owner"):
        MODULE.station_object(json.dumps(payload), STATION)
