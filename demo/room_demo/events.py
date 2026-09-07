from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any


class EventStore:
    """Thread-safe run state, ordered event journal, and SSE replay source."""

    def __init__(
        self,
        run_id: str,
        world: dict[str, Any],
        event_path: Path,
        *,
        persist: bool = True,
    ):
        self.run_id = run_id
        self.world = world
        self.initial_world = copy.deepcopy(world)
        self.event_path = event_path
        self.persist = persist
        self._events: list[dict[str, Any]] = []
        self._condition = threading.Condition()
        self._started_monotonic = time.monotonic()
        first = world.get("generations", [{}])[0]
        base_positions = first.get("positions", {})
        base_presence = first.get("present", {})
        self._state: dict[str, Any] = {
            "schema": "easymesh.room-demo.state.v2",
            "run_id": run_id,
            "state": "preparing",
            "run_state": "preparing",
            "scenario_clock_state": "stopped",
            "interaction_state": "unowned",
            "optimizer_authority": "observe",
            "act_arm_state": "disarmed",
            "scenario": world["name"],
            "world_url": "/api/demo/world",
            "duration_ms": world["duration_ms"],
            "tick_ms": world["tick_ms"],
            "world_time_ms": 0,
            "clocks": {"run_elapsed_ms": 0, "scenario_time_ms": 0},
            "sequence": 0,
            "world_revision": 0,
            "environment_epoch": 0,
            "medium": {},
            "roles": {
                role: {
                    "kind": kind,
                    "base_position": copy.deepcopy(base_positions.get(role)),
                    "authoritative_position": copy.deepcopy(base_positions.get(role)),
                    "present": bool(base_presence.get(role, True)),
                    "control_state": "scripted",
                }
                for role, kind in sorted(world.get("roles", {}).items())
            },
            "leases": {},
            "movements": {},
            "recording": {},
            "optimizer": {},
            "network": {},
            "health": {},
            "outcome": None,
            "restored": False,
            "error": None,
            "latest": {},
            "evidence_digest": None,
            "state_digest": None,
        }

    @staticmethod
    def _event_hash(event: dict[str, Any]) -> str:
        unsigned = dict(event)
        unsigned.pop("event_hash", None)
        material = json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(material).hexdigest()

    def _set_run_state(self, value: str) -> None:
        self._state["state"] = value
        self._state["run_state"] = value

    def _state_hash(self) -> str:
        unsigned = copy.deepcopy(self._state)
        unsigned.pop("state_digest", None)
        material = json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(material).hexdigest()

    def _reduce(self, event: dict[str, Any]) -> None:
        kind = event["kind"]
        payload = event.get("payload") or {}
        self._state["clocks"] = {
            "run_elapsed_ms": int(event.get("run_elapsed_ms", event["world_time_ms"])),
            "scenario_time_ms": int(event.get("scenario_time_ms", event["world_time_ms"])),
        }
        self._state["world_time_ms"] = self._state["clocks"]["scenario_time_ms"]
        if "revision" in payload:
            self._state["world_revision"] = max(
                self._state["world_revision"], int(payload["revision"])
            )
        if "environment_epoch" in payload:
            self._state["environment_epoch"] = max(
                self._state["environment_epoch"], int(payload["environment_epoch"])
            )
        if kind == "room.world.committed":
            self.world = copy.deepcopy(payload["world"])
            self._state.update({"scenario": self.world["name"],
                                "duration_ms": self.world["duration_ms"],
                                "tick_ms": self.world["tick_ms"],
                                "movements": {}, "recording": {}, "optimizer": {}, "network": {}, "health": {}})
            self._state["roles"] = {
                role: {"kind": self.world["roles"].get(role, "station"),
                       "base_position": copy.deepcopy(value["position"]),
                       "authoritative_position": copy.deepcopy(value["position"]),
                       "present": value["present"], "control_state": "manual" if value["present"] else "absent"}
                for role, value in payload["roles"].items()
            }
            for stale_kind in list(self._state["latest"]):
                if stale_kind != kind and stale_kind.startswith(("room.", "interaction.movement.", "interaction.recording.", "network.", "optimizer.", "health.", "traffic.")):
                    del self._state["latest"][stale_kind]
        elif kind.startswith("interaction.playback."):
            self._state["playback"] = copy.deepcopy(payload["playback"])
        elif kind in {"room.position.committed", "room.presence.committed"}:
            role = payload.get("role")
            if role in self._state["roles"]:
                reduced = self._state["roles"][role]
                if payload.get("position") is not None:
                    reduced["authoritative_position"] = copy.deepcopy(payload["position"])
                if "present" in payload:
                    reduced["present"] = bool(payload["present"])
                reduced["control_state"] = (
                    "manual" if reduced["present"] else "absent"
                )
        elif kind.startswith("interaction.movement.") and payload.get("movement"):
            movement = copy.deepcopy(payload["movement"])
            movement_id = movement.get("id")
            role = movement.get("role")
            if movement_id:
                self._state["movements"][movement_id] = movement
            if role in self._state["roles"]:
                if movement.get("position") is not None:
                    self._state["roles"][role]["authoritative_position"] = copy.deepcopy(
                        movement["position"]
                    )
                self._state["roles"][role]["control_state"] = (
                    "moving" if movement.get("status") in {"running", "paused"} else "manual"
                )
        elif kind == "interaction.lease.acquired":
            self._state["interaction_state"] = "leased"
            self._state["leases"] = {"active": copy.deepcopy(payload)}
        elif kind in {"interaction.lease.released", "interaction.lease.expired"}:
            self._state["interaction_state"] = "unowned"
            self._state["leases"] = {}
        elif kind.startswith("interaction.recording."):
            self._state["recording"] = copy.deepcopy(payload.get("recording") or payload)
        elif kind in {"rf.generation.applied", "rf.generation.noop"}:
            self._state["medium"].update({
                "instance_id": payload.get("daemon_instance_id")
                or self._state["medium"].get("instance_id"),
                "generation": payload.get("daemon_generation"),
                "last_change": kind,
                "changed_link_count": payload.get("changed_link_count", 0),
            })
        elif kind == "interaction.session.ready":
            self._state["medium"].update({
                "instance_id": payload.get("daemon_instance_id"),
                "generation": payload.get("daemon_generation"),
                "contaminated": False,
            })
        elif kind == "medium.external_write_detected":
            self._state["medium"].update({
                "contaminated": True,
                "contamination": copy.deepcopy(payload),
            })
        elif kind in {"optimizer.evaluation", "optimizer.measurement.unavailable"}:
            self._state["optimizer"] = copy.deepcopy(payload)
        elif kind == "network.snapshot":
            self._state["network"] = copy.deepcopy(payload)
        elif kind == "health.sample":
            self._state["health"] = copy.deepcopy(payload)

    def _publish(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("schema") != "easymesh.room-demo.event.v1":
            raise ValueError("unsupported room-demo event schema")
        if event.get("run_id") != self.run_id:
            raise ValueError("event run_id does not match the active run")
        with self._condition:
            if self._events and event["sequence"] <= self._events[-1]["sequence"]:
                raise ValueError("event sequence is not strictly increasing")
            if event.get("event_hash"):
                if event["event_hash"] != self._event_hash(event):
                    raise ValueError("event hash does not match event contents")
                expected_previous = (
                    self._events[-1].get("event_hash") if self._events else None
                )
                if event.get("previous_event_hash") != expected_previous:
                    raise ValueError("event hash chain is discontinuous")
            self._events.append(event)
            kind = event["kind"]
            self._state["sequence"] = event["sequence"]
            self._state["latest"][kind] = event
            self._reduce(event)
            if kind == "runner.preflight":
                self._set_run_state("ready")
            elif kind in {"scenario.started", "scenario.clock", "scenario.mark",
                          "scenario.generation"}:
                self._set_run_state("running")
                self._state["scenario_clock_state"] = "playing"
            elif kind == "rf.restore.started":
                self._set_run_state("restoring")
            elif kind == "rf.restore.completed":
                self._state["restored"] = bool(event["payload"].get("verified"))
            elif kind == "scenario.completed":
                payload = event["payload"]
                self._set_run_state(payload["outcome"])
                self._state["scenario_clock_state"] = "stopped"
                self._state["outcome"] = payload["outcome"]
                self._state["restored"] = bool(payload["restored"])
                self._state["error"] = payload.get("error")
                self._state["run_directory"] = payload.get("run_directory")
            elif kind == "demo.state":
                self._set_run_state(
                    event["payload"].get("state", self._state["state"])
                )
                mode = str(event["payload"].get("mode") or "")
                authority = mode.rsplit("-", 1)[-1]
                if authority == "act":
                    self._state["optimizer_authority"] = "act-capable"
                elif authority == "recommend":
                    self._state["optimizer_authority"] = "recommend"
                elif mode:
                    self._state["optimizer_authority"] = "observe"
            elif kind == "run.completed":
                payload = event["payload"]
                self._set_run_state(payload["outcome"])
                self._state["outcome"] = payload["outcome"]
                self._state["restored"] = bool(payload["restored"])
                self._state["error"] = payload.get("error")
                self._state["scenario_clock_state"] = "stopped"
            self._state["evidence_digest"] = event.get("event_hash")
            self._state["state_digest"] = self._state_hash()
            if self.persist:
                self.event_path.parent.mkdir(parents=True, exist_ok=True)
                with self.event_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, sort_keys=True) + "\n")
            self._condition.notify_all()
            return dict(event)

    def publish(self, event: dict[str, Any]) -> None:
        """Publish an already globally sequenced event.

        This compatibility entry point is useful when loading evidence. Live
        multi-producer code should call :meth:`emit` or :meth:`ingest`.
        """
        self._publish(dict(event))

    def emit(
        self,
        kind: str,
        world_time_ms: int,
        payload: dict[str, Any] | None = None,
        *,
        producer: str = "conductor",
    ) -> dict[str, Any]:
        """Create and publish one centrally sequenced live event."""
        with self._condition:
            sequence = self._events[-1]["sequence"] + 1 if self._events else 1
            event = {
                "schema": "easymesh.room-demo.event.v1",
                "run_id": self.run_id,
                "sequence": sequence,
                "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "world_time_ms": max(0, int(world_time_ms)),
                "run_elapsed_ms": max(
                    0, round((time.monotonic() - self._started_monotonic) * 1000)
                ),
                "scenario_time_ms": max(0, int(world_time_ms)),
                "kind": kind,
                "producer": producer,
                "payload": payload or {},
                "previous_event_hash": (
                    self._events[-1].get("event_hash") if self._events else None
                ),
            }
            event["event_hash"] = self._event_hash(event)
            return self._publish(event)

    def ingest(self, event: dict[str, Any], *, producer: str = "wmdcfg") -> dict[str, Any]:
        """Re-sequence an event emitted by an independently sequenced producer."""
        if event.get("schema") != "easymesh.room-demo.event.v1":
            raise ValueError("unsupported room-demo event schema")
        if event.get("run_id") != self.run_id:
            raise ValueError("event run_id does not match the active run")
        payload = dict(event.get("payload") or {})
        payload.setdefault("producer_sequence", event.get("sequence"))
        return self.emit(
            str(event["kind"]),
            int(event.get("world_time_ms") or 0),
            payload,
            producer=producer,
        )

    def current(self) -> dict[str, Any]:
        with self._condition:
            return copy.deepcopy(self._state)

    def current_world(self) -> dict[str, Any]:
        with self._condition:
            return copy.deepcopy(self.world)

    def all(self) -> list[dict[str, Any]]:
        with self._condition:
            return [dict(event) for event in self._events]

    def after(self, sequence: int) -> list[dict[str, Any]]:
        with self._condition:
            return [event for event in self._events if event["sequence"] > sequence]

    def wait_after(self, sequence: int, timeout: float) -> list[dict[str, Any]]:
        with self._condition:
            events = [event for event in self._events if event["sequence"] > sequence]
            if events:
                return events
            self._condition.wait(timeout)
            return [event for event in self._events if event["sequence"] > sequence]

    @classmethod
    def from_evidence(cls, run_dir: Path) -> "EventStore":
        """Load a completed run without contacting the live lab."""
        world = json.loads((run_dir / "world.json").read_text(encoding="utf-8"))
        path = run_dir / "live-events.jsonl"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not rows:
            raise ValueError(f"{path} contains no events")
        store = cls(str(rows[0]["run_id"]), world, path, persist=False)
        for event in rows:
            store.publish(event)
        return store
