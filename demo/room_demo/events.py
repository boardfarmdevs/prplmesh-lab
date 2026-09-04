from __future__ import annotations

import datetime as dt
import json
import threading
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
        self.event_path = event_path
        self.persist = persist
        self._events: list[dict[str, Any]] = []
        self._condition = threading.Condition()
        self._state: dict[str, Any] = {
            "schema": "easymesh.room-demo.state.v1",
            "run_id": run_id,
            "state": "preparing",
            "scenario": world["name"],
            "world_url": "/api/demo/world",
            "duration_ms": world["duration_ms"],
            "tick_ms": world["tick_ms"],
            "world_time_ms": 0,
            "sequence": 0,
            "outcome": None,
            "restored": False,
            "error": None,
            "latest": {},
        }

    def _publish(self, event: dict[str, Any]) -> dict[str, Any]:
        if event.get("schema") != "easymesh.room-demo.event.v1":
            raise ValueError("unsupported room-demo event schema")
        if event.get("run_id") != self.run_id:
            raise ValueError("event run_id does not match the active run")
        with self._condition:
            if self._events and event["sequence"] <= self._events[-1]["sequence"]:
                raise ValueError("event sequence is not strictly increasing")
            self._events.append(event)
            kind = event["kind"]
            self._state["sequence"] = event["sequence"]
            self._state["world_time_ms"] = event["world_time_ms"]
            self._state["latest"][kind] = event
            if kind == "runner.preflight":
                self._state["state"] = "ready"
            elif kind in {"scenario.started", "scenario.clock", "scenario.mark",
                          "scenario.generation"}:
                self._state["state"] = "running"
            elif kind == "rf.restore.started":
                self._state["state"] = "restoring"
            elif kind == "rf.restore.completed":
                self._state["restored"] = bool(event["payload"].get("verified"))
            elif kind == "scenario.completed":
                payload = event["payload"]
                self._state["state"] = payload["outcome"]
                self._state["outcome"] = payload["outcome"]
                self._state["restored"] = bool(payload["restored"])
                self._state["error"] = payload.get("error")
                self._state["run_directory"] = payload.get("run_directory")
            elif kind == "demo.state":
                self._state["state"] = event["payload"].get("state", self._state["state"])
            elif kind == "run.completed":
                payload = event["payload"]
                self._state["state"] = payload["outcome"]
                self._state["outcome"] = payload["outcome"]
                self._state["restored"] = bool(payload["restored"])
                self._state["error"] = payload.get("error")
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
                "kind": kind,
                "producer": producer,
                "payload": payload or {},
            }
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
            value = dict(self._state)
            value["latest"] = dict(self._state["latest"])
            return value

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
