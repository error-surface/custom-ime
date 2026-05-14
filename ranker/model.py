import json
import math
import pickle
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import SGDClassifier

from ranker.config import ALPHA, BETA, GAMMA, DECAY, SKIP_PENALTY, LENGTH_BONUS, PHASE2_THRESHOLD
from ranker.db import SelectionDB


class RankingModel:
    def __init__(self, db: SelectionDB, model_path: Path):
        self._db = db
        self._model_path = model_path
        self._sgd = None

    def current_phase(self) -> int:
        if self._sgd is not None:
            return 2
        return 1

    def rank(self, pinyin: str, context: str, candidates: list) -> list:
        if not candidates:
            return []
        if self._sgd is not None:
            return self._rank_phase2(pinyin, context, candidates)
        scored = [(c, self._score_phase1(c, context)) for c in candidates]
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
        # Normalize skip penalty by selection count: a frequently-chosen word
        # overcomes early skips; a never-chosen word keeps the full penalty.
        skip_penalty = SKIP_PENALTY * skip_count / (1 + unigram)
        length_bonus = LENGTH_BONUS * max(0, len(word) - 1)
        return ALPHA * unigram + BETA * bigram + GAMMA * recency - skip_penalty + length_bonus

    def _extract_features(self, word: str, context: str, position: int,
                          n_candidates: int) -> list:
        unigram = self._db.get_unigram_freq(word)
        bigram = self._db.get_bigram_freq(context, word) if context else 0
        last_used = self._db.get_last_used(word)
        recency = 0.0
        if last_used is not None:
            days_ago = (time.time() - last_used) / 86400
            recency = math.pow(DECAY, days_ago)
        norm_position = position / max(n_candidates, 1)
        word_len = len(word)
        hour = time.localtime().tm_hour
        time_bucket = 0 if hour < 8 else (1 if hour < 18 else 2)
        return [unigram, bigram, recency, norm_position, word_len, time_bucket]

    def _rank_phase2(self, pinyin: str, context: str, candidates: list) -> list:
        features = []
        for i, c in enumerate(candidates):
            features.append(self._extract_features(c, context, i, len(candidates)))
        X = np.array(features)
        scores = self._sgd.decision_function(X)
        indices = np.argsort(-scores)
        return [candidates[i] for i in indices]

    def maybe_train_phase2(self):
        count = self._db.get_selection_count()
        if count < PHASE2_THRESHOLD:
            return
        selections = self._db.get_all_selections()
        X, y = [], []
        for sel in selections:
            cands = json.loads(sel["candidates"]) if isinstance(sel["candidates"], str) else sel["candidates"]
            chosen = sel["chosen"]
            context = sel["context"]
            for i, c in enumerate(cands):
                feat = self._extract_features(c, context, i, len(cands))
                X.append(feat)
                y.append(1 if c == chosen else 0)
        X = np.array(X)
        y = np.array(y)
        if len(set(y)) < 2:
            return
        self._sgd = SGDClassifier(loss="log_loss", random_state=42, max_iter=1000)
        self._sgd.fit(X, y)
        self._save_model()

    def load_phase2(self):
        if self._model_path.exists():
            with open(self._model_path, "rb") as f:
                self._sgd = pickle.load(f)

    def _save_model(self):
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._model_path, "wb") as f:
            pickle.dump(self._sgd, f)

    def record(self, pinyin: str, context: str, chosen: str,
               candidates: list, position: int):
        self._db.record_selection(pinyin, context, chosen, candidates, position)
        if self._sgd is not None and len(candidates) > 0:
            X_new, y_new = [], []
            for i, c in enumerate(candidates):
                feat = self._extract_features(c, context, i, len(candidates))
                X_new.append(feat)
                y_new.append(1 if c == chosen else 0)
            X_new = np.array(X_new)
            y_new = np.array(y_new)
            if len(set(y_new)) >= 2:
                self._sgd.partial_fit(X_new, y_new)
                self._save_model()
