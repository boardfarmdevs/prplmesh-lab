from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from room_demo.events import EventStore


WORLD = {"name": "test-world", "duration_ms": 1000, "tick_ms": 100}


def event(sequence: int, kind: str, **payload):
    return {
        "schema": "easymesh.room-demo.event.v1",
        "run_id": "run-1",
        "sequence": sequence,
        "recorded_at": "2026-09-03T00:00:00+00:00",
        "world_time_ms": min(sequence * 100, 1000),
        "kind": kind,
        "payload": payload,
    }


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "live-events.jsonl"
        self.store = EventStore("run-1", WORLD, self.path)

    def test_state_follows_runner_and_persists_events(self):
        self.store.publish(event(1, "runner.preflight", health={}))
        self.store.publish(event(2, "scenario.started"))
        self.store.publish(event(3, "rf.restore.completed", verified=True))
        self.store.publish(event(4, "scenario.completed", outcome="passed",
                                 restored=True, error=None, run_directory="/tmp/run-1"))
        current = self.store.current()
        self.assertEqual(current["state"], "passed")
        self.assertTrue(current["restored"])
        self.assertEqual(current["sequence"], 4)
        self.assertEqual(len(self.path.read_text().splitlines()), 4)

    def test_replay_is_strictly_after_sequence(self):
        self.store.publish(event(1, "scenario.started"))
        self.store.publish(event(2, "scenario.clock"))
        self.assertEqual([item["sequence"] for item in self.store.after(1)], [2])

    def test_rejects_out_of_order_event(self):
        self.store.publish(event(1, "scenario.started"))
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            self.store.publish(event(1, "scenario.clock"))

    def test_multiple_producers_are_centrally_sequenced(self):
        first = self.store.ingest(event(80, "scenario.clock"))
        second = self.store.emit(
            "network.snapshot", 100, {"clients": []}, producer="network"
        )
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(first["payload"]["producer_sequence"], 80)
        self.assertEqual(second["sequence"], 2)
        self.assertEqual(self.store.current()["latest"]["network.snapshot"], second)

    def test_completed_evidence_can_be_loaded_without_rewriting_it(self):
        self.store.publish(event(1, "scenario.started"))
        run_dir = self.path.parent
        (run_dir / "world.json").write_text(__import__("json").dumps(WORLD))
        before = self.path.read_text()
        loaded = EventStore.from_evidence(run_dir)
        self.assertEqual(loaded.all()[0]["kind"], "scenario.started")
        self.assertEqual(self.path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
