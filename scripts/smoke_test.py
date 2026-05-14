#!/usr/bin/env python3
"""Smoke test for the custom-ime ranker service.

Sends rank/select requests to the Unix socket and prints pass/fail results.
Usage: python scripts/smoke_test.py
"""
import json
import os
import socket
import sys
from pathlib import Path

SOCKET_PATH = Path.home() / ".local" / "share" / "custom-ime" / "ranker.sock"
TIMEOUT = 3.0

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def send_request(sock_path: Path, request: dict) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)
    sock.connect(str(sock_path))
    sock.sendall(json.dumps(request, ensure_ascii=False).encode() + b"\n")
    response = b""
    while b"\n" not in response:
        response += sock.recv(4096)
    sock.close()
    return json.loads(response)


def main():
    results = []

    # Check 1: Socket exists
    if SOCKET_PATH.exists():
        print(f"  [{PASS}] Socket exists at {SOCKET_PATH}")
        results.append(True)
    else:
        print(f"  [{FAIL}] Socket not found at {SOCKET_PATH}")
        print("    Is the ranker running? Try: ./scripts/start_ranker.sh start")
        results.append(False)
        sys.exit(1)

    # Check 2: Rank request
    try:
        resp = send_request(SOCKET_PATH, {
            "action": "rank",
            "pinyin": "ceshi",
            "context": "",
            "candidates": ["测试", "策时", "侧视"],
        })
        ranked = resp.get("ranked", [])
        if set(ranked) == {"测试", "策时", "侧视"} and len(ranked) == 3:
            print(f"  [{PASS}] Rank request returned 3 candidates")
            results.append(True)
        else:
            print(f"  [{FAIL}] Rank response unexpected: {resp}")
            results.append(False)
    except Exception as e:
        print(f"  [{FAIL}] Rank request failed: {e}")
        results.append(False)

    # Check 3: Select request
    try:
        resp = send_request(SOCKET_PATH, {
            "action": "select",
            "pinyin": "ceshi",
            "context": "",
            "chosen": "测试",
            "candidates": ["测试", "策时", "侧视"],
            "position": 0,
        })
        if resp.get("status") == "ok":
            print(f"  [{PASS}] Select request accepted")
            results.append(True)
        else:
            print(f"  [{FAIL}] Select response unexpected: {resp}")
            results.append(False)
    except Exception as e:
        print(f"  [{FAIL}] Select request failed: {e}")
        results.append(False)

    # Check 4: Round-trip learning (select then rank verifies ordering)
    try:
        for _ in range(5):
            send_request(SOCKET_PATH, {
                "action": "select",
                "pinyin": "ceshi_smoke",
                "context": "",
                "chosen": "侧视",
                "candidates": ["测试", "策时", "侧视"],
                "position": 2,
            })
        resp = send_request(SOCKET_PATH, {
            "action": "rank",
            "pinyin": "ceshi_smoke",
            "context": "",
            "candidates": ["测试", "策时", "侧视"],
        })
        if resp.get("ranked", [None])[0] == "侧视":
            print(f"  [{PASS}] Learning round-trip: '侧视' ranked first after 5 selections")
            results.append(True)
        else:
            print(f"  [{FAIL}] Learning round-trip failed: {resp}")
            results.append(False)
    except Exception as e:
        print(f"  [{FAIL}] Learning round-trip failed: {e}")
        results.append(False)

    passed = sum(results)
    total = len(results)
    print()
    if passed == total:
        print(f"  All {total} checks passed.")
    else:
        print(f"  {passed}/{total} checks passed, {total - passed} failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
