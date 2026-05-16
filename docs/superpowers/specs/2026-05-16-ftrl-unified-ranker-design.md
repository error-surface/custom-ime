# Unify Phase 1 + Phase 2 into Single FTRL Ranker

## Goal

Replace the two-stage ranking (Phase 1 heuristic + Phase 2 FTRL residual) with a unified
FTRL model that takes all Phase 1 features as input. Eliminate the 8 hand-tuned constants
(α,β,γ,decay,skip_penalty,reject_penalty,length_bonus,last_pinyin_boost) — FTRL learns their
equivalent weights online.

## Architecture Change

**Before:**
```
candidates → Phase1(8 hand-tuned weights, 6 features) → base score
                                                           ↓
                           Phase2(FTRL learns ±0.5 residual) → final ranking
```

**After:**
```
candidates → P1 feature extraction (unigram, bigram, recency, skip, reject,
                                     length, last_pinyin) → raw numbers
                                                              ↓
                  FTRL takes P1 features + positional/pinyin/context features
                  → single score per candidate → final ranking
```

`model.rank()` returns `sorted(candidates, key=FTRL.predict, reverse=True)`.

## Cold Start

Keep Phase 1 scoring formula as fallback for the first 30 selections (MIN_SAMPLES).
After 30 selections, switch to pure FTRL. No behavior change from user perspective.

## Feature Set

### New P1 features fed into FTRL (replacing `phase1`/`phase1_gap` pseudo-features):

| Feature | Source | Notes |
|---------|--------|-------|
| `p1_unigram` | DB unigram count | raw count, not α-weighted |
| `p1_bigram` | DB bigram count | raw count, not β-weighted |
| `p1_recency` | `DECAY ** days_ago` | scalar [0,1] |
| `p1_skip_rate` | `skip_count / (1 + count)` | normalized |
| `p1_reject_rate` | `reject_count / (1 + count)` | normalized |
| `p1_length_bonus` | `(len-1)^2` for len>1 else 0 | raw value |
| `p1_last_pinyin` | 1.0 if word == last chosen for this pinyin | binary |

### Existing FTRL features retained:

`bias`, `len`, `n_cands`, `pos_norm`, `wlen_{1,2,3,4}`, `is_first`, `is_last`,
`hour_{0..3}`, `has_ctx`, `bigram_{ctx}_{word}`, `py_{pinyin}`, `is_abbrev`,
`py_len_ratio`, `word_{word}`

### Removed:

`phase1` (composite score), `phase1_gap` — replaced by the individual P1 features above.

## Files Changed

| File | Change |
|------|--------|
| `ranker/local_ranker.py` | `_featurize()` accepts `p1_features` dict instead of `phase1_score`/`max_phase1`; `predict()`/`update()`/`update_reject()` signatures updated |
| `ranker/model.py` | New `_get_p1_features(word, context, pinyin)` method; `rank()` uses pure FTRL after warmup (cold-start path uses P1 formula); `record()`/`reject()` pass P1 features to FTRL |
| `ranker/config.py` | No change — weights remain for cold-start P1 only |
| `scripts/eval_final.py` | Update evaluation to reflect unified architecture |

Files NOT changed: `db.py`, `server.py`, `rerank_filter.lua`, `select_notifier.lua`.

## Scoring Flow

```
rank(pinyin, context, candidates):
    if FTRL not ready (updates < 30):
        return P1 formula scores (backward compat)
    else:
        p1_feats = extract_p1_features(each candidate)
        for each candidate:
            score = FTRL.predict(word, context, position, n_cands,
                                 p1_features=feats, pinyin=pinyin)
        return sorted by score desc
```

## Key Invariants

- `select_notifier.lua` is unchanged — skip/reject signals keep flowing
- `db.py` is unchanged — all DB writes identical
- FTRL weight file format unchanged — backward compatible
- Server protocol (rank/select/reject actions) unchanged
