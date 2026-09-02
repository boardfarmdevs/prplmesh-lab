import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[2] / "tests" / "topology-acceptance.py"
SPEC = importlib.util.spec_from_file_location("topology_acceptance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TopologyAcceptanceTest(unittest.TestCase):
    def test_ap_interface_maps_lab_bss(self):
        cases = [
            ("2.4 GHz", "private_ssid", "wlan0"),
            ("2.4 GHz", "iot_ssid", "wlan0.0"),
            ("5 GHz", "private_ssid", "wlan2"),
            ("5 GHz", "iot_ssid", "wlan2.0"),
            ("6 GHz", "private_ssid", "wlan4"),
            ("6 GHz", "iot_ssid", "wlan4.0"),
        ]
        for band, ssid, expected in cases:
            with self.subTest(band=band, ssid=ssid):
                self.assertEqual(MODULE.ap_interface(band, ssid), expected)

    def test_ap_interface_rejects_unknown_bss(self):
        with self.assertRaisesRegex(ValueError, "unsupported AP band/SSID"):
            MODULE.ap_interface("6 GHz", "mesh_backhaul")

    def test_parse_ap_stations_accepts_exact_station_rows(self):
        output = """Station 02:00:00:10:06:00 (on wlan4)
\tinactive time:\t10 ms
Station 02:00:00:20:04:00 (on wlan4.0)
\tsignal:\t-51 dBm
"""
        self.assertEqual(
            MODULE.parse_ap_stations(output),
            {"02:00:00:10:06:00", "02:00:00:20:04:00"},
        )

    def test_parse_ap_stations_rejects_stale_supplicant_text(self):
        output = (
            "Connected to 02:00:00:00:08:00 (on wlan0)\n"
            "wpa_state=COMPLETED\n"
        )
        self.assertEqual(MODULE.parse_ap_stations(output), set())


if __name__ == "__main__":
    unittest.main()
