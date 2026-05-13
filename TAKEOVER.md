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

## Current Runtime State

Checked on 2026-05-07:

- LaunchAgent `com.custom-ime.ranker` is loaded and running.
- Current ranker PID was `49735` at takeover time.
- Socket exists at `~/.local/share/custom-ime/ranker.sock`.
- Database exists at `~/.local/share/custom-ime/selections.db`.
- Metrics reported:
  - Total selections: 11
  - Top-1 hit rate: 100.0%
  - Average position: 0.00

Useful commands:

```bash
launchctl print gui/501/com.custom-ime.ranker
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err
cd ~/custom-ime && .venv/bin/python -m ranker.metrics
```

## Verified Baseline

The test suite passes when run outside the restricted sandbox:

```bash
cd ~/custom-ime && .venv/bin/pytest -q
```

Result at takeover:

```text
18 passed in 1.88s
```

Inside a restricted sandbox, socket tests may fail with `PermissionError: [Errno 1] Operation not permitted` when binding `/tmp/*.sock`; that is an environment issue, not a project failure.

## Claude Context Recovered

The original conversation started from the user's request:

> "我的本地输入法和我的习惯不相同 想开发一个新的输入法我自己训练 有什么建议吗"

Design choices from that conversation:

- Use RIME/Squirrel rather than building a macOS input method from scratch.
- Keep the personalization logic local and offline.
- Start with simple frequency, bigram, and recency ranking.
- Switch to an online `SGDClassifier` after 500 selections.
- Store all learned data locally in SQLite and a local pickle model file.
- Run the Python ranker as a LaunchAgent for background operation.

Important follow-up history:

- The repo was created and pushed to GitHub under `error-surface/custom-ime`.
- README and MIT license were added.
- Squirrel was installed.
- The ranker was installed as a background LaunchAgent.
- Simplified Chinese output was configured with `switches/@2/reset: 1`.
- Stale `Squirrel --deploy` processes previously caused switching issues and were fixed by restarting Squirrel.

Security note: an old GitHub personal access token appeared in the Claude chat log during repository creation. It should be considered compromised and revoked if it has not already been revoked.

## Known Risks

1. Lua JSON construction is fragile.
   `rime/lua/rerank_filter.lua` and `rime/lua/select_notifier.lua` build JSON with string formatting. Quotes, backslashes, newlines, or unusual candidate text can break requests.

2. Selection learning is incomplete.
   `select_notifier.lua` currently records the committed text but sends an empty candidate list and no useful context. This means the model learns basic unigram frequency, but richer ranking features and position-based training are limited.

3. Context capture is weak.
   The Python model supports bigram context, but the Lua notifier currently sends an empty context.

4. Shelling through `echo | nc` is brittle and may add latency.
   It works for a prototype, but robust production behavior may require a safer Lua socket/JSON path or a small helper command with proper escaping.

5. Phase 2 is unproven in real usage.
   Tests cover the code path, but the live database has only 11 selections, far below the 500-selection threshold.

## Recommended Next Work

1. Harden Lua request encoding.
   Add a tested JSON escaping helper in Lua and cover candidate text containing quotes, backslashes, punctuation, and non-ASCII characters.

2. Record full selection events.
   Preserve the last ranked candidate list and selected position so the Python ranker can train on real candidate lists instead of empty arrays.

3. Improve context tracking.
   Track the previous committed Chinese token or phrase and send it as `context` for bigram learning.

4. Add a local smoke test script.
   Provide a command that sends rank/select requests to the Unix socket and prints a clear pass/fail result.

5. Update README with troubleshooting.
   Add concrete commands for checking LaunchAgent state, restarting Squirrel, redeploying RIME, and verifying learned selection counts.

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

Deploy Squirrel config:

```bash
/Library/Input\ Methods/Squirrel.app/Contents/MacOS/Squirrel --deploy
```

Restart Squirrel if switching gets stuck:

```bash
killall Squirrel 2>/dev/null
open /Library/Input\ Methods/Squirrel.app
```
