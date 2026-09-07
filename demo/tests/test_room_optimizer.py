from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from optimizer.model import CandidateObservation, ClientObservation, MeshHealth, Snapshot
from optimizer.policy import PolicyConfig, ThresholdPolicy
from room_demo.conductor import LiveConductor
from room_demo.events import EventStore


class RoomOptimizerTests(unittest.TestCase):
    def _evaluate(self, expected_counts, actual_counts=None, devices=5, missing_metric=False):
        actual_counts = actual_counts or expected_counts
        timestamp = "2026-09-05T23:00:00Z"
        roles = [f"sta_static_{index:02d}" for index in range(1, 21)]
        clients = tuple(ClientObservation(
            sta_mac=f"02:00:00:00:{index:02x}:00",
            connected_device_id="02:00:00:00:00:20",
            connected_device_name="Agent-1", connected_bssid="02:00:00:00:00:01",
            rcpi=80, association_uptime_seconds=90,
            metric_observed_at=timestamp, measurement_source="associated_sta_link_metrics",
            band="5", ssid="private_ssid", cohort="private",
        ) for index in range(1, 21))
        if missing_metric:
            clients = (replace(clients[0], rcpi=None, metric_observed_at=None), *clients[1:])
        candidates = tuple(CandidateObservation(
            sta_mac=client.sta_mac, bssid="02:00:00:00:00:02",
            device_id="02:00:00:00:00:21", device_name="Extender-2", rcpi=138,
            metric_observed_at=timestamp, measurement_source="candidate", band="5",
        ) for client in clients)
        rooms = [{
            "revision": index, "environment_epoch": index, "stable_for_seconds": 10,
            "daemon": {"instance_id": "medium", "generation": index},
            "expected_online_clients": expected,
            "last_rf_applied_at": "2026-09-05T22:59:59Z",
            "roles": {role: {"present": ordinal < expected}
                      for ordinal, role in enumerate(roles)},
        } for index, expected in enumerate(expected_counts)]
        snapshots = [Snapshot(
            schema_version=1, sequence=index, controller_url="http://controller",
            observed_at=timestamp, health=MeshHealth(devices, actual),
            clients=clients[:actual], candidates=candidates[:actual],
        ) for index, actual in enumerate(actual_counts)]
        policy_config = PolicyConfig(expected_clients=20, condition_hold_seconds=0)
        policy = ThresholdPolicy(replace(policy_config, current_rcpi_below=220,
                                         minimum_target_gain_rcpi=1))
        with tempfile.TemporaryDirectory() as directory:
            world = {"name": "test", "duration_ms": 1000, "tick_ms": 100,
                     "roles": {role: "station" for role in roles}}
            store = EventStore("test", world, Path(directory) / "events.jsonl")
            plan = {"bindings": {role: {
                "role_type": "station", "radio_permanent_mac": client.sta_mac,
                "container": f"prpl-client-{index:02d}",
            } for index, (role, client) in enumerate(zip(roles, clients))}}
            manifest = {"hero": {"role": roles[0]}, "policy": "policy.yaml",
                        "optimizer": {"allow_simulated_candidates": True, "request_only": True,
                                      "interval_seconds": 5, "action_window_ms": [0, 1000],
                                      "max_actions": 10}}
            conductor = LiveConductor(store, plan, manifest, mode="recommend",
                                      repo_root=Path(directory), interactive=True,
                                      room_state=Mock(side_effect=[room for room in rooms for _repeat in range(2)]))
            store.emit("demo.state", 0, {"state": "running"})
            observer = Mock(last_raw={"topology": {"nodes": []}})
            observer.observe.side_effect = snapshots
            provider = Mock(last_raw=[], last_selected_sta_macs={client.sta_mac for client in clients})
            actuator = Mock()
            with patch("room_demo.conductor.load_policy", return_value=policy_config), \
                 patch("room_demo.conductor.ThresholdPolicy", return_value=policy), \
                 patch("room_demo.conductor.PrplMeshCandidateProvider", return_value=provider), \
                 patch("room_demo.conductor.PrplMeshObserver", side_effect=[observer, Mock()]), \
                 patch("room_demo.conductor.SteerActuator", return_value=actuator), \
                 patch.object(conductor, "_sleep", side_effect=[False] * (len(rooms) - 1) + [True]):
                conductor._run_worker("optimizer", conductor._optimizer_worker)
            self.assertEqual(conductor.errors, [])
            actuator.execute.assert_not_called()
            evaluations = [event["payload"] for event in store.all()
                           if event["kind"] == "optimizer.evaluation"]
            self.assertEqual(len(evaluations), len(rooms))
            return evaluations, policy_config

    def test_steering_policy_follows_selected_online_roster_and_default_restore(self):
        counts = [20, 12, 10, 19, 20]
        evaluations, original = self._evaluate(counts)
        self.assertEqual(original.expected_clients, 20)
        for expected, evaluation in zip(counts, evaluations):
            with self.subTest(expected=expected):
                self.assertEqual(evaluation["decision"]["action"], "steer")
                self.assertEqual(evaluation["fleet"]["actionable_clients"], expected)
                self.assertEqual(evaluation["expected_online_clients"], expected)

    def test_observed_count_is_not_rewritten_to_bypass_health_guard(self):
        evaluations, _config = self._evaluate([12, 10], [10, 12])
        for evaluation in evaluations:
            self.assertEqual(evaluation["decision"]["reason"], "client_count_mismatch")
            self.assertEqual(evaluation["fleet"]["actionable_clients"], 0)

    def test_missing_mesh_device_still_blocks_steering_in_smaller_room(self):
        evaluations, _config = self._evaluate([10], devices=4)
        self.assertEqual(evaluations[0]["decision"]["reason"], "mesh_device_count_mismatch")
        self.assertEqual(evaluations[0]["fleet"]["actionable_clients"], 0)

    def test_missing_returning_client_metric_does_not_block_other_clients(self):
        evaluations, _config = self._evaluate([10], missing_metric=True)
        evaluation = evaluations[0]
        self.assertEqual(evaluation["decision"]["action"], "steer")
        self.assertEqual(evaluation["fleet"]["actionable_clients"], 9)
        self.assertEqual(evaluation["fleet"]["clients_checked"], 9)
        self.assertFalse(evaluation["fleet"]["measurement_complete"])
        self.assertFalse(evaluation["fleet"]["converged"])


if __name__ == "__main__":
    unittest.main()
