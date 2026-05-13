"""
Sync learned phrases from the ranker's SQLite DB to Rime's custom_phrase.txt
(stabledb — no decay, survives indefinitely).

Uses pypinyin to generate correct pinyin for Chinese text.
Runs incrementally after each selection, and periodically does a full sync.
"""

import re
import sqlite3
from pathlib import Path

from pypinyin import lazy_pinyin

from ranker.config import DB_PATH

CUSTOM_PHRASE = Path.home() / "Library" / "Rime" / "custom_phrase.txt"
MIN_COUNT = 1


def _is_chinese(text: str) -> bool:
    """Check if text contains at least one Chinese character."""
    return bool(re.search(r"[一-鿿]", text))


def _chinese_ratio(text: str) -> float:
    """Ratio of Chinese characters in text."""
    if not text:
        return 0.0
    chinese = len(re.findall(r"[一-鿿]", text))
    return chinese / len(text)


def _get_pinyin_for_phrase(phrase: str) -> str:
    """Generate pinyin for a Chinese phrase using pypinyin."""
    return "".join(lazy_pinyin(phrase))


def _get_existing_phrases() -> dict:
    """Read existing custom_phrase.txt. Returns {pinyin: {word: weight}}."""
    result = {}
    if not CUSTOM_PHRASE.exists():
        return result
    for line in CUSTOM_PHRASE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            word, pinyin = parts[0], parts[1]
            weight = int(parts[2]) if len(parts) >= 3 else 0
            result.setdefault(pinyin, {})[word] = weight
    return result


def _write_custom_phrase(entries: list):
    """Write the full custom_phrase.txt with header + sorted entries."""
    header = (
        "# Rime 自定义短语 (stabledb — 不参与衰减)\n"
        "# 由 custom-ime ranker 自动同步\n"
        "#\n"
        "# 格式：词<Tab>拼音<Tab>权重\n"
        "#\n"
    )

    # Preserve manual entries (before the auto-sync marker)
    manual_lines = []
    if CUSTOM_PHRASE.exists():
        in_auto = False
        for line in CUSTOM_PHRASE.read_text(encoding="utf-8").splitlines():
            if line.startswith("# === AUTO-SYNC"):
                in_auto = True
                continue
            if line.startswith("# === END AUTO-SYNC"):
                in_auto = False
                continue
            if not in_auto:
                manual_lines.append(line)

    while manual_lines and not manual_lines[-1].strip():
        manual_lines.pop()

    lines = manual_lines if manual_lines else [header.rstrip()]
    lines.append("")
    lines.append("# === AUTO-SYNC (ranker 自动生成，请勿编辑) ===")

    entries.sort(key=lambda e: (-e[2], e[1]))
    for word, pinyin, weight in entries:
        lines.append(f"{word}\t{pinyin}\t{weight}")

    lines.append("# === END AUTO-SYNC ===")
    lines.append("")

    CUSTOM_PHRASE.write_text("\n".join(lines), encoding="utf-8")


def _should_include(text: str) -> bool:
    """Filter: must be pure Chinese characters, no ASCII, 2-8 chars."""
    if len(text) < 2 or len(text) > 8:
        return False
    # Reject if contains any ASCII letters, digits, or punctuation
    if re.search(r"[a-zA-Z0-9]", text):
        return False
    # Must be all Chinese characters (no punctuation, no spaces)
    if not re.fullmatch(r"[一-鿿]+", text):
        return False
    return True


def sync_full(min_count: int = MIN_COUNT):
    """Full sync: read all phrases from SQLite, write to custom_phrase.txt."""
    if not DB_PATH.exists():
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT word, count FROM unigram_freq WHERE count >= ? ORDER BY count DESC",
        (min_count,),
    ).fetchall()
    conn.close()

    entries = []
    for row in rows:
        word = row["word"]
        count = row["count"]
        if not _should_include(word):
            continue
        pinyin = _get_pinyin_for_phrase(word)
        if not pinyin:
            continue
        weight = max(1, count * 10)
        entries.append((word, pinyin, weight))

    _write_custom_phrase(entries)
    return len(entries)


def sync_incremental(chosen: str, pinyin: str):
    """Incremental sync: add/update a single phrase in custom_phrase.txt."""
    if not _should_include(chosen):
        return

    generated_pinyin = _get_pinyin_for_phrase(chosen)
    if not generated_pinyin:
        return

    existing = _get_existing_phrases()
    pinyin_entries = existing.get(generated_pinyin, {})

    current_weight = pinyin_entries.get(chosen, 0)
    new_weight = max(1, current_weight + 10)
    pinyin_entries[chosen] = new_weight
    existing[generated_pinyin] = pinyin_entries

    entries = []
    for py, words in existing.items():
        for word, weight in words.items():
            entries.append((word, py, weight))

    _write_custom_phrase(entries)


if __name__ == "__main__":
    count = sync_full()
    print(f"Synced {count} phrases to {CUSTOM_PHRASE}")
