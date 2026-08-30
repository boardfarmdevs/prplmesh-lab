import importlib.util
import unittest
from pathlib import Path


PATH = Path(__file__).parents[1] / "scripts" / "kernel-medium-aliases.py"
SPEC = importlib.util.spec_from_file_location("kernel_medium_aliases", PATH)
ALIASES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ALIASES)


class KernelMediumAliasesTests(unittest.TestCase):
    def setUp(self):
        self.aliases = ALIASES.build(4, 20, 3)["aliases"]

    def test_mesh_bsses_resolve_to_transmit_radio(self):
        self.assertEqual(
            self.aliases["02:00:00:00:07:02"],
            "42:00:00:00:07:00",
        )

    def test_agent_backhaul_sta_resolves_to_five_ghz_radio(self):
        self.assertEqual(
            self.aliases["02:00:00:30:02:00"],
            "42:00:00:00:07:00",
        )

    def test_interleaved_client_cohorts_resolve_to_assigned_radios(self):
        self.assertEqual(
            self.aliases["02:00:00:10:04:00"],
            "42:00:00:00:15:00",
        )
        self.assertEqual(
            self.aliases["02:00:00:20:04:00"],
            "42:00:00:00:16:00",
        )


if __name__ == "__main__":
    unittest.main()
