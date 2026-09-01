#!/usr/bin/env python3
"""Regression checks for the VM acceptance stimulus selector."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "deploy/lxd-vm/select-optimizer-stimulus.py"


def mesh(name: str, ordinal: int) -> dict:
    return {
        "kind": "mesh",
        "container": name,
        "interfaces": [
            {"mac": f"02:00:00:00:{ordinal:02x}:00", "ssid": "private_ssid"},
            {"mac": f"02:00:00:00:{ordinal:02x}:01", "ssid": "iot_ssid"},
        ],
        "band_radios": {
            "5": {
                "interfaces": [
                    {
                        "mac": f"02:00:00:00:{ordinal:02x}:00",
                        "ssid": "private_ssid",
                    },
                    {
                        "mac": f"02:00:00:00:{ordinal:02x}:01",
                        "ssid": "iot_ssid",
                    },
                ]
            }
        },
    }


def station(name: str, bssid: str, ssid: str = "private_ssid") -> dict:
    return {
        "kind": "station",
        "container": name,
        "associated_bssid": bssid,
        "band": "5",
        "ssid": ssid,
    }


class SelectorTest(unittest.TestCase):
    def run_selector(self, radios: list[dict]) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as inventory:
            json.dump({"radios": radios}, inventory)
            inventory.flush()
            return subprocess.run(
                [str(SELECTOR), inventory.name, "prpl-agent-02"],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_selects_first_compatible_client_not_on_target(self) -> None:
        radios = [
            mesh("prpl-controller", 1),
            mesh("prpl-agent-02", 2),
            station("prpl-client-01", "02:00:00:00:02:00"),
            station("prpl-client-03", "02:00:00:00:01:00"),
            station("prpl-client-02", "02:00:00:00:01:00"),
        ]
        result = self.run_selector(radios)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "prpl-client-02 prpl-agent-02")

    def test_fails_when_all_compatible_clients_are_on_target(self) -> None:
        radios = [
            mesh("prpl-controller", 1),
            mesh("prpl-agent-02", 2),
            station("prpl-client-01", "02:00:00:00:02:00"),
            station("prpl-client-02", "02:00:00:00:02:01", "iot_ssid"),
        ]
        result = self.run_selector(radios)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no associated station outside prpl-agent-02", result.stderr)


if __name__ == "__main__":
    unittest.main()
