"""Domestic / global news collector. Never converts news directly to TradeProposal."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from ai_investment_agent.adapters.live.config import news_http_config
from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.adapters.live.errors import result_from_http_error
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.adapters.live.news.parser import parse_news_payload
from ai_investment_agent.collectors.query import collect_accessible
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass, IntelligenceKind
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord

PROVIDER = "live-news"
NEWS_KINDS = frozenset({IntelligenceKind.DOMESTIC_NEWS, IntelligenceKind.FOREIGN_NEWS})


class LiveNewsCollector:
    """NewsCollector over a configured wire/media JSON feed.

    GET {NEWS_BASE_URL}/news?ticker=&asOf=
    Outages are DATA_UNAVAILABLE — never an empty OK/NO_EVENT disguise.
    """

    def __init__(
        self,
        client: ProviderHttpClient | None = None,
        *,
        received_at_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client or ProviderHttpClient(config=news_http_config())
        self._received_at = received_at_fn or (lambda: datetime.now(timezone.utc))
        self.last_diagnostics: ProviderDiagnostics | None = None

    def collect(
        self,
        ticker: str | None,
        as_of: datetime,
        kinds: Sequence[IntelligenceKind] | None = None,
        include_current_receive: bool = False,
    ) -> CollectionResult[IntelligenceRecord]:
        requested_at = self._received_at()
        if not self._client.config.base_url:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="NOT_CONFIGURED",
                error_message="NEWS_BASE_URL is not set",
                requested_at=requested_at,
                received_at=requested_at,
            )
            return CollectionResult.unavailable(
                error="NEWS_BASE_URL is not set",
                as_of=as_of,
                freshness_class=FreshnessClass.INTRADAY,
            )

        params = {"asOf": as_of.isoformat()}
        if ticker:
            params["ticker"] = ticker
        try:
            payload = self._client.get_json("/news", params=params)
        except ProviderHttpError as exc:
            received = self._received_at()
            result, diagnostics = result_from_http_error(
                exc,
                as_of=as_of,
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received,
                attempt_count=self._client.last_attempt_count,
                circuit_open=self._client.circuit.is_open,
                freshness_class=FreshnessClass.INTRADAY,
            )
            self.last_diagnostics = diagnostics
            if result.status is CollectionStatus.NO_EVENT:
                return CollectionResult.unavailable(
                    error="news unavailable (refusing empty disguise)",
                    as_of=as_of,
                )
            return result

        received_at = self._received_at()
        if payload is None:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="EMPTY_PAYLOAD",
                error_message="empty news payload",
                requested_at=requested_at,
                received_at=received_at,
            )
            return CollectionResult.unavailable(error="news empty payload", as_of=as_of)
        if not isinstance(payload, dict):
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="SCHEMA_INVALID",
                error_message="news payload must be object",
                requested_at=requested_at,
                received_at=received_at,
            )
            return CollectionResult.unavailable(error="news schema invalid", as_of=as_of)

        status_hint = str(payload.get("status") or "").upper()
        if status_hint == "NO_EVENT":
            self.last_diagnostics = ProviderDiagnostics.no_event(
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.no_event(
                as_of=as_of,
                freshness_class=FreshnessClass.INTRADAY,
            )
        if status_hint == "DATA_UNAVAILABLE":
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="PROVIDER_STATUS",
                error_message=str(payload.get("error") or "news unavailable"),
                requested_at=requested_at,
                received_at=received_at,
            )
            return CollectionResult.unavailable(error="news provider unavailable", as_of=as_of)

        try:
            records = parse_news_payload(payload, ticker=ticker, collected_at=received_at)
        except (ValueError, KeyError, TypeError) as exc:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="SCHEMA_INVALID",
                error_message=str(exc),
                requested_at=requested_at,
                received_at=received_at,
            )
            return CollectionResult.unavailable(error=f"news parse failure: {exc}", as_of=as_of)

        requested_kinds = set(kinds) if kinds is not None else set(NEWS_KINDS)
        if not requested_kinds.issubset(NEWS_KINDS):
            return CollectionResult.unavailable(
                error=f"news collector does not serve {sorted(k.value for k in requested_kinds - NEWS_KINDS)}",
                as_of=as_of,
            )

        def match(record: IntelligenceRecord) -> bool:
            if record.kind not in requested_kinds:
                return False
            if ticker is None:
                return True
            return record.ticker == ticker or record.ticker is None

        access_as_of = received_at if include_current_receive else as_of
        result = collect_accessible(
            records,
            as_of=access_as_of,
            unavailable=False,
            unavailable_reason="news unavailable",
            match=match,
            timestamps_of=lambda record: record.timestamps,
            freshness_of=lambda record: record.freshness_class,
            id_of=lambda record: record.record_id,
            empty_status=CollectionStatus.NO_EVENT,
            reject_future_event_occurred=True,
        )
        latency_ms = (received_at - requested_at).total_seconds() * 1000.0
        if result.status is CollectionStatus.OK:
            self.last_diagnostics = ProviderDiagnostics.ok(
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received_at,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
            )
        elif result.status is CollectionStatus.NO_EVENT:
            self.last_diagnostics = ProviderDiagnostics.no_event(
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received_at,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
            )
        else:
            self.last_diagnostics = ProviderDiagnostics(
                provider=PROVIDER,
                status=result.status,
                requested_at=requested_at,
                received_at=received_at,
                latency_ms=latency_ms,
                attempt_count=self._client.last_attempt_count,
                error_code=result.status.value,
                error_message=result.error,
            )
        return result
