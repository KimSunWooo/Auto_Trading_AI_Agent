"""OpenDART disclosure collector. Query-only; never places orders."""

from __future__ import annotations

import os
from collections.abc import Callable
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
PAGE_SIZE = 100
PAGE_CAP = 50


def resolve_dart_corp_code(ticker: str) -> str | None:
    specific = os.environ.get(f"DART_CORP_CODE_{ticker}", "").strip()
    generic = os.environ.get("DART_CORP_CODE", "").strip()
    value = specific or generic
    return value or None


class LiveDisclosureCollector:
    """DisclosureCollector for OpenDART list.json (read-only).

    Env:
      DART_API_KEY (required for live calls)
      DART_BASE_URL (default https://opendart.fss.or.kr/api)
      DART_CORP_CODE_<TICKER> or DART_CORP_CODE (required; unfiltered list is refused)
    """

    def __init__(
        self,
        client: ProviderHttpClient | None = None,
        *,
        received_at_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client or ProviderHttpClient(config=dart_http_config())
        self._received_at = received_at_fn or (lambda: datetime.now(timezone.utc))
        self.last_diagnostics: ProviderDiagnostics | None = None

    def collect(
        self,
        ticker: str,
        as_of: datetime,
        include_current_receive: bool = False,
    ) -> CollectionResult[IntelligenceRecord]:
        requested_at = self._received_at()
        api_key = self._client.config.api_key()
        if not api_key and not self._client.config.base_url.startswith("https://example"):
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

        corp_code = resolve_dart_corp_code(ticker)
        if not corp_code:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="MISSING_CORP_CODE",
                error_message="ticker↔corp_code mapping is required",
                requested_at=requested_at,
                received_at=requested_at,
            )
            return CollectionResult.unavailable(
                error="DART MISSING_CORP_CODE: ticker↔corp_code mapping is required",
                as_of=as_of,
                freshness_class=FreshnessClass.DAILY,
            )

        end = as_of.astimezone(timezone.utc).date()
        start = end - timedelta(days=30)
        page_no = 1
        total_page = 1
        merged: dict[str, object] = {"status": "000", "list": []}
        incomplete = False
        incomplete_reason = ""
        received_at = requested_at

        while page_no <= min(total_page, PAGE_CAP):
            params = {
                "crtfc_key": api_key or "",
                "bgn_de": start.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"),
                "page_count": str(PAGE_SIZE),
                "page_no": str(page_no),
                "corp_code": corp_code,
            }
            try:
                payload = self._client.get_json("/list.json", params=params)
            except ProviderHttpError as exc:
                received_at = self._received_at()
                if page_no == 1:
                    result, diagnostics = result_from_http_error(
                        exc,
                        as_of=as_of,
                        provider=PROVIDER,
                        requested_at=requested_at,
                        received_at=received_at,
                        attempt_count=self._client.last_attempt_count,
                        circuit_open=self._client.circuit.is_open,
                        freshness_class=FreshnessClass.DAILY,
                    )
                    self.last_diagnostics = diagnostics
                    if result.status is CollectionStatus.NO_EVENT:
                        return CollectionResult.unavailable(
                            error="dart unavailable (refusing NO_EVENT disguise)",
                            as_of=as_of,
                        )
                    return result
                incomplete = True
                incomplete_reason = f"PAGINATION_INCOMPLETE: page {page_no} failed ({exc.error_code})"
                break

            received_at = self._received_at()
            if not isinstance(payload, dict):
                if page_no == 1:
                    self.last_diagnostics = ProviderDiagnostics.unavailable(
                        provider=PROVIDER,
                        error_code="SCHEMA_INVALID",
                        error_message="dart payload must be object",
                        requested_at=requested_at,
                        received_at=received_at,
                        attempt_count=self._client.last_attempt_count,
                    )
                    return CollectionResult.unavailable(error="dart schema invalid", as_of=as_of)
                incomplete = True
                incomplete_reason = f"PAGINATION_INCOMPLETE: page {page_no} schema invalid"
                break

            status = str(payload.get("status") or "")
            if page_no == 1 and status == "013":
                self.last_diagnostics = ProviderDiagnostics.no_event(
                    provider=PROVIDER,
                    requested_at=requested_at,
                    received_at=received_at,
                    attempt_count=self._client.last_attempt_count,
                )
                return CollectionResult.no_event(as_of=as_of, freshness_class=FreshnessClass.DAILY)
            if status and status != "000":
                if page_no == 1:
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
                incomplete = True
                incomplete_reason = f"PAGINATION_INCOMPLETE: page {page_no} status {status}"
                break

            rows = payload.get("list") or []
            if not isinstance(rows, list):
                if page_no == 1:
                    self.last_diagnostics = ProviderDiagnostics.unavailable(
                        provider=PROVIDER,
                        error_code="SCHEMA_INVALID",
                        error_message="dart list must be an array",
                        requested_at=requested_at,
                        received_at=received_at,
                    )
                    return CollectionResult.unavailable(error="dart schema invalid", as_of=as_of)
                incomplete = True
                incomplete_reason = f"PAGINATION_INCOMPLETE: page {page_no} list invalid"
                break

            merged["list"] = list(merged.get("list") or []) + rows
            reported_total = payload.get("total_page") or payload.get("totalPage")
            if reported_total not in (None, ""):
                try:
                    total_page = max(1, int(reported_total))
                except (TypeError, ValueError):
                    total_page = page_no
            elif page_no == 1 and len(rows) >= PAGE_SIZE:
                incomplete = True
                incomplete_reason = "PAGINATION_INCOMPLETE: total_page missing after a full page"
                break
            else:
                total_page = page_no
            page_no += 1
            if page_no > PAGE_CAP and page_no <= total_page:
                incomplete = True
                incomplete_reason = "PAGINATION_INCOMPLETE: page cap reached"
                break

        seen: set[str] = set()
        unique_rows: list[object] = []
        for row in list(merged.get("list") or []):
            if not isinstance(row, dict):
                continue
            key = str(row.get("rcept_no") or "").strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            unique_rows.append(row)
        merged["list"] = unique_rows

        try:
            records, rejected = dart_list_to_records(
                merged,
                ticker=ticker,
                collected_at=received_at,
                corp_code=corp_code,
                received_at=received_at,
            )
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

        if rejected and not records and not incomplete:
            self.last_diagnostics = ProviderDiagnostics.unavailable(
                provider=PROVIDER,
                error_code="COMPANY_MISMATCH",
                error_message="response corp_code/stock_code did not match the requested mapping",
                requested_at=requested_at,
                received_at=received_at,
                attempt_count=self._client.last_attempt_count,
            )
            return CollectionResult.unavailable(
                error="DART COMPANY_MISMATCH: response company did not match ticker mapping",
                as_of=as_of,
                freshness_class=FreshnessClass.DAILY,
            )

        access_as_of = received_at if include_current_receive else as_of
        result = collect_accessible(
            records,
            as_of=access_as_of,
            unavailable=False,
            unavailable_reason="dart unavailable",
            match=lambda record: record.ticker == ticker,
            timestamps_of=lambda record: record.timestamps,
            freshness_of=lambda record: record.freshness_class,
            id_of=lambda record: record.record_id,
            empty_status=CollectionStatus.NO_EVENT,
            reject_future_event_occurred=True,
        )
        if incomplete:
            result = CollectionResult.degraded(
                list(result.items),
                error=incomplete_reason or "PAGINATION_INCOMPLETE",
                as_of=as_of,
                freshness_class=FreshnessClass.DAILY,
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
                error_code=result.status.value if not incomplete else "PAGINATION_INCOMPLETE",
                error_message=result.error,
            )
        return result
