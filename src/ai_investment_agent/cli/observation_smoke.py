"""Manual LIVE_OBSERVATION smoke. Requires real env credentials; skipped in CI."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from ai_investment_agent.domain.enums import Action, CollectionStatus


REQUIRED_PROVIDER_NAMES = ("market", "disclosure", "macro", "news", "llm")


def classify_observation_smoke(
    *,
    action: Action,
    readiness_allows_new_buy: bool | None,
    diagnostics: dict[str, object],
    llm_called: bool,
) -> tuple[int, str]:
    """Distinguish healthy NO_TRADE from required-provider failure.

    Exit 0: collectors completed and the judgment is a valid NO_TRADE / wait.
    Exit 1: a required provider failed, was not configured, or was never called.
    Exit 2: environment refused (NO_NETWORK / wrong mode) — handled by main.
    """
    failed: list[str] = []
    for name in REQUIRED_PROVIDER_NAMES:
        diag = diagnostics.get(name)
        if diag is None:
            failed.append(f"{name}:NOT_CALLED")
            continue
        status = getattr(diag, "status", None)
        if status in {CollectionStatus.DATA_UNAVAILABLE, CollectionStatus.DEGRADED}:
            failed.append(f"{name}:{status.value}")
    if not llm_called:
        failed.append("llm:NOT_CALLED")
    if failed:
        return 1, "REQUIRED_PROVIDER_FAILURE " + ",".join(failed)
    if action is Action.NO_TRADE:
        label = "HEALTHY_NO_TRADE"
        if readiness_allows_new_buy is False:
            label = "HEALTHY_NO_TRADE_GATED"
        return 0, label
    return 0, f"COMPLETED action={action.value}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LIVE_OBSERVATION smoke (manual). Does not place orders.",
    )
    parser.add_argument("--ticker", default=os.environ.get("OBSERVATION_TICKER", "005930"))
    args = parser.parse_args(argv)

    if os.environ.get("NO_NETWORK") == "1":
        print("Refusing live smoke under NO_NETWORK=1", file=sys.stderr)
        return 2
    if os.environ.get("AI_DATA_MODE", "").upper() != "LIVE_OBSERVATION":
        print("Set AI_DATA_MODE=LIVE_OBSERVATION to run this smoke.", file=sys.stderr)
        return 2

    from ai_investment_agent.adapters.live.factory import build_live_observation_service

    service = build_live_observation_service(now_fn=lambda: datetime.now(timezone.utc))
    result = service.evaluate(args.ticker)
    readiness = result.readiness.status.value if result.readiness else "UNKNOWN"
    market_diag = getattr(service.market, "last_diagnostics", None)
    dart_diag = getattr(service.disclosure, "last_diagnostics", None)
    macro_diag = getattr(service.macro, "last_diagnostics", None)
    news_diag = getattr(service.news, "last_diagnostics", None)
    llm_diag = getattr(service.llm, "last_diagnostics", None) if service.llm else None
    llm_called = llm_diag is not None

    def status_of(diag: object | None, fallback: str) -> str:
        if diag is None:
            return fallback
        status = getattr(diag, "status", None)
        return status.value if status is not None else fallback

    code, classification = classify_observation_smoke(
        action=result.action,
        readiness_allows_new_buy=(
            result.readiness.allows_new_buy if result.readiness is not None else None
        ),
        diagnostics={
            "market": market_diag,
            "disclosure": dart_diag,
            "macro": macro_diag,
            "news": news_diag,
            "llm": llm_diag,
        },
        llm_called=llm_called,
    )

    print(f"Runtime:\n{result.data_mode.value}\n")
    print(f"Market:\n{status_of(market_diag, result.market_status.value)}\n")
    print(f"DART:\n{status_of(dart_diag, 'UNKNOWN')}\n")
    print(f"Macro:\n{status_of(macro_diag, 'UNKNOWN')}\n")
    print(f"News:\n{status_of(news_diag, 'UNKNOWN')}\n")
    print(f"LLM:\n{status_of(llm_diag, 'UNKNOWN')}\n")
    print(f"Readiness:\n{readiness}\n")
    print(f"Classification:\n{classification}\n")
    print(f"Ticker:\n{result.ticker}\n")
    print(f"Action:\n{result.action.value}\n")
    print("isOrder:\nfalse\n")
    print("BrokerCalled:\nfalse\n")
    print("OrdersPlaced:\n0")
    assert result.broker_called is False
    assert result.orders_placed == 0
    if result.envelope is not None:
        assert result.envelope.is_order is False
    return code


if __name__ == "__main__":
    raise SystemExit(main())
