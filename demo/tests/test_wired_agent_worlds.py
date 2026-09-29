"""The lab's own rooms with its Agent on a wired backhaul (extender_5: prpl-agent-05,
worlds-wired): selected by its manifest alone, the native rooms unchanged, and the
rooms about the wired Agent itself."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest

from room_demo.worlds import BoundWorlds
from wmdcfg.world import load_json

REPO = Path(__file__).resolve().parents[2]
CONFIGURATOR = REPO / "wmediumd/configurator"
NATIVE = CONFIGURATOR / "worlds"
WIRED = CONFIGURATOR / "worlds-wired"
MANIFEST = REPO / "demo/manifests/private-client-room-walk-wired.json"
WIRED_ONLY = {"home-a-wired-walk-in", "home-a-wired-walk-out", "home-a-wired-extender-loss-recovery",
              "backhaul-wired-parent"}


def catalog(root):
    world = load_json(root / "golden/home-a-private-client-room-walk.world.json")
    return BoundWorlds(world, load_json(root / "layouts" / f"{world['layout']}.json"), root).catalog()


class WiredAgentWorldTests(unittest.TestCase):
    def test_the_manifest_names_its_world_bindings_and_worlds_root(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(REPO / manifest["worlds_root"], WIRED)
        world = load_json(REPO / manifest["world"])
        bindings = json.loads((REPO / manifest["bindings"]).read_text())["roles"]
        self.assertTrue(set(world["roles"]) <= set(bindings))
        self.assertEqual(bindings["extender_5"], "prpl-agent-05")
        self.assertEqual(world["wired_backhaul"], ["extender_5"])

    def test_every_mirrored_room_is_the_native_room_plus_the_wired_agent(self):
        for path in sorted((WIRED / "golden").glob("*.world.json")):
            if path.name.removesuffix(".world.json") in WIRED_ONLY:
                continue
            wired, native = load_json(path), load_json(NATIVE / "golden" / path.name)
            self.assertEqual(set(wired["roles"]) - set(native["roles"]), {"extender_5"}, path.name)
            self.assertEqual(wired["mobility"], native["mobility"], path.name)

    def test_a_room_bound_with_it_offers_the_native_rooms_and_its_own(self):
        wired, native = catalog(WIRED), catalog(NATIVE)
        self.assertEqual(sorted(entry["id"] for entry in wired["worlds"]),
                         sorted([entry["id"] for entry in native["worlds"]] + list(WIRED_ONLY)))
        self.assertEqual(wired["mesh_devices"], native["mesh_devices"] + 1)
        self.assertEqual(wired["worlds_root"], "wmediumd/configurator/worlds-wired")

    def test_the_goldens_match_their_layouts_and_positions(self):
        result = subprocess.run([sys.executable, str(WIRED / "build-goldens.py"), "--check"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
