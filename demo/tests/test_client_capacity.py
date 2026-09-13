from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from room_demo.engine import RoomEngine
from room_demo.events import EventStore
from room_demo.interactions import InteractiveMediumSession
from room_demo.pool import bind_client_pool, expand_initial_world
from room_demo.worlds import BoundWorlds
from wmdcfg.model import ScenarioError
from wmdcfg.world import load_json

from test_interactions import FakeClient


ROOT = Path(__file__).resolve().parents[2] / "wmediumd/configurator/worlds"


class CapacityClient(FakeClient):
    def _status(self):
        return replace(super()._status(), max_updates=10000)


class ClientCapacityTests(unittest.TestCase):
    def setUp(self):
        self.world = load_json(ROOT / "golden/home-a-private-client-room-walk.world.json")
        self.layout = load_json(ROOT / "layouts/home-five-agent.json")
        self.roles = {**self.world["roles"],
                      **{f"sta_pool_{ordinal:03d}": "station" for ordinal in range(21, 101)}}

    def test_expansion_preserves_default_and_signed_input(self):
        original = copy.deepcopy(self.world)
        expanded = expand_initial_world(self.world, self.roles)
        self.assertEqual(self.world, original)
        self.assertEqual(len(expanded["roles"]), 105)
        first = expanded["generations"][0]
        self.assertEqual(sum(first["present"][role] for role, kind in self.roles.items()
                             if kind == "station"), 20)
        self.assertFalse(first["present"]["sta_pool_100"])

    def test_binding_pool_is_bounded_unique_and_deterministic(self):
        station_roles = [role for role, kind in self.world["roles"].items() if kind == "station"]
        initial = {"roles": dict(zip(station_roles, (f"client-{ordinal:03d}"
                                                   for ordinal in range(1, 21))))}
        initial["roles"].update({role: role for role, kind in self.world["roles"].items()
                                 if kind == "fronthaul_ap"})
        radios = [{"container": f"client-{ordinal:03d}", "kind": "station"}
                  for ordinal in range(1, 101)]
        bound = bind_client_pool(self.world, initial, {"radios": list(reversed(radios))})
        self.assertEqual(len(bound["roles"]), 105)
        self.assertEqual(bound["roles"]["sta_pool_100"], "client-100")
        self.assertEqual(len(initial["roles"]), 25)
        with self.assertRaises(ScenarioError):
            bind_client_pool(self.world, initial, {"radios": radios + [radios[0]]})
        with self.assertRaises(ScenarioError):
            bind_client_pool(self.world, initial, {"radios": radios + [
                {"container": "client-101", "kind": "station"}]})

    def test_default_twenty_to_fifty_and_back_uses_one_captured_pool(self):
        worlds = BoundWorlds(self.world, self.layout, ROOT, roles=self.roles)
        self.assertEqual(len(worlds.catalog()["worlds"]), 18)
        bindings = {}
        for ordinal, (role, kind) in enumerate(sorted(self.roles.items()), 1):
            bindings[role] = {"role_type": kind, "radio_tx_mac": f"02:00:00:{ordinal:02x}:00:00"}
            if kind == "fronthaul_ap":
                bindings[role]["fronthaul_frequencies_mhz"] = {"2.4": 2412, "5": 5180, "6": 5955}
                bindings[role]["band_radios"] = {
                    band: {"tx_mac": f"02:00:00:{ordinal:02x}:00:{index:02x}"}
                    for index, band in enumerate(("2.4", "5", "6"), 1)}
        disconnected = []
        reconnected = []

        @contextmanager
        def disconnect(role):
            disconnected.append(role)
            yield

        with tempfile.TemporaryDirectory() as directory:
            store = EventStore("capacity", self.world, Path(directory) / "events.jsonl")
            self.addCleanup(store.close)
            client = CapacityClient("unused")
            session = InteractiveMediumSession(
                store, self.world, self.layout, {"bindings": bindings}, "unused",
                client_factory=lambda _: client, worlds=worlds,
                disconnect_client=disconnect, reconnect_client=reconnected.append,
            )
            engine = RoomEngine(session)
            self.addCleanup(engine.close)
            engine.start()
            snapshot = engine.snapshot()
            self.assertEqual(snapshot["pool_clients"], 100)
            self.assertEqual(snapshot["expected_online_clients"], 20)
            self.assertEqual(len(disconnected), 80)
            captured = set(session._baseline)
            token = engine.acquire("capacity-test", command_id="pool-lease")["token"]
            result = engine.apply_world(
                "fifty-client-counter-roam", token=token,
                expected_revision=engine.snapshot()["revision"], command_id="pool-fifty")
            self.assertEqual(result["expected_online_clients"], 50)
            self.assertEqual(set(session._baseline), captured)
            self.assertEqual(engine.snapshot()["pool_clients"], 100)
            result = engine.apply_world(
                "default", token=token, expected_revision=engine.snapshot()["revision"],
                command_id="pool-default")
            self.assertEqual(result["expected_online_clients"], 20)
            self.assertEqual(len(bindings), 105)
            self.assertTrue(engine.close())
            self.assertTrue(all(not overridden for value, overridden in client.values.values()))


if __name__ == "__main__":
    unittest.main()
