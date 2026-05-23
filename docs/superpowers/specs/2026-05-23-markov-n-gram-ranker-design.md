# Integrate Markov n-gram Framework into FTRL Ranker

## Goal

Replace the ad-hoc `BETA * bigram_count` term in Phase 1 scoring with a principled
Markov n-gram transition model, inspired by PERT's Bayesian decomposition:

```
P(word|pinyin, context) ∝ P_emission(word|pinyin) × P_transition(word|context)
```

The n-gram transition probability becomes a first-class scoring factor (multiplied,
not added as one feature among many), with Katz backoff smoothing and FTRL-learned
weighting.

## Architecture Change

**Before:**
```
score = α·unigram + β·bigram + γ·recency - σ_s·skip - σ_r·reject + δ·length + boost + FTRL_residual
         └─────────── 8 hand-tuned features mashed together ──────────┘
```

**After:**
```
score = emission_score(word, pinyin) + λ·log P_markov(word|context) + FTRL_residual
        └───── context-free ─────┘   └──── context-aware ────┘
```

- `emission_score`: unigram + recency + skip/reject penalties + length_bonus + last_pinyin_boost (bigram removed)
- `log P_markov`: Katz backoff interpolated 3-gram → 2-gram → 1-gram log-probability
- `λ`: learned online by FTRL, starts from config default, self-adjusts as n-gram data accumulates

## Data Model

New table in SQLite:

```sql
CREATE TABLE IF NOT EXISTS trigram_freq (
    prev2_word TEXT NOT NULL,
    prev1_word TEXT NOT NULL,
    curr_word  TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (prev2_word, prev1_word, curr_word)
);
```

Written on each `record_selection` when context has at least 2 prior words.

Existing `bigram_freq` and `unigram_freq` tables unchanged.

## Smoothing: Katz Backoff

```
if trigram count >= K_MIN:
    P_3 = (count - DISCOUNT) / total_from_context
elif bigram count >= K_MIN:
    P_2 = α_2 · (count - DISCOUNT) / total_from_ctx1
else:
    P_1 = α_1 · unigram_count / total_unigrams

log P_markov = log(P_3 or P_2 or P_1)
```

- `DISCOUNT` = 0.5 (absolute discounting)
- `K_MIN` = 3 (fall back below this threshold)
- `α_1`, `α_2`: backoff weights ensuring probability mass sums to 1

## Scoring Flow

```
rank(pinyin, context, candidates):
    emission = {c: emission_score(c, pinyin) for c in candidates}
    trans    = {c: transition_score(c, context) for c in candidates}

    if FTRL ready:
        for each candidate:
            # markov_logp is a FTRL feature; its weight w_markov is λ
            ftrl_score = FTRL.predict(c, context, ..., emission[c], trans[c], pinyin)
            score = emission[c] + ftrl_score  # FTRL internally handles w_markov · trans[c]
    else:
        # cold start: fixed λ₀
        score = emission[c] + LAMBDA_INIT · trans[c]

    return sorted by score descending
```

### How λ works

`markov_logp` is added as a continuous FTRL feature alongside existing features.
FTRL learns its weight `w_markov` through standard online gradient descent —
this weight **is** λ. During cold start (updates < 30), `LAMBDA_INIT` is used as
a fixed multiplier since FTRL weights haven't converged.

FTRL's `_featurize()` receives `emission` (float) and `markov_logp` (float)
individually, so it can learn separate weights for each. The old `phase1` and
`phase1_gap` features are removed.

### FTRL Feature Changes

In `_featurize()`, remove:
- `phase1` (composite weighted sum)
- `phase1_gap` (gap to max phase1)

Add:
- `emission` (float) — context-free base score
- `markov_logp` (float, ≤0) — log transition probability from n-gram model

All other features (`bias`, `len`, `n_cands`, `pos_norm`, `wlen_*`, `is_first`,
`is_last`, `hour_*`, `has_ctx`, `py_*`, `is_abbrev`, `py_len_ratio`, `word_*`)
retained unchanged.

## Configuration Changes

| Param | Action |
|-------|--------|
| `BETA` | Removed (bigram absorbed into transition_score) |
| `LAMBDA_INIT` | New, default 0.5 — initial weight on Markov transition |
| `BACKOFF_K_MIN` | New, default 3 |
| `DISCOUNT` | New, default 0.5 |

Other config values (`ALPHA`, `GAMMA`, `DECAY`, `SKIP_PENALTY`, `REJECT_PENALTY`,
`LENGTH_BONUS`, `LAST_PINYIN_BOOST`) retained for emission_score.

## Files Changed

| File | Change |
|------|--------|
| `ranker/db.py` | Add `trigram_freq` table + migration; write trigram in `record_selection`; add `get_trigram_freq()`, `get_unigram_total()` |
| `ranker/config.py` | Remove `BETA`; add `LAMBDA_INIT`, `BACKOFF_K_MIN`, `DISCOUNT` |
| `ranker/model.py` | Split `_score_phase1` into `_emission_score` + `_transition_score`; update `rank()` to use emission + λ·transition + FTRL; `record()`/`reject()` pass emission and markov_logp to FTRL |
| `ranker/local_ranker.py` | `_featurize()` accepts `emission` (float) and `markov_logp` (float) instead of `phase1_score`/`max_phase1`; add `markov_logp` feature; `predict()`/`update()`/`update_reject()` signatures updated |
| `rime/lua/rerank_filter.lua` | Track and pass `context2` (the word before `context`) by maintaining a sliding window of the last 2 committed words via `ctx:get_commit_text()` parsing |
| `scripts/eval_final.py` | Adapt to new scoring formula |

## What Stays the Same

- Cold-start behavior (first 30 selections use emission + LAMBDA_INIT·transition, structurally equivalent to current Phase 1 minus β·bigram)
- FTRL weights file format (new features auto-initialize to 0)
- External protocol: `rank`/`record`/`reject` action interface unchanged
- skip/reject negative feedback mechanism unchanged
- Server, socket, Lua filter architecture unchanged

## Implementation Order

1. `ranker/config.py` — config changes
2. `ranker/db.py` — trigram table + queries
3. `ranker/local_ranker.py` — FTRL feature signature update
4. `ranker/model.py` — scoring formula restructure
5. `rime/lua/rerank_filter.lua` — context2 passthrough
6. `scripts/eval_final.py` — evaluation update
7. Run tests (`tests/test_model.py`, `tests/test_db.py`, `tests/test_integration.py`)
