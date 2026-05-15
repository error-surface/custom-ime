import json
import socket
import threading
import time
from pathlib import Path

from ranker.config import SOCKET_PATH, DB_PATH
from ranker.db import SelectionDB
from ranker.model import RankingModel
from ranker.seed_data import seed as seed_db
from ranker.sync_phrases import sync_full, sync_incremental


class RankerServer:
    SYNC_INTERVAL = 1800  # full sync every 30 minutes

    def __init__(self, socket_path: Path = SOCKET_PATH,
                 db_path: Path = DB_PATH):
        self._socket_path = socket_path
        self._db = SelectionDB(db_path)
        self._model = RankingModel(self._db)
        self._server_socket = None
        self._running = False

    JANITOR_INTERVAL = 21600   # trim every 6 hours
    VACUUM_INTERVAL = 86400    # vacuum every 24 hours

    def _start_sync_thread(self):
        """Background thread: periodic full sync to custom_phrase.txt."""
        def _sync_loop():
            while self._running:
                try:
                    count = sync_full()
                    if count:
                        print(f"[sync] full sync: {count} phrases")
                except Exception as e:
                    print(f"[sync] error: {e}")
                time.sleep(self.SYNC_INTERVAL)

        t = threading.Thread(target=_sync_loop, daemon=True)
        t.start()

    def _start_janitor_thread(self):
        """Background thread: periodic DB cleanup (trim old data, vacuum)."""
        def _janitor_loop():
            last_vacuum = 0
            while self._running:
                try:
                    self._db.trim_old_selections(keep_days=90)
                    self._db.remove_noise_words(max_skip_ratio=5.0)
                    now = time.time()
                    if now - last_vacuum > self.VACUUM_INTERVAL:
                        self._db._conn.execute("VACUUM")
                        last_vacuum = now
                        print("[janitor] vacuum complete")
                except Exception as e:
                    print(f"[janitor] error: {e}")
                time.sleep(self.JANITOR_INTERVAL)

        t = threading.Thread(target=_janitor_loop, daemon=True)
        t.start()

    def serve(self):
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self._socket_path.exists():
            self._socket_path.unlink()

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(str(self._socket_path))
        self._server_socket.listen(5)
        self._server_socket.settimeout(0.5)
        self._running = True

        # Seed common vocabulary for cold-start
        try:
            inserted, boosted = seed_db()
            if inserted or boosted:
                print(f"[seed] {inserted} new + {boosted} boosted")
        except Exception as e:
            print(f"[seed] error: {e}")

        # Initial full sync + start periodic sync thread
        try:
            count = sync_full()
            print(f"[sync] initial sync: {count} phrases")
        except Exception as e:
            print(f"[sync] initial sync error: {e}")
        self._start_sync_thread()
        self._start_janitor_thread()

        while self._running:
            try:
                client, _ = self._server_socket.accept()
            except socket.timeout:
                continue
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client: socket.socket):
        try:
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            request = json.loads(data.decode("utf-8"))
            response = self._dispatch(request)
            client.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
        except Exception as e:
            try:
                client.sendall(json.dumps({"error": str(e)}).encode("utf-8") + b"\n")
            except OSError:
                pass
        finally:
            client.close()

    def _dispatch(self, request: dict) -> dict:
        action = request.get("action")
        if action == "rank":
            ranked = self._model.rank(
                pinyin=request["pinyin"],
                context=request.get("context", ""),
                candidates=request["candidates"],
            )
            return {"ranked": ranked}
        elif action == "select":
            self._model.record(
                pinyin=request["pinyin"],
                context=request.get("context", ""),
                chosen=request["chosen"],
                candidates=request["candidates"],
                position=request.get("position", 0),
            )
            # Incremental sync: immediately persist to custom_phrase.txt
            try:
                sync_incremental(request["chosen"], request["pinyin"])
            except Exception as e:
                print(f"[sync] incremental error: {e}")
            return {"status": "ok"}
        elif action == "reject":
            self._model.reject(
                pinyin=request["pinyin"],
                context=request.get("context", ""),
                rejected=request["rejected"],
                candidates=request.get("candidates", []),
            )
            return {"status": "ok"}
        else:
            return {"error": f"unknown action: {action}"}

    def stop(self):
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        if self._socket_path.exists():
            self._socket_path.unlink()
        self._db.close()


def main():
    import signal
    server = RankerServer()
    signal.signal(signal.SIGTERM, lambda *_: server.stop())
    print(f"Ranker listening on {SOCKET_PATH}")
    try:
        server.serve()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
