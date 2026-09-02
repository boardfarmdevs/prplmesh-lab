#!/usr/bin/env python3
"""Loopback-only forwarder from the radio VM to the nested NBAPI adapter."""

import argparse
import select
import socket
import socketserver


class Proxy(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(self.server.target, timeout=5) as upstream:
            sockets = [self.request, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], 30)
                if not readable:
                    continue
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = upstream if source is self.request else self.request
                    destination.sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, default=8092)
    args = parser.parse_args()
    with Server((args.listen, args.port), Proxy) as server:
        server.target = (args.target_host, args.target_port)
        server.serve_forever()


if __name__ == "__main__":
    main()
