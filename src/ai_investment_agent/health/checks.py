from __future__ import annotations


def health() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "judgment_only",
        "terminalArtifact": "TradeProposal",
        "ordersEnabled": False,
        "brokerConnected": False,
        "autoTradingSystemConnected": False,
        "liveLlmConnected": False,
        "liveMarketDataConnected": False,
    }
