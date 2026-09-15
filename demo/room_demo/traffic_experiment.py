from __future__ import annotations

import copy
from contextlib import contextmanager, nullcontext
import ipaddress
import json
import math
import os
import re
import signal
import subprocess
import threading
import time

from optimizer.band_scan import NativeBandScanner


def phase_at(profile, time_ms):
    if profile:
        return next(((index, phase) for index, phase in enumerate(profile["phases"])
                     if phase["start_ms"] <= time_ms < phase["end_ms"]), None)
    return None


def packet_counts(output):
    match = re.search(r"(\d+) packets transmitted,\s*(\d+) (?:packets )?received", output)
    return ({"transmitted_packets": int(match[1]), "received_echo_replies": int(match[2])}
            if match else {"transmitted_packets": None, "received_echo_replies": None})


class TrafficCancelled(RuntimeError):
    pass


def namespace_ping(container, target, phase, remaining_ms, *, admit=nullcontext):
    deadline = time.monotonic() + remaining_ms / 1000
    NativeBandScanner._validate_container(container)
    address = ipaddress.ip_address(target)
    if address.version != 4 or not any(address in ipaddress.ip_network(network)
                                       for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise ValueError("traffic target must be the configured private IPv4 lab gateway")
    state = subprocess.run(["lxc", "query", f"/1.0/instances/{container}/state"], check=True,
                           capture_output=True, text=True, timeout=3)
    namespace_pid = json.loads(state.stdout)["pid"]
    if type(namespace_pid) is not int or namespace_pid <= 1:
        raise ValueError("traffic source container is not running")
    namespace_fd = os.open(f"/proc/{namespace_pid}/ns/net", os.O_RDONLY)
    try:
        seconds = min(20, deadline - time.monotonic())
        if seconds <= 0:
            raise TrafficCancelled("traffic phase expired while resolving its container")
        packets = max(1, math.floor(seconds * phase["packets_per_second"]))
        command = ["nsenter", f"--net=/proc/self/fd/{namespace_fd}", "--", "ping", "-n", "-q",
                   "-I", "wlan0", "-i", str(1 / phase["packets_per_second"]),
                   "-s", str(phase["payload_bytes"]), "-c", str(packets),
                   "-w", str(math.ceil(seconds)), str(address)]
        with admit():
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, start_new_session=True, pass_fds=(namespace_fd,))
        return process, packets
    finally:
        os.close(namespace_fd)


class TrafficExperiment:
    def __init__(self, target, publish, *, launcher=namespace_ping):
        self.target = target
        self.publish = publish
        self.launcher = launcher
        self._condition = threading.Condition()
        self._desired = None
        self._version = 0
        self._closed = False
        self._thread = None
        self._state = {"state": "idle", "history": []}
        self._process = None

    def snapshot(self):
        with self._condition:
            return copy.deepcopy(self._state)

    def sync(self, key, phase=None, container=None, remaining_ms=0):
        with self._condition:
            if self._closed:
                return
            if key is not None and self._desired and self._desired["key"] == key:
                return
            if key is None and self._desired is None:
                return
            self._version += 1
            if self._process is not None:
                self._signal(self._process, signal.SIGINT)
            self._desired = ({"key": key, "phase": copy.deepcopy(phase), "container": container,
                              "deadline": time.monotonic() + remaining_ms / 1000}
                             if key is not None else None)
            if self._thread is None and key is not None:
                self._thread = threading.Thread(target=self._worker, name="room-traffic", daemon=True)
                self._thread.start()
            self._condition.notify_all()

    @staticmethod
    def _signal(process, signum):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    @contextmanager
    def _admit(self, version, deadline):
        with self._condition:
            if self._closed or self._version != version or time.monotonic() >= deadline:
                raise TrafficCancelled("traffic phase no longer owns the playback")
            yield

    def _report(self, state, result=None):
        with self._condition:
            history = self._state["history"]
            if result is not None:
                history = (history + [result])[-8:]
            self._state = {"world_sha256": self._state.get("world_sha256"), **state, "history": history}
            payload = copy.deepcopy(self._state)
        self.publish(payload)

    def _worker(self):
        handled = -1
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._version != handled)
                if self._closed:
                    return
                handled = self._version
                job = copy.deepcopy(self._desired)
            if job is None:
                self._report({"state": "off"})
                continue
            phase = job["phase"]
            detail = {"key": list(job["key"]), "world_sha256": job["key"][0], "role": phase["role"],
                      "source": "bound_client_wlan0_icmp_echo", "target": self.target,
                      "requested_packets_per_second": phase["packets_per_second"],
                      "payload_bytes": phase["payload_bytes"], "transmitted_packets": None,
                      "received_echo_replies": None}
            process = None
            started = time.monotonic()
            cancelled = False
            try:
                remaining_ms = max(0, round((job["deadline"] - started) * 1000))
                if not remaining_ms:
                    self._report({**detail, "state": "expired"}, {**detail, "state": "expired"})
                    continue
                process, requested = self.launcher(job["container"], self.target, phase, remaining_ms,
                                                   admit=lambda: self._admit(handled, job["deadline"]))
                with self._condition:
                    self._process = process
                    cancelled = self._closed or self._version != handled
                if cancelled:
                    self._signal(process, signal.SIGINT)
                if not cancelled:
                    self._report({**detail, "state": "running", "requested_packets": requested})
                while process.poll() is None:
                    with self._condition:
                        cancelled = self._closed or self._version != handled
                        if not cancelled and time.monotonic() < job["deadline"]:
                            self._condition.wait(timeout=min(0.1, max(0, job["deadline"] - time.monotonic())))
                            continue
                    self._signal(process, signal.SIGINT)
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self._signal(process, signal.SIGKILL)
                    break
                output, _unused = process.communicate(timeout=2)
                with self._condition:
                    cancelled = cancelled or self._closed or self._version != handled
                counts = packet_counts(output)
                result = {**detail, **counts, "requested_packets": requested,
                          "elapsed_seconds": round(time.monotonic() - started, 3),
                          "returncode": process.returncode,
                          "state": "cancelled" if cancelled else
                                   ("completed" if counts["transmitted_packets"] is not None else "failed")}
                if counts["transmitted_packets"] is None:
                    result["error"] = output[-500:]
                self._report(result, result)
            except TrafficCancelled:
                self._report({**detail, "state": "cancelled"}, {**detail, "state": "cancelled"})
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                self._report({**detail, "state": "failed", "error": str(error)},
                             {**detail, "state": "failed", "error": str(error)})
            finally:
                if process is not None and process.poll() is None:
                    self._signal(process, signal.SIGKILL)
                    process.communicate(timeout=2)
                with self._condition:
                    self._process = None

    def close(self):
        with self._condition:
            self._closed = True
            self._version += 1
            self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=7)
            if thread.is_alive():
                raise RuntimeError("bounded room traffic worker did not stop")
