# Markov n-gram FTRL Ranker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ad-hoc `BETA * bigram` term with a principled Markov n-gram transition probability factor (emission × transition), per PERT's Bayesian framework.

**Architecture:** Split Phase 1 scoring into `emission_score` (context-free) and `transition_score` (n-gram log-probability with Katz backoff). FTRL receives both as separate features and learns λ (the weight on transition) online. New `trigram_freq` table extends bigram to 3-gram with backoff.

**Tech Stack:** Python 3, SQLite, FTRL-Proximal, Lua (Rime filter)

---

### Task 1: Config changes

**Files:**
- Modify: `ranker/config.py`

- [ ] **Step 1: Remove BETA, add new Markov config constants**

```python
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
LAMBDA_INIT = 0.50       # initial weight on transition_score (FTRL learns true λ)
BACKOFF_K_MIN = 3         # fall back below this count
DISCOUNT = 0.5            # absolute discounting
```

- [ ] **Step 2: Commit**

```bash
git add ranker/config.py
git commit -m "config: replace BETA with Markov n-gram constants (LAMBDA_INIT, BACKOFF_K_MIN, DISCOUNT)"
```

---

### Task 2: DB trigram support

**Files:**
- Modify: `ranker/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Add trigram_freq table migration and query methods**

In `_create_tables()`, add after bigram_freq:

```python
self._conn.execute("""
    CREATE TABLE IF NOT EXISTS trigram_freq (
        prev2_word TEXT NOT NULL,
        prev1_word TEXT NOT NULL,
        curr_word  TEXT NOT NULL,
        count      INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (prev2_word, prev1_word, curr_word)
    );
""")
```

Add migration block (before `self._conn.commit()`):

```python
try:
    self._conn.execute("ALTER TABLE unigram_freq ADD COLUMN reject_count INTEGER NOT NULL DEFAULT 0")
except Exception:
    pass
```

Add new methods to `SelectionDB`:

```python
def get_trigram_freq(self, prev2: str, prev1: str, word: str) -> int:
    row = self._conn.execute(
        "SELECT count FROM trigram_freq WHERE prev2_word = ? AND prev1_word = ? AND curr_word = ?",
        (prev2, prev1, word),
    ).fetchone()
    return row[0] if row else 0

def get_bigram_total(self, prev_word: str) -> int:
    row = self._conn.execute(
        "SELECT SUM(count) FROM bigram_freq WHERE prev_word = ?", (prev_word,)
    ).fetchone()
    return row[0] if row and row[0] else 0

def get_trigram_total(self, prev2: str, prev1: str) -> int:
    row = self._conn.execute(
        "SELECT SUM(count) FROM trigram_freq WHERE prev2_word = ? AND prev1_word = ?",
        (prev2, prev1),
    ).fetchone()
    return row[0] if row and row[0] else 0

def get_unigram_total(self) -> int:
    row = self._conn.execute("SELECT SUM(count) FROM unigram_freq").fetchone()
    return row[0] if row and row[0] else 0
```

- [ ] **Step 2: Write trigram on record_selection**

In `record_selection()`, after the bigram INSERT block, add:

```python
# Write trigram when context has enough history (context2 provided externally)
# context2 is passed as a separate parameter — see record_selection signature update below
```

Update `record_selection` signature to accept optional `context2`:

```python
def record_selection(self, pinyin: str, context: str, chosen: str,
                     candidates: list, position: int, context2: str = ""):
```

After bigram block, add:

```python
if context2 and context:
    self._conn.execute(
        "INSERT INTO trigram_freq (prev2_word, prev1_word, curr_word, count) "
        "VALUES (?, ?, ?, 1) "
        "ON CONFLICT(prev2_word, prev1_word, curr_word) "
        "DO UPDATE SET count = count + 1",
        (context2, context, chosen),
    )
```

- [ ] **Step 3: Add test for trigram**

In `tests/test_db.py`, add:

```python
def test_trigram_frequency(db):
    db.record_selection("nihao", "你", "你好", ["你好"], 0, context2="们")
    db.record_selection("nihao", "你", "你好", ["你好"], 0, context2="们")
    db.record_selection("nihao", "你", "你好", ["你好"], 0, context2="我")
    assert db.get_trigram_freq("们", "你", "你好") == 2
    assert db.get_trigram_freq("我", "你", "你好") == 1
    assert db.get_trigram_freq("他", "你", "你好") == 0

def test_unigram_total(db):
    db.record_selection("a", "", "你", ["你"], 0)
    db.record_selection("b", "", "好", ["好"], 0)
    assert db.get_unigram_total() == 2
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_db.py -v
```
Expected: PASS (5 tests including the 2 new)

- [ ] **Step 5: Commit**

```bash
git add ranker/db.py tests/test_db.py
git commit -m "db: add trigram_freq table with backoff queries and context2 passthrough"
```

---

### Task 3: FTRL feature signature update

**Files:**
- Modify: `ranker/local_ranker.py`

- [ ] **Step 1: Replace phase1 features with emission and markov_logp**

In `_featurize()`, change signature:

```python
def _featurize(self, word, context, position, n_candidates,
               emission=0.0, markov_logp=0.0, pinyin=""):
```

Replace the `phase1`/`phase1_gap` block:

Remove:
```python
"phase1": phase1_score,
```
```python
feats["phase1_gap"] = phase1_score - max_phase1
```

Add instead:
```python
feats["emission"] = emission
feats["markov_logp"] = markov_logp
```

- [ ] **Step 2: Update predict() signature**

```python
def predict(self, word, context, position, n_candidates,
            emission=0.0, markov_logp=0.0, pinyin=""):
    feats = self._featurize(word, context, position, n_candidates,
                            emission, markov_logp, pinyin)
    return self._score(feats)
```

- [ ] **Step 3: Update update() signature**

```python
def update(self, chosen, context, candidates, position,
           emissions=None, markov_logps=None, pinyin=""):
    em = emissions or {}
    ml = markov_logps or {}
    for i, c in enumerate(candidates):
        feats = self._featurize(
            c, context, i, len(candidates),
            emission=em.get(c, 0.0),
            markov_logp=ml.get(c, 0.0),
            pinyin=pinyin,
        )
        label = 1.0 if c == chosen else 0.0
        pred = self._score(feats)
        grad = pred - label
        for f, x in feats.items():
            n_old = self.n.get(f, 0.0)
            n_new = n_old + grad * grad
            sigma = (math.sqrt(n_new) - math.sqrt(n_old)) / self.alpha
            w = self._compute_weight(f)
            self.z[f] = self.z.get(f, 0.0) + grad * x - sigma * w
            self.n[f] = n_new
    self._update_count += 1
    self._save()
```

- [ ] **Step 4: Update update_reject() signature**

```python
def update_reject(self, rejected, context, candidates,
                  emissions=None, markov_logps=None, pinyin=""):
    em = emissions or {}
    ml = markov_logps or {}
    for i, c in enumerate(candidates):
        feats = self._featurize(
            c, context, i, len(candidates),
            emission=em.get(c, 0.0),
            markov_logp=ml.get(c, 0.0),
            pinyin=pinyin,
        )
        label = 0.0
        pred = self._score(feats)
        grad = pred - label
        if c == rejected:
            grad *= 2.0
        for f, x in feats.items():
            n_old = self.n.get(f, 0.0)
            n_new = n_old + grad * grad
            sigma = (math.sqrt(n_new) - math.sqrt(n_old)) / self.alpha
            w = self._compute_weight(f)
            self.z[f] = self.z.get(f, 0.0) + grad * x - sigma * w
            self.n[f] = n_new
    self._update_count += 1
    self._save()
```

- [ ] **Step 5: Commit**

```bash
git add ranker/local_ranker.py
git commit -m "ftrl: replace phase1/phase1_gap with emission + markov_logp features"
```

---

### Task 4: Model scoring restructure

**Files:**
- Modify: `ranker/model.py`
- Modify: `ranker/server.py`

- [ ] **Step 1: Split _score_phase1 into _emission_score**

Rename and strip bigram:

```python
def _emission_score(self, word: str, pinyin: str = "") -> float:
    unigram = self._db.get_unigram_freq(word)
    skip_count = self._db.get_skip_count(word)
    reject_count = self._db.get_reject_count(word)
    last_used = self._db.get_last_used(word)
    recency = 0.0
    if last_used is not None:
        days_ago = (time.time() - last_used) / 86400
        recency = math.pow(DECAY, days_ago)
    skip_penalty = SKIP_PENALTY * skip_count / (1 + unigram)
    reject_penalty = REJECT_PENALTY * reject_count / (1 + unigram)
    extra = max(0, len(word) - 1)
    length_bonus = LENGTH_BONUS * (extra ** 2)
    score = (ALPHA * unigram + GAMMA * recency
             - skip_penalty - reject_penalty + length_bonus)
    if pinyin and word == self._db.get_last_chosen_for_pinyin(pinyin):
        score += LAST_PINYIN_BOOST
    return score
```

- [ ] **Step 2: Add _transition_score with Katz backoff**

```python
def _transition_score(self, word: str, context: str, context2: str = "") -> float:
    from ranker.config import BACKOFF_K_MIN, DISCOUNT

    # Try trigram
    if context2 and context:
        tri_count = self._db.get_trigram_freq(context2, context, word)
        if tri_count >= BACKOFF_K_MIN:
            total = self._db.get_trigram_total(context2, context)
            p = max(tri_count - DISCOUNT, 0.1) / max(total, 1)
            return math.log(max(p, 1e-10))

    # Try bigram
    if context:
        bi_count = self._db.get_bigram_freq(context, word)
        if bi_count >= BACKOFF_K_MIN:
            total = self._db.get_bigram_total(context)
            p = max(bi_count - DISCOUNT, 0.1) / max(total, 1)
            return math.log(max(p, 1e-10))

    # Fall back to unigram
    uni_count = self._db.get_unigram_freq(word)
    total = self._db.get_unigram_total()
    p = max(uni_count, 0.1) / max(total, 1)
    return math.log(max(p, 1e-10))
```

- [ ] **Step 3: Rewrite rank()**

```python
def rank(self, pinyin: str, context: str, candidates: list,
         context2: str = "") -> list:
    if not candidates:
        return []

    emissions = {c: self._emission_score(c, pinyin) for c in candidates}
    transitions = {c: self._transition_score(c, context, context2) for c in candidates}

    if self._ftrl.ready:
        scored = []
        for i, c in enumerate(candidates):
            ftrl_score = self._ftrl.predict(
                c, context, i, len(candidates),
                emission=emissions[c],
                markov_logp=transitions[c],
                pinyin=pinyin,
            )
            scored.append((c, emissions[c] + ftrl_score))
    else:
        scored = [(c, emissions[c] + LAMBDA_INIT * transitions[c])
                  for c in candidates]

    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored]
```

Add import:

```python
from ranker.config import ALPHA, GAMMA, DECAY, SKIP_PENALTY, REJECT_PENALTY, LENGTH_BONUS, LAST_PINYIN_BOOST, LAMBDA_INIT
```

Keep `_score_phase1` as a deprecated wrapper for backward compat (used by eval):

```python
def _score_phase1(self, word: str, context: str, pinyin: str = "") -> float:
    """Deprecated: kept for eval backward compat. Use _emission_score + _transition_score."""
    return self._emission_score(word, pinyin) + LAMBDA_INIT * self._transition_score(word, context)
```

- [ ] **Step 4: Update record()**

```python
def record(self, pinyin: str, context: str, chosen: str,
           candidates: list, position: int, context2: str = ""):
    self._db.record_selection(pinyin, context, chosen, candidates, position, context2)

    if len(candidates) > 0:
        emissions = {c: self._emission_score(c, pinyin) for c in candidates}
        transitions = {c: self._transition_score(c, context, context2) for c in candidates}
        self._ftrl.update(chosen, context, candidates, position,
                          emissions=emissions, markov_logps=transitions, pinyin=pinyin)
```

- [ ] **Step 5: Update reject()**

```python
def reject(self, pinyin: str, context: str, rejected: str,
           candidates: list = None, context2: str = ""):
    self._db.record_reject(rejected)

    if candidates and len(candidates) > 0:
        emissions = {c: self._emission_score(c, pinyin) for c in candidates}
        transitions = {c: self._transition_score(c, context, context2) for c in candidates}
        self._ftrl.update_reject(rejected, context, candidates,
                                 emissions=emissions, markov_logps=transitions, pinyin=pinyin)
```

- [ ] **Step 6: Update server.py _dispatch() to pass context2**

In `_dispatch()`:

```python
elif action == "select":
    self._model.record(
        pinyin=request["pinyin"],
        context=request.get("context", ""),
        chosen=request["chosen"],
        candidates=request["candidates"],
        position=request.get("position", 0),
        context2=request.get("context2", ""),
    )
```

And in `rank`:

```python
if action == "rank":
    ranked = self._model.rank(
        pinyin=request["pinyin"],
        context=request.get("context", ""),
        candidates=request["candidates"],
        context2=request.get("context2", ""),
    )
```

And in `reject`:

```python
elif action == "reject":
    self._model.reject(
        pinyin=request["pinyin"],
        context=request.get("context", ""),
        rejected=request["rejected"],
        candidates=request.get("candidates", []),
        context2=request.get("context2", ""),
    )
```

- [ ] **Step 7: Commit**

```bash
git add ranker/model.py ranker/server.py
git commit -m "model: split scoring into emission + Markov n-gram transition with Katz backoff"
```

---

### Task 5: Lua filter context2 passthrough

**Files:**
- Modify: `rime/lua/rerank_filter.lua`
- Modify: `rime/lua/select_notifier.lua`

- [ ] **Step 1: Pass context2 in rerank_filter.lua**

In `rerank_filter()`, after getting context and pinyin, compute context2 from the committed text. The Lua environment persists per-session. Add a module-level variable to track the last 2 committed words:

```lua
local last_words = {}  -- sliding window of last 2 committed words
```

In the rank request, add `context2`:

```lua
local request = json_helper.encode({
    action = "rank",
    pinyin = pinyin,
    context = context,
    context2 = last_words[2] or "",
    candidates = candidates,
})
```

- [ ] **Step 2: Track word history in select_notifier.lua**

After `env.prev_word = text` in the select callback, add:

```lua
-- Track second-to-last word for trigram context
env.prev_word2 = env.prev_word2 or ""
if env.prev_word and env.prev_word ~= "" then
    env.prev_word2 = env.prev_word
end
```

Also need to expose `env.prev_word2` so the rerank filter can read it. Add in the select callback:

```lua
if ctx.set_property then
    ctx:set_property("custom_ime.prev_word2", env.prev_word2 or "")
end
```

- [ ] **Step 3: Read context2 from property in rerank_filter.lua**

```lua
local context2 = ctx:get_property and (ctx:get_property("custom_ime.prev_word2") or "") or ""
```

- [ ] **Step 4: Commit**

```bash
git add rime/lua/rerank_filter.lua rime/lua/select_notifier.lua
git commit -m "lua: pass context2 for trigram Markov transition scoring"
```

---

### Task 6: Update evaluation script

**Files:**
- Modify: `scripts/eval_final.py`

- [ ] **Step 1: Update import to remove BETA, add LAMBDA_INIT**

```python
from ranker.config import ALPHA, GAMMA, DECAY, SKIP_PENALTY, LENGTH_BONUS, LAMBDA_INIT
```

- [ ] **Step 2: Update ablation configs**

Replace bigram row:

```python
ablations = [
    ("Full Phase 1", ALPHA, GAMMA, DECAY, SKIP_PENALTY, LENGTH_BONUS, LAMBDA_INIT),
    ("- unigram (α=0)", 0.0, GAMMA, DECAY, SKIP_PENALTY, LENGTH_BONUS, LAMBDA_INIT),
    ("- recency (γ=0)", ALPHA, 0.0, DECAY, SKIP_PENALTY, LENGTH_BONUS, LAMBDA_INIT),
    ("- skip penalty", ALPHA, GAMMA, DECAY, 0.0, LENGTH_BONUS, LAMBDA_INIT),
    ("- length bonus", ALPHA, GAMMA, DECAY, SKIP_PENALTY, 0.0, LAMBDA_INIT),
    ("- markov (λ=0)", ALPHA, GAMMA, DECAY, SKIP_PENALTY, LENGTH_BONUS, 0.0),
]
```

- [ ] **Step 3: Update scoring in ablation loop**

Replace the manual score calculation:

```python
for name, a, g, d, sp, lb, lam in ablations:
    ...
    scores = {}
    for c in cand_words:
        uni = db_a.get_unigram_freq(c)
        skip = db_a.get_skip_count(c)
        lu = db_a.get_last_used(c)
        rec = 0.0
        if lu:
            rec = math.pow(d, (time.time() - lu) / 86400)
        sp_val = sp * skip / (1 + uni)
        extra = max(0, len(c) - 1)
        lb_val = lb * (extra ** 2)
        emission = a * uni + g * rec - sp_val + lb_val
        # Markov transition for ablation
        bi_count = db_a.get_bigram_freq("", c)
        uni_total = max(db_a.get_unigram_total(), 1)
        trans = math.log(max(max(bi_count - 0.5, 0.1) / uni_total, 1e-10))
        scores[c] = emission + lam * trans
```

- [ ] **Step 4: Update Phase 1 references in main eval loop**

Replace `model._score_phase1(c, "")` with `model._emission_score(c, "")`:

```python
p1_scores = {c: model._emission_score(c, "") for c in cand_words}
```

And in the training section:

```python
emissions = {c: model._emission_score(c, "") for c in cand_words}
transitions = {c: model._transition_score(c, "") for c in cand_words}
model._ftrl.update(chosen, "", cand_words, 0, emissions=emissions, markov_logps=transitions, pinyin=py)
```

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_final.py
git commit -m "eval: update ablation and scoring for emission + Markov transition model"
```

---

### Task 7: Update existing tests

**Files:**
- Modify: `tests/test_model.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Fix test_model.py for new scoring formula**

The test `test_rank_with_unigram_history` records "泥号" 2x and "你好" 1x. With old formula including BETA*bigram, "泥号" ranked first. After removing BETA, unigram + recency should still put "泥号" first. Verify:

```bash
python3 -m pytest tests/test_model.py -v
```

If any test fails, adjust expectations. The key invariant: `test_ftrl_phase2_blend` must still pass (FTRL activates and learns). If `test_rank_with_bigram_boost` relies on the old `BETA * bigram_count` behavior, update it:

```python
def test_rank_with_bigram_boost(model, db):
    # Record selections with context "你" → "好" to build bigram data
    for _ in range(10):
        db.record_selection("hao", "你", "好", ["好", "号", "毫"], 0)
    for _ in range(3):
        db.record_selection("hao", "", "号", ["好", "号", "毫"], 1)
    # With strong bigram "你"→"好", "好" should rank first when context="你"
    ranked = model.rank("hao", "你", ["好", "号", "毫"])
    assert ranked[0] == "好"
```

- [ ] **Step 2: Update test_integration.py for context2**

No changes needed to `test_full_learning_cycle` — it doesn't use context2. Verify:

```bash
python3 -m pytest tests/test_integration.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: update test expectations for emission + Markov transition scoring"
```

---

### Task 8: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests PASS (7+ tests across test_db.py, test_model.py, test_integration.py)

- [ ] **Step 2: Run evaluation**

```bash
python3 scripts/eval_final.py
```
Expected: evaluation completes without errors, shows Top-1/Top-3/MRR for all configurations

- [ ] **Step 3: Commit if any final fixes were needed**

```bash
git add -A
git commit -m "test: final test fixes after Markov n-gram integration"
```
