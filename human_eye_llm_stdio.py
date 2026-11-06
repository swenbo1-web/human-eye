"""Relay MCP stdio bytes over one local TCP connection."""

import argparse
import os
import socket
import sys
from threading import Thread


_CHUNK = 64 * 1024


def _shutdown(connection, how):
    try:
        connection.shutdown(how)
    except OSError:
        pass


def relay(connection, input_fd, output_fd):
    """Copy both directions independently and drain after stdin EOF."""
    failures = []

    def upload():
        try:
            while chunk := os.read(input_fd, _CHUNK):
                connection.sendall(chunk)
        except OSError as error:
            failures.append(error)
            _shutdown(connection, socket.SHUT_RDWR)
        else:
            _shutdown(connection, socket.SHUT_WR)

    # Raw descriptor reads avoid holding a buffered Python stream lock when
    # the peer closes while the host keeps stdin open.
    Thread(target=upload, daemon=True).start()
    try:
        while chunk := connection.recv(_CHUNK):
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(output_fd, remaining)
                if not written:
                    raise OSError("Unable to write relay output")
                remaining = remaining[written:]
        if failures:
            raise failures[0]
    finally:
        _shutdown(connection, socket.SHUT_RDWR)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    input_fd, output_fd = sys.stdin.fileno(), sys.stdout.fileno()
    if os.name == "nt":
        import msvcrt

        msvcrt.setmode(input_fd, os.O_BINARY)
        msvcrt.setmode(output_fd, os.O_BINARY)
    try:
        with socket.create_connection((args.host, args.port)) as connection:
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            relay(connection, input_fd, output_fd)
    except OSError as error:
        print(f"stdio relay: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
