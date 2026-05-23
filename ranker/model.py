import math
import time
from pathlib import Path

from ranker.config import ALPHA, GAMMA, DECAY, SKIP_PENALTY, REJECT_PENALTY, LENGTH_BONUS, LAST_PINYIN_BOOST, LAMBDA_INIT, BACKOFF_K_MIN, DISCOUNT, FTRL_WEIGHTS_PATH
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

    def _transition_score(self, word: str, context: str, context2: str = "") -> float:
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

    def _score_phase1(self, word: str, context: str, pinyin: str = "") -> float:
        """Deprecated: kept for eval backward compat."""
        return self._emission_score(word, pinyin) + LAMBDA_INIT * self._transition_score(word, context)

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

    def record(self, pinyin: str, context: str, chosen: str,
               candidates: list, position: int, context2: str = ""):
        self._db.record_selection(pinyin, context, chosen, candidates, position, context2)

        if len(candidates) > 0:
            emissions = {c: self._emission_score(c, pinyin) for c in candidates}
            transitions = {c: self._transition_score(c, context, context2) for c in candidates}
            self._ftrl.update(chosen, context, candidates, position,
                              emissions=emissions, markov_logps=transitions, pinyin=pinyin)

    def reject(self, pinyin: str, context: str, rejected: str,
               candidates: list = None, context2: str = ""):
        self._db.record_reject(rejected)

        if candidates and len(candidates) > 0:
            emissions = {c: self._emission_score(c, pinyin) for c in candidates}
            transitions = {c: self._transition_score(c, context, context2) for c in candidates}
            self._ftrl.update_reject(rejected, context, candidates,
                                     emissions=emissions, markov_logps=transitions, pinyin=pinyin)
