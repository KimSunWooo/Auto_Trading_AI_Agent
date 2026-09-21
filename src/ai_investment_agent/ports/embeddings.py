from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Future embedding backend. Fixture implementations must stay local."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...
