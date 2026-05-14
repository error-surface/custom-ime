import json
import sqlite3
import time
from pathlib import Path


class SelectionDB:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pinyin TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                chosen TEXT NOT NULL,
                candidates TEXT NOT NULL,
                position INTEGER NOT NULL,
                timestamp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS unigram_freq (
                word TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                skip_count INTEGER NOT NULL DEFAULT 0,
                last_used REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bigram_freq (
                prev_word TEXT NOT NULL,
                curr_word TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (prev_word, curr_word)
            );
        """)
        # Migration: add skip_count column if missing (pre-optimization databases)
        try:
            self._conn.execute("ALTER TABLE unigram_freq ADD COLUMN skip_count INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        self._conn.commit()

    def record_selection(self, pinyin: str, context: str, chosen: str,
                         candidates: list, position: int):
        now = time.time()
        self._conn.execute(
            "INSERT INTO selections (pinyin, context, chosen, candidates, position, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pinyin, context, chosen, json.dumps(candidates, ensure_ascii=False), position, now),
        )
        self._conn.execute(
            "INSERT INTO unigram_freq (word, count, skip_count, last_used) VALUES (?, 1, 0, ?) "
            "ON CONFLICT(word) DO UPDATE SET count = count + 1, last_used = ?",
            (chosen, now, now),
        )
        # Implicit negative feedback: increment skip_count for candidates
        # shown before the chosen position that the user passed over.
        for i, c in enumerate(candidates):
            if i < position and c != chosen:
                self._conn.execute(
                    "INSERT INTO unigram_freq (word, count, skip_count, last_used) VALUES (?, 0, 1, ?) "
                    "ON CONFLICT(word) DO UPDATE SET skip_count = skip_count + 1",
                    (c, now),
                )
        if context:
            self._conn.execute(
                "INSERT INTO bigram_freq (prev_word, curr_word, count) VALUES (?, ?, 1) "
                "ON CONFLICT(prev_word, curr_word) DO UPDATE SET count = count + 1",
                (context, chosen),
            )
        self._conn.commit()

    def get_selection_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM selections").fetchone()
        return row[0]

    def get_unigram_freq(self, word: str) -> int:
        row = self._conn.execute(
            "SELECT count FROM unigram_freq WHERE word = ?", (word,)
        ).fetchone()
        return row[0] if row else 0

    def get_bigram_freq(self, prev_word: str, curr_word: str) -> int:
        row = self._conn.execute(
            "SELECT count FROM bigram_freq WHERE prev_word = ? AND curr_word = ?",
            (prev_word, curr_word),
        ).fetchone()
        return row[0] if row else 0

    def get_skip_count(self, word: str) -> int:
        row = self._conn.execute(
            "SELECT skip_count FROM unigram_freq WHERE word = ?", (word,)
        ).fetchone()
        return row[0] if row else 0

    def get_last_used(self, word: str):
        row = self._conn.execute(
            "SELECT last_used FROM unigram_freq WHERE word = ?", (word,)
        ).fetchone()
        return row[0] if row else None

    def get_all_selections(self) -> list:
        rows = self._conn.execute(
            "SELECT pinyin, context, chosen, candidates, position, timestamp "
            "FROM selections ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def trim_old_selections(self, keep_days=90):
        cutoff = time.time() - keep_days * 86400
        self._conn.execute("DELETE FROM selections WHERE timestamp < ?", (cutoff,))
        self._conn.commit()

    def remove_noise_words(self, max_skip_ratio=5.0):
        self._conn.execute("""
            DELETE FROM unigram_freq
            WHERE count = 0 AND skip_count > 0
               OR (count > 0 AND CAST(skip_count AS REAL) / count > ?)
        """, (max_skip_ratio,))
        self._conn.commit()

    def close(self):
        self._conn.close()
