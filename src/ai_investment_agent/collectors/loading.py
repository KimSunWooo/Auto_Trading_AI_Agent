from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from ai_investment_agent.domain.collection import (
    CollectionTimestamps,
    INTELLIGENCE_FRESHNESS,
    MARKET_DATA_FRESHNESS,
)
from ai_investment_agent.domain.corporate_action import CorporateAction
from ai_investment_agent.domain.enums import (
    CorporateActionType,
    FreshnessClass,
    IntelligenceKind,
    MarketDataKind,
)
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord
from ai_investment_agent.domain.market_feed import MarketDataRecord, OhlcvBar

DATA_DIR = Path(__file__).resolve().parent / "data"


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_required_dt(value: str | datetime | None, field: str) -> datetime:
    parsed = parse_dt(value)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _get(raw: dict[str, Any], *keys: str, default: object = None) -> object:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def timestamps_from_dict(raw: dict[str, Any]) -> CollectionTimestamps:
    return CollectionTimestamps(
        event_occurred_at=parse_dt(_get(raw, "eventOccurredAt", "event_occurred_at")),  # type: ignore[arg-type]
        published_at=parse_dt(_get(raw, "publishedAt", "published_at")),  # type: ignore[arg-type]
        source_received_at=parse_dt(_get(raw, "sourceReceivedAt", "source_received_at")),  # type: ignore[arg-type]
        collected_at=parse_required_dt(
            _get(raw, "collectedAt", "collected_at"),  # type: ignore[arg-type]
            "collectedAt",
        ),
        normalized_at=parse_dt(_get(raw, "normalizedAt", "normalized_at")),  # type: ignore[arg-type]
        analyzed_at=parse_dt(_get(raw, "analyzedAt", "analyzed_at")),  # type: ignore[arg-type]
        tradable_at=parse_required_dt(
            _get(raw, "tradableAt", "tradable_at"),  # type: ignore[arg-type]
            "tradableAt",
        ),
    )


def _decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _date(value: object | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def market_record_from_dict(raw: dict[str, Any]) -> MarketDataRecord:
    ohlcv_raw = _get(raw, "ohlcv")
    ohlcv = None
    if isinstance(ohlcv_raw, dict):
        ohlcv = OhlcvBar(
            open=Decimal(str(ohlcv_raw["open"])),
            high=Decimal(str(ohlcv_raw["high"])),
            low=Decimal(str(ohlcv_raw["low"])),
            close=Decimal(str(ohlcv_raw["close"])),
            volume=Decimal(str(ohlcv_raw.get("volume", "0"))),
            bar_start=parse_required_dt(
                ohlcv_raw.get("barStart") or ohlcv_raw.get("bar_start"),
                "barStart",
            ),
            bar_end=parse_required_dt(
                ohlcv_raw.get("barEnd") or ohlcv_raw.get("bar_end"),
                "barEnd",
            ),
        )
    kind = MarketDataKind(str(_get(raw, "kind")))
    freshness_raw = _get(raw, "freshnessClass", "freshness_class")
    freshness = FreshnessClass(str(freshness_raw)) if freshness_raw else None

    return MarketDataRecord(
        record_id=str(_get(raw, "recordId", "record_id")),
        kind=kind,
        instrument=str(_get(raw, "instrument")),
        timestamps=timestamps_from_dict(_get(raw, "timestamps") or {}),  # type: ignore[arg-type]
        freshness_class=freshness or MARKET_DATA_FRESHNESS[kind],
        value=_decimal(_get(raw, "value")),
        ohlcv=ohlcv,
        currency=_get(raw, "currency"),  # type: ignore[arg-type]
        unit=_get(raw, "unit"),  # type: ignore[arg-type]
        source=str(_get(raw, "source", default="fixture")),
        raw_ref=_get(raw, "rawRef", "raw_ref"),  # type: ignore[arg-type]
    )


def intelligence_record_from_dict(raw: dict[str, Any]) -> IntelligenceRecord:
    kind = IntelligenceKind(str(_get(raw, "kind")))
    freshness_raw = _get(raw, "freshnessClass", "freshness_class")

    return IntelligenceRecord(
        record_id=str(_get(raw, "recordId", "record_id")),
        kind=kind,
        headline=str(_get(raw, "headline")),
        timestamps=timestamps_from_dict(_get(raw, "timestamps") or {}),  # type: ignore[arg-type]
        freshness_class=(
            FreshnessClass(str(freshness_raw)) if freshness_raw else INTELLIGENCE_FRESHNESS[kind]
        ),
        ticker=_get(raw, "ticker"),  # type: ignore[arg-type]
        body=_get(raw, "body"),  # type: ignore[arg-type]
        source=str(_get(raw, "source", default="fixture")),
        language=_get(raw, "language"),  # type: ignore[arg-type]
        country=_get(raw, "country"),  # type: ignore[arg-type]
        raw_ref=_get(raw, "rawRef", "raw_ref"),  # type: ignore[arg-type]
    )


def corporate_action_from_dict(raw: dict[str, Any]) -> CorporateAction:
    freshness_raw = _get(raw, "freshnessClass", "freshness_class")
    return CorporateAction(
        action_id=str(_get(raw, "actionId", "action_id")),
        ticker=str(_get(raw, "ticker")),
        action_type=CorporateActionType(str(_get(raw, "actionType", "action_type"))),
        timestamps=timestamps_from_dict(_get(raw, "timestamps") or {}),  # type: ignore[arg-type]
        freshness_class=(
            FreshnessClass(str(freshness_raw)) if freshness_raw else FreshnessClass.LONG_HORIZON
        ),
        ex_date=_date(_get(raw, "exDate", "ex_date")),
        effective_date=_date(_get(raw, "effectiveDate", "effective_date")),
        ratio=_decimal(_get(raw, "ratio")),
        cash_amount=_decimal(_get(raw, "cashAmount", "cash_amount")),
        currency=_get(raw, "currency"),  # type: ignore[arg-type]
        new_ticker=_get(raw, "newTicker", "new_ticker"),  # type: ignore[arg-type]
        details=_get(raw, "details", default={}) or {},  # type: ignore[arg-type]
        source=str(_get(raw, "source", default="fixture")),
        raw_ref=_get(raw, "rawRef", "raw_ref"),  # type: ignore[arg-type]
    )
