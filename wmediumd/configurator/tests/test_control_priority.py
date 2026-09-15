import unittest

from wmdcfg.control_priority import OWNER, TABLE, transaction


class ControlPriorityTests(unittest.TestCase):
    def test_only_native_control_frames_are_classified_without_drop_or_shaping(self):
        script = transaction({}, True)
        self.assertIn('ether type 0x893a counter meta priority set 0x00000107', script)
        self.assertIn('hook forward priority -150; policy accept;', script)
        self.assertNotIn('drop', script)
        self.assertNotIn('limit', script)
        self.assertNotIn('flush ruleset', script)

    def test_owned_update_is_one_delete_and_recreate_transaction(self):
        existing = {"nftables": [{"table": {"family": "bridge", "name": TABLE, "comment": OWNER}}]}
        script = transaction(existing, True)
        self.assertTrue(script.startswith(f"delete table bridge {TABLE}\nadd table bridge {TABLE}"))
        self.assertEqual(transaction(existing, False), f"delete table bridge {TABLE}\n")

    def test_disable_without_our_table_leaves_other_firewall_tables_alone(self):
        existing = {"nftables": [{"table": {"family": "inet", "name": "firewall"}}]}
        self.assertEqual(transaction(existing, False), "")

    def test_unowned_collision_is_never_replaced_or_removed(self):
        for enable in (False, True):
            with self.assertRaisesRegex(RuntimeError, "unowned"):
                transaction({"nftables": [{"table": {"family": "bridge", "name": TABLE}}]}, enable)
