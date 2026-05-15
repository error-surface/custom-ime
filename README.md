[English](#english) &nbsp;|&nbsp; [中文](#chinese)

---

<h2 id="english">English</h2>

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
│   ├── seed_data.py        # 82K-word built-in vocabulary for cold start
│   ├── server.py           # Unix socket server handling rank/select actions
│   ├── sync_phrases.py     # Sync learned phrases to Rime's custom_phrase.txt
│   └── metrics.py          # Top-1 hit rate and average position reporting
├── rime/
│   ├── default.custom.yaml         # RIME schema list override
│   ├── luna_pinyin.custom.yaml     # Wires up Lua filter and notifier
│   ├── squirrel.custom.yaml        # Squirrel appearance / app-specific settings
│   └── lua/
│       ├── rerank_filter.lua       # Sends candidates to Python, returns reranked list
│       └── select_notifier.lua     # Records confirmed word selections
├── scripts/
│   ├── install.sh                          # Installs Squirrel and symlinks RIME config
│   ├── start_ranker.sh                     # Start / install / uninstall the service
│   ├── ranker_relay.c                      # C socket relay (~2ms startup)
│   ├── smoke_test.py                       # 4-check end-to-end verification
│   ├── eval_final.py                       # Offline replay evaluation (paper)
│   ├── eval_synthetic.py                   # Synthetic evaluation (paper)
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

## Configuration

Edit `ranker/config.py` to tune the model behavior:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ALPHA` | `0.30` | Weight for unigram frequency |
| `BETA` | `0.45` | Weight for bigram context |
| `GAMMA` | `0.25` | Weight for recency |
| `DECAY` | `0.80` | Recency decay factor per day |
| `SKIP_PENALTY` | `0.15` | Penalty per skip (candidates passed over) |
| `REJECT_PENALTY` | `0.60` | Penalty for explicitly rejected words |
| `LENGTH_BONUS` | `0.25` | Quadratic bonus for multi-character words |

## Smoke Test

```bash
python3 scripts/smoke_test.py
```

Expect `All 4 checks passed.`

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Candidates not reranked | Ranker not running | `./scripts/start_ranker.sh install` |
| Squirrel won't switch | Stale deploy process | `killall Squirrel && open /Library/Input\ Methods/Squirrel.app` |
| Config changes ignored | Need redeploy | Run `Squirrel --deploy` |
| Socket permission error | Stale socket file | Restart the ranker |

**View ranker logs:**
```bash
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err
```

**Check if the ranker is running:**
```bash
launchctl print gui/$(id -u)/com.custom-ime.ranker | head -5
```

## License

[MIT](LICENSE)

---

<h2 id="chinese">中文</h2>

# custom-ime

基于 [RIME](https://rime.im/) 的 macOS 个性化拼音输入法，通过在线学习候选词排序引擎持续适配你的打字习惯。

## 工作原理

RIME 负责拼音解析和候选词生成。Lua 过滤器拦截候选词列表，通过 Unix Domain Socket 转发给本地 Python 排序服务。该服务基于学习模型重排候选词并在几毫秒内返回结果。

```
按键 → RIME → 候选词列表
                    │
              Lua 过滤器 (rerank_filter.lua)
                    │  Unix Socket
              Python 排序服务
                    │
              重排后的候选词 → 显示
                    │
              记录选择 → 更新模型
```

### 学习阶段

| 阶段 | 触发条件 | 模型 |
|------|---------|------|
| 第一阶段 | 即刻生效 | 词频 + 二元上下文 + 时间衰减 + 长度加成 − 跳过惩罚 |
| 第二阶段 | 30 次选择后 | FTRL-Proximal 在线逻辑回归，在第一阶段基础上学习残差修正 |

两个阶段始终共同作用——第二阶段以适度调整的方式融入，而非替代第一阶段。第二阶段特征包括候选词位置、词长、时段分桶以及第一阶段得分本身（让 FTRL 学到启发式方法在哪里出错）。

## 环境要求

- macOS 12+
- Python 3.9+
- Homebrew

## 安装

```bash
git clone https://github.com/error-surface/custom-ime.git
cd custom-ime

# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 安装鼠须管并链接配置文件
./scripts/install.sh
```

安装后：

1. 注销并重新登录（鼠须管注册为输入法需要）
2. 打开 **系统设置 → 键盘 → 输入法 → +**
3. 搜索 **Squirrel** 并添加
4. 点击菜单栏输入法图标，选择 **Squirrel**
5. 在鼠须管菜单中点击 **Deploy（重新部署）** 应用自定义配置

## 启动排序服务

排序服务必须处于运行状态，重排才能生效。如果服务不可用，Lua 过滤器会透明地回退到 RIME 默认候选词顺序。

**前台运行（测试用）：**
```bash
./scripts/start_ranker.sh
```

**安装为后台服务（推荐）：**
```bash
./scripts/start_ranker.sh install
```

这会注册一个 launchd 代理，登录时自动启动。

**卸载后台服务：**
```bash
./scripts/start_ranker.sh uninstall
```

**查看日志：**
```bash
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err
```

## 查看学习进度

```bash
source .venv/bin/activate
python -m ranker.metrics
```

输出示例：
```
Total selections: 1284
Top-1 hit rate:   73.4%
Avg position:     0.41
```

- **Top-1 hit rate** — 首选命中率，即候选词第一位就是你想要的比例（越高越好）
- **Avg position** — 你选择的词在候选列表中的平均位置（越低越好）

## 项目结构

```
custom-ime/
├── ranker/
│   ├── config.py           # 路径配置、超参数
│   ├── db.py               # SQLite 层：选择记录、词频/二元表
│   ├── local_ranker.py     # FTRL-Proximal 在线学习器（第二阶段）
│   ├── model.py            # 第一阶段启发式评分 + 第二阶段 FTRL 融合
│   ├── seed_data.py        # 8.2 万内置词库，用于冷启动
│   ├── server.py           # Unix socket 服务器，处理 rank/select 请求
│   ├── sync_phrases.py     # 将学习到的词组同步至 Rime 的 custom_phrase.txt
│   └── metrics.py          # 首选命中率和平均位置统计
├── rime/
│   ├── default.custom.yaml         # RIME 方案列表
│   ├── luna_pinyin.custom.yaml     # Lua 过滤器和通知器接入
│   ├── squirrel.custom.yaml        # 鼠须管外观/应用适配设置
│   └── lua/
│       ├── rerank_filter.lua       # 发送候选词至 Python，返回重排结果
│       └── select_notifier.lua     # 记录确认的词选择
├── scripts/
│   ├── install.sh                          # 安装鼠须管并链接配置
│   ├── start_ranker.sh                     # 启动 / 安装 / 卸载服务
│   ├── ranker_relay.c                      # C 语言 socket 中继（~2ms 启动）
│   ├── smoke_test.py                       # 端到端 4 项验证
│   ├── eval_final.py                       # 离线回放评估（论文）
│   ├── eval_synthetic.py                   # 合成评估（论文）
│   └── com.custom-ime.ranker.plist         # launchd 代理定义
├── tests/
│   ├── test_db.py          # 数据库层单元测试
│   ├── test_model.py       # 排序模型单元测试（第一阶段 + 第二阶段）
│   ├── test_server.py      # Socket 服务器单元测试
│   └── test_integration.py # 端到端学习循环测试
├── requirements.txt
└── pyproject.toml
```

## 数据存储

所有运行时数据存储在 `~/.local/share/custom-ime/`：

| 文件 | 内容 |
|------|------|
| `selections.db` | 选择日志、词频和二元词频表 |
| `ftrl_weights.json` | FTRL 模型权重序列化文件（第二阶段） |
| `ranker.sock` | Unix Domain Socket（仅运行时） |

## 运行测试

```bash
source .venv/bin/activate
pytest -v
```

## 配置

编辑 `ranker/config.py` 调整模型行为：

| 参数 | 默认值 | 说明 |
|-----------|---------|-------------|
| `ALPHA` | `0.30` | 词频权重 |
| `BETA` | `0.45` | 二元上下文权重 |
| `GAMMA` | `0.25` | 时间衰减权重 |
| `DECAY` | `0.80` | 每天衰减系数 |
| `SKIP_PENALTY` | `0.15` | 每次跳过惩罚（被忽略的候选词） |
| `REJECT_PENALTY` | `0.60` | 显式拒绝惩罚（重打纠正） |
| `LENGTH_BONUS` | `0.25` | 多字词二次方加成 |

## 冒烟测试

```bash
python3 scripts/smoke_test.py
```

预期输出 `All 4 checks passed.`

## 常见问题

| 症状 | 可能原因 | 解决方法 |
|---------|-------------|-----|
| 候选词未重排 | 排序服务未运行 | `./scripts/start_ranker.sh install` |
| 无法切换到鼠须管 | 部署进程卡住 | `killall Squirrel && open /Library/Input\ Methods/Squirrel.app` |
| 配置修改未生效 | 需要重新部署 | 运行 `Squirrel --deploy` |
| Socket 权限错误 | 旧的 socket 文件残留 | 重启排序服务 |

**查看排序服务日志：**
```bash
cat /tmp/custom-ime-ranker.log
cat /tmp/custom-ime-ranker.err
```

**检查服务是否在运行：**
```bash
launchctl print gui/$(id -u)/com.custom-ime.ranker | head -5
```

## 开源协议

[MIT](LICENSE)
