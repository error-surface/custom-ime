# custom-ime

基于 RIME（鼠须管）的个性化拼音输入法，通过记录你的选词行为持续优化候选词排序。

## 原理

RIME 负责拼音解析和候选词生成，自定义 Python 服务负责重排序：

```
RIME → Lua Filter → Python Ranker → 重排后的候选词
                         ↑
                    记录选词行为，持续学习
```

**阶段一（冷启动）**：基于词频 + 二元语法 + 时间衰减打分，立即生效。

**阶段二（500 条记录后自动切换）**：在线逻辑回归，综合上下文、位置、时段等特征增量训练。

## 环境要求

- macOS
- Python 3.9+
- Homebrew

## 安装

```bash
git clone https://github.com/error-surface/custom-ime.git
cd custom-ime

# 安装 Python 依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 安装鼠须管 + 链接 RIME 配置
./scripts/install.sh
```

安装完成后：
1. 注销并重新登录（或重启）
2. 系统设置 → 键盘 → 输入法 → 添加「鼠须管」
3. 点击菜单栏鼠须管图标 → 重新部署

## 启动 Ranker 服务

**手动启动（当前终端）：**
```bash
./scripts/start_ranker.sh
```

**开机自动启动：**
```bash
./scripts/start_ranker.sh install
```

**停止自动启动：**
```bash
./scripts/start_ranker.sh uninstall
```

## 查看学习效果

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

## 项目结构

```
custom-ime/
├── ranker/
│   ├── config.py       # 路径、超参数配置
│   ├── db.py           # SQLite 选词日志与词频表
│   ├── model.py        # 阶段一频率模型 + 阶段二 SGD 模型
│   ├── server.py       # Unix Socket 服务（rank / select）
│   └── metrics.py      # Top-1 命中率统计
├── rime/
│   ├── default.custom.yaml
│   ├── luna_pinyin.custom.yaml
│   └── lua/
│       ├── rerank_filter.lua    # 调用 Python 服务重排候选词
│       └── select_notifier.lua  # 记录用户选词行为
├── scripts/
│   ├── install.sh               # 安装鼠须管 + 链接配置
│   ├── start_ranker.sh          # 启动 / 安装 / 卸载服务
│   └── com.custom-ime.ranker.plist
└── tests/                       # 18 个单元 + 集成测试
```

## 运行测试

```bash
source .venv/bin/activate
pytest -v
```

## 数据存储位置

所有数据存储在 `~/.local/share/custom-ime/`：

| 文件 | 内容 |
|------|------|
| `selections.db` | 选词日志、词频表 |
| `sgd_model.pkl` | 阶段二模型权重 |
| `ranker.sock` | Unix Socket |
