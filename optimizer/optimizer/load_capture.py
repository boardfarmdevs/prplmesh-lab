from __future__ import annotations

import argparse
import json
import os
import select
import socket
import struct
import sys
import time


def mac(raw):
    return ":".join(f"{octet:02x}" for octet in raw)


class NativeLoadDecoder:
    def __init__(self):
        self.pending = {}
        self.completed = {}

    def feed(self, frame, timestamp):
        if len(frame) < 22 or frame[12:14] != b"\x89\x3a":
            return None
        cmdu = frame[14:]
        if cmdu[0] != 0 or cmdu[2:4] != b"\x80\x0c":
            return None
        source = mac(frame[6:12])
        identifier = struct.unpack_from("!H", cmdu, 4)[0]
        key = (source, identifier)
        self.pending = {key: value for key, value in self.pending.items() if 0 <= timestamp - value["started"] <= 5}
        self.completed = {key: value for key, value in self.completed.items() if 0 <= timestamp - value <= 5}
        if key in self.completed:
            return None
        if len(self.pending) >= 1024 and key not in self.pending:
            raise ValueError("native AP metrics fragment budget exceeded")
        assembly = self.pending.setdefault(key, {"started": timestamp, "parts": {}, "last": None, "invalid": False})
        fragment, payload = cmdu[6], cmdu[8:]
        if fragment in assembly["parts"] and assembly["parts"][fragment] != payload:
            assembly["invalid"] = True
        assembly["parts"][fragment] = payload
        if cmdu[7] & 0x80:
            if assembly["last"] is not None and assembly["last"] != fragment:
                assembly["invalid"] = True
            assembly["last"] = fragment
        if sum(map(len, assembly["parts"].values())) > 65535:
            raise ValueError("oversized native AP metrics message")
        last = assembly["last"]
        if assembly["invalid"] or last is None or set(assembly["parts"]) != set(range(last + 1)):
            return None
        payload = b"".join(assembly["parts"][index] for index in range(last + 1))
        del self.pending[key]
        position = 0
        loads, traffic = [], []
        while position + 3 <= len(payload):
            kind, length = struct.unpack_from("!BH", payload, position)
            data = payload[position + 3:position + 3 + length]
            position += 3 + length
            if len(data) != length:
                return None
            if kind == 0:
                if length:
                    return None
                if len(self.completed) >= 4096:
                    raise ValueError("native AP metrics deduplication budget exceeded")
                self.completed[key] = timestamp
                return {"source": source, "message_id": identifier, "received_at": timestamp,
                        "loads": loads, "traffic": traffic}
            if kind == 0x94:
                if length < 10:
                    return None
                loads.append({"bssid": mac(data[:6]), "utilization": data[6],
                              "station_count": struct.unpack_from("!H", data, 7)[0]})
            elif kind == 0xA2:
                if length != 34:
                    return None
                sent, received = struct.unpack_from("!II", data, 14)
                traffic.append({"sta_mac": mac(data[:6]), "packets_sent": sent, "packets_received": received})
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opt-in native 1905 AP metrics receiver; no RF oracle")
    parser.add_argument("--watch-stdin", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid():
        parser.error("requires root in the controller network namespace")
    decoder = NativeLoadDecoder()
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x893a)) as receiver:
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
        print(json.dumps({"kind": "ready"}), flush=True)
        checked_at = time.monotonic()
        while True:
            inputs = [receiver] + ([sys.stdin] if args.watch_stdin else [])
            ready, _, _ = select.select(inputs, [], [], 1)
            if args.watch_stdin and sys.stdin in ready and not os.read(sys.stdin.fileno(), 1):
                return 0
            now = time.monotonic()
            if now - checked_at >= 1:
                _packets, drops = struct.unpack("II", receiver.getsockopt(263, 6, 8))
                if drops:
                    raise RuntimeError("native load receiver dropped packets; refusing incomplete observations")
                checked_at = now
            if receiver not in ready:
                continue
            frame = receiver.recv(65536)
            timestamp = time.time()
            result = decoder.feed(frame, time.monotonic())
            if result is not None:
                result["received_at"] = timestamp
                result["kind"] = "ap_metrics"
                result["monotonic_ns"] = time.monotonic_ns()
                print(json.dumps(result, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
