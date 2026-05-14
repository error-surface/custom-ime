import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
from ranker.server import RankerServer
_counter = 0

@pytest.fixture
def server(tmp_path):
    global _counter
    _counter += 1
    sock_path = Path(f"/tmp/ime_t{os.getpid()}_{_counter}.sock")
    srv = RankerServer(socket_path=sock_path, db_path=tmp_path / "test.db")
    thread = threading.Thread(target=srv.serve, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield srv, sock_path
    srv.stop()


def _send(sock_path, request):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(sock_path))
    client.sendall(json.dumps(request, ensure_ascii=False).encode() + b"\n")
    resp = b""
    while b"\n" not in resp:
        chunk = client.recv(4096)
        if not chunk:
            break
        resp += chunk
    client.close()
    return json.loads(resp)


def test_rank_action(server):
    _, sock_path = server
    resp = _send(sock_path, {"action": "rank", "pinyin": "nihao", "context": "",
                             "candidates": ["你好", "泥号", "拟好"]})
    assert set(resp["ranked"]) == {"你好", "泥号", "拟好"}


def test_select_action(server):
    _, sock_path = server
    resp = _send(sock_path, {"action": "select", "pinyin": "nihao", "context": "",
                             "chosen": "你好", "candidates": ["你好", "泥号"], "position": 0})
    assert resp["status"] == "ok"


def test_select_then_rank(server):
    _, sock_path = server
    for _ in range(3):
        _send(sock_path, {"action": "select", "pinyin": "nihao", "context": "",
                          "chosen": "拟好", "candidates": ["你好", "泥号", "拟好"], "position": 2})
    resp = _send(sock_path, {"action": "rank", "pinyin": "nihao", "context": "",
                             "candidates": ["你好", "泥号", "拟好"]})
    assert resp["ranked"][0] == "拟好"


def test_invalid_action(server):
    _, sock_path = server
    resp = _send(sock_path, {"action": "invalid"})
    assert "error" in resp


def test_special_char_candidates(server):
    _, sock_path = server
    cands = ['a"b', r"a\\b", "line\nbreak", "tab\tchar"]
    resp = _send(sock_path, {"action": "rank", "pinyin": "x", "context": "", "candidates": cands})
    assert set(resp["ranked"]) == set(cands)

    resp = _send(
        sock_path,
        {"action": "select", "pinyin": "x", "context": "", "chosen": 'a"b', "candidates": cands, "position": 0},
    )
    assert resp["status"] == "ok"
