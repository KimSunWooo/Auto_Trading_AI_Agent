"""Extensible event subtypes. Category is closed; type is an open string."""

from __future__ import annotations

KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "UNKNOWN",
        "RETRACTION",
        "RATE_DECISION",
        "INFLATION_PRINT",
        "EMPLOYMENT_PRINT",
        "POLICY_STATEMENT",
        "EARNINGS",
        "GUIDANCE",
        "DIVIDEND",
        "M_AND_A",
        "LEGAL",
        "PRODUCT",
        "SUPPLY_CHAIN",
        "RATING_CHANGE",
        "SANCTION",
        "CONFLICT",
        "MARKET_STRUCTURE",
        "LISTING_STATUS",
        "BOARD_MEETING",
        "INDUSTRY_CYCLE",
    }
)


def canonicalize_event_type(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    return value.strip().upper().replace(" ", "_").replace("-", "_")
