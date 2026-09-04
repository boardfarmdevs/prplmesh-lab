from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from room_demo.events import EventStore
from room_demo.server import RoomDemoServer


class ServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "index.html").write_text("<html>viewer</html>")
        (root / "vendor").mkdir()
        (root / "vendor" / "three.min.js").write_text("window.THREE={};")
        world = {
            "schema": "wmdcfg.world-plan.v1",
            "name": "test-world",
            "duration_ms": 1000,
            "tick_ms": 100,
        }
        self.store = EventStore("run-1", world, root / "events.jsonl")
        self.server = RoomDemoServer(("127.0.0.1", 0), self.store, root)
        self.server.start()
        self.addCleanup(self.server.close)
        self.base = f"http://127.0.0.1:{self.server.address[1]}"

    def _json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=2) as response:
            return json.load(response)

    def test_health_current_world_and_viewer(self):
        self.assertEqual(self._json("/healthz")["status"], "ok")
        self.assertEqual(self._json("/api/demo/current")["state"], "preparing")
        self.assertEqual(self._json("/api/demo/world")["name"], "test-world")
        with urllib.request.urlopen(self.base + "/viewer/?mode=live", timeout=2) as response:
            self.assertIn(b"viewer", response.read())
        with urllib.request.urlopen(
            self.base + "/viewer/vendor/three.min.js", timeout=2
        ) as response:
            self.assertIn(b"THREE", response.read())

    def test_post_is_not_a_control_surface(self):
        request = urllib.request.Request(self.base + "/api/demo/current", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 405)

    def test_sse_replays_an_ordered_event(self):
        self.store.publish({
            "schema": "easymesh.room-demo.event.v1",
            "run_id": "run-1",
            "sequence": 1,
            "recorded_at": "2026-09-03T00:00:00+00:00",
            "world_time_ms": 100,
            "kind": "scenario.clock",
            "payload": {},
        })
        with urllib.request.urlopen(self.base + "/api/demo/events?after=0", timeout=2) as response:
            self.assertEqual(response.readline().decode().strip(), "id: 1")
            data = response.readline().decode().strip()
        self.assertTrue(data.startswith("data: "))
        self.assertEqual(json.loads(data[6:])["kind"], "scenario.clock")

    def test_events_json_supports_browser_replay(self):
        self.store.emit("scenario.clock", 100, producer="wmdcfg")
        payload = self._json("/api/demo/events.json")
        self.assertEqual(payload["schema"], "easymesh.room-demo.events.v1")
        self.assertEqual(payload["events"][0]["kind"], "scenario.clock")


if __name__ == "__main__":
    unittest.main()
