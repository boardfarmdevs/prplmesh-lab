import importlib.util
import pathlib
import unittest


PATH = pathlib.Path(__file__).parents[1] / "scripts" / "generate-wmediumd-identity-inventory.py"
SPEC = importlib.util.spec_from_file_location("inventory", PATH)
inventory = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(inventory)


class IdentityInventoryTests(unittest.TestCase):
    def test_tri_band_nodes_and_client_cohorts_use_ui_names(self):
        document = inventory.build(radios=40, agents=4, clients=20, radios_per_node=3)
        stations = {entry["mac"]: entry for entry in document["stations"]}
        self.assertEqual(stations["42:00:00:00:00:00"]["label"], "Controller 2.4 GHz")
        self.assertEqual(stations["42:00:00:00:04:00"]["label"], "Extender-1 5 GHz")
        self.assertEqual(stations["42:00:00:00:0f:00"]["label"], "sta-01")
        self.assertEqual(stations["42:00:00:00:10:00"]["label"], "iot-01")
        self.assertEqual(stations["42:00:00:00:22:00"]["label"], "iot-10")
        self.assertEqual(stations["42:00:00:00:23:00"]["role"], "spare")

    def test_rejects_an_undersized_pool(self):
        with self.assertRaises(ValueError):
            inventory.build(radios=34, agents=4, clients=20, radios_per_node=3)


if __name__ == "__main__":
    unittest.main()
