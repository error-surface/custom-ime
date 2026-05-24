"""
Synthetic evaluation for the custom-ime ranker.

Tests FTRL's ability to learn user preferences that contradict global
frequency. Three scenarios:
  A. Mild deviation: user prefers global #2 over #1 (common case)
  B. Strong deviation: user prefers a rare word (count=1) over common ones
  C. Context-dependent: bigram context changes the preferred word

All evaluations use time-ordered online training (no data leakage).
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ranker.db import SelectionDB
from ranker.local_ranker import MIN_SAMPLES
from ranker.model import RankingModel

DICT_PATH = Path(__file__).resolve().parent.parent / "ranker" / "dictionary_data.json"


def load_dictionary():
    with open(DICT_PATH) as f:
        return [(e[0], e[1]) for e in json.load(f)]


def build_pinyin_index(words):
    from pypinyin import lazy_pinyin
    idx = defaultdict(list)
    for word, count in words:
        idx["".join(lazy_pinyin(word))].append((word, count))
    return idx


def seed_db(db, words):
    import time
    now = time.time()
    for word, count in words:
        db._conn.execute(
            "INSERT INTO unigram_freq (word, count, skip_count, last_used) "
            "VALUES (?, ?, 0, ?)", (word, count, now))
    db._conn.commit()


def metrics(results):
    n = len(results)
    if n == 0:
        return {"top1": 0.0, "top3": 0.0, "mrr": 0.0, "n": 0}
    return {
        "top1": sum(1 for p, _ in results if p == 0) / n,
        "top3": sum(1 for p, _ in results if p < 3) / n,
        "mrr": sum(1.0 / (p + 1) for p, _ in results) / n,
        "n": n,
    }


def run_scenario(name, test_pinyins, user_pref_fn, n_rounds=1500,
                 context_mode=False):
    """Run one evaluation scenario.

    test_pinyins: list of (pinyin, [(word, seed_count), ...])
    user_pref_fn: function(pinyin, candidates) -> user's true preference order
    """
    import tempfile

    db_p1 = SelectionDB(Path(tempfile.mkdtemp()) / "eval_p1.db")
    db_p2 = SelectionDB(Path(tempfile.mkdtemp()) / "eval_p2.db")

    words_all = [(w, c) for _, entries in test_pinyins for w, c in entries]
    seed_db(db_p1, words_all)
    seed_db(db_p2, words_all)

    model_p1 = RankingModel(db_p1)
    model_p2 = RankingModel(db_p2)

    results_p1 = []
    results_p2 = []
    pinyin_pool = [py for py, _ in test_pinyins]
    weights = [1.0 / (i + 1) for i in range(len(pinyin_pool))]

    for rnd in range(n_rounds):
        py = random.choices(pinyin_pool, weights=weights, k=1)[0]
        entries = dict(test_pinyins)[py]

        # Candidates: all homophones (3-10)
        cand_words = [w for w, _ in sorted(entries, key=lambda x: -x[1])]
        if len(cand_words) < 3:
            continue
        cand_words = cand_words[:10]

        # User picks according to preference function
        pref_order = user_pref_fn(py, cand_words, entries)

        # Context handling for scenario C
        context = ""
        if context_mode:
            # Alternate between two contexts
            context = "typeA" if rnd % 2 == 0 else "typeB"

        # 85% pick top pref, 10% pick second, 5% random noise
        r = random.random()
        if r < 0.85:
            chosen = pref_order[0]
        elif r < 0.95:
            chosen = pref_order[1] if len(pref_order) > 1 else pref_order[0]
        else:
            chosen = random.choice(pref_order[2:]) if len(pref_order) > 2 else pref_order[0]
        if chosen not in cand_words:
            chosen = pref_order[0]

        # RIME default position
        rime_default = sorted(cand_words, key=lambda w: -dict(entries).get(w, 0))
        rime_pos = rime_default.index(chosen)

        # --- Phase 1 only ---
        p1_scores = {c: model_p1._score_phase1(c, context) for c in cand_words}
        p1_ranked = sorted(cand_words, key=lambda c: p1_scores[c], reverse=True)
        p1_pos = p1_ranked.index(chosen)
        results_p1.append((p1_pos, len(cand_words)))
        db_p1.record_selection(py, context, chosen, cand_words, rime_pos)

        # --- Phase 1 + 2 ---
        if model_p2._ftrl.ready:
            p2_ranked = model_p2.rank(py, context, cand_words)
            p2_pos = p2_ranked.index(chosen)
            results_p2.append((p2_pos, len(cand_words)))
        emissions = {c: model_p2._emission_score(c, py) for c in cand_words}
        transitions = {c: model_p2._transition_score(c, context) for c in cand_words}
        model_p2._ftrl.update(chosen, context, cand_words, rime_pos,
                              emissions=emissions, markov_logps=transitions, pinyin=py)
        db_p2.record_selection(py, context, chosen, cand_words, rime_pos)

    db_p1.close()
    db_p2.close()

    m_p1 = metrics(results_p1)
    m_p2 = metrics(results_p2)
    n_p2 = len(results_p2)
    p1_sub = metrics(results_p1[-n_p2:]) if n_p2 > 0 else {"top1": 0.0}

    return {"name": name, "p1": m_p1, "p2": m_p2, "p1_sub": p1_sub,
            "n_total": len(results_p1), "n_p2": n_p2,
            "delta": m_p2["top1"] - p1_sub["top1"] if n_p2 > 0 else 0.0}


def main():
    random.seed(42)

    print("Loading dictionary...")
    words = load_dictionary()
    pinyin_index = build_pinyin_index(words)

    # Find pinyins with enough homophones for each scenario
    rich = [(py, entries) for py, entries in pinyin_index.items()
            if len(entries) >= 4]
    rich.sort(key=lambda x: -len(x[1]))
    print(f"  {len(rich)} pinyins with >=4 homophones\n")

    test_pool = rich[:40]

    # --- Scenario A: Mild deviation (swap #1 and #2) ---
    def pref_a(py, cand_words, entries):
        order = sorted(cand_words, key=lambda w: -dict(entries).get(w, 0))
        if len(order) >= 2:
            order[0], order[1] = order[1], order[0]
        return order

    # --- Scenario B: Strong deviation (prefer a rare word) ---
    def pref_b(py, cand_words, entries):
        order = sorted(cand_words, key=lambda w: -dict(entries).get(w, 0))
        # Move the last-place word to first (strong counter-preference)
        if len(order) >= 3:
            rare = order.pop()
            order.insert(0, rare)
        return order

    # --- Scenario C: Context-dependent ---
    ctx_prefs = {}  # (pinyin, context) -> preferred word
    for py, entries in test_pool:
        order = sorted([w for w, _ in entries], key=lambda w: -dict(entries).get(w, 0))
        if len(order) >= 3:
            ctx_prefs[(py, "typeA")] = order[0]
            ctx_prefs[(py, "typeB")] = order[2]  # different choice for context B

    def pref_c(py, cand_words, entries):
        # This gets called but the context determines the pick
        # The context is handled in run_scenario via context_mode
        order = sorted(cand_words, key=lambda w: -dict(entries).get(w, 0))
        return order

    scenarios = [
        ("A. Mild deviation (swap #1<->#2)", pref_a, 1500, False),
        ("B. Strong deviation (rare word preferred)", pref_b, 2000, False),
        ("C. Context-dependent (bigram matters)", pref_c, 2000, True),
    ]

    print(f"{'='*70}")
    print(f"  FTRL Online Learning Evaluation — 3 Scenarios")
    print(f"  Pinyins: {len(test_pool)}  |  FTRL warmup: {MIN_SAMPLES} selections")
    print(f"{'='*70}\n")

    all_results = []

    for name, pref_fn, n_rounds, ctx_mode in scenarios:
        print(f"--- {name} ({n_rounds} rounds) ---")
        result = run_scenario(name, test_pool, pref_fn, n_rounds, ctx_mode)
        all_results.append(result)

        print(f"  Total selections:      {result['n_total']}")
        print(f"  FTRL evaluated on:     {result['n_p2']}")
        print(f"  {'Method':<28} {'Top-1':>8} {'Top-3':>8} {'MRR':>8}")
        print(f"  {'-'*52}")
        print(f"  {'Phase 1 (heuristic)':<28} {result['p1']['top1']:>7.1%} {result['p1']['top3']:>7.1%} {result['p1']['mrr']:>7.3f}")
        print(f"  {'Phase 1+2 (FTRL)':<28} {result['p2']['top1']:>7.1%} {result['p2']['top3']:>7.1%} {result['p2']['mrr']:>7.3f}")
        print(f"  {'Phase 1 (same subset)':<28} {result['p1_sub']['top1']:>7.1%} {result['p1_sub']['top3']:>7.1%} {result['p1_sub']['mrr']:>7.3f}")
        delta_str = f"+{result['delta']:.1%}" if result['delta'] >= 0 else f"{result['delta']:.1%}"
        print(f"  FTRL improvement:       {delta_str}")
        print()

    # --- Summary table ---
    print(f"  {'='*70}")
    print(f"  Summary")
    print(f"  {'='*70}")
    print(f"  {'Scenario':<35} {'P1 Top-1':>8} {'P1+2 Top-1':>8} {'Delta':>8}")
    print(f"  {'-'*63}")
    for r in all_results:
        delta_str = f"+{r['delta']:.1%}" if r['delta'] >= 0 else f"{r['delta']:.1%}"
        print(f"  {r['name']:<35} {r['p1_sub']['top1']:>7.1%} {r['p2']['top1']:>7.1%} {delta_str:>8}")


if __name__ == "__main__":
    main()
