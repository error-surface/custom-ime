import math
import time
from pathlib import Path

from ranker.config import ALPHA, BETA, GAMMA, DECAY, SKIP_PENALTY, LENGTH_BONUS, FTRL_WEIGHTS_PATH
from ranker.db import SelectionDB
from ranker.local_ranker import FTRLRanker, MIN_SAMPLES


class RankingModel:
    def __init__(self, db: SelectionDB, ftrl_weights_path=None):
        self._db = db
        if ftrl_weights_path is None:
            ftrl_weights_path = FTRL_WEIGHTS_PATH
        self._ftrl = FTRLRanker(weights_path=ftrl_weights_path)

    def current_phase(self) -> int:
        if self._ftrl.ready:
            return 2
        return 1

    def rank(self, pinyin: str, context: str, candidates: list) -> list:
        if not candidates:
            return []

        # Phase 1: heuristic scores (always used, handles cold start)
        p1_scores = {c: self._score_phase1(c, context) for c in candidates}

        # Phase 2: blend FTRL corrections on top of Phase 1
        if self._ftrl.ready:
            scored = []
            for i, c in enumerate(candidates):
                p1 = p1_scores[c]
                ftrl_prob = self._ftrl.predict(
                    c, context, i, len(candidates), phase1_score=p1,
                )
                # FTRL correction: boost (prob > 0.5) or penalize (prob < 0.5)
                # The adjustment is modest so Phase 1 heuristics still dominate
                adjustment = ftrl_prob - 0.5
                scored.append((c, p1 + adjustment))
        else:
            scored = [(c, p1_scores[c]) for c in candidates]

        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored]

    def _score_phase1(self, word: str, context: str) -> float:
        unigram = self._db.get_unigram_freq(word)
        bigram = self._db.get_bigram_freq(context, word) if context else 0
        skip_count = self._db.get_skip_count(word)
        last_used = self._db.get_last_used(word)
        recency = 0.0
        if last_used is not None:
            days_ago = (time.time() - last_used) / 86400
            recency = math.pow(DECAY, days_ago)
        skip_penalty = SKIP_PENALTY * skip_count / (1 + unigram)
        extra = max(0, len(word) - 1)
        length_bonus = LENGTH_BONUS * (extra ** 2)
        return ALPHA * unigram + BETA * bigram + GAMMA * recency - skip_penalty + length_bonus

    def record(self, pinyin: str, context: str, chosen: str,
               candidates: list, position: int):
        self._db.record_selection(pinyin, context, chosen, candidates, position)

        # Online FTRL update with Phase 1 scores as features
        if len(candidates) > 0:
            p1_scores = {c: self._score_phase1(c, context) for c in candidates}
            self._ftrl.update(chosen, context, candidates, position,
                              phase1_scores=p1_scores)
