"""
Offline replay evaluation for the custom-ime ranker.

Replays user selections in time order, computing Top-1/Top-3 accuracy
and MRR for three ranking strategies:
  - RIME default (original candidate order)
  - Phase 1 only (heuristic scores)
  - Phase 1 + 2 (FTRL online, trained only on prior selections)

No data leakage: FTRL is updated after each prediction, not before.
"""
import json
import sys
from pathlib import Path

# Add project root so imports work from scripts/ or paper/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ranker.config import DB_PATH
from ranker.db import SelectionDB
from ranker.local_ranker import FTRLRanker, MIN_SAMPLES
from ranker.model import RankingModel


def compute_metrics(positions, n_total):
    """Compute Top-1, Top-3 accuracy and MRR from list of (position, n_cands)."""
    top1 = sum(1 for p, _ in positions if p == 0) / n_total
    top3 = sum(1 for p, _ in positions if p < 3) / n_total
    mrr = sum(1.0 / (p + 1) for p, _ in positions) / n_total
    return {"top1": top1, "top3": top3, "mrr": mrr}


def evaluate():
    db = SelectionDB(DB_PATH)

    # Load all selections in time order
    rows = db.get_all_selections()
    if not rows:
        print("No selections found.")
        return

    print(f"Replaying {len(rows)} selections in time order...\n")

    # We use a fresh FTRL model for fair evaluation
    # (train only on prior selections, no pre-training)
    model = RankingModel(db)
    # Reset FTRL to empty state for clean time-ordered evaluation
    model._ftrl.z = {}
    model._ftrl.n = {}
    model._ftrl._update_count = 0

    rime_positions = []     # RIME default
    p1_positions = []       # Phase 1 only
    p2_positions = []       # Phase 1 + 2
    phase2_active = 0       # first selection where FTRL was ready

    for idx, row in enumerate(rows):
        pinyin = row["pinyin"]
        context = row["context"] or ""
        chosen = row["chosen"]
        candidates = json.loads(row["candidates"]) if isinstance(row["candidates"], str) else row["candidates"]
        original_pos = row["position"]

        if not candidates or chosen not in candidates:
            continue

        # --- RIME default ---
        rime_positions.append((original_pos, len(candidates)))

        # --- Phase 1 only ---
        p1_scores = {c: model._score_phase1(c, context) for c in candidates}
        p1_ranked = sorted(candidates, key=lambda c: p1_scores[c], reverse=True)
        p1_pos = p1_ranked.index(chosen)
        p1_positions.append((p1_pos, len(candidates)))

        # --- Phase 1 + 2 (FTRL, only if enough data accumulated) ---
        if model._ftrl.ready:
            p2_ranked = model.rank(pinyin, context, candidates)
            p2_pos = p2_ranked.index(chosen)
            p2_positions.append((p2_pos, len(candidates)))
            if phase2_active == 0:
                phase2_active = idx + 1

        # Train FTRL on this selection (after prediction, no leakage)
        emissions = {c: model._emission_score(c, pinyin) for c in candidates}
        transitions = {c: model._transition_score(c, context) for c in candidates}
        model._ftrl.update(chosen, context, candidates, original_pos,
                           emissions=emissions, markov_logps=transitions, pinyin=pinyin)

    # --- Results ---
    n = len(rime_positions)
    n_p2 = len(p2_positions)
    phase1_valid = n - MIN_SAMPLES  # FTRL-independent comparison range

    print(f"{'='*60}")
    print(f"Total selections replayed: {n}")
    print(f"FTRL active after: {MIN_SAMPLES} selections")
    print(f"Phase 1+2 evaluated on: {n_p2} selections")
    print(f"{'='*60}\n")

    rime_m = compute_metrics(rime_positions, n)
    p1_m = compute_metrics(p1_positions, n)

    print(f"{'Method':<25} {'Top-1':>8} {'Top-3':>8} {'MRR':>8}")
    print(f"{'-'*49}")
    print(f"{'RIME default':<25} {rime_m['top1']:>7.1%} {rime_m['top3']:>7.1%} {rime_m['mrr']:>7.3f}")
    print(f"{'Phase 1 (heuristic)':<25} {p1_m['top1']:>7.1%} {p1_m['top3']:>7.1%} {p1_m['mrr']:>7.3f}")

    if n_p2 > 0:
        p2_m = compute_metrics(p2_positions, n_p2)
        print(f"{'Phase 1+2 (FTRL)':<25} {p2_m['top1']:>7.1%} {p2_m['top3']:>7.1%} {p2_m['mrr']:>7.3f}")

        # Compare Phase 1 vs Phase 1+2 on the same subset where FTRL was active
        p1_subset = p1_positions[MIN_SAMPLES:]
        p1_sub_m = compute_metrics(p1_subset, n_p2)
        print(f"\n--- Same-subset comparison (last {n_p2} selections) ---")
        print(f"{'Phase 1 only':<25} {p1_sub_m['top1']:>7.1%} {p1_sub_m['top3']:>7.1%} {p1_sub_m['mrr']:>7.3f}")
        print(f"{'Phase 1+2 (FTRL)':<25} {p2_m['top1']:>7.1%} {p2_m['top3']:>7.1%} {p2_m['mrr']:>7.3f}")

        # Improvement
        delta = p2_m['top1'] - p1_sub_m['top1']
        print(f"\nTop-1 improvement from FTRL: {delta:+.1%}")

    db.close()


if __name__ == "__main__":
    evaluate()
