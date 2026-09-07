from __future__ import annotations

from dataclasses import asdict, replace
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from optimizer.actuator import SteerActuator
from optimizer.candidates import (
    CandidateMetricsError, CandidateMetricsUnavailable,
)
from optimizer.config import load_policy
from optimizer.model import normalize_band, parse_time
from optimizer.prplmesh import PrplMeshObserver, PrplMeshCandidateProvider
from optimizer.policy import ThresholdPolicy
from optimizer.state import PolicyState
from optimizer.verifier import OutcomeVerifier
from wmdcfg.observers import mesh_health

from .events import EventStore
from .client_wifi import read_client_link
from .topology import project_topology


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


def _single_action_state(
    prior: PolicyState, evaluation, selected_sta: str
) -> PolicyState:
    """Keep all non-selected steer candidates eligible for the next cycle."""
    state = evaluation.state
    for decision in evaluation.decisions:
        if decision.action != "steer" or decision.sta_mac == selected_sta:
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


def _interrupted_measurement_state(state: PolicyState) -> PolicyState:
    """Restart unacted holds without discarding cooldown or action history."""
    return PolicyState(tuple(
        replace(item, phase="stable", source_bssid=None, target_bssid=None,
                condition_since=None)
        if item.phase in {"holding", "recommended"} else item
        for item in state.clients
    ))


def _ranked_action_batch(decisions, limit: int):
    """Choose a bounded fleet batch, moving weakest serving links first.

    Every decision in the batch comes from one controller-measured candidate
    snapshot. Actions remain sequential and individually verified; batching
    avoids repeating the expensive whole-fleet candidate query after every
    single BTM request.
    """
    if limit <= 0:
        return []
    actionable = [item for item in decisions if item.action == "steer"]
    actionable.sort(key=lambda item: (
        item.current_rcpi if item.current_rcpi is not None else 221,
        -(
            (item.target_rcpi if item.target_rcpi is not None else -1)
            - (item.current_rcpi if item.current_rcpi is not None else -1)
        ),
        item.sta_mac,
    ))
    return actionable[:limit]


def _fleet_status(snapshot, selected_sta_macs: set[str]) -> dict[str, Any]:
    """Summarize measured best-AP convergence independently of policy phase."""
    better: list[dict[str, Any]] = []
    for client in snapshot.clients:
        if client.rcpi is None:
            continue
        candidates = [
            item for item in snapshot.candidates_for(client.sta_mac)
            if item.eligible and item.rcpi is not None
            and item.bssid != client.connected_bssid
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda item: (int(item.rcpi), item.bssid))
        if int(best.rcpi) > int(client.rcpi):
            better.append({
                "sta_mac": client.sta_mac,
                "current_bssid": client.connected_bssid,
                "current_rcpi": client.rcpi,
                "target_bssid": best.bssid,
                "target_rcpi": best.rcpi,
                "gain_rcpi": int(best.rcpi) - int(client.rcpi),
            })
    checked = len(selected_sta_macs)
    total = len(snapshot.clients)
    return {
        "clients_evaluated": total,
        "clients_checked": checked,
        "candidate_measurements": sum(
            item.rcpi is not None for item in snapshot.candidates
        ),
        "clients_with_stronger_ap": len(better),
        "stronger_candidates": sorted(
            better, key=lambda item: (-item["gain_rcpi"], item["sta_mac"])
        ),
        "measurement_complete": checked == total,
        "converged": checked == total and not better,
    }


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
        room_state: Callable[[], dict[str, Any]] | None = None,
        interactive: bool = False,
        maximum_actions: int | None = None,
        steering_transaction: Callable[
            [str, str, str, str, Callable[[], Any]], Any
        ] | None = None,
    ) -> None:
        if mode not in {"stimulus", "recommend", "act"}:
            raise ValueError(f"unsupported demo mode {mode!r}")
        self.store = store
        self.plan = plan
        self.manifest = manifest
        self.mode = mode
        self.repo_root = repo_root
        self.base_url = base_url
        self.room_state = room_state
        self.interactive = interactive
        self.maximum_actions = maximum_actions
        self.steering_transaction = steering_transaction
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.action_attempts = 0
        self.action_successes = 0
        self.verification_successes = 0
        self._error_lock = threading.Lock()
        self._controller_lock = threading.Lock()
        self._candidate_active = threading.Event()
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
        self._mac_by_role = {
            role: value.get("station_mac", value["radio_permanent_mac"]).lower()
            for role, value in plan["bindings"].items()
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
        self.hero_mac = plan["bindings"][hero_role].get("station_mac", plan["bindings"][hero_role]["radio_permanent_mac"]).lower()
        self.hero_container = plan["bindings"][hero_role]["container"]

    def _optimization_subject(
        self, room: dict[str, Any] | None
    ) -> tuple[str, str, str] | None:
        """Resolve the only client eligible for this optimizer cycle."""
        hero_role = self.manifest["hero"]["role"]
        if not self.interactive:
            return hero_role, self.hero_mac, self.hero_container
        if room is None:
            return None
        role = room.get("last_rf_role")
        mac = self._mac_by_role.get(str(role))
        role_state = (room.get("roles") or {}).get(str(role), {})
        if mac is None or role_state.get("present") is not True:
            return None
        return str(role), mac, self._container_by_mac[mac]

    def _client_link_fallback(self, client, room):
        role = self._role_by_mac.get(client.sta_mac)
        if room is None or not room.get("roles", {}).get(role, {}).get("present"):
            return client
        sample = read_client_link(self._container_by_mac[client.sta_mac],
                                  client.connected_bssid, client.band,
                                  self.manifest["traffic"]["target"])
        return replace(client, **sample) if sample else client

    def _action_window(self, now_ms: int, configured: list[int]) -> tuple[bool, str]:
        if self.interactive:
            return True, "stable_interactive_environment"
        start, end = [int(value) for value in configured]
        return start <= now_ms <= end, "scenario_time"

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
            "measurement_source": client.measurement_source,
        }

    def _topology_payload(self, topology: dict[str, Any] | None) -> dict[str, Any]:
        return project_topology(topology, self._ap_role_by_bssid)

    def _network_payload(
        self, snapshot, topology: dict[str, Any] | None = None
    ) -> dict[str, Any]:
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
            "mesh": self._topology_payload(topology),
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
        payload = self._network_payload(snapshot, observer.last_raw["topology"])
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
            if self._candidate_active.is_set():
                if self._sleep(0.2):
                    break
                continue
            try:
                if not self._controller_lock.acquire(timeout=0.5):
                    continue
                try:
                    snapshot = observer.observe()
                finally:
                    self._controller_lock.release()
                self.store.emit(
                    "network.snapshot", self._time(), self._network_payload(
                        snapshot, observer.last_raw["topology"]
                    ),
                    producer="network",
                )
            except (CandidateMetricsUnavailable, OSError, ValueError, KeyError) as error:
                # The RDK libemcli adapter serializes its native command path.
                # A passive GET can time out while the bounded candidate
                # transaction owns that path; the next sample and the final
                # authoritative health gate decide whether this was transient.
                self._record_error("network", error, fatal=False)
            if self._sleep(2):
                break

    def _traffic_worker(self) -> None:
        if not self._wait_for_run():
            return
        interval = float(self.manifest["traffic"]["interval_seconds"])
        while not self.stop_event.is_set() and self._active():
            room = self.room_state() if self.room_state else None
            if room is not None and not room.get("roles", {}).get(self.manifest["hero"]["role"], {}).get("present", True):
                if self._sleep(interval):
                    break
                continue
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
                room = self.room_state() if self.room_state else None
                if room is not None:
                    expected_clients = int(room.get("expected_online_clients", expected_clients))
                payload = mesh_health(expected_devices, expected_clients)
                payload["pool_clients"] = int(health["expected_clients"])
                payload["expected_online_clients"] = expected_clients
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
        if self.interactive:
            label = (
                "Continuous topology reconciliation is active; move any client "
                "and the optimizer will reconverge the fleet"
                if self.mode == "act" else
                "The optimizer continuously recommends the best eligible APs"
            )
            self.store.emit(
                "demo.mark", self._time(), {"label": label, "interactive": True},
                producer="conductor",
            )
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
        policy_config = load_policy(policy_path)
        if self.interactive:
            # An explicitly moved client asks the room optimizer to find the
            # best eligible AP. Keep the normal gain/hysteresis gate, but do
            # not require the old association to be below the weak-link
            # threshold before measuring alternatives.
            policy_config = replace(
                policy_config,
                current_rcpi_below=220,
                minimum_target_gain_rcpi=1,
            )
        policy = ThresholdPolicy(policy_config)
        provider = PrplMeshCandidateProvider(
            allow_simulated=bool(optimizer["allow_simulated_candidates"]),
            timeout_seconds=float(optimizer.get("candidate_timeout_seconds", 30)),
            client_selector=lambda client, observed_at: (
                (self.interactive or client.sta_mac == self.hero_mac)
                and policy.requires_candidate_measurement(client, observed_at)
            ),
        )
        observer = PrplMeshObserver(
            self.base_url, candidate_provider=provider,
            current_link_fallback=(lambda client: self._client_link_fallback(client, room_before))
            if self.interactive and self.room_state else None,
        )
        verify_observer = PrplMeshObserver(self.base_url)
        verifier = OutcomeVerifier(
            verify_observer,
            traffic_probe=lambda sta: self._ping(
                self._container_by_mac[sta.lower()]
            )["success"],
        )
        actuator = SteerActuator(
            self.repo_root / "scripts/steer-client.sh",
            request_only=bool(optimizer["request_only"]),
        )
        state = PolicyState()
        interval = float(optimizer["interval_seconds"])
        action_window = [int(value) for value in optimizer["action_window_ms"]]
        maximum_actions = (
            int(self.maximum_actions)
            if self.maximum_actions is not None else int(optimizer["max_actions"])
        )
        observed_epoch: int | None = None
        consecutive_measurement_failures = 0
        while not self.stop_event.is_set() and self._active():
            cycle_started = time.monotonic()
            retry_delay = 0.0
            try:
                room_before = self.room_state() if self.room_state else None
                if room_before is not None:
                    epoch = int(room_before["environment_epoch"])
                    stable_for = room_before.get("stable_for_seconds")
                    if observed_epoch != epoch:
                        state = PolicyState()
                        observed_epoch = epoch
                        self.store.emit(
                            "optimizer.environment.changed", self._time(),
                            {
                                "environment_epoch": epoch,
                                "world_revision": room_before["revision"],
                                "policy_hold_reset": True,
                            },
                            producer="optimizer",
                        )
                    if room_before.get("movement_active") or stable_for is None or stable_for < 2:
                        self.store.emit(
                            "optimizer.measurement.waiting", self._time(),
                            {
                                "reason": (
                                    "movement_active" if room_before.get("movement_active")
                                    else "rf_settle_interval"
                                ),
                                "environment_epoch": epoch,
                                "world_revision": room_before["revision"],
                                "stable_for_seconds": stable_for,
                            },
                            producer="optimizer",
                        )
                        if self._sleep(0.5):
                            break
                        continue
                preferred_subject = self._optimization_subject(room_before)
                if preferred_subject is None:
                    hero_role = self.manifest["hero"]["role"]
                    preferred_subject = (
                        hero_role, self.hero_mac, self.hero_container
                    )
                self._candidate_active.set()
                with self._controller_lock:
                    snapshot = observer.observe()
                consecutive_measurement_failures = 0
                room_after = self.room_state() if self.room_state else None
                if room_before is not None and room_after is not None:
                    before_key = (
                        room_before["revision"],
                        room_before["environment_epoch"],
                        room_before["daemon"]["instance_id"],
                        room_before["daemon"]["generation"],
                    )
                    after_key = (
                        room_after["revision"],
                        room_after["environment_epoch"],
                        room_after["daemon"]["instance_id"],
                        room_after["daemon"]["generation"],
                    )
                    if before_key != after_key or room_after.get("movement_active"):
                        state = PolicyState()
                        self.store.emit(
                            "observation.inconsistent_rf_epoch", self._time(),
                            {
                                "start": before_key,
                                "end": after_key,
                                "movement_active": room_after.get("movement_active"),
                            },
                            producer="optimizer",
                        )
                        continue
                    online_macs = {
                        self._mac_by_role[role] for role, value in room_after.get("roles", {}).items()
                        if value.get("present") and role in self._mac_by_role
                    }
                    observed_snapshot = snapshot
                    snapshot = replace(snapshot,
                        clients=tuple(item for item in snapshot.clients if item.sta_mac in online_macs),
                        candidates=tuple(item for item in snapshot.candidates if item.sta_mac in online_macs))
                    policy.config = replace(
                        policy_config, expected_clients=int(room_after["expected_online_clients"])
                    )
                    applied_at = room_after.get("last_rf_applied_at")
                    if applied_at:
                        applied_time = parse_time(applied_at)
                        moved_role = room_after.get("last_rf_role")
                        moved_mac = self._mac_by_role.get(str(moved_role))
                        relevant = (
                            [item for item in snapshot.clients
                             if item.sta_mac == moved_mac]
                            if moved_mac else list(snapshot.clients)
                        )
                        not_fresh = [
                            item for item in relevant
                            if item.metric_observed_at is None
                            or parse_time(item.metric_observed_at) <= applied_time
                        ]
                        if not_fresh:
                            self.store.emit(
                                "optimizer.measurement.waiting", self._time(),
                                {
                                    "reason": "fresh_current_link_metric",
                                    "environment_epoch": room_after["environment_epoch"],
                                    "world_revision": room_after["revision"],
                                    "rf_applied_at": applied_at,
                                    "waiting_clients": len(not_fresh),
                                    "waiting_roles": [
                                        self._role_by_mac.get(item.sta_mac)
                                        for item in not_fresh
                                    ],
                                },
                                producer="optimizer",
                            )
                            self.store.emit(
                                "network.snapshot", self._time(),
                                self._network_payload(observed_snapshot, observer.last_raw["topology"]),
                                producer="network",
                            )
                            waiting_macs = {item.sta_mac for item in not_fresh}
                            snapshot = replace(snapshot, clients=tuple(
                                replace(item, rcpi=None, metric_observed_at=None)
                                if item.sta_mac in waiting_macs else item
                                for item in snapshot.clients
                            ))
                prior = state
                evaluation = policy.evaluate(snapshot, prior)
                if not evaluation.decisions:
                    self.store.emit(
                        "optimizer.measurement.waiting", self._time(),
                        {"reason": "controller_client_roster_empty"},
                        producer="optimizer",
                    )
                    continue
                steer_decisions = [
                    item for item in evaluation.decisions if item.action == "steer"
                ]
                fleet = _fleet_status(snapshot, provider.last_selected_sta_macs & {
                    item.sta_mac for item in snapshot.clients if item.rcpi is not None
                })
                ranked_steer_decisions = _ranked_action_batch(
                    steer_decisions, len(steer_decisions)
                )
                selected_action = (
                    ranked_steer_decisions[0]
                    if ranked_steer_decisions else None
                )
                preferred_role, preferred_mac, _preferred_container = preferred_subject
                preferred_decision = next(
                    (item for item in evaluation.decisions
                     if item.sta_mac == preferred_mac),
                    None,
                )
                decision = selected_action or preferred_decision or min(
                    evaluation.decisions,
                    key=lambda item: (
                        item.current_rcpi if item.current_rcpi is not None else 221,
                        item.sta_mac,
                    ),
                )
                subject_mac = decision.sta_mac
                subject_role = self._role_by_mac.get(subject_mac, preferred_role)
                subject_container = self._container_by_mac[subject_mac]
                now = self._time()
                window_open, window_kind = self._action_window(now, action_window)
                can_act = (
                    self.mode == "act"
                    and window_open
                    and self.action_attempts < maximum_actions
                )
                configured_batch_size = max(
                    1, int(optimizer.get("interactive_action_batch_size", 1))
                )
                batch_size = configured_batch_size if self.interactive else 1
                remaining_actions = max(0, maximum_actions - self.action_attempts)
                action_batch = (
                    ranked_steer_decisions[:min(batch_size, remaining_actions)]
                    if can_act else []
                )
                if action_batch:
                    selected_action = action_batch[0]
                if steer_decisions and self.mode == "recommend":
                    state = _recommendation_state(prior, evaluation)
                elif steer_decisions and self.mode == "act" and not can_act:
                    state = (
                        _deferred_state(prior, evaluation)
                        if not window_open else _recommendation_state(prior, evaluation)
                    )
                elif selected_action is not None and can_act:
                    state = _single_action_state(
                        prior, evaluation, selected_action.sta_mac
                    )
                else:
                    state = evaluation.state
                subject_state = state.for_sta(subject_mac)
                candidates = []
                for item in snapshot.candidates_for(subject_mac):
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
                        "subject_role": subject_role,
                        "subject_mac": subject_mac,
                        "subject_container": subject_container,
                        "decision": decision.to_dict(),
                        "policy_state": asdict(subject_state),
                        "candidates": candidates,
                        "candidate_transactions": len(provider.last_raw),
                        "action_window_ms": (
                            None if self.interactive else action_window
                        ),
                        "action_window_kind": window_kind,
                        "action_window_open": window_open,
                        "automatic_actuation": self.mode == "act",
                        "automatic_actuation_ready": can_act,
                        "actuation_path": (
                            "room_serialized_rf_assist_btm"
                            if self.steering_transaction is not None else
                            "btm_request"
                        ),
                        "optimization_goal": "best_eligible_same_network_band_ap",
                        "minimum_target_gain_rcpi": policy.config.minimum_target_gain_rcpi,
                        "expected_online_clients": policy.config.expected_clients,
                        "kernel_current_link_measurements": [
                            {"sta_mac": item.sta_mac, "bssid": item.connected_bssid,
                             "rssi_dbm": _rssi(item.rcpi), "observed_at": item.metric_observed_at,
                             "source": item.measurement_source}
                            for item in snapshot.clients
                            if item.measurement_source == "client_kernel_iw_link_after_wlan_traffic_probe"
                        ],
                        **({"environment_epoch": room_after["environment_epoch"]} if room_after else {}),
                        "fleet": {
                            **fleet,
                            "actionable_clients": len(steer_decisions),
                        },
                        "actions_used": self.action_attempts,
                        "maximum_actions": maximum_actions,
                        "action_batch_size": len(action_batch),
                        "action_batch_limit": batch_size,
                        "action_batch_subjects": [
                            self._role_by_mac.get(item.sta_mac, item.sta_mac)
                            for item in action_batch
                        ],
                        "observation_elapsed_ms": round(
                            (time.monotonic() - cycle_started) * 1000, 3
                        ),
                    },
                    producer="optimizer",
                )
                if action_batch:
                    batch_guard = None
                    if room_after is not None:
                        batch_guard = (
                            room_after["revision"],
                            room_after["environment_epoch"],
                            room_after["daemon"]["instance_id"],
                        )
                    for batch_index, decision in enumerate(action_batch, 1):
                        if self.room_state is not None:
                            current_room = self.room_state()
                            current_guard = (
                                current_room["revision"],
                                current_room["environment_epoch"],
                                current_room["daemon"]["instance_id"],
                            )
                            if (
                                current_guard != batch_guard
                                or current_room.get("movement_active")
                            ):
                                self.store.emit(
                                    "optimizer.batch.aborted", self._time(),
                                    {
                                        "reason": (
                                            "movement_active"
                                            if current_room.get("movement_active")
                                            else "room_environment_changed"
                                        ),
                                        "completed_actions": batch_index - 1,
                                        "planned_actions": len(action_batch),
                                        "expected": batch_guard,
                                        "actual": current_guard,
                                    },
                                    producer="optimizer",
                                )
                                break
                            # The policy initially left deferred batch members
                            # in holding state. Mark only the action that is
                            # about to be sent as pending, so an interrupted
                            # batch cannot leave unsent clients in timeout.
                            state = state.replace(
                                evaluation.state.for_sta(decision.sta_mac)
                            )
                        subject_mac = decision.sta_mac
                        subject_role = self._role_by_mac[subject_mac]
                        self.action_attempts += 1
                        self.store.emit(
                            "optimizer.action", self._time(),
                            {"phase": "requested", "subject_role": subject_role,
                             "decision": decision.to_dict(),
                             "batch_index": batch_index,
                             "batch_size": len(action_batch),
                             "actions_used": self.action_attempts,
                             "measurement_reused": batch_index > 1},
                            producer="optimizer",
                        )
                        source_ap_role = self._ap_role_by_bssid.get(
                            decision.source_bssid
                        )
                        target_ap_role = self._ap_role_by_bssid.get(
                            decision.target_bssid or ""
                        )
                        execute_action = lambda current=decision: actuator.execute(
                            current, snapshot
                        )
                        if self.steering_transaction is not None:
                            if source_ap_role is None or target_ap_role is None:
                                raise ValueError(
                                    "steering source or target is not bound to a room AP"
                                )
                            result = self.steering_transaction(
                                subject_role,
                                source_ap_role,
                                target_ap_role,
                                decision.target_band or decision.current_band or "",
                                execute_action,
                                expected_epoch=room_after["environment_epoch"] if room_after else None,
                            )
                        else:
                            result = execute_action()
                        if result.success:
                            self.action_successes += 1
                        self.store.emit(
                            "optimizer.action", self._time(),
                            {"phase": "submitted", "subject_role": subject_role,
                             "decision": decision.to_dict(),
                             "result": result.to_dict(),
                             "batch_index": batch_index,
                             "batch_size": len(action_batch),
                             "actions_used": self.action_attempts,
                             "measurement_reused": batch_index > 1},
                            producer="optimizer",
                        )
                        if not result.success:
                            self.store.emit(
                                "optimizer.batch.aborted", self._time(),
                                {
                                    "reason": "steering_request_failed",
                                    "completed_actions": batch_index - 1,
                                    "planned_actions": len(action_batch),
                                    "subject_role": subject_role,
                                },
                                producer="optimizer",
                            )
                            break
                        verified = verifier.verify(
                            decision.sta_mac,
                            decision.target_bssid,
                            timeout_seconds=policy.config.steer_timeout_seconds,
                        )
                        if verified.success:
                            self.verification_successes += 1
                        self.store.emit(
                            "optimizer.verification", self._time(),
                            {
                                **verified.to_dict(),
                                "subject_role": subject_role,
                                "subject_mac": subject_mac,
                                "target_bssid": decision.target_bssid,
                                "batch_index": batch_index,
                                "batch_size": len(action_batch),
                            },
                            producer="optimizer",
                        )
                        if not verified.success:
                            self.store.emit(
                                "optimizer.batch.aborted", self._time(),
                                {
                                    "reason": "verification_failed",
                                    "completed_actions": batch_index - 1,
                                    "planned_actions": len(action_batch),
                                    "subject_role": subject_role,
                                },
                                producer="optimizer",
                            )
                            break
            except CandidateMetricsUnavailable as error:
                if not self.interactive:
                    self._record_error("optimizer", error, fatal=True)
                    return
                consecutive_measurement_failures += 1
                retry_delay = min(
                    30.0,
                    max(5.0, interval) * 2 ** min(consecutive_measurement_failures - 1, 3),
                )
                state = _interrupted_measurement_state(state)
                self._record_error("optimizer", error, fatal=False)
                self.store.emit(
                    "optimizer.measurement.unavailable", self._time(),
                    {
                        "status": "unavailable",
                        "mode": self.mode,
                        "reason": "candidate_metrics_unavailable",
                        "message": str(error),
                        "consecutive_failures": consecutive_measurement_failures,
                        "retry_delay_seconds": retry_delay,
                        "automatic_actuation": self.mode == "act",
                        "automatic_actuation_ready": False,
                        "actions_used": self.action_attempts,
                        "maximum_actions": maximum_actions,
                        "policy_hold_reset": True,
                        "fleet": {"measurement_complete": False, "converged": False},
                        "failed_transactions": [
                            transaction for transaction in provider.last_raw
                            if "error" in transaction
                        ],
                    },
                    producer="optimizer",
                )
            except (CandidateMetricsError, OSError, ValueError, KeyError) as error:
                self._record_error("optimizer", error, fatal=True)
                return
            finally:
                self._candidate_active.clear()
            elapsed = time.monotonic() - cycle_started
            if self._sleep(retry_delay or max(0.1, interval - elapsed)):
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
