"""Read-only live market data collector. No order/buy/sell/cancel endpoints."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from ai_investment_agent.adapters.live.config import market_http_config
from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.adapters.live.errors import result_from_http_error
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.adapters.live.market.parser import parse_market_document
from ai_investment_agent.collectors.query import collect_accessible
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, MarketDataKind
from ai_investment_agent.domain.market_feed import MarketDataRecord

PROVIDER = "live-market"


class LiveMarketDataCollector:
    """MarketDataCollector backed by a read-only JSON market feed.

    Path: GET {MARKET_DATA_BASE_URL}/market/{instrument}
    Optional query: asOf (ISO-8601).

    This adapter never calls order, buy, sell, cancel, or account endpoints.
    """

    def __init__(self, client: ProviderHttpClient | None = None) -> None:
        self._client = client or ProviderHttpClient(config=market_http_config())
        self.last_diagnostics: ProviderDiagnostics | None = None

    def collect(
        self,
        instrument: str,
        as_of: datetime,
        kinds: Sequence[MarketDataKind] | None = None,
        include_current_receive: bool = False,
    ) -> CollectionResult[MarketDataRecord]:
        requested_at = datetime.now(timezone.utc)
        try:
            payload = self._client.get_json(
                f"/market/{instrument}",
                params={"asOf": as_of.isoformat()},
            )
        except ProviderHttpError as exc:
            received = datetime.now(timezone.utc)
            result, diagnostics = result_from_http_error(
                exc,
                as_of=as_of,
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received,
                attempt_count=self._client.last_attempt_count,
                circuit_open=self._client.circuit.is_open,
            )
            self.last_diagnostics = diagnostics
            return result

        received_at = datetime.now(timezone.utc)
        if payload is None:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="EMPTY_PAYLOAD",
                error_message="market provider returned empty body",
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(
                error="live market empty payload",
                as_of=as_of,
            )
        if not isinstance(payload, dict):
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="SCHEMA_INVALID",
                error_message="market payload must be an object",
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(
                error="live market schema invalid",
                as_of=as_of,
            )

        status_hint = str(payload.get("status") or "").upper()
        if status_hint == "DATA_UNAVAILABLE":
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="PROVIDER_STATUS",
                error_message=str(payload.get("error") or "provider reported unavailable"),
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(
                error="live market provider status DATA_UNAVAILABLE",
                as_of=as_of,
            )

        try:
            parsed = parse_market_document(
                payload,
                instrument=instrument,
                collected_at=received_at,
            )
            records = parsed.records
        except (ValueError, KeyError, TypeError) as exc:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="SCHEMA_INVALID",
                error_message=str(exc),
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(
                error=f"live market parse failure: {exc}",
                as_of=as_of,
            )

        allowed = set(kinds) if kinds is not None else None

        def match(record: MarketDataRecord) -> bool:
            if record.instrument != instrument:
                return False
            if allowed is not None and record.kind not in allowed:
                return False
            return True

        access_as_of = received_at if include_current_receive else as_of
        result = collect_accessible(
            records,
            as_of=access_as_of,
            unavailable=False,
            unavailable_reason="live market unavailable",
            match=match,
            timestamps_of=lambda record: record.timestamps,
            freshness_of=lambda record: record.freshness_class,
            id_of=lambda record: record.record_id,
            empty_status=CollectionStatus.DATA_UNAVAILABLE,
            empty_error=f"No accessible live market data for {instrument}",
        )
        if parsed.skipped_incomplete and result.items:
            result = CollectionResult.degraded(
                list(result.items),
                error=f"INCOMPLETE_RECORDS: skipped {parsed.skipped_incomplete} invalid market rows",
                as_of=access_as_of,
                stale_item_ids=result.stale_item_ids,
            )
        latency_ms = (received_at - requested_at).total_seconds() * 1000.0
        if result.status is CollectionStatus.OK:
            self.last_diagnostics = ProviderDiagnostics.ok(
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received_at,
                source_timestamp=records[0].timestamps.source_received_at if records else None,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
            )
        elif result.status is CollectionStatus.STALE:
            self.last_diagnostics = ProviderDiagnostics(
                provider=PROVIDER,
                status=CollectionStatus.STALE,
                requested_at=requested_at,
                received_at=received_at,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
                error_code="STALE",
                error_message="market data older than freshness policy",
            )
        elif result.status is CollectionStatus.DEGRADED:
            self.last_diagnostics = ProviderDiagnostics.degraded(
                provider=PROVIDER,
                error_code="INCOMPLETE_RECORDS",
                error_message=result.error or "incomplete market rows",
                requested_at=requested_at,
                received_at=received_at,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
            )
        else:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="NO_ACCESSIBLE_DATA",
                error_message=result.error or "no accessible market data",
                requested_at=requested_at,
                received_at=received_at,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
            )
        return result


# Explicitly document that order-related methods are not part of this type.
FORBIDDEN_MARKET_METHODS = frozenset(
    {
        "place_order",
        "submit_order",
        "buy_order",
        "sell_order",
        "cancel_order",
        "broker_submit",
    }
)
