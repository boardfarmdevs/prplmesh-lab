import unittest

from room_demo.topology import project_topology


class PrplMeshTopologyTests(unittest.TestCase):
    def test_backhaul_uses_observed_parent_and_bssid_bound_roles(self):
        topology = {"devices": [
            {"id": "AA:00", "name": "controller", "radios": [
                {"bsses": [{"bssid": "BB:00"}]}]},
            {"id": "AA:01", "name": "discovery-order-not-a-role", "radios": [
                {"bsses": [{"bssid": "BB:01"}]}],
             "backhaul": {"parent_id": "AA:00", "type": "Wi-Fi", "mac": "CC:01"}},
        ]}
        projected = project_topology(topology, {"bb:00": "gateway", "bb:01": "extender_4"})
        self.assertEqual(projected["source"], "prplmesh_nbapi")
        self.assertEqual(projected["unresolved_edges"], 0)
        edge = projected["backhaul_edges"][0]
        self.assertEqual(edge["parent_role"], "gateway")
        self.assertEqual(edge["child_role"], "extender_4")
        self.assertEqual(edge["signal"], {})
        self.assertIsNone(edge["band"])

    def test_absent_or_unresolved_topology_is_not_invented(self):
        self.assertFalse(project_topology(None, {})["available"])
        projected = project_topology({"devices": [
            {"id": "child", "backhaul": {"parent_id": "unknown"}}
        ]}, {})
        self.assertEqual(projected["backhaul_edges"], [])
        self.assertEqual(projected["unresolved_edges"], 1)
