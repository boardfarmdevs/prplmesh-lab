import unittest
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class SnapshotProjectionTests(unittest.TestCase):
    def test_projection_uses_one_native_snapshot(self):
        device = server.ROOT + ".Device.1"
        radio = device + ".Radio.1"
        bss = radio + ".BSS.1"
        objects = {
            device + ".": {"ID": "02:00:00:27:01:01"},
            radio + ".": {"ID": "02:00:00:00:01:00"},
            radio + ".CurrentOperatingClassProfile.1.": {"Class": 115, "Channel": 36},
            bss + ".": {"BSSID": "02:00:00:00:01:00", "SSID": "private_ssid", "FronthaulUse": True},
            bss + ".STA.1.": {"MACAddress": "02:00:00:10:01:00", "SignalStrength": 122,
                                "TimeStamp": "2026-09-08T00:00:00Z"},
        }
        with patch.object(server, "ubus", return_value=objects) as native:
            value = server.topology()
        native.assert_called_once_with(server.ROOT, "_get", {"rel_path": "", "depth": 10})
        self.assertEqual(len(value["devices"]), 1)
        observed = value["devices"][0]["radios"][0]["bsses"][0]["clients"][0]
        self.assertEqual(observed["signal_raw"], 122)
        self.assertEqual(observed["signal_updated_at"], "2026-09-08T00:00:00Z")


class StableDeviceNameTests(unittest.TestCase):
    def test_controller_name_is_role_based(self):
        self.assertEqual(
            server.device_name("02:00:00:27:01:01", "controller", 9),
            "controller",
        )

    def test_agent_name_comes_from_provisioned_al_mac(self):
        self.assertEqual(
            server.device_name("02:00:00:27:05:01", "agent", 1),
            "agent-4",
        )

    def test_unmanaged_identity_uses_bounded_fallback(self):
        self.assertEqual(
            server.device_name("aa:bb:cc:dd:ee:ff", "agent", 3),
            "agent-3",
        )


class InternalAdapterSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def request(self, path):
        return urllib.request.urlopen(
            f"http://127.0.0.1:{self.httpd.server_port}{path}", timeout=2
        )

    def test_health_is_the_only_non_topology_surface(self):
        with self.request("/health") as response:
            self.assertEqual(json.load(response), {"status": "ok"})

    def test_obsolete_topology_page_is_not_served(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/")
        self.assertEqual(error.exception.code, 404)

if __name__ == "__main__":
    unittest.main()
