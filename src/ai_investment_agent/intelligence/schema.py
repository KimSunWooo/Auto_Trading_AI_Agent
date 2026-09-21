from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ai_investment_agent.domain.event_intelligence import ExtractedEntities
from ai_investment_agent.domain.event_types import canonicalize_event_type


ALLOWED_EXTRACTION_FIELDS = frozenset(
    {
        "countries",
        "entities",
        "sectors",
        "tickers",
        "eventType",
        "event_type",
        "category",
        "directionEvidence",
        "direction_evidence",
    }
)

FORBIDDEN_EXTRACTION_FIELDS = frozenset(
    {
        "action",
        "decision",
        "suggestedCapitalPct",
        "order",
        "buy",
        "sell",
        "system",
        "instructions",
    }
)


class ExtractionRejected(ValueError):
    pass


def validate_extraction(payload: dict[str, Any]) -> ExtractedEntities:
    """Schema gate: extra trade/instruction keys are rejected, not executed."""

    lowered = {str(key).lower(): key for key in payload}
    for forbidden in FORBIDDEN_EXTRACTION_FIELDS:
        if forbidden.lower() in lowered:
            raise ExtractionRejected(f"extractor returned forbidden field: {forbidden}")

    unknown = [
        key
        for key in payload
        if key not in ALLOWED_EXTRACTION_FIELDS and not str(key).startswith("_")
    ]
    if unknown:
        raise ExtractionRejected(f"extractor returned unknown fields: {unknown}")

    try:
        extracted = ExtractedEntities.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionRejected(str(exc)) from exc
    extracted.event_type = canonicalize_event_type(extracted.event_type)
    return extracted
