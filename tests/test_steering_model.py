import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
NETWORK = "Device.WiFi.DataElements.Network"
STATION = NETWORK + ".Device.5.Radio.2.BSS.1.STA.1."
BSS = NETWORK + ".Device.5.Radio.2.BSS.1."
MAC = "02:00:00:10:02:00"
BSSID = "02:00:00:00:0d:00"


@unittest.skipUnless(shutil.which("jq"), "jq is required by the lab scripts")
class SteeringModelTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="prpl-steering-model-")
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)
        source = (ROOT / "scripts/test-steering.sh").read_text()
        self.functions = "\n".join(re.search(
            rf"^{name}\(\)\n\{{\n.*?^\}}", source, re.M | re.S).group()
            for name in ("station_object", "model_bssid"))
        self.calls = self.work / "calls"
        self.stations = {STATION: {"MACAddress": MAC}}
        self.bsses = {BSS: {"BSSID": BSSID}}

    def query(self, *, native_error=0, exit_status=0, malformed=False):
        (self.work / "stations.json").write_text(
            "not json" if malformed else json.dumps(self.stations) + "\n{}\n"
            + json.dumps({"amxd-error-code": native_error}))
        (self.work / "bss.json").write_text(json.dumps(self.bsses) + "\n{}\n"
                                          + json.dumps({"amxd-error-code": 0}))
        script = r'''
set -euo pipefail
CONTROLLER=prpl-controller
lxc()
{
    printf '%s\n' "$*" >> calls
    case "$*" in
        *'Device.*.Radio.*.BSS.*.STA.'*) cat stations.json ;;
        *) cat bss.json ;;
    esac
    return "$QUERY_STATUS"
}
''' + self.functions + f'\nmodel_bssid "{MAC}"'
        return subprocess.run(["bash", "-c", f"QUERY_STATUS={exit_status}\n" + script],
                              cwd=self.work, text=True, capture_output=True, timeout=5)

    def test_hundred_clients_use_two_native_calls(self):
        self.stations.update({NETWORK + f".Device.1.Radio.1.BSS.1.STA.{index}.":
                              {"MACAddress": f"02:00:00:20:{index:02x}:00"}
                              for index in range(1, 100)})
        result = self.query()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), BSSID)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("--mode non-interactive" in call and "timeout -k 1 8" in call
                            for call in calls))
        self.assertNotIn("_get_instances", calls[0])
        self.assertTrue(all(f"ubus call {NETWORK} _get" in call for call in calls))
        self.assertIn('"rel_path":"Device.5.Radio.2.BSS.1."', calls[1])

    def test_missing_or_duplicate_station_fails_closed(self):
        for stations in ({}, {**self.stations, NETWORK + ".Device.1.Radio.1.BSS.1.STA.2.":
                             {"MACAddress": MAC}}):
            with self.subTest(stations=len(stations)):
                self.stations = stations
                result = self.query()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_native_error_and_transport_failure_fail_closed(self):
        for arguments in ({"native_error": 5}, {"exit_status": 124}, {"malformed": True}):
            with self.subTest(arguments=arguments):
                result = self.query(**arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_missing_bssid_fails_closed(self):
        self.bsses = {BSS: {}}
        result = self.query()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_non_station_mac_is_not_ownership(self):
        self.stations = {BSS: {"MACAddress": MAC}}
        self.assertNotEqual(self.query().returncode, 0)


if __name__ == "__main__":
    unittest.main()
