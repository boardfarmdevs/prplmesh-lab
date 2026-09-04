from __future__ import annotations

from dataclasses import asdict, replace
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from optimizer.actuator import SteerActuator
from optimizer.candidates import CandidateMetricsError
from optimizer.config import load_policy
from optimizer.prplmesh import PrplMeshCandidateProvider, PrplMeshObserver
from optimizer.policy import ThresholdPolicy
from optimizer.state import PolicyState
from optimizer.verifier import OutcomeVerifier
from wmdcfg.observers import mesh_health

from .events import EventStore


DEVICE_ROLES = {
    "controller": "gateway",
    "agent-1": "extender_1",
    "agent-2": "extender_2",
    "agent-3": "extender_3",
    "agent-4": "extender_4",
}


def _world_device_name(role: str | None) -> str | None:
    if role == "gateway":
        return "Agent-1"
    if role and role.startswith("extender_"):
        return "Extender-" + role.rsplit("_", 1)[1]
    return None


def _recommendation_state(prior: PolicyState, evaluation) -> PolicyState:
    state = evaluation.state
    for decision in evaluation.decisions:
        if decision.action != "steer":
            continue
        proposed = state.for_sta(decision.sta_mac)
        previous = prior.for_sta(decision.sta_mac)
        state = state.replace(replace(
            proposed,
            phase="recommended",
            pending_since=None,
            last_action_at=previous.last_action_at,
        ))
    return state


def _deferred_state(prior: PolicyState, evaluation) -> PolicyState:
    """Keep a satisfied condition eligible without pretending it was sent."""
    state = evaluation.state
    for decision in evaluation.decisions:
        if decision.action != "steer":
            continue
        proposed = state.for_sta(decision.sta_mac)
        previous = prior.for_sta(decision.sta_mac)
        state = state.replace(replace(
            proposed,
            phase="holding",
            pending_since=None,
            last_action_at=previous.last_action_at,
        ))
    return state


def _rssi(rcpi: int | None) -> int | None:
    return None if rcpi is None else int(round(rcpi / 2 - 110))


class LiveConductor:
    """Join live controller truth, optimizer state, traffic and health to one run."""

    def __init__(
        self,
        store: EventStore,
        plan: dict[str, Any],
        manifest: dict[str, Any],
        *,
        mode: str,
        repo_root: Path,
        base_url: str = "http://127.0.0.1:8092",
    ) -> None:
        if mode not in {"stimulus", "recommend", "act"}:
            raise ValueError(f"unsupported demo mode {mode!r}")
        self.store = store
        self.plan = plan
        self.manifest = manifest
        self.mode = mode
        self.repo_root = repo_root
        self.base_url = base_url
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.action_attempts = 0
        self.action_successes = 0
        self.verification_successes = 0
        self._error_lock = threading.Lock()
        self._role_by_mac = {
            value.get("station_mac", value["radio_permanent_mac"]).lower(): role
            for role, value in plan["bindings"].items()
            if value["role_type"] == "station"
        }
        self._container_by_mac = {
            value.get("station_mac", value["radio_permanent_mac"]).lower(): value["container"]
            for value in plan["bindings"].values()
            if value["role_type"] == "station"
        }
        # Controller display ordinals reflect discovery order and can differ
        # from the manifest's stable container/world ordinals.  BSSID
        # ownership is the authoritative bridge between both namespaces.
        self._ap_role_by_bssid: dict[str, str] = {}
        for role, value in plan["bindings"].items():
            if value["role_type"] != "fronthaul_ap":
                continue
            for radio in value.get("band_radios", {}).values():
                for interface in radio.get("interfaces", []):
                    mac = interface.get("mac")
                    if mac:
                        self._ap_role_by_bssid[mac.lower()] = role
        hero_role = manifest["hero"]["role"]
        self.hero_mac = plan["bindings"][hero_role].get(
            "station_mac", plan["bindings"][hero_role]["radio_permanent_mac"]
        ).lower()
        self.hero_container = plan["bindings"][hero_role]["container"]

    def _time(self) -> int:
        return int(self.store.current()["world_time_ms"])

    def _active(self) -> bool:
        return self.store.current()["state"] in {"running", "ready"}

    def _wait_for_run(self) -> bool:
        while not self.stop_event.is_set():
            if self.store.current()["state"] == "running":
                return True
            time.sleep(0.1)
        return False

    def _sleep(self, seconds: float) -> bool:
        return self.stop_event.wait(seconds)

    def _record_error(self, worker: str, error: Exception, *, fatal: bool) -> None:
        message = f"{worker}: {type(error).__name__}: {error}"
        with self._error_lock:
            (self.errors if fatal else self.warnings).append(message)
        self.store.emit(
            "worker.error", self._time(),
            {"worker": worker, "fatal": fatal,
             "error_type": type(error).__name__, "message": str(error)},
            producer=worker,
        )

    def _client_payload(self, client) -> dict[str, Any]:
        role = self._role_by_mac.get(client.sta_mac)
        connected_role = self._ap_role_by_bssid.get(client.connected_bssid)
        if connected_role is None:
            connected_role = DEVICE_ROLES.get(client.connected_device_name.lower())
        return {
            "role": role,
            "container": self._container_by_mac.get(client.sta_mac),
            "sta_mac": client.sta_mac,
            "cohort": client.cohort,
            "ssid": client.ssid,
            "band": client.band,
            "connected_bssid": client.connected_bssid,
            "connected_device_name": client.connected_device_name,
            "connected_role": connected_role,
            "connected_world_name": _world_device_name(connected_role),
            "rcpi": client.rcpi,
            "rssi_dbm": _rssi(client.rcpi),
            "association_uptime_seconds": client.association_uptime_seconds,
            "metric_observed_at": client.metric_observed_at,
        }

    def _network_payload(self, snapshot) -> dict[str, Any]:
        clients = [self._client_payload(item) for item in snapshot.clients]
        hero = next((item for item in clients if item["sta_mac"] == self.hero_mac), None)
        return {
            "observed_at": snapshot.observed_at,
            "health": {
                "mesh_devices": snapshot.health.devices,
                "clients": snapshot.health.clients,
                "bsses": snapshot.health.bsses,
            },
            "cohorts": {
                "private": sum(item["cohort"] == "private" for item in clients),
                "iot": sum(item["cohort"] == "iot" for item in clients),
                "other": sum(item["cohort"] == "other" for item in clients),
            },
            "clients": clients,
            "hero": hero,
        }

    def _ping(self, container: str) -> dict[str, Any]:
        traffic = self.manifest["traffic"]
        target = str(traffic["target"])
        timeout = max(1, int(traffic["timeout_seconds"]))
        started = time.monotonic()
        command = (
            "lxc", "exec", container, "--", "ping", "-c", "1", "-W",
            str(timeout), target,
        )
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout + 2,
            )
            text = result.stdout + result.stderr
            match = re.search(r"time[=<]([0-9.]+)\s*ms", text)
            return {
                "container": container,
                "target": target,
                "success": result.returncode == 0,
                "rtt_ms": float(match.group(1)) if match else None,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "returncode": result.returncode,
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            return {
                "container": container,
                "target": target,
                "success": False,
                "rtt_ms": None,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "error": str(error),
            }

    def preflight(self) -> None:
        observer = PrplMeshObserver(self.base_url)
        snapshot = observer.observe()
        payload = self._network_payload(snapshot)
        hero = payload["hero"]
        expected = self.manifest["health"]
        failures = []
        if snapshot.health.devices != int(expected["expected_mesh_devices"]):
            failures.append(f"mesh devices={snapshot.health.devices}")
        if snapshot.health.clients != int(expected["expected_clients"]):
            failures.append(f"clients={snapshot.health.clients}")
        if payload["cohorts"]["private"] != int(expected["expected_private_clients"]):
            failures.append(f"private clients={payload['cohorts']['private']}")
        if payload["cohorts"]["iot"] != int(expected["expected_iot_clients"]):
            failures.append(f"IoT clients={payload['cohorts']['iot']}")
        if hero is None:
            failures.append(f"hero {self.hero_mac} is absent")
        else:
            if hero["ssid"] != self.manifest["hero"]["expected_ssid"]:
                failures.append(f"hero SSID={hero['ssid']!r}")
            if hero["band"] != self.manifest["hero"]["expected_band"]:
                failures.append(f"hero band={hero['band']!r}")
            if hero["rcpi"] is None:
                failures.append("hero RCPI is missing")
        ping = self._ping(self.hero_container)
        if not ping["success"]:
            failures.append("hero traffic probe failed")
        self.store.emit("network.snapshot", 0, payload, producer="network")
        self.store.emit("traffic.sample", 0, ping, producer="traffic")
        if failures:
            raise RuntimeError("demo preflight failed: " + "; ".join(failures))
        self.store.emit(
            "demo.state", 0,
            {"state": "ready", "mode": self.mode, "hero_mac": self.hero_mac},
            producer="conductor",
        )

    def start(self) -> None:
        workers = [
            ("network", self._network_worker),
            ("traffic", self._traffic_worker),
            ("health", self._health_worker),
            ("narrative", self._narrative_worker),
        ]
        if self.mode != "stimulus":
            workers.append(("optimizer", self._optimizer_worker))
        for name, target in workers:
            thread = threading.Thread(
                target=self._run_worker,
                args=(name, target),
                name=f"room-demo-{name}",
                daemon=True,
            )
            thread.start()
            self.threads.append(thread)

    def _run_worker(self, name: str, target) -> None:
        """Turn an unexpected worker exception into a failed demo result."""
        try:
            target()
        except Exception as error:  # the evidence must retain programming faults too
            self._record_error(name, error, fatal=True)

    def stop(self) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=90)

    def _network_worker(self) -> None:
        if not self._wait_for_run():
            return
        observer = PrplMeshObserver(self.base_url)
        while not self.stop_event.is_set() and self._active():
            try:
                snapshot = observer.observe()
                self.store.emit(
                    "network.snapshot", self._time(), self._network_payload(snapshot),
                    producer="network",
                )
            except (OSError, ValueError, KeyError) as error:
                # NBAPI collection and an active candidate transaction can
                # overlap. The next sample and final authoritative health gate
                # decide whether a transport failure was transient.
                self._record_error("network", error, fatal=False)
            if self._sleep(2):
                break

    def _traffic_worker(self) -> None:
        if not self._wait_for_run():
            return
        interval = float(self.manifest["traffic"]["interval_seconds"])
        while not self.stop_event.is_set() and self._active():
            self.store.emit(
                "traffic.sample", self._time(), self._ping(self.hero_container),
                producer="traffic",
            )
            if self._sleep(interval):
                break

    def _health_worker(self) -> None:
        if not self._wait_for_run():
            return
        health = self.manifest["health"]
        interval = float(health["interval_seconds"])
        expected_devices = int(health["expected_mesh_devices"])
        expected_clients = int(health["expected_clients"])
        while not self.stop_event.is_set() and self._active():
            try:
                payload = mesh_health(expected_devices, expected_clients)
                payload["healthy"] = (
                    payload.get("api_active") == expected_clients
                    and payload.get("topology_nodes") == expected_devices
                    and payload.get("complete_nodes") == expected_devices
                )
                self.store.emit("health.sample", self._time(), payload, producer="health")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self._record_error("health", error, fatal=False)
            if self._sleep(interval):
                break

    def _narrative_worker(self) -> None:
        if not self._wait_for_run():
            return
        pending = list(self.manifest.get("narrative", []))
        while pending and not self.stop_event.is_set() and self._active():
            now = self._time()
            while pending and now >= int(pending[0]["time_ms"]):
                mark = pending.pop(0)
                self.store.emit(
                    "demo.mark", now,
                    {"scheduled_time_ms": int(mark["time_ms"]), "label": mark["label"]},
                    producer="conductor",
                )
            self._sleep(0.2)

    def _optimizer_worker(self) -> None:
        if not self._wait_for_run():
            return
        optimizer = self.manifest["optimizer"]
        policy_path = self.repo_root / self.manifest["policy"]
        policy = ThresholdPolicy(load_policy(policy_path))
        provider = PrplMeshCandidateProvider(
            allow_simulated=bool(optimizer["allow_simulated_candidates"]),
            timeout_seconds=float(optimizer.get("candidate_timeout_seconds", 30)),
            client_selector=lambda client, observed_at: (
                client.sta_mac == self.hero_mac
                and policy.requires_candidate_measurement(client, observed_at)
            ),
        )
        observer = PrplMeshObserver(self.base_url, candidate_provider=provider)
        verify_observer = PrplMeshObserver(self.base_url)
        verifier = OutcomeVerifier(
            verify_observer,
            traffic_probe=lambda _sta: self._ping(self.hero_container)["success"],
        )
        actuator = SteerActuator(
            self.repo_root / "scripts/steer-client.sh",
            request_only=bool(optimizer["request_only"]),
        )
        state = PolicyState()
        interval = float(optimizer["interval_seconds"])
        window_start, window_end = [int(value) for value in optimizer["action_window_ms"]]
        maximum_actions = int(optimizer["max_actions"])
        while not self.stop_event.is_set() and self._active():
            cycle_started = time.monotonic()
            try:
                snapshot = observer.observe()
                prior = state
                evaluation = policy.evaluate(snapshot, prior)
                decision = next(
                    item for item in evaluation.decisions if item.sta_mac == self.hero_mac
                )
                now = self._time()
                window_open = window_start <= now <= window_end
                can_act = (
                    self.mode == "act"
                    and window_open
                    and self.action_attempts < maximum_actions
                )
                if decision.action == "steer" and self.mode == "recommend":
                    state = _recommendation_state(prior, evaluation)
                elif (
                    decision.action == "steer"
                    and self.mode == "act"
                    and self.action_attempts == 0
                    and not window_open
                ):
                    state = _deferred_state(prior, evaluation)
                else:
                    state = evaluation.state
                hero_state = state.for_sta(self.hero_mac)
                candidates = []
                for item in snapshot.candidates_for(self.hero_mac):
                    if item.rcpi is None:
                        continue
                    candidate = asdict(item)
                    candidate["role"] = self._ap_role_by_bssid.get(item.bssid)
                    candidate["world_name"] = _world_device_name(candidate["role"])
                    candidates.append(candidate)
                self.store.emit(
                    "optimizer.evaluation", now,
                    {
                        "mode": self.mode,
                        "decision": decision.to_dict(),
                        "policy_state": asdict(hero_state),
                        "candidates": candidates,
                        "candidate_transactions": len(provider.last_raw),
                        "action_window_ms": [window_start, window_end],
                        "action_window_open": window_open,
                        "observation_elapsed_ms": round(
                            (time.monotonic() - cycle_started) * 1000, 3
                        ),
                    },
                    producer="optimizer",
                )
                if decision.action == "steer" and can_act:
                    self.action_attempts += 1
                    self.store.emit(
                        "optimizer.action", now,
                        {"phase": "requested", "decision": decision.to_dict()},
                        producer="optimizer",
                    )
                    result = actuator.execute(decision, snapshot)
                    if result.success:
                        self.action_successes += 1
                    self.store.emit(
                        "optimizer.action", self._time(),
                        {"phase": "submitted", "decision": decision.to_dict(),
                         "result": result.to_dict()},
                        producer="optimizer",
                    )
                    if result.success:
                        verified = verifier.verify(
                            decision.sta_mac,
                            decision.target_bssid,
                            timeout_seconds=policy.config.steer_timeout_seconds,
                        )
                        if verified.success:
                            self.verification_successes += 1
                        self.store.emit(
                            "optimizer.verification", self._time(), verified.to_dict(),
                            producer="optimizer",
                        )
            except (CandidateMetricsError, OSError, ValueError, KeyError) as error:
                self._record_error("optimizer", error, fatal=True)
                return
            elapsed = time.monotonic() - cycle_started
            if self._sleep(max(0.1, interval - elapsed)):
                break

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "hero_role": self.manifest["hero"]["role"],
            "hero_mac": self.hero_mac,
            "action_attempts": self.action_attempts,
            "action_successes": self.action_successes,
            "verification_successes": self.verification_successes,
            "worker_errors": list(self.errors),
            "worker_warnings": list(self.warnings),
        }


def load_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "easymesh.room-demo.v1":
        raise ValueError(f"{path}: unsupported room demo manifest schema")
    for key in ("world", "bindings", "policy"):
        target = repo_root / value[key]
        if not target.is_file():
            raise ValueError(f"{path}: {key} does not exist: {target}")
    return value
