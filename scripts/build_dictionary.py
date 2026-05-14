"""
Build expanded seed dictionary from THUOCL + chinese-xinhua.

Merges:
  - THUOCL (Tsinghua Open Chinese Lexicon): word + DF frequency
  - chinese-xinhua: 30K idioms + 264K words

Outputs ranker/dictionary_data.json used by seed_data.py on startup.
"""
import json
import re
import sys
from pathlib import Path

SOURCE_DIR = Path("/tmp/THUOCL_data")
IDIOM_PATH = Path("/tmp/idiom.json")

OUTPUT = Path(__file__).resolve().parent.parent / "ranker" / "dictionary_data.json"

PURE_CHINESE = re.compile(r"^[一-鿿]+$")


def is_valid(word: str) -> bool:
    """Pure Chinese, 2-8 characters."""
    if len(word) < 2 or len(word) > 8:
        return False
    return bool(PURE_CHINESE.match(word))


def load_thuocl() -> dict:
    """Load all THUOCL .txt files, return {word: max_df}."""
    words = {}
    for fpath in sorted(SOURCE_DIR.glob("THUOCL_*.txt")):
        for line in fpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            word, df_str = parts[0], parts[1]
            try:
                df = int(df_str)
            except ValueError:
                continue
            if not is_valid(word):
                continue
            # Keep max DF across categories
            words[word] = max(words.get(word, 0), df)
    return words


def load_idioms() -> set:
    """Load chinese-xinhua idioms (word only)."""
    if not IDIOM_PATH.exists():
        return set()
    data = json.loads(IDIOM_PATH.read_text(encoding="utf-8"))
    return {e["word"] for e in data if is_valid(e["word"])}



def assign_count(word: str, df: int, is_idiom: bool) -> int:
    """Assign seed count based on THUOCL DF or idiom status."""
    if df >= 10000:
        return 5
    elif df >= 1000:
        return 4
    elif df >= 100:
        return 3
    elif df >= 10:
        return 2
    elif is_idiom:
        # Idioms not in THUOCL still get count=2 (common cultural knowledge)
        return 2
    else:
        return 1


def main():
    if not SOURCE_DIR.exists():
        print("THUOCL data not found. Run: curl files from raw.githubusercontent.com/thunlp/THUOCL/master/data/")
        sys.exit(1)

    print("Loading THUOCL...")
    thuocl = load_thuocl()
    print(f"  {len(thuocl)} valid words from THUOCL")

    print("Loading chinese-xinhua idioms...")
    idioms = load_idioms()
    print(f"  {len(idioms)} idioms")

    # Merge: THUOCL takes precedence (has frequency), then idioms
    result = {}  # word -> (count, source)

    for word, df in thuocl.items():
        is_idiom = word in idioms
        result[word] = (assign_count(word, df, is_idiom), "thuocl")

    for word in idioms:
        if word not in result:
            result[word] = (2, "idiom")

    # ci.json words only included if already in THUOCL or idioms (avoids 270K obscure words)
    print(f"\nTotal unique words: {len(result)}")
    for cnt in range(5, 0, -1):
        n = sum(1 for c, _ in result.values() if c == cnt)
        print(f"  count={cnt}: {n} words")

    # Output as sorted list of [word, count]
    output = []
    for word, (count, _) in sorted(result.items()):
        output.append([word, count])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    print(f"\nWritten {len(output)} entries to {OUTPUT}")
    print(f"File size: {OUTPUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
