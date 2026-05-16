#!/usr/bin/env python3
"""
ranker_client.py

Safe Unix-socket client for the custom-ime ranker.
Called from Lua via io.popen("python3 scripts/ranker_client.py ...") to avoid
brittle echo | nc pipelines.

Usage:
    python3 scripts/ranker_client.py <socket_path> <request_json>

Or via stdin (if only socket_path is given, reads JSON from stdin):
    echo '<request_json>' | python3 scripts/ranker_client.py <socket_path>

Exit codes:
    0  success (response printed to stdout)
    1  connection or socket error
    2  invalid arguments
"""

import json
import socket
import sys
from pathlib import Path


def send_request(sock_path: Path, request: dict) -> dict:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5.0)
    client.connect(str(sock_path))
    client.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")

    resp = b""
    while b"\n" not in resp:
        chunk = client.recv(4096)
        if not chunk:
            break
        resp += chunk
    client.close()
    return json.loads(resp.decode("utf-8"))


def main():
    if len(sys.argv) < 2:
        print("Usage: ranker_client.py <socket_path> [request_json]", file=sys.stderr)
        sys.exit(2)

    sock_path = Path(sys.argv[1])

    if len(sys.argv) >= 3:
        request_json = sys.argv[2]
    else:
        request_json = sys.stdin.read()

    if not request_json.strip():
        print("Error: empty request", file=sys.stderr)
        sys.exit(2)

    try:
        request = json.loads(request_json)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)

    if not sock_path.exists():
        print(f"Error: socket not found: {sock_path}", file=sys.stderr)
        sys.exit(1)

    try:
        response = send_request(sock_path, request)
        print(json.dumps(response, ensure_ascii=False))
    except (socket.error, OSError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
