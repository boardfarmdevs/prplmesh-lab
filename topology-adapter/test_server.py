import unittest
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import server


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
