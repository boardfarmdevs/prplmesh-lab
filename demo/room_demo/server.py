from __future__ import annotations

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .events import EventStore


class RoomDemoServer:
    def __init__(
        self,
        address: tuple[str, int],
        store: EventStore,
        viewer_root: Path,
    ):
        self.store = store
        self.viewer_root = viewer_root.resolve()
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(address, handler)
        self.httpd.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.httpd.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="room-demo-http",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _handler(self):
        store = self.store
        viewer_root = self.viewer_root

        class Handler(BaseHTTPRequestHandler):
            server_version = "EasyMeshRoomDemo/0.1"

            def log_message(self, format, *args):
                return

            def _headers(self, status: int, content_type: str, length: int | None = None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if length is not None:
                    self.send_header("Content-Length", str(length))
                self.end_headers()

            def _json(self, value, status: int = HTTPStatus.OK):
                body = (json.dumps(value, sort_keys=True) + "\n").encode()
                self._headers(status, "application/json; charset=utf-8", len(body))
                self.wfile.write(body)

            def _static(self, relative: str):
                target = (viewer_root / relative).resolve()
                if viewer_root not in target.parents and target != viewer_root:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not target.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = target.read_bytes()
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self._headers(HTTPStatus.OK, content_type, len(body))
                self.wfile.write(body)

            def _events(self, parsed):
                query = parse_qs(parsed.query)
                raw = self.headers.get("Last-Event-ID") or query.get("after", ["0"])[0]
                try:
                    sequence = max(0, int(raw))
                except ValueError:
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid event sequence")
                    return
                self._headers(HTTPStatus.OK, "text/event-stream; charset=utf-8")
                try:
                    while True:
                        events = store.wait_after(sequence, 10)
                        if not events:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        for event in events:
                            encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
                            self.wfile.write(f"id: {event['sequence']}\ndata: {encoded}\n\n".encode())
                            sequence = event["sequence"]
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", "/viewer/?mode=live")
                    self.end_headers()
                elif parsed.path == "/healthz":
                    current = store.current()
                    self._json({"status": "ok", "run_id": store.run_id,
                                "state": current["state"]})
                elif parsed.path == "/api/demo/current":
                    self._json(store.current())
                elif parsed.path == "/api/demo/world":
                    self._json(store.world)
                elif parsed.path == "/api/demo/events":
                    self._events(parsed)
                elif parsed.path == "/api/demo/events.json":
                    self._json({
                        "schema": "easymesh.room-demo.events.v1",
                        "run_id": store.run_id,
                        "events": store.all(),
                    })
                elif parsed.path in {"/viewer", "/viewer/", "/viewer/index.html"}:
                    self._static("index.html")
                elif parsed.path.startswith("/viewer/"):
                    self._static(parsed.path[len("/viewer/"):])
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self):
                self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "read-only milestone")

        return Handler
