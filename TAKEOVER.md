# Project Takeover Notes

## Current Scope

This project is a macOS personal Pinyin input method built on RIME/Squirrel. RIME generates the candidate list, Lua forwards candidates to a local Python ranker over a Unix domain socket, and the Python service records selections so ranking can improve over time.

Repository:

- Local: `/Users/chenxiansheng/custom-ime`
- Remote: `https://github.com/error-surface/custom-ime.git`
- Branch: `main`

Runtime integration:

- `~/Library/Rime/default.custom.yaml` points to `rime/default.custom.yaml`
- `~/Library/Rime/luna_pinyin.custom.yaml` points to `rime/luna_pinyin.custom.yaml`
- Lua files are linked under `~/Library/Rime/lua/`
- Runtime data lives in `~/.local/share/custom-ime/`

## Architecture

Two-phase ranking model in `ranker/model.py`:

- **Phase 1 (always active)**: heuristic scoring — unigram frequency + bigram context + recency decay + quadratic length bonus − skip penalty. Handles cold start.
- **Phase 2 (activates after 30 selections)**: FTRL-Proximal online logistic regression (`ranker/local_ranker.py`) learns residual corrections on top of Phase 1 scores. Phase 1 score is an input feature, so FTRL refines rather than replaces.

Both phases always contribute; Phase 2 blends in as `p1_score + (ftrl_prob − 0.5)`.

Key config in `ranker/config.py`:

```
ALPHA = 0.4      # unigram weight
BETA = 0.4       # bigram weight
GAMMA = 0.2      # recency weight
DECAY = 0.85     # daily recency decay
SKIP_PENALTY = 0.15
LENGTH_BONUS = 0.15  # quadratic: len_bonus * (extra_chars ^ 2)
```

## Runtime Data

- `~/.local/share/custom-ime/selections.db` — SQLite with selection history, unigram/bigram frequencies, skip counts
- `~/.local/share/custom-ime/ftrl_weights.json` — FTRL weights (z, n, update count)
- `~/Library/Rime/custom_phrase.txt` — auto-synced phrases for RIME's stabledb (no decay)

## Useful Commands

```bash
# Check ranker status
launchctl list | grep custom-ime

# View logs
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err

# Run metrics
cd ~/custom-ime && .venv/bin/python -m ranker.metrics

# Run tests
cd ~/custom-ime && .venv/bin/pytest -q

# Smoke test (requires running ranker)
cd ~/custom-ime && .venv/bin/python scripts/smoke_test.py

# Restart ranker after code changes
launchctl stop com.custom-ime.ranker
launchctl start com.custom-ime.ranker
```

## Seed Vocabulary

`ranker/seed_data.py` contains 630 common Chinese words pre-seeded into the DB on server startup. Covers high-frequency single chars, common disyllabic words, and explicit same-pinyin competition groups (e.g. 测试/侧视, 你好/泥号). Only boosts words whose count is below the seed count — user-learned data always wins.

## Background Threads

The ranker server (`ranker/server.py`) runs three daemon threads:

| Thread | Interval | Purpose |
|--------|----------|---------|
| Sync | 30 min | Full sync of learned phrases to `custom_phrase.txt` |
| Janitor | 6 hours | Trim selections older than 90 days, remove noise words (skip/count ratio > 5) |
| Vacuum | 24 hours | SQLite VACUUM (inside janitor thread) |

## Communication Protocol

1. Lua `rerank_filter.lua` builds a JSON request, writes it to a temp file, and pipes it via stdin to `scripts/ranker_client.py` using `io.popen`. This avoids shell interpolation of JSON content.
2. `ranker_client.py` reads stdin, sends the request over the Unix socket, prints the response.
3. A SIGALRM hard timeout (3 seconds) kills the Python process if the socket call hangs; RIME falls back to original candidate order.

## Test Suite

18 tests across 4 files:

| File | Tests |
|------|-------|
| `tests/test_db.py` | 5 — CRUD, frequencies, timestamps |
| `tests/test_model.py` | 7 — Phase 1 ranking, FTRL blend, persistence, phases |
| `tests/test_server.py` | 5 — rank/select dispatch, edge cases |
| `tests/test_integration.py` | 1 — end-to-end learning cycle |

## Known Limitations

1. Lua JSON parser is hand-rolled. It handles escaped characters and Unicode escapes but could be replaced with a proper library if RIME's Lua environment supports one.
2. FTRL features are sparse per-word and per-bigram — with heavy usage the weights file will grow. L1 regularization zeros out unused features, but the JSON file isn't pruned currently.
3. Candidate list is fully determined by RIME's translators; the custom ranker only reorders. Raw pinyin appearing as a candidate is a RIME dictionary issue.
4. No test coverage for `sync_phrases.py` or `seed_data.py`.

## Operational Commands

Install or refresh RIME links:

```bash
cd ~/custom-ime && ./scripts/install.sh
```

Install background ranker:

```bash
cd ~/custom-ime && ./scripts/start_ranker.sh install
```

Uninstall background ranker:

```bash
cd ~/custom-ime && ./scripts/start_ranker.sh uninstall
```

Deploy RIME config:

```bash
/Library/Input\ Methods/Squirrel.app/Contents/MacOS/Squirrel --deploy
```

Restart Squirrel if switching gets stuck:

```bash
killall Squirrel 2>/dev/null
open /Library/Input\ Methods/Squirrel.app
```
