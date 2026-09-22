from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "wmediumd/observer"


def load_module(filename):
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), OBSERVER / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConsoleNGContractTests(unittest.TestCase):
    def test_generated_property_catalogs_and_protocol_allocations(self):
        from optimizer.rf_observations import property_catalog
        from wmdcfg import actuator
        from wmdcfg.protocol_registry import protocol_registry
        registry = protocol_registry()
        catalog = {**property_catalog(), "protocol": registry}
        for path in (OBSERVER / "web/ng/rf-catalog.json",
                     ROOT / "wmediumd/configurator/worlds/viewer/rf-catalog.json"):
            self.assertEqual(json.loads(path.read_text()), json.loads(json.dumps(catalog)))
        for name, value in vars(actuator).items():
            if name.startswith("OP_"):
                self.assertEqual(registry["opcodes"][value], name[3:].lower())
        for mask, name in actuator.CAPABILITIES.items():
            self.assertEqual(registry["capability_bits"][mask.bit_length() - 1], name)
        patch = (ROOT / "patches/wmediumd/0033-wmediumd-console-ng-detail.patch").read_text()
        self.assertIn("WMDC_OP_EXPLORER_DETAIL = 17", patch)
        self.assertIn("WMDC_CAP_EXPLORER_DETAIL = 1U << 16", patch)
        self.assertEqual(registry["opcodes"][17], "explorer_detail")
        self.assertEqual(registry["capability_bits"][16], "explorer_details")

    def test_readiness_accepts_go_timestamp_precision(self):
        readiness = load_module("check-ready.py")
        now = datetime(2026, 9, 21, 21, 38, 54, tzinfo=timezone.utc)
        with patch.object(readiness, "datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            for fraction in [""] + ["." + "123456789"[:length] for length in range(1, 10)]:
                for local_time, zone in (("21:38:53", "Z"), ("21:38:53", "+00:00"),
                                         ("22:38:53", "+01:00")):
                    stamp = "2026-09-21T" + local_time + fraction + zone
                    with self.subTest(stamp=stamp):
                        self.assertTrue(readiness.fresh({"available": True, "observed_at": stamp}))

    def test_readiness_rejects_stale_future_and_invalid_timestamps(self):
        readiness = load_module("check-ready.py")
        now = datetime(2026, 9, 21, 21, 38, 54, tzinfo=timezone.utc)
        with patch.object(readiness, "datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            for stamp in ("2026-09-21T21:38:48.123456789Z", "2026-09-21T21:38:55.1Z",
                          "2026-09-21T21:38:53.123456", "invalid", None, 123):
                with self.subTest(stamp=stamp):
                    self.assertFalse(readiness.fresh({"available": True, "observed_at": stamp}))
            self.assertFalse(readiness.fresh({"available": True}))
            self.assertFalse(readiness.fresh({"available": False, "observed_at": now.isoformat()}))

    def test_embedded_rf_guide_matches_source(self):
        renderer = load_module("build-manual.py")
        source = (ROOT / "reference/radio/console-rf-properties.md").read_text()
        rendered = (OBSERVER / "web/ng/rf-properties.html").read_text()
        self.assertIn(renderer.render(source), rendered)
        for anchor in ("directed-snr", "noise-reference-and-cca", "channel-utilization",
                       "advertised-beacon-bss-load", "room-exclusion-and-fronthaul-availability"):
            self.assertIn(f'id="{anchor}"', rendered)
        self.assertIn('href="/ng/manual.html"', rendered)

    def test_readiness_requires_matching_sources(self):
        readiness = load_module("check-ready.py")
        stamp = datetime.now(timezone.utc).isoformat()

        def report(data):
            return {"available": True, "observed_at": stamp, "data": data}

        document = {
            "daemon": {"instance_id": "one", "capabilities": ["explorer_details"]},
            "summary": {"available": True}, "identity_inventory": {"matched": "105"},
            "service": report({"airtime_profile": "legacy20"}),
            "room": report({"live": True, "instance_id": "one", "roles": [{"role": "station_1"}]}),
            "survey": report({"instance_id": "one", "reader_monotonic_ns": "1000001",
                              "recorded_monotonic_ns": "1000000", "written": [{"radio": "radio"}]}),
        }
        self.assertEqual(readiness.missing_sources(document, True, True), [])
        document["room"]["data"]["instance_id"] = "old"
        document["survey"]["data"]["reader_monotonic_ns"] = "5000000000"
        self.assertEqual(len(readiness.missing_sources(document, True, True)), 2)
        document["service"]["data"].clear()
        self.assertIn("live RF model/service telemetry", readiness.missing_sources(document))


if __name__ == "__main__":
    unittest.main()
