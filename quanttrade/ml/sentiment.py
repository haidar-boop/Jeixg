"""Sentiment, news and social-media analysis.

Ships with a zero-dependency finance lexicon scorer so it works out of the box,
and an optional transformer-based scorer (lazy-imported) for higher accuracy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Compact finance sentiment lexicon (extend for production use).
_POSITIVE = {
    "beat", "beats", "bullish", "surge", "surged", "rally", "rallies", "gain",
    "gains", "profit", "profits", "upgrade", "upgraded", "outperform", "strong",
    "growth", "record", "soar", "soared", "jump", "jumped", "buy", "boom",
    "breakout", "momentum", "exceeds", "exceeded", "optimistic", "rebound",
}
_NEGATIVE = {
    "miss", "misses", "missed", "bearish", "plunge", "plunged", "crash", "crashed",
    "loss", "losses", "downgrade", "downgraded", "underperform", "weak", "decline",
    "declined", "drop", "dropped", "fall", "fell", "sell", "bankruptcy", "fraud",
    "lawsuit", "warning", "cut", "slump", "fear", "recession", "selloff", "default",
}
_NEGATORS = {"not", "no", "never", "without", "n't"}
_WORD_RE = re.compile(r"[a-zA-Z']+")


@dataclass
class SentimentResult:
    score: float          # -1..1
    label: str            # positive / negative / neutral
    positive_hits: int = 0
    negative_hits: int = 0


class SentimentAnalyzer:
    """Lexicon-based sentiment with optional transformer backend."""

    def __init__(self, use_transformer: bool = False) -> None:
        self.use_transformer = use_transformer
        self._pipeline = None

    def score(self, text: str) -> float:
        return self.analyze(text).score

    def analyze(self, text: str) -> SentimentResult:
        tokens = _WORD_RE.findall(text.lower())
        pos = neg = 0
        for i, tok in enumerate(tokens):
            negated = i > 0 and tokens[i - 1] in _NEGATORS
            if tok in _POSITIVE:
                neg, pos = (neg + 1, pos) if negated else (neg, pos + 1)
            elif tok in _NEGATIVE:
                pos, neg = (pos + 1, neg) if negated else (pos, neg + 1)
        total = pos + neg
        score = 0.0 if total == 0 else (pos - neg) / total
        label = "neutral" if abs(score) < 0.2 else ("positive" if score > 0 else "negative")
        return SentimentResult(score=round(score, 4), label=label,
                               positive_hits=pos, negative_hits=neg)

    def score_transformer(self, text: str) -> float:  # pragma: no cover - optional
        """Use a HuggingFace sentiment pipeline if `transformers` is installed."""
        if self._pipeline is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise ImportError("pip install transformers torch to use the "
                                  "transformer sentiment backend") from exc
            self._pipeline = pipeline("sentiment-analysis")
        res = self._pipeline(text[:512])[0]
        sign = 1.0 if res["label"].upper().startswith("POS") else -1.0
        return sign * float(res["score"])

    def analyze_headlines(self, headlines: list[str]) -> dict:
        """Aggregate sentiment across a list of news headlines."""
        if not headlines:
            return {"mean": 0.0, "count": 0, "positive": 0, "negative": 0}
        results = [self.analyze(h) for h in headlines]
        mean = sum(r.score for r in results) / len(results)
        return {
            "mean": round(mean, 4),
            "count": len(results),
            "positive": sum(1 for r in results if r.label == "positive"),
            "negative": sum(1 for r in results if r.label == "negative"),
            "neutral": sum(1 for r in results if r.label == "neutral"),
        }

    def analyze_social(self, posts: list[str]) -> dict:
        """Aggregate social-media sentiment (Twitter/Reddit-style short posts)."""
        agg = self.analyze_headlines(posts)
        agg["bullish_ratio"] = (agg["positive"] / agg["count"]) if agg["count"] else 0.0
        return agg
