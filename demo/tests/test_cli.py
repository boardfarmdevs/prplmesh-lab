from __future__ import annotations

import unittest

from room_demo.cli import parser


class CliDefaultsTests(unittest.TestCase):
    def test_check_uses_prplmesh_control_socket(self):
        args = parser().parse_args(["check"])
        self.assertEqual(args.socket, "/run/prpl-wmediumd/control.sock")


if __name__ == "__main__":
    unittest.main()
