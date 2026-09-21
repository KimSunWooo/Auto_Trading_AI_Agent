from __future__ import annotations

import re

from ai_investment_agent.domain.event_intelligence import NormalizedEvent, RawEvent, SanitizedDocument
from ai_investment_agent.intelligence.text import normalize_whitespace, token_fingerprint, tokenize

_RETRACTION_RE = re.compile(
    r"(정정보도|오보\s*정정|기사\s*취소|retraction|we\s+retract|corrects?\s+earlier|false\s+report)",
    re.IGNORECASE,
)


class EventNormalizer:
    def normalize(self, sanitized: SanitizedDocument, raw: RawEvent) -> NormalizedEvent:
        title = normalize_whitespace(sanitized.title)
        text = normalize_whitespace(sanitized.text)
        tokens = tokenize(f"{title} {text}")
        return NormalizedEvent(
            raw_id=raw.raw_id,
            source=raw.source,
            source_id=raw.source_id,
            canonical_headline=title or text[:120],
            canonical_text=text,
            fingerprint=token_fingerprint(tokens),
            tokens=tokens,
            kind=raw.kind,
            published_at=raw.published_at,
            collected_at=raw.collected_at,
            language=sanitized.language or raw.language,
            ticker_hint=raw.ticker,
            country_hint=raw.country,
            injection_flags=list(sanitized.injection_flags),
            stripped_spans=list(sanitized.stripped_spans),
            looks_like_retraction=bool(_RETRACTION_RE.search(f"{raw.headline}\n{raw.body}")),
        )
