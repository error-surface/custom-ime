# custom-ime

A personalized Pinyin input method for macOS built on [RIME](https://rime.im/), with an online-learning candidate reranker that continuously adapts to your typing habits.

## How It Works

RIME handles Pinyin parsing and candidate generation. A Lua filter intercepts the candidate list and forwards it to a local Python ranking service via Unix Domain Socket. The service reorders candidates based on a learned model and returns the result — all within a few milliseconds.

```
Keystrokes → RIME → Candidate List
                          │
                    Lua Filter (rerank_filter.lua)
                          │  Unix Socket
                    Python Ranker
                          │
                    Reranked Candidates → Display
                          │
                    Selection recorded → Model updated
```

### Learning Phases

| Phase | Trigger | Model |
|-------|---------|-------|
| Phase 1 | Immediately | Unigram frequency + bigram context + recency decay |
| Phase 2 | After 500 selections | Online logistic regression (SGDClassifier) with incremental updates |

The transition between phases is automatic. Phase 2 uses richer features including candidate position, word length, and time-of-day bucket.

## Requirements

- macOS 12+
- Python 3.9+
- Homebrew

## Installation

```bash
git clone https://github.com/error-surface/custom-ime.git
cd custom-ime

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Squirrel (RIME for macOS) and symlink config files
./scripts/install.sh
```

After installation:

1. Log out and log back in (required for Squirrel to register as an input method)
2. Open **System Settings → Keyboard → Input Sources → +**
3. Search for **Squirrel** and add it
4. Click the input method icon in the menu bar and select **Squirrel**
5. Click **Deploy** from the Squirrel menu to apply the custom config

## Starting the Ranking Service

The Python ranking service must be running for reranking to work. If it is unavailable, the Lua filter falls back to RIME's original candidate order transparently.

**Run in foreground (for testing):**
```bash
./scripts/start_ranker.sh
```

**Install as a background service (recommended):**
```bash
./scripts/start_ranker.sh install
```

This registers a launchd agent that starts automatically on login.

**Uninstall the background service:**
```bash
./scripts/start_ranker.sh uninstall
```

**View logs:**
```bash
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err
```

## Monitoring Learning Progress

```bash
source .venv/bin/activate
python -m ranker.metrics
```

Example output:
```
Total selections: 1284
Top-1 hit rate:   73.4%
Avg position:     0.41
```

- **Top-1 hit rate** — percentage of times you selected the first candidate (higher is better)
- **Avg position** — average position of your chosen candidate in the list (lower is better)

## Project Structure

```
custom-ime/
├── ranker/
│   ├── config.py           # Paths, hyperparameters, phase threshold
│   ├── db.py               # SQLite layer: selection log, unigram/bigram tables
│   ├── model.py            # Phase 1 frequency model + Phase 2 SGDClassifier
│   ├── server.py           # Unix socket server handling rank/select actions
│   └── metrics.py          # Top-1 hit rate and average position reporting
├── rime/
│   ├── default.custom.yaml         # RIME schema list override
│   ├── luna_pinyin.custom.yaml     # Wires up Lua filter and notifier
│   └── lua/
│       ├── rerank_filter.lua       # Sends candidates to Python, returns reranked list
│       └── select_notifier.lua     # Records confirmed word selections
├── scripts/
│   ├── install.sh                          # Installs Squirrel and symlinks RIME config
│   ├── start_ranker.sh                     # Start / install / uninstall the service
│   └── com.custom-ime.ranker.plist         # launchd agent definition
├── tests/
│   ├── test_db.py          # Database layer unit tests
│   ├── test_model.py       # Ranking model unit tests (Phase 1 + Phase 2)
│   ├── test_server.py      # Socket server unit tests
│   └── test_integration.py # End-to-end learning cycle test
├── requirements.txt
└── pyproject.toml
```

## Data Storage

All runtime data is stored in `~/.local/share/custom-ime/`:

| File | Contents |
|------|----------|
| `selections.db` | Selection log, unigram and bigram frequency tables |
| `sgd_model.pkl` | Serialized Phase 2 model weights |
| `ranker.sock` | Unix Domain Socket (runtime only) |

## Running Tests

```bash
source .venv/bin/activate
pytest -v
```

All 18 tests should pass (unit tests for db, model, server, and an end-to-end integration test).

## Configuration

Edit `ranker/config.py` to tune the model behavior:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ALPHA` | `0.4` | Weight for unigram frequency |
| `BETA` | `0.4` | Weight for bigram context |
| `GAMMA` | `0.2` | Weight for recency |
| `DECAY` | `0.95` | Recency decay factor per day |
| `PHASE2_THRESHOLD` | `500` | Number of selections before switching to Phase 2 |

## License

[MIT](LICENSE)
