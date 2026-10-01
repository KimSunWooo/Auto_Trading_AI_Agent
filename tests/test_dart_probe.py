"""Network-free DART-only probe tests. Does not call real OpenDART."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    ProviderHttpConfig,
    RateLimitConfig,
    RetryConfig,
)
from ai_investment_agent.adapters.live.http import ProviderHttpClient
from ai_investment_agent.cli import dart_probe
from ai_investment_agent.cli.dart_probe import (
    EXIT_CONFIG_CHECK_ONLY,
    EXIT_FAILED,
    EXIT_LIVE_DEGRADED,
    EXIT_LIVE_OK,
    EXIT_NETWORK_BLOCKED,
    run_probe,
)
from tests.test_live_acceptance_1058 import _dart_row
from tests.test_live_observation import FakeTransport
from tests.test_provider_framework import FakeTransport as SeqTransport


T0 = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
SECRET = "supersecret-dart-key-xyz12345"


class CountingTransport:
    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.calls: list[str] = []

    def request(self, method, url, *, headers, body, connect_timeout, read_timeout):
        self.calls.append(url)
        return self.inner.request(
            method,
            url,
            headers=headers,
            body=body,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )


def _run(argv, *, transport=None, monkeypatch=None):
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_probe(
        argv,
        transport=transport,
        now_fn=lambda: T0,
        stdout=stdout,
        stderr=stderr,
    )
    text = stdout.getvalue()
    payload = json.loads(text) if text.strip() else {}
    return code, payload, text, stderr.getvalue()


def _live_env(monkeypatch, **extra: str | None) -> None:
    monkeypatch.setenv("DART_API_KEY", SECRET)
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("DART_BASE_URL", "https://example.test/api")
    for key, value in extra.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_default_config_check_uses_no_network(monkeypatch):
    _live_env(monkeypatch)
    boom = CountingTransport(FakeTransport({}))
    code, payload, text, _err = _run([], transport=boom, monkeypatch=monkeypatch)
    assert code == EXIT_CONFIG_CHECK_ONLY
    assert payload["outcome"] == "CONFIG_CHECK_ONLY"
    assert payload["networkExecuted"] is False
    assert payload["judgmentPipelineRun"] is False
    assert payload["otherProvidersCalled"] == []
    assert payload["apiKeyConfigured"] is True
    assert payload["corpCode"] == "00126380"
    assert SECRET not in text
    assert boom.calls == []


def test_no_network_blocks_live_even_with_flag(monkeypatch):
    _live_env(monkeypatch)
    monkeypatch.setenv("NO_NETWORK", "1")
    boom = CountingTransport(
        FakeTransport(
            {"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())}
        )
    )
    code, payload, _text, _err = _run(["--live"], transport=None, monkeypatch=monkeypatch)
    assert code == EXIT_NETWORK_BLOCKED
    assert payload["outcome"] == "NETWORK_BLOCKED"
    assert payload["networkExecuted"] is False
    assert boom.calls == []


def test_missing_api_key_and_corp_mapping(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("DART_CORP_CODE", raising=False)
    monkeypatch.delenv("DART_CORP_CODE_005930", raising=False)
    monkeypatch.setenv("DART_BASE_URL", "https://example.test/api")
    code, payload, _text, _err = _run([], monkeypatch=monkeypatch)
    assert code == EXIT_FAILED
    assert payload["outcome"] == "FAILED"
    assert payload["errorCode"] == "MISSING_CREDENTIAL"
    assert payload["networkExecuted"] is False

    monkeypatch.setenv("DART_API_KEY", SECRET)
    code, payload, _text, _err = _run([], monkeypatch=monkeypatch)
    assert code == EXIT_FAILED
    assert payload["errorCode"] == "MISSING_CORP_CODE"


def test_live_single_and_multi_page(monkeypatch):
    _live_env(monkeypatch)
    single = CountingTransport(
        FakeTransport(
            {
                "/list.json": (
                    200,
                    json.dumps({"status": "000", "list": [_dart_row()]}).encode(),
                )
            }
        )
    )
    code, payload, text, _err = _run(["--live"], transport=single, monkeypatch=monkeypatch)
    assert code == EXIT_LIVE_OK
    assert payload["outcome"] == "LIVE_OK"
    assert payload["status"] == "OK"
    assert payload["networkExecuted"] is True
    assert payload["accessibleCount"] == 1
    assert payload["paginationComplete"] is True
    assert payload["uniqueRowCount"] == 1
    assert SECRET not in text
    assert "crtfc_key" not in text
    assert single.calls
    assert all("/list.json" in url for url in single.calls)

    page = {"status": "000", "total_page": 2, "list": [_dart_row("20260921000001")]}
    page2 = {"status": "000", "total_page": 2, "list": [_dart_row("20260921000002")]}
    multi = CountingTransport(
        SeqTransport([(200, json.dumps(page).encode()), (200, json.dumps(page2).encode())])
    )
    code, payload, _text, _err = _run(["--live"], transport=multi, monkeypatch=monkeypatch)
    assert code == EXIT_LIVE_OK
    assert payload["outcome"] == "LIVE_OK"
    assert payload["pagesFetched"] == 2
    assert payload["uniqueRowCount"] == 2
    assert payload["accessibleCount"] == 2


def test_live_no_event_is_successful_query(monkeypatch):
    _live_env(monkeypatch)
    transport = CountingTransport(
        FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    )
    code, payload, _text, _err = _run(["--live"], transport=transport, monkeypatch=monkeypatch)
    assert code == EXIT_LIVE_OK
    assert payload["outcome"] == "LIVE_NO_EVENT"
    assert payload["status"] == "NO_EVENT"


def test_company_mismatch_and_duplicate_pages(monkeypatch):
    _live_env(monkeypatch)
    mismatch = CountingTransport(
        FakeTransport(
            {
                "/list.json": (
                    200,
                    json.dumps(
                        {
                            "status": "000",
                            "list": [_dart_row(corp_code="00000000", stock_code="000000")],
                        }
                    ).encode(),
                )
            }
        )
    )
    code, payload, _text, _err = _run(["--live"], transport=mismatch, monkeypatch=monkeypatch)
    assert code == EXIT_FAILED
    assert payload["outcome"] == "FAILED"
    assert payload["errorCode"] == "COMPANY_MISMATCH"
    assert payload["rejectedCompanyMismatch"] == 1

    page = {"status": "000", "total_page": 2, "list": [_dart_row("20260921000001")]}
    dup = CountingTransport(
        SeqTransport([(200, json.dumps(page).encode()), (200, json.dumps(page).encode())])
    )
    code, payload, _text, _err = _run(["--live"], transport=dup, monkeypatch=monkeypatch)
    assert code == EXIT_LIVE_OK
    assert payload["rawRowCount"] == 2
    assert payload["uniqueRowCount"] == 1
    assert payload["accessibleCount"] == 1


def test_mid_page_failure_is_degraded_not_full_success(monkeypatch):
    _live_env(monkeypatch)
    transport = CountingTransport(
        SeqTransport(
            [
                (200, json.dumps({"status": "000", "total_page": 2, "list": [_dart_row()]}).encode()),
                (500, b'{"error":"page2"}'),
                (500, b'{"error":"page2-retry"}'),
            ]
        )
    )
    code, payload, _text, _err = _run(["--live"], transport=transport, monkeypatch=monkeypatch)
    assert code == EXIT_LIVE_DEGRADED
    assert payload["outcome"] == "LIVE_DEGRADED"
    assert payload["status"] == "DEGRADED"
    assert payload["paginationComplete"] is False
    assert payload["accessibleCount"] == 1


def test_auth_timeout_invalid_json(monkeypatch):
    _live_env(monkeypatch)
    auth = CountingTransport(FakeTransport({"/list.json": (401, b'{"error":"auth"}')}))
    code, payload, _text, _err = _run(["--live"], transport=auth, monkeypatch=monkeypatch)
    assert code == EXIT_FAILED
    assert payload["outcome"] == "FAILED"
    assert payload["errorCode"] in {"HTTP_401", "DATA_UNAVAILABLE"}

    invalid = CountingTransport(FakeTransport({"/list.json": (200, b"{not-json")}))
    code, payload, _text, _err = _run(["--live"], transport=invalid, monkeypatch=monkeypatch)
    assert code == EXIT_FAILED
    assert payload["errorCode"] in {"SCHEMA_INVALID", "HTTP_ERROR", "INVALID_JSON"}

    clock = [0.0]

    class LateTransport:
        def request(self, method, url, *, headers, body, connect_timeout, read_timeout):
            clock[0] += 20.0
            return 200, json.dumps({"status": "013", "list": []}).encode()

    cfg = ProviderHttpConfig(
        name="dart",
        base_url="https://example.test/api",
        api_key_env="DART_API_KEY",
        timeout=HttpTimeoutConfig(total_seconds=1.0, connect_seconds=5.0, read_seconds=5.0),
        retry=RetryConfig(max_attempts=1),
        rate_limit=RateLimitConfig(max_requests_per_second=0),
        circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
    )
    late_client = ProviderHttpClient(
        config=cfg,
        transport=LateTransport(),
        monotonic_fn=lambda: clock[0],
        sleep_fn=lambda _s: None,
    )
    code = _run_with_client(late_client, monkeypatch)
    assert code == EXIT_FAILED


def _run_with_client(client, monkeypatch) -> int:
    stdout = io.StringIO()
    stderr = io.StringIO()
    original = dart_probe.ProviderHttpClient

    def factory(*args, **kwargs):
        del args, kwargs
        return client

    monkeypatch.setattr(dart_probe, "ProviderHttpClient", factory)
    try:
        return run_probe(
            ["--live"],
            transport=object(),
            now_fn=lambda: T0,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        monkeypatch.setattr(dart_probe, "ProviderHttpClient", original)


def test_secret_not_exposed_in_stdout_or_evidence(monkeypatch, tmp_path: Path):
    _live_env(monkeypatch)
    evidence = tmp_path / "dart-probe.json"
    transport = CountingTransport(
        FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    )
    code, payload, text, _err = _run(
        ["--live", "--write-evidence", str(evidence)],
        transport=transport,
        monkeypatch=monkeypatch,
    )
    assert code == EXIT_LIVE_OK
    saved = evidence.read_text(encoding="utf-8")
    assert SECRET not in text
    assert SECRET not in saved
    assert "crtfc_key" not in text
    assert "Authorization" not in text
    assert payload["apiKeyValue"] is None
    exists_code, _payload, _text, err = _run(
        ["--live", "--write-evidence", str(evidence)],
        transport=transport,
        monkeypatch=monkeypatch,
    )
    assert exists_code == EXIT_FAILED
    assert "already exists" in err


def test_probe_does_not_construct_other_providers_or_llm(monkeypatch):
    _live_env(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("other provider must not be constructed")

    monkeypatch.setattr(
        "ai_investment_agent.adapters.live.market.LiveMarketDataCollector.__init__", boom
    )
    monkeypatch.setattr(
        "ai_investment_agent.adapters.live.news.LiveNewsCollector.__init__", boom
    )
    monkeypatch.setattr(
        "ai_investment_agent.adapters.live.macro.LiveMacroCollector.__init__", boom
    )
    monkeypatch.setattr("ai_investment_agent.adapters.live.llm.LiveLlmProvider.__init__", boom)
    monkeypatch.setattr("ai_investment_agent.analysis.service.AnalysisService.evaluate", boom)
    monkeypatch.setattr("ai_investment_agent.cli.observation_smoke.main", boom)
    transport = CountingTransport(
        FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    )
    code, payload, _text, _err = _run(["--live"], transport=transport, monkeypatch=monkeypatch)
    assert code == EXIT_LIVE_OK
    assert payload["otherProvidersCalled"] == []
    assert payload["judgmentPipelineRun"] is False
    assert all("/list.json" in url for url in transport.calls)
    assert not any(token in url for url in transport.calls for token in ("/market/", "/news", "/macro", "/chat"))
