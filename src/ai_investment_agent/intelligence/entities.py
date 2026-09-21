from __future__ import annotations

import re

from ai_investment_agent.domain.enums import EventCategory, IntelligenceKind
from ai_investment_agent.domain.event_intelligence import ExtractedEntities, NormalizedEvent
from ai_investment_agent.domain.event_types import canonicalize_event_type
from ai_investment_agent.intelligence.schema import ExtractionRejected, validate_extraction

_TICKER_RE = re.compile(r"\b(\d{6})\b")
_US_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")

_COUNTRIES = {
    "korea": "KR",
    "south korea": "KR",
    "한국": "KR",
    "대한민국": "KR",
    "united states": "US",
    "u.s.": "US",
    "us ": "US",
    "미국": "US",
    "china": "CN",
    "중국": "CN",
    "japan": "JP",
    "일본": "JP",
    "euro": "EU",
    "europe": "EU",
    "유럽": "EU",
}

_ENTITIES = {
    "federal reserve": "Federal Reserve",
    "fed": "Federal Reserve",
    "연준": "Federal Reserve",
    "bank of korea": "Bank of Korea",
    "한국은행": "Bank of Korea",
    "samsung electronics": "Samsung Electronics",
    "samsung": "Samsung Electronics",
    "삼성전자": "Samsung Electronics",
    "sk hynix": "SK hynix",
    "sk하이닉스": "SK hynix",
}

_SECTORS = {
    "semiconductor": "semiconductor",
    "반도체": "semiconductor",
    "bank": "financials",
    "은행": "financials",
    "auto": "auto",
    "자동차": "auto",
    "energy": "energy",
    "에너지": "energy",
}

_TYPE_HINTS = (
    (
        "RATE_DECISION",
        re.compile(
            r"rate\s+(hold|hike|cut)|holds?\s+(interest\s+)?rates?|"
            r"interest rates? unchanged|금리\s*(동결|인상|인하)",
            re.I,
        ),
    ),
    ("INFLATION_PRINT", re.compile(r"\bcpi\b|inflation|물가", re.I)),
    ("EARNINGS", re.compile(r"earnings|operating profit|실적|영업이익", re.I)),
    ("SANCTION", re.compile(r"sanction|제재", re.I)),
    ("CONFLICT", re.compile(r"war|missile|침공|미사일|전쟁", re.I)),
    ("M_AND_A", re.compile(r"acquire|merger|인수|합병", re.I)),
    ("LISTING_STATUS", re.compile(r"delist|trading halt|상장폐지|거래정지", re.I)),
    ("BOARD_MEETING", re.compile(r"board meeting|이사회", re.I)),
    ("RETRACTION", re.compile(r"retract|정정보도|오보", re.I)),
    ("POLICY_STATEMENT", re.compile(r"policy|정책", re.I)),
)

_KIND_CATEGORY = {
    IntelligenceKind.CENTRAL_BANK: EventCategory.MACRO,
    IntelligenceKind.GOVERNMENT_POLICY: EventCategory.MACRO,
    IntelligenceKind.ECONOMIC_INDICATOR: EventCategory.MACRO,
    IntelligenceKind.GEOPOLITICS: EventCategory.GEOPOLITICAL,
    IntelligenceKind.CORPORATE_DISCLOSURE: EventCategory.CORPORATE,
    IntelligenceKind.CORPORATE_EVENT: EventCategory.CORPORATE,
    IntelligenceKind.INDUSTRY_EVENT: EventCategory.INDUSTRY,
    IntelligenceKind.DOMESTIC_NEWS: EventCategory.MARKET,
    IntelligenceKind.FOREIGN_NEWS: EventCategory.MARKET,
}

_US_TICKER_ALLOW = frozenset({"AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG", "META", "JPM"})


class EntityExtractor:
    """Gazetteer/regex extractor. Document text is data, never an instruction."""

    def extract(self, members: list[NormalizedEvent]) -> ExtractedEntities:
        blob = " ".join(f"{item.canonical_headline} {item.canonical_text}" for item in members)
        lowered = blob.lower()
        countries = _unique(
            [member.country_hint for member in members if member.country_hint]
            + [code for needle, code in _COUNTRIES.items() if needle in lowered]
        )
        entities = _unique(
            [name for needle, name in _ENTITIES.items() if needle in lowered]
        )
        sectors = _unique([name for needle, name in _SECTORS.items() if needle in lowered])
        tickers = _unique(
            [member.ticker_hint for member in members if member.ticker_hint]
            + _TICKER_RE.findall(blob)
            + [token for token in _US_TICKER_RE.findall(blob) if token in _US_TICKER_ALLOW]
        )
        event_type = "UNKNOWN"
        for name, pattern in _TYPE_HINTS:
            if pattern.search(blob):
                event_type = name
                break
        if any(member.looks_like_retraction for member in members):
            event_type = "RETRACTION"
        category = _category_for(members, event_type)
        payload = {
            "countries": countries,
            "entities": entities,
            "sectors": sectors,
            "tickers": tickers,
            "eventType": canonicalize_event_type(event_type),
            "category": category.value if category else None,
            "directionEvidence": [],
        }
        return validate_extraction(payload)


def extraction_from_untrusted_payload(payload: dict) -> ExtractedEntities:
    """Used in tests to prove command-shaped LLM JSON cannot pass the schema."""
    try:
        return validate_extraction(payload)
    except ExtractionRejected:
        return ExtractedEntities(event_type="UNKNOWN")


def _category_for(members: list[NormalizedEvent], event_type: str) -> EventCategory:
    if event_type in {"RATE_DECISION", "INFLATION_PRINT", "EMPLOYMENT_PRINT", "POLICY_STATEMENT"}:
        return EventCategory.MACRO
    if event_type in {"SANCTION", "CONFLICT"}:
        return EventCategory.GEOPOLITICAL
    if event_type in {"EARNINGS", "GUIDANCE", "M_AND_A", "BOARD_MEETING", "LISTING_STATUS"}:
        return EventCategory.CORPORATE
    if event_type == "INDUSTRY_CYCLE":
        return EventCategory.INDUSTRY
    for member in members:
        if member.kind is not None:
            return _KIND_CATEGORY.get(member.kind, EventCategory.MARKET)
    return EventCategory.MARKET


def _unique(values: list[str | None]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            seen.append(value)
    return seen
