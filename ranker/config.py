import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("IME_DATA_DIR", Path.home() / ".local/share/custom-ime"))

SOCKET_PATH = DATA_DIR / "ranker.sock"
DB_PATH = DATA_DIR / "selections.db"
MODEL_PATH = DATA_DIR / "sgd_model.pkl"

ALPHA = 0.4
BETA = 0.4
GAMMA = 0.2
DECAY = 0.85
SKIP_PENALTY = 0.15
LENGTH_BONUS = 0.08

PHASE2_THRESHOLD = 150
