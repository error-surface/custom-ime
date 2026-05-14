import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("IME_DATA_DIR", Path.home() / ".local/share/custom-ime"))

SOCKET_PATH = DATA_DIR / "ranker.sock"
DB_PATH = DATA_DIR / "selections.db"
FTRL_WEIGHTS_PATH = DATA_DIR / "ftrl_weights.json"

ALPHA = 0.4
BETA = 0.4
GAMMA = 0.2
DECAY = 0.85
SKIP_PENALTY = 0.15
LENGTH_BONUS = 0.15
