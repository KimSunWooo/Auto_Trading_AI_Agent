"""OpenDART disclosure collector. Query-only; never places orders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_investment_agent.adapters.live.config import dart_http_config
from ai_investment_agent.adapters.live.dart.parser import dart_list_to_records
from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.adapters.live.errors import result_from_http_error
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.collectors.query import collect_accessible
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord

PROVIDER = "opendart"


class LiveDisclosureCollector:
    """DisclosureCollector for OpenDART list.json (read-only).

    Env:
      DART_API_KEY (required for live calls)
      DART_BASE_URL (default https://opendart.fss.or.kr/api)
      DART_CORP_CODE_<TICKER> optional corp_code override (e.g. DART_CORP_CODE_005930)
    """

    def __init__(self, client: ProviderHttpClient | None = None) -> None:
        self._client = client or ProviderHttpClient(config=dart_http_config())
        self.last_diagnostics: ProviderDiagnostics | None = None

    def collect(self, ticker: str, as_of: datetime) -> CollectionResult[IntelligenceRecord]:
        import os

        requested_at = datetime.now(timezone.utc)
        api_key = self._client.config.api_key()
        if not api_key and not self._client.config.base_url.startswith("https://example"):
            # Still allow fake/test base URLs without a key when transport is injected.
            if "opendart.fss.or.kr" in self._client.config.base_url:
                self.last_diagnostics = ProviderDiagnostics.unavailable(
                    provider=PROVIDER,
                    error_code="MISSING_CREDENTIAL",
                    error_message="DART_API_KEY is not set",
                    requested_at=requested_at,
                    received_at=requested_at,
                )
                return CollectionResult.unavailable(
                    error="DART_API_KEY is not set",
                    as_of=as_of,
                    freshness_class=FreshnessClass.DAILY,
                )

        corp_code = os.environ.get(f"DART_CORP_CODE_{ticker}") or os.environ.get(
            "DART_CORP_CODE",
            "",
        )
        end = as_of.astimezone(timezone.utc).date()
        start = end - timedelta(days=30)
        params = {
            "crtfc_key": api_key or "",
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "page_count": "100",
        }
        if corp_code:
            params["corp_code"] = corp_code

        try:
            payload = self._client.get_json("/list.json", params=params)
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
                freshness_class=FreshnessClass.DAILY,
            )
            self.last_diagnostics = diagnostics
            # Critical: never disguise DART outage as NO_EVENT.
            if result.status is CollectionStatus.NO_EVENT:
                return CollectionResult.unavailable(
                    error="dart unavailable (refusing NO_EVENT disguise)",
                    as_of=as_of,
                )
            return result

        received_at = datetime.now(timezone.utc)
        if not isinstance(payload, dict):
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="SCHEMA_INVALID",
                error_message="dart payload must be object",
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(error="dart schema invalid", as_of=as_of)

        status = str(payload.get("status") or "")
        # 013 = no data (genuine empty). 000 = ok.
        if status == "013":
            self.last_diagnostics = ProviderDiagnostics.no_event(
                provider=PROVIDER,
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.no_event(as_of=as_of, freshness_class=FreshnessClass.DAILY)
        if status and status != "000":
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code=f"DART_STATUS_{status}",
                error_message=str(payload.get("message") or status),
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(
                error=f"dart status {status}",
                as_of=as_of,
            )

        try:
            records = dart_list_to_records(payload, ticker=ticker, collected_at=received_at)
        except (ValueError, KeyError, TypeError) as exc:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="SCHEMA_INVALID",
                error_message=str(exc),
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(error=f"dart parse failure: {exc}", as_of=as_of)

        result = collect_accessible(
            records,
            as_of=as_of,
            unavailable=False,
            unavailable_reason="dart unavailable",
            match=lambda record: record.ticker == ticker,
            timestamps_of=lambda record: record.timestamps,
            freshness_of=lambda record: record.freshness_class,
            id_of=lambda record: record.record_id,
            empty_status=CollectionStatus.NO_EVENT,
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
