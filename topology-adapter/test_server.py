import unittest
import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import patch

import server


class SnapshotProjectionTests(unittest.TestCase):
    def test_only_inflight_reads_are_shared_and_failures_are_not_cached(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                started, release = threading.Event(), threading.Event()
                waiting = threading.Barrier(3, timeout=2)
                pending = Future()
                result = pending.result
                calls = []

                def collect():
                    calls.append(True)
                    started.set()
                    if not release.wait(2):
                        raise TimeoutError("test collection was not released")
                    if failed and len(calls) == 1:
                        raise OSError("native unavailable")
                    return {"generation": len(calls)}

                def wait_for_result():
                    if not pending.done():
                        waiting.wait()
                    return result(timeout=2)

                reader = server.TopologyReader(collect)
                with ThreadPoolExecutor(max_workers=3) as executor:
                    with patch.object(server, "Future", return_value=pending), \
                         patch.object(pending, "result", side_effect=wait_for_result):
                        leader = executor.submit(reader.read)
                        self.assertTrue(started.wait(2))
                        followers = [executor.submit(reader.read) for index in range(2)]
                        waiting.wait()
                        release.set()
                        for request in [leader, *followers]:
                            if failed:
                                with self.assertRaisesRegex(OSError, "native unavailable"):
                                    request.result(timeout=2)
                            else:
                                self.assertEqual(request.result(timeout=2), {"generation": 1})
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(reader.read(), {"generation": 2})

    def test_projection_uses_bounded_device_snapshot(self):
        device = server.ROOT + ".Device.1"
        radio = device + ".Radio.1"
        bss = radio + ".BSS.1"
        objects = {
            server.ROOT + ".": {"ControllerID": "02:00:00:27:01:01"},
            device + ".": {"ID": "02:00:00:27:01:01"},
            device + ".MultiAPDevice.Backhaul.": {"MACAddress": "02:00:00:30:01:00"},
            device + ".MultiAPDevice.Backhaul.Stats.": {"SignalStrength": 86,
                                                      "TimeStamp": "2026-09-08T00:00:00Z"},
            radio + ".": {"ID": "02:00:00:00:01:00"},
            radio + ".CurrentOperatingClassProfile.1.": {"Class": 115, "Channel": 36},
            bss + ".": {"BSSID": "02:00:00:00:01:00", "SSID": "private_ssid", "FronthaulUse": True},
            bss + ".STA.1.": {"MACAddress": "02:00:00:10:01:00", "SignalStrength": 122,
                                "TimeStamp": "2026-09-08T00:00:00Z"},
        }
        with patch.object(server, "instances", return_value=[device]), patch.object(server, "ubus", return_value=objects) as native:
            value = server.topology()
        self.assertEqual(native.call_count, 3)
        native.assert_any_call(server.ROOT, "_get", {"rel_path": "", "depth": 0})
        native.assert_any_call(server.ROOT, "_get", {"rel_path": "Device.1.", "depth": 4})
        self.assertTrue(all(call.args[0] == server.ROOT for call in native.call_args_list))
        native.assert_any_call(server.ROOT, "_get", {"rel_path": "Device.*.Radio.*.BSS.*.STA.", "depth": 1})
        self.assertEqual(len(value["devices"]), 1)
        backhaul = value["devices"][0]["backhaul"]
        self.assertEqual(backhaul["station_mac"], "02:00:00:30:01:00")
        self.assertEqual(backhaul["signal_dbm"], -67)
        self.assertEqual(backhaul["signal_updated_at"], "2026-09-08T00:00:00Z")
        self.assertIsNone(server.rcpi_dbm(True))
        observed = value["devices"][0]["radios"][0]["bsses"][0]["clients"][0]
        self.assertEqual(observed["signal_raw"], 122)
        self.assertEqual(observed["signal_updated_at"], "2026-09-08T00:00:00Z")

    def test_device_reads_overlap_and_merge(self):
        devices = [server.ROOT + f".Device.{number}" for number in range(1, 6)]
        barrier = threading.Barrier(len(devices), timeout=2)

        def read_device(path, method, arguments):
            self.assertEqual(path, server.ROOT)
            self.assertEqual(method, "_get")
            if arguments["rel_path"] == "":
                return {server.ROOT + ".": {"ControllerID": "02:00:00:27:01:01"}}
            if arguments["rel_path"] == "Device.*.Radio.*.BSS.*.STA.":
                return {}
            self.assertEqual(arguments["depth"], 4)
            barrier.wait()
            device = server.ROOT + "." + arguments["rel_path"]
            return {device: {"ID": device.rstrip(".")}}

        with patch.object(server, "instances", return_value=devices), patch.object(server, "ubus", side_effect=read_device):
            value = server.topology()
        self.assertEqual(len(value["devices"]), 5)

    def test_roaming_membership_comes_from_one_atomic_station_read(self):
        source = server.ROOT + ".Device.1.Radio.1.BSS.1"
        target = server.ROOT + ".Device.2.Radio.1.BSS.1"
        station = {"MACAddress": "02:00:00:10:04:00", "SignalStrength": 120}
        snapshots = {}
        for bss in (source, target):
            device, _radio = bss.split(".Radio.")
            radio, _bss = bss.split(".BSS.")
            snapshots[device] = {device + ".": {"ID": device}, radio + ".": {"ID": radio},
                                 bss + ".": {"BSSID": bss, "SSID": "private_ssid"},
                                 bss + ".STA.1.": station}
        def read(path, method, arguments):
            self.assertEqual(path, server.ROOT)
            if arguments["rel_path"] == "":
                return {server.ROOT + ".": {"ControllerID": "02:00:00:27:01:01"}}
            if arguments["rel_path"] == "Device.*.Radio.*.BSS.*.STA.":
                return {target + ".STA.1.": station}
            return snapshots[server.ROOT + "." + arguments["rel_path"].rstrip(".")]
        with patch.object(server, "instances", return_value=list(snapshots)), patch.object(server, "ubus", side_effect=read):
            value = server.topology()
        owners = [(bss["bssid"], client["id"]) for device in value["devices"] for radio in device["radios"]
                  for bss in radio["bsses"] for client in bss["clients"]]
        self.assertEqual(owners, [(target, station["MACAddress"])])

    def test_failed_atomic_station_read_is_not_a_cached_roster(self):
        for response in ([], None):
            with self.subTest(response=response), patch.object(server, "instances", return_value=[]), \
                    patch.object(server, "ubus", return_value=response):
                with self.assertRaisesRegex(ValueError, "snapshot"):
                    server.topology()

    def test_failed_device_read_is_not_an_empty_topology(self):
        with patch.object(server, "instances", return_value=[server.ROOT + ".Device.1"]), patch.object(server, "ubus", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                server.topology()

    def test_parentless_reconnecting_agents_do_not_become_extra_controllers(self):
        controller = "aa:bb:cc:dd:ee:01"
        for parent in (None, "", "00:00:00:00:00:00", controller):
            with self.subTest(parent=parent):
                objects = {server.ROOT + ".": {"ControllerID": controller.upper()}}
                for index, address in enumerate(("02:00:00:27:02:01", controller,
                                                  "02:00:00:27:03:01"), 7):
                    device = server.ROOT + f".Device.{index}"
                    objects[device + "."] = {"ID": address}
                    objects[device + ".MultiAPDevice.Backhaul."] = {"BackhaulDeviceID": parent}
                devices = server.topology(objects)["devices"]
                self.assertEqual([device["id"] for device in devices if device["role"] == "controller"],
                                 [controller])
                self.assertEqual([device["name"] for device in devices], ["agent-1", "controller", "agent-2"])
                self.assertEqual(devices[0]["backhaul"]["parent_id"], parent)

    def test_missing_controller_identity_is_not_guessed_from_parentlessness(self):
        for identity in (None, "", "00:00:00:00:00:00", "invalid", False):
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, "controller identity"):
                server.topology({server.ROOT + ".": {"ControllerID": identity},
                                 server.ROOT + ".Device.1.": {"ID": "02:00:00:27:01:01"}})


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


class InternalAdapterSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.httpd = server.TopologyServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def request(self, path):
        return urllib.request.urlopen(
            f"http://127.0.0.1:{self.httpd.server_port}{path}", timeout=2
        )

    def test_health_is_the_only_non_topology_surface(self):
        with self.request("/health") as response:
            self.assertEqual(json.load(response), {"status": "ok"})

    def test_topology_errors_remain_unavailable_and_the_next_request_is_fresh(self):
        with patch.object(self.httpd.topology_reader, "reader", side_effect=[
                {"generation": 1}, OSError("native unavailable"), {"generation": 2}]):
            with self.request("/api/topology") as response:
                self.assertEqual(json.load(response), {"generation": 1})
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/topology")
            self.assertEqual(error.exception.code, 503)
            self.assertEqual(json.load(error.exception), {"error": "native unavailable"})
            with self.request("/api/topology") as response:
                self.assertEqual(json.load(response), {"generation": 2})

    def test_obsolete_topology_page_is_not_served(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/")
        self.assertEqual(error.exception.code, 404)

if __name__ == "__main__":
    unittest.main()
