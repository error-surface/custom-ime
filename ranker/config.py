import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("IME_DATA_DIR", Path.home() / ".local/share/custom-ime"))

SOCKET_PATH = DATA_DIR / "ranker.sock"
DB_PATH = DATA_DIR / "selections.db"
FTRL_WEIGHTS_PATH = DATA_DIR / "ftrl_weights.json"

ALPHA = 0.30
GAMMA = 0.25
DECAY = 0.80
SKIP_PENALTY = 0.15
REJECT_PENALTY = 0.60
LENGTH_BONUS = 0.25
LAST_PINYIN_BOOST = 0.15

# Markov n-gram transition
LAMBDA_INIT = 0.50
BACKOFF_K_MIN = 3
DISCOUNT = 0.5
