import unittest
import subprocess
from unittest import mock

from optimizer.candidates import CandidateMetricsUnavailable
from room_demo.cli import _interactive_preflight, TOPOLOGY_URL
from wmdcfg.actuator import ActuatorError


class RecoveryPreflightTests(unittest.TestCase):
    def check(self, errors, recovered=True, cancelled=False):
        conductor = mock.Mock()
        conductor.preflight.side_effect = errors
        stop = mock.Mock()
        stop.wait.return_value = cancelled
        with mock.patch("room_demo.cli.mesh_health", return_value={"healthy": True}), \
             mock.patch("room_demo.cli.Runner._require_healthy"):
            result = _interactive_preflight(conductor, 5, 20, recovered, stop)
        return result, conductor, stop

    def test_recovered_roster_waits_for_traffic_readiness(self):
        result, conductor, stop = self.check([
            RuntimeError("demo preflight failed: hero traffic probe failed"), None])
        self.assertTrue(result["healthy"])
        self.assertEqual(conductor.preflight.call_count, 2)
        stop.wait.assert_called_once_with(0.5)

    def test_normal_startup_does_not_add_a_retry_policy(self):
        with self.assertRaisesRegex(RuntimeError, "hero traffic"):
            self.check([RuntimeError("demo preflight failed: hero traffic")], recovered=False)

    def test_native_inventory_unavailability_retries_without_restarting_rf(self):
        result, conductor, stop = self.check([
            CandidateMetricsUnavailable("native query timed out"), None], recovered=False)
        self.assertTrue(result["healthy"])
        self.assertEqual(conductor.preflight.call_count, 2)
        stop.wait.assert_called_once_with(0.5)

    def test_unavailable_inventory_still_has_a_deadline(self):
        with mock.patch("room_demo.cli.time.monotonic", side_effect=[0, 31]), \
             self.assertRaisesRegex(CandidateMetricsUnavailable, "timed out"):
            self.check([CandidateMetricsUnavailable("native query timed out")], recovered=False)

    def test_unavailable_inventory_retry_can_be_cancelled(self):
        with self.assertRaisesRegex(ActuatorError, "cancelled"):
            self.check([CandidateMetricsUnavailable("native query timed out")],
                       recovered=False, cancelled=True)

    def test_health_http_failure_retries_without_accepting_empty_inventory(self):
        for failure in (subprocess.CalledProcessError(22, ("curl", "-fsS", TOPOLOGY_URL)),
                        subprocess.TimeoutExpired(("curl", "-fsS", TOPOLOGY_URL), 10)):
            with self.subTest(failure=type(failure).__name__):
                conductor, stop = mock.Mock(), mock.Mock()
                stop.wait.return_value = False
                with mock.patch("room_demo.cli.mesh_health", side_effect=[failure, {"healthy": True}]), \
                     mock.patch("room_demo.cli.Runner._require_healthy"):
                    self.assertTrue(_interactive_preflight(conductor, 5, 100, False, stop)["healthy"])
                conductor.preflight.assert_called_once()
                stop.wait.assert_called_once_with(0.5)

    def test_unrelated_command_failure_is_not_retried(self):
        for failure in (subprocess.CalledProcessError(1, ("false",)),
                        subprocess.SubprocessError("missing command"),
                        subprocess.CalledProcessError(1, None)):
            with self.subTest(failure=str(failure)), self.assertRaises(type(failure)):
                self.check([failure], recovered=False)

    def test_unexpected_faults_are_not_hidden(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            self.check([RuntimeError("unexpected programming fault")])

    def test_recovery_wait_has_a_deadline_and_is_cancellable(self):
        with mock.patch("room_demo.cli.time.monotonic", side_effect=[0, 31]), \
             self.assertRaisesRegex(RuntimeError, "hero traffic"):
            self.check([RuntimeError("demo preflight failed: hero traffic")])
        with self.assertRaisesRegex(ActuatorError, "cancelled"):
            self.check([RuntimeError("demo preflight failed: hero traffic")], cancelled=True)
