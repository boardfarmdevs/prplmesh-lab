import unittest

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


if __name__ == "__main__":
    unittest.main()
