from __future__ import annotations

from ai_investment_agent.domain.event_intelligence import ParsedDocument, RawEvent
from ai_investment_agent.intelligence.text import normalize_whitespace


class EventParser:
    version = "0.1.0"

    def parse(self, raw: RawEvent) -> ParsedDocument:
        title = normalize_whitespace(raw.headline)
        body = normalize_whitespace(raw.body)
        text = normalize_whitespace(f"{title}\n{body}")
        return ParsedDocument(
            raw_id=raw.raw_id,
            title=title,
            text=text,
            language=raw.language,
            parser_version=self.version,
        )
