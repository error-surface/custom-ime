"""
FTRL-Proximal online learner for fine-tuning Phase 1 rankings.

Does NOT replace Phase 1 — it learns residual corrections on top of
the heuristic scores.  Activated only after MIN_SAMPLES selections.
"""
import json
import math
import time
from pathlib import Path

from ranker.config import FTRL_WEIGHTS_PATH

MIN_SAMPLES = 30


def _safe_sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(min(x, 20), -20)))


class FTRLRanker:
    """Online logistic regression that learns per-word and per-context
    adjustments to Phase 1 scores."""

    def __init__(self, alpha=0.05, beta=1.0, l1=0.5, l2=1.0,
                 weights_path=FTRL_WEIGHTS_PATH):
        self.alpha = alpha
        self.beta = beta
        self.l1 = l1
        self.l2 = l2
        self._weights_path = weights_path
        self.z = {}    # per-feature accumulated gradients
        self.n = {}    # per-feature squared gradient sums
        self._update_count = 0
        self._load()

    @property
    def ready(self):
        return self._update_count >= MIN_SAMPLES

    def _featurize(self, word, context, position, n_candidates,
                   phase1_score=0.0, max_phase1=0.0, pinyin=""):
        """Sparse features.  phase1_score lets FTRL learn residuals."""
        feats = {
            "bias": 1.0,
            "len": len(word),
            "n_cands": n_candidates,
            "pos_norm": position / max(n_candidates, 1),
            "phase1": phase1_score,
        }
        # Homophone competition: how far behind the group leader
        feats["phase1_gap"] = phase1_score - max_phase1
        # Word length one-hot (1, 2, 3, 4+)
        feats[f"wlen_{min(len(word), 4)}"] = 1.0
        # RIME's original ordering is a strong signal
        if position == 0:
            feats["is_first"] = 1.0
        if position == n_candidates - 1 and n_candidates > 1:
            feats["is_last"] = 1.0
        # Time bucket (4 periods)
        hour = time.localtime().tm_hour
        feats[f"hour_{hour // 6}"] = 1.0
        # Context features
        if context:
            feats["has_ctx"] = 1.0
            feats[f"bigram_{context}_{word}"] = 1.0
        # Pinyin identity (FTRL learns per-pinyin preferences)
        if pinyin:
            feats[f"py_{pinyin}"] = 1.0
            # Abbreviated pinyin detection: consonant-only segments = initials input
            segments = pinyin.replace("'", " ").replace("-", " ").split()
            has_abbrev = any(s and not any(c in s for c in "aeiouüAEIOUÜ") for s in segments)
            if has_abbrev:
                feats["is_abbrev"] = 1.0
            # Pinyin-to-word length ratio (small = more abbreviated)
            feats["py_len_ratio"] = len(pinyin) / max(len(word), 1)
        # Per-word identity
        feats[f"word_{word}"] = 1.0
        return feats

    def _compute_weight(self, f):
        """Closed-form FTRL weight for feature f."""
        z = self.z.get(f, 0.0)
        n = self.n.get(f, 0.0)
        if abs(z) <= self.l1:
            return 0.0
        sign = 1.0 if z >= 0 else -1.0
        denominator = (self.beta + math.sqrt(n)) / self.alpha + self.l2
        return (sign * self.l1 - z) / denominator

    def _score(self, features):
        wTx = sum(self._compute_weight(f) * x for f, x in features.items())
        return _safe_sigmoid(wTx)

    def predict(self, word, context, position, n_candidates,
                phase1_score=0.0, max_phase1=0.0, pinyin=""):
        """Return probability [0, 1] that this candidate is the right one."""
        feats = self._featurize(word, context, position, n_candidates,
                                phase1_score, max_phase1, pinyin)
        return self._score(feats)

    def update(self, chosen, context, candidates, position,
               phase1_scores=None, pinyin=""):
        """Online update after a user selection.

        phase1_scores: dict of word→Phase1 score, used as features.
        """
        p1 = phase1_scores or {}
        max_p1 = max(p1.values()) if p1 else 0.0
        for i, c in enumerate(candidates):
            feats = self._featurize(
                c, context, i, len(candidates),
                phase1_score=p1.get(c, 0.0),
                max_phase1=max_p1,
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

    def update_reject(self, rejected, context, candidates,
                      phase1_scores=None, pinyin=""):
        """Stronger negative update when user explicitly rejects a word.

        The rejected word gets label=0 with 2x gradient weight.
        Other candidates get label=0 normally (we don't know which is correct).
        """
        p1 = phase1_scores or {}
        max_p1 = max(p1.values()) if p1 else 0.0
        for i, c in enumerate(candidates):
            feats = self._featurize(
                c, context, i, len(candidates),
                phase1_score=p1.get(c, 0.0),
                max_phase1=max_p1,
                pinyin=pinyin,
            )
            label = 0.0  # all are negative in a rejection event
            pred = self._score(feats)
            grad = pred - label
            if c == rejected:
                grad *= 2.0  # double gradient for the explicitly rejected word
            for f, x in feats.items():
                n_old = self.n.get(f, 0.0)
                n_new = n_old + grad * grad
                sigma = (math.sqrt(n_new) - math.sqrt(n_old)) / self.alpha
                w = self._compute_weight(f)
                self.z[f] = self.z.get(f, 0.0) + grad * x - sigma * w
                self.n[f] = n_new
        self._update_count += 1
        self._save()

    def _save(self):
        if self._weights_path is None:
            return
        self._weights_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._weights_path, "w") as f:
            json.dump({
                "z": self.z, "n": self.n,
                "updates": self._update_count,
                "alpha": self.alpha, "beta": self.beta,
                "l1": self.l1, "l2": self.l2,
            }, f)

    def _load(self):
        if self._weights_path is None or not self._weights_path.exists():
            return
        with open(self._weights_path) as f:
            data = json.load(f)
        self.z = data.get("z", {})
        self.n = data.get("n", {})
        self._update_count = data.get("updates", 0)
        self.alpha = data.get("alpha", self.alpha)
        self.beta = data.get("beta", self.beta)
        self.l1 = data.get("l1", self.l1)
        self.l2 = data.get("l2", self.l2)
