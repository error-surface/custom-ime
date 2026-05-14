import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
from ranker.server import RankerServer


@pytest.fixture
def full_stack(tmp_path):
    sock_path = Path(f"/tmp/ime_int_{os.getpid()}.sock")
    srv = RankerServer(socket_path=sock_path, db_path=tmp_path / "int.db")
    thread = threading.Thread(target=srv.serve, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield sock_path
    srv.stop()


def _req(sock_path, data):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(sock_path))
    client.sendall(json.dumps(data, ensure_ascii=False).encode() + b"\n")
    resp = b""
    while b"\n" not in resp:
        resp += client.recv(4096)
    client.close()
    return json.loads(resp)


def test_full_learning_cycle(full_stack):
    sock = full_stack
    cands = ["测试", "策时", "侧视"]

    for _ in range(5):
        _req(sock, {"action": "select", "pinyin": "ceshi", "context": "",
                     "chosen": "侧视", "candidates": cands, "position": 2})
    resp = _req(sock, {"action": "rank", "pinyin": "ceshi", "context": "", "candidates": cands})
    assert resp["ranked"][0] == "侧视"

    for _ in range(5):
        _req(sock, {"action": "select", "pinyin": "ceshi", "context": "单元",
                     "chosen": "测试", "candidates": cands, "position": 0})
    resp = _req(sock, {"action": "rank", "pinyin": "ceshi", "context": "单元", "candidates": cands})
    assert resp["ranked"][0] == "测试"
