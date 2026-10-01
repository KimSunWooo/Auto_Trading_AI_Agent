"""DART-only manual inspect. Does not run AnalysisService or other providers.

Default: configuration check, no network.
Live query requires --live and is blocked when NO_NETWORK=1 unless a
test transport is injected.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    ProviderHttpConfig,
    RateLimitConfig,
    RetryConfig,
    dart_http_config,
    mask_secrets,
)
from ai_investment_agent.adapters.live.dart import (
    PAGE_CAP,
    PAGE_SIZE,
    PROVIDER,
    LiveDisclosureCollector,
    resolve_dart_corp_code,
)
from ai_investment_agent.adapters.live.http import ProviderHttpClient
from ai_investment_agent.domain.enums import CollectionStatus

PROBE_PAGE_CAP = 10
PROBE_MAX_ATTEMPTS = 2
PROBE_TOTAL_SECONDS = 15.0
EXIT_LIVE_OK = 0
EXIT_NETWORK_BLOCKED = 2
EXIT_CONFIG_CHECK_ONLY = 3
EXIT_LIVE_DEGRADED = 4
EXIT_FAILED = 5


def repo_commit_sha() -> str:
    try:
        raw = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return raw.decode().strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key_configured() -> bool:
    value = os.environ.get("DART_API_KEY", "")
    return bool(value.strip())


def _probe_http_config() -> ProviderHttpConfig:
    base = dart_http_config()
    attempts = min(base.retry.max_attempts, PROBE_MAX_ATTEMPTS)
    total = min(base.timeout.total_seconds, PROBE_TOTAL_SECONDS)
    return ProviderHttpConfig(
        name=base.name,
        base_url=base.base_url,
        api_key_env=base.api_key_env,
        timeout=HttpTimeoutConfig(
            connect_seconds=min(base.timeout.connect_seconds, 3.0),
            read_seconds=min(base.timeout.read_seconds, 10.0),
            total_seconds=total,
        ),
        retry=RetryConfig(max_attempts=max(1, attempts), base_backoff_seconds=0.0),
        rate_limit=RateLimitConfig(max_requests_per_second=min(base.rate_limit.max_requests_per_second, 1.0)),
        circuit=CircuitBreakerConfig(
            failure_threshold=base.circuit.failure_threshold,
            cooldown_seconds=base.circuit.cooldown_seconds,
        ),
    )


def _base_payload(*, ticker: str, corp_code: str | None, network_executed: bool) -> dict[str, Any]:
    return {
        "commitSha": repo_commit_sha(),
        "provider": PROVIDER,
        "collector": "LiveDisclosureCollector",
        "ticker": ticker,
        "corpCode": corp_code,
        "corpCodeConfigured": corp_code is not None,
        "apiKeyConfigured": _key_configured(),
        "apiKeyValue": None,
        "networkExecuted": network_executed,
        "judgmentPipelineRun": False,
        "otherProvidersCalled": [],
        "isOrder": False,
        "ordersPlaced": 0,
        "pageCap": min(PROBE_PAGE_CAP, PAGE_CAP),
        "pageSize": PAGE_SIZE,
        "retryMaxAttempts": min(dart_http_config().retry.max_attempts, PROBE_MAX_ATTEMPTS),
        "totalTimeoutSeconds": min(dart_http_config().timeout.total_seconds, PROBE_TOTAL_SECONDS),
    }


def classify_config(*, ticker: str, corp_code: str | None) -> tuple[str, int, str | None]:
    if not ticker.strip():
        return "FAILED", EXIT_FAILED, "MISSING_TICKER"
    if not _key_configured():
        return "FAILED", EXIT_FAILED, "MISSING_CREDENTIAL"
    if corp_code is None:
        return "FAILED", EXIT_FAILED, "MISSING_CORP_CODE"
    return "CONFIG_CHECK_ONLY", EXIT_CONFIG_CHECK_ONLY, None


def classify_live(status: CollectionStatus, error_code: str | None) -> tuple[str, int]:
    if status is CollectionStatus.OK:
        return "LIVE_OK", EXIT_LIVE_OK
    if status is CollectionStatus.NO_EVENT:
        return "LIVE_NO_EVENT", EXIT_LIVE_OK
    if status is CollectionStatus.DEGRADED:
        return "LIVE_DEGRADED", EXIT_LIVE_DEGRADED
    return "FAILED", EXIT_FAILED


def run_probe(
    argv: list[str] | None = None,
    *,
    transport: Any | None = None,
    now_fn: Callable[[], datetime] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "DART-only inspect. Default is a configuration check. "
            "Pass --live to query OpenDART. Does not place orders."
        )
    )
    parser.add_argument("--ticker", default=os.environ.get("OBSERVATION_TICKER", "005930"))
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute a real DART list.json query. Default is config check only.",
    )
    parser.add_argument(
        "--write-evidence",
        metavar="PATH",
        help="Write redacted JSON evidence. Refuses to overwrite an existing file.",
    )
    args = parser.parse_args(argv)
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    clock = now_fn or _now
    ticker = str(args.ticker).strip()
    corp_code = resolve_dart_corp_code(ticker) if ticker else None

    if args.live and transport is None and os.environ.get("NO_NETWORK") == "1":
        payload = _base_payload(ticker=ticker, corp_code=corp_code, network_executed=False)
        payload.update(
            {
                "outcome": "NETWORK_BLOCKED",
                "status": None,
                "errorCode": "NETWORK_BLOCKED",
                "errorMessage": "NO_NETWORK=1 blocked DART live probe",
                "requestedAt": None,
                "receivedAt": None,
            }
        )
        if not _emit(payload, out, args.write_evidence, err):
            return EXIT_FAILED
        return EXIT_NETWORK_BLOCKED

    if not args.live:
        outcome, code, error = classify_config(ticker=ticker, corp_code=corp_code)
        payload = _base_payload(ticker=ticker, corp_code=corp_code, network_executed=False)
        payload.update(
            {
                "outcome": outcome,
                "status": None,
                "errorCode": error,
                "errorMessage": None if error is None else _message_for(error),
                "requestedAt": None,
                "receivedAt": None,
                "attemptCount": 0,
                "pagesFetched": 0,
                "paginationComplete": None,
                "rawRowCount": 0,
                "uniqueRowCount": 0,
                "accessibleCount": 0,
                "rejectedCompanyMismatch": 0,
            }
        )
        if not _emit(payload, out, args.write_evidence, err):
            return EXIT_FAILED
        return code

    config_outcome, config_code, config_error = classify_config(ticker=ticker, corp_code=corp_code)
    if config_outcome != "CONFIG_CHECK_ONLY":
        payload = _base_payload(ticker=ticker, corp_code=corp_code, network_executed=False)
        payload.update(
            {
                "outcome": "FAILED",
                "status": CollectionStatus.DATA_UNAVAILABLE.value,
                "errorCode": config_error,
                "errorMessage": _message_for(config_error or "CONFIG_INCOMPLETE"),
                "requestedAt": None,
                "receivedAt": None,
                "attemptCount": 0,
                "pagesFetched": 0,
                "paginationComplete": False,
                "rawRowCount": 0,
                "uniqueRowCount": 0,
                "accessibleCount": 0,
                "rejectedCompanyMismatch": 0,
            }
        )
        if not _emit(payload, out, args.write_evidence, err):
            return EXIT_FAILED
        return config_code

    http_config = _probe_http_config()
    if transport is None:
        client = ProviderHttpClient(config=http_config)
    else:
        client = ProviderHttpClient(config=http_config, transport=transport)
        client.sleep_fn = lambda _s: None
    collector = LiveDisclosureCollector(client=client, received_at_fn=clock)
    as_of = clock()
    result = collector.collect(
        ticker,
        as_of,
        include_current_receive=True,
        page_cap=min(PROBE_PAGE_CAP, PAGE_CAP),
    )
    diagnostics = collector.last_diagnostics
    stats = collector.last_collection_stats or {}
    error_code = getattr(diagnostics, "error_code", None)
    outcome, code = classify_live(result.status, error_code)
    payload = _base_payload(ticker=ticker, corp_code=corp_code, network_executed=True)
    payload.update(
        {
            "outcome": outcome,
            "status": result.status.value,
            "errorCode": error_code,
            "errorMessage": mask_secrets(result.error) if result.error else None,
            "requestedAt": (
                diagnostics.requested_at.isoformat()
                if diagnostics is not None and diagnostics.requested_at is not None
                else as_of.isoformat()
            ),
            "receivedAt": (
                diagnostics.received_at.isoformat()
                if diagnostics is not None and diagnostics.received_at is not None
                else clock().isoformat()
            ),
            "attemptCount": getattr(diagnostics, "attempt_count", 0),
            "pagesFetched": stats.get("pagesFetched"),
            "totalPageReported": stats.get("totalPageReported"),
            "paginationComplete": stats.get("paginationComplete"),
            "rawRowCount": stats.get("rawRowCount"),
            "uniqueRowCount": stats.get("uniqueRowCount"),
            "accessibleCount": stats.get("accessibleCount", len(result.items)),
            "rejectedCompanyMismatch": stats.get("rejectedCompanyMismatch"),
        }
    )
    if not _emit(payload, out, args.write_evidence, err):
        return EXIT_FAILED
    return code


def _message_for(error_code: str) -> str:
    messages = {
        "MISSING_TICKER": "ticker is required",
        "MISSING_CREDENTIAL": "DART_API_KEY is not set",
        "MISSING_CORP_CODE": "DART_CORP_CODE or DART_CORP_CODE_<TICKER> is required",
        "CONFIG_INCOMPLETE": "DART configuration is incomplete",
    }
    return messages.get(error_code, error_code)


def _emit(
    payload: dict[str, Any],
    out: TextIO,
    evidence_path: str | None,
    err: TextIO,
) -> bool:
    text = mask_secrets(json.dumps(payload, ensure_ascii=False, indent=2))
    if "crtfc_key" in text.lower() or "authorization" in text.lower():
        print("refusing to emit a payload that looks like it contains secrets", file=err)
        return False
    print(text, file=out)
    if not evidence_path:
        return True
    path = Path(evidence_path)
    if path.exists():
        print(f"evidence file already exists: {path}", file=err)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    return run_probe(argv)


if __name__ == "__main__":
    raise SystemExit(main())
