from __future__ import annotations

import math
from collections.abc import Sequence

from ai_investment_agent.intelligence.text import stable_hash


class HashedBagEmbeddingProvider:
    """Deterministic lexical embedding. Replace later with a real model."""

    def __init__(self, dimensions: int = 48) -> None:
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        tokens = [part for part in text.lower().split() if part]
        if not tokens:
            return vec
        for token in tokens:
            idx = stable_hash(token, self.dimensions)
            vec[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]
