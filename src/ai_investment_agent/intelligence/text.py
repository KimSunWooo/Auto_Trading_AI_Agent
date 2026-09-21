from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]{2,}")

STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "this",
        "are",
        "was",
        "were",
        "have",
        "has",
        "been",
        "will",
        "its",
        "said",
        "says",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "as",
        "is",
        "be",
        "or",
        "it",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "와",
        "과",
        "도",
        "으로",
        "하다",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in _TOKEN_RE.findall(text or "")
        if token.lower() not in STOPWORDS
    ]


def normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def token_fingerprint(tokens: list[str]) -> str:
    material = "|".join(sorted(set(tokens)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return max(0.0, min(1.0, dot))


def stable_hash(text: str, modulo: int) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest, 16) % modulo
