"""
Thin socket client for Lua → Python ranker communication.
Reads a JSON request from stdin, sends it to the Unix socket,
and prints the response. Lua calls this via io.popen to avoid
shell-based JSON injection.

A SIGALRM hard timeout (3s) ensures the process dies even if the
socket call hangs; Lua then falls back to original candidate order.
"""
import argparse
import json
import signal
import socket
import sys

HARD_TIMEOUT = 3  # seconds


def _on_timeout(*_):
    sys.exit(1)


def send(sock_path: str, request: str, timeout: float = 2.0) -> str:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(sock_path)
    sock.sendall(request.encode() + b"\n")
    response = b""
    while b"\n" not in response:
        response += sock.recv(4096)
    sock.close()
    return response.decode()


def main():
    signal.signal(signal.SIGALRM, _on_timeout)
    signal.alarm(HARD_TIMEOUT)

    parser = argparse.ArgumentParser()
    parser.add_argument("sock_path", help="Path to Unix domain socket")
    parser.add_argument("--async", dest="async_mode", action="store_true",
                        help="Fire and forget (no response expected)")
    args = parser.parse_args()

    request = sys.stdin.read()

    if args.async_mode:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect(args.sock_path)
            sock.sendall(request.encode() + b"\n")
            sock.close()
        except Exception:
            pass
        return

    try:
        response = send(args.sock_path, request)
        sys.stdout.write(response)
    except Exception as e:
        sys.stderr.write(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
