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
| Phase 1 | Immediately | Unigram frequency + bigram context + recency decay + length bonus − skip penalty |
| Phase 2 | After 30 selections | FTRL-Proximal online logistic regression, learns residual corrections on top of Phase 1 |

Both phases always contribute — Phase 2 blends in as a modest adjustment rather than replacing Phase 1. Phase 2 features include candidate position, word length, time-of-day bucket, and the Phase 1 score itself (so FTRL learns where the heuristics are wrong).

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
│   ├── config.py           # Paths, hyperparameters
│   ├── db.py               # SQLite layer: selection log, unigram/bigram tables
│   ├── local_ranker.py     # FTRL-Proximal online learner (Phase 2)
│   ├── model.py            # Phase 1 heuristic scoring + Phase 2 FTRL blend
│   ├── seed_data.py        # 630-word built-in vocabulary for cold start
│   ├── server.py           # Unix socket server handling rank/select actions
│   ├── sync_phrases.py     # Sync learned phrases to Rime's custom_phrase.txt
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
│   ├── ranker_client.py                    # Socket relay (Lua → Python), stdin+timeout
│   ├── ranker_relay.c                      # C socket relay (~2ms startup, replaces Python)
│   ├── smoke_test.py                       # 4-check end-to-end verification
│   └── com.custom-ime.ranker.plist         # launchd agent definition
├── tests/
│   ├── test_db.py          # Database layer unit tests
│   ├── test_model.py       # Ranking model unit tests (Phase 1 + FTRL Phase 2)
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
| `ftrl_weights.json` | Serialized FTRL model weights (Phase 2) |
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
| `DECAY` | `0.85` | Recency decay factor per day |
| `SKIP_PENALTY` | `0.15` | Penalty per skip (candidates passed over) |
| `LENGTH_BONUS` | `0.20` | Quadratic bonus for multi-character words |

## Smoke Test

Verify the full pipeline (socket, ranker, learning) with a single command:

```bash
python3 scripts/smoke_test.py
```

Expect `All 4 checks passed.` — if any fail, see the Troubleshooting section below.

## Troubleshooting

**Check if the ranker is running:**

```bash
launchctl print gui/$(id -u)/com.custom-ime.ranker | head -5
```

Look for `state = running`. If not running, start it:

```bash
cd ~/custom-ime && ./scripts/start_ranker.sh start &
```

Or reinstall the LaunchAgent:

```bash
cd ~/custom-ime && ./scripts/start_ranker.sh install
```

**View ranker logs:**

```bash
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err
```

**Check learning progress:**

```bash
cd ~/custom-ime && source .venv/bin/activate && python -m ranker.metrics
```

**Redeploy RIME config after editing Lua or YAML files:**

```bash
/Library/Input\ Methods/Squirrel.app/Contents/MacOS/Squirrel --deploy
```

**Restart Squirrel if input switching gets stuck:**

```bash
killall Squirrel 2>/dev/null
open /Library/Input\ Methods/Squirrel.app
```

**Verify the socket exists:**

```bash
ls -la ~/.local/share/custom-ime/ranker.sock
```

If the socket is missing but the ranker should be running, restart it with the `start` command above.

**Common issues:**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Candidates not reranked | Ranker not running | `./scripts/start_ranker.sh install` |
| Squirrel won't switch | Stale deploy process | `killall Squirrel && open /Library/Input\ Methods/Squirrel.app` |
| Config changes ignored | Need redeploy | Run `Squirrel --deploy` |
| Socket permission error | Stale socket file | Restart the ranker |

## License

[MIT](LICENSE)
