# IME Optimization Papers — Organized Reference

> 为 Custom-IME 后续优化整理的文献清单。按主题分类，标注了与项目的关联点和可借鉴方向。

---

## 1. 你的论文已引用的文献

| # | 论文 | 出处 | 关键内容 |
|---|---|---|---|
| 1 | **GeneInput** — Ding et al., *Generative Input: Towards Next-Generation Input Methods Paradigm* | Findings of ACL 2024 | LLM 统一生成范式做 Pinyin-to-Character, RLHF 在线个性化，SOTA |
| 2 | **CVM-IME** — Sun et al., *Exploring Conditional Variational Mechanism to Pinyin Input Method* | ACL 2024 Short | 条件变分机制解决一对多映射，面向低资源/离线场景 |
| 3 | **AttnInput** — *Revolutionizing Pinyin Input with Context-Aware RWKV Language Models* | Under review, 2024 | RWKV 线性 Transformer 做上下文感知拼音输入 |
| 4 | **FTRL-Proximal** — McMahan et al., *Ad Click Prediction: a View from the Trenches* | KDD 2013 | FTRL 经典论文，稀疏在线学习的工业基石 |
| 5 | **FORM** — *Follow the Online Regularized Meta-Leader for Cold-Start Recommendation* | SIGIR 2021 | FTRL + 元学习解决冷启动，可借鉴其自适应学习率设计 |
| 6 | **FFM-Wubi** — 李泽南等, *基于场感知分解机的五笔输入法* | 计算机技术与发展, 2023 | FFM 做五笔候选排序，Top-1 准确率 98.91%，你的论文 future work 提到了 |
| 7 | **THUOCL** — Tsinghua Open Chinese Lexicon | GitHub | 你的种子词典来源 |
| 8 | **N-gram IME** — *Sentence-level Chinese Character Input Method* | 中文信息学报, 2000 | 传统 n-gram IME 基线 |

---

## 2. Gboard / 工业界联邦学习 + 键盘个性化

### 2.1 DP-FTRL & Gboard Language Models
- **Xu et al., *Federated Learning of Gboard Language Models with Differential Privacy*, ACL 2023 Industry**
  - arXiv: [2305.18465](https://arxiv.org/abs/2305.18465)
  - 用 DP-FTRL 训练 Gboard 的 next-word prediction LMs，包含 20+ 个语言模型
  - 引入了 quantile-based clip estimation，自适应选择梯度裁剪阈值
  - **可借鉴**：DP-FTRL 的隐私保证机制 + client participation criterion

### 2.2 Private Federated Learning in Gboard (White Paper)
- **Zhang et al., *Private Federated Learning in Gboard*, 2023**
  - arXiv: [2306.14793](https://arxiv.org/abs/2306.14793)
  - 综合白皮书：DP-FTRL + Secure Aggregation + DP 在 suggestion/prediction/correction 中的完整方案
  - **可借鉴**：完整的生产级 FL 架构设计

### 2.3 DP-FTRL with BLTs
- **McMahan, Xu, Zhang, *A Hassle-free Algorithm for Private Learning in Practice: Don't Use Tree Aggregation, Use BLTs*, 2024**
  - arXiv: [2408.08868](https://arxiv.org/abs/2408.08868)
  - BLT (Buffered Linear Toeplitz) 改进 DP-FTRL 的隐私-效用 tradeoff
  - 明确提到在 mobile keyboard IME 中已实际使用 DP-FTRL
  - **可借鉴**：如果你的系统未来要考虑隐私保护，这是最前沿的 DP 方案

### 2.4 Spatial Model Personalization in Gboard
- **PACM HCI, 2022**
  - Gboard 空间模型个性化：自适应 key center offset + 学习的协方差矩阵
  - **可借鉴**：在线个性化不限于语言模型，触控模型也可以持续学习

### 2.5 Gboard Privacy Attack
- **Suliman et al., *Two Models are Better than One: Federated Learning Is Not Private For Google GBoard Next Word Prediction*, ESORICS 2023**
  - arXiv: [2210.16947](https://arxiv.org/abs/2210.16947)
  - 演示了没有 DP 保护的 FL 可以泄露用户输入的具体词汇
  - **可借鉴**：反面案例，说明为什么需要 DP 保护

---

## 3. Neural / Transformer IME

### 3.1 PERT
- **Xiao et al. (Huawei Noah's Ark), *PERT: A New Solution to Pinyin to Character Conversion Task*, 2022**
  - arXiv: [2205.11737](https://arxiv.org/abs/2205.11737)
  - 双向 Transformer 做 Pinyin-to-Character
  - 关键创新：PERT + **n-gram Markov 联合框架**（深度学习 + 统计模型结合，与你的 Phase1+2 两阶段思路相似）
  - 外部词典集成解决 OOD 问题
  - **可借鉴**：神经网络与传统 n-gram 的联合排序框架，你可考虑 Phase1 启发式 + 轻量神经网络替代 FTRL

---

## 4. 隐式负反馈 / 在线学习信号

### 4.1 X2T
- **Gao et al., *X2T: Training an X-to-Text Typing Interface with Online Learning from User Feedback*, ICLR 2021**
  - arXiv: [2203.02072](https://arxiv.org/abs/2203.02072)
  - 用 **退格键 (backspace)** 作为隐式负反馈信号
  - 在线学习框架，不需要标注数据
  - **可借鉴**：你的 skip/reject 信号之外，退格（删除刚选的词）是另一种有价值的负反馈，可以直接加到 Phase1 penalty 里

### 4.2 NIFTY
- **Towle & Zhou, *NIFTY: Enhancing AI Assisted Writing with One-Shot Implicit Negative Feedback*, 2024**
  - arXiv: [2410.11009](https://arxiv.org/abs/2410.11009)
  - 用户忽略建议 = 隐式负反馈，用 classifier guidance 引导生成远离被拒意图
  - R@1 从 16.4% → 28.5%（接近 2x 提升）
  - **可借鉴**：你的 skip signal 可以不只是 penalty，还可以在 Phase2 做更强力的 gradient 信号

### 4.3 Cursor Tab RL
- **Cursor, *Improving Cursor Tab with Online RL*, 2024**
  - 代码补全场景：接受 +0.75，拒绝 -0.25，未显示 0
  - Policy gradient 在线学习，接受率提升 28%，建议数减少 21%
  - **可借鉴**：reward 函数设计的量化参考；你的 reject 权重是 skip 的 4x (σ_r=0.60 vs σ_s=0.15)，可以对比他们的 ratio

### 4.4 Implicit Negative Feedback for Short-Video Recommendation
- **Pan et al. (Kuaishou/Tsinghua), *Learning and Optimization of Implicit Negative Feedback for Industrial Short-video Recommender System*, 2023**
  - arXiv: [2308.13249](https://arxiv.org/abs/2308.13249)
  - 十亿级用户的 skip 信号建模，多目标优化 (watch time vs skip rate)
  - **可借鉴**：大规模 skip signal 建模的工程实践

---

## 5. 用户行为分析

### 5.1 Typing Behavior Strategies
- **Lehmann, Kornecki, Buschek, Feit, *Typing Behavior is About More than Speed: Users' Strategies for Choosing Word Suggestions Despite Slower Typing Rates*, 2023**
  - PACM HCI (MHCI), Vol.7
  - 分析 15,162 个移动端用户的 8 种选词策略
  - 用户跳过建议自己打字的行为模式 → 可作为隐式反馈设计依据
  - **可借鉴**：了解用户何时/为什么跳过候选，有助于设计更精准的 skip signal

### 5.2 Anima
- **Natraj et al., *Anima: Adaptive Personalized Software Keyboard*, 2015**
  - arXiv: [1501.05696](https://arxiv.org/abs/1501.05696)
  - 早期自适应键盘工作，但思路经典：在线学习用户特定行为模式
  - **可借鉴**：早期基线，展示了个性化键盘的核心设计原则

---

## 6. 按你的优化方向分类

### 🔥 如果想改进 Phase2 在线学习：
- FORM (元学习+FTRL冷启动)
- Cursor Tab RL (reward 量化设计)
- DP-FTRL/BLTs (隐私保护的在线学习)

### 🔥 如果想增强负反馈信号：
- X2T (退格 = 负反馈)
- NIFTY (忽略 = 分类器引导远离)
- Typing Behavior Strategies (用户跳过行为模式)

### 🔥 如果想引入神经网络：
- PERT (Transformer + n-gram 联合，与你的思路最接近)
- GeneInput (LLM全集，重但SOTA)
- AttnInput (RWKV轻量替代)

### 🔥 如果想改进特征工程：
- FFM-Wubi (场感知分解机，稀疏特征交互)
- FORM (自适应学习率 per user)

### 🔥 如果想增强隐私保护：
- Gboard FL + DP-FTRL (ACL 2023)
- BLTs (2024 最新 DP 方案)
- Private FL in Gboard (完整白皮书)

---

## 7. 快速入口：最应该精读的 5 篇

1. **PERT** — Transformer + n-gram 联合框架，与你的两阶段设计理念一致
2. **X2T** — 隐式负反馈在线学习键盘，退格信号可直接加到你的系统
3. **Gboard FL + DP-FTRL** — FTRL 在键盘中的工业实践，证明这条路是对的
4. **NIFTY** — 如何更聪明地利用 "用户不看" 这个信号
5. **Cursor Tab RL** — 代码补全场景的 reward 设计，数值可参考
