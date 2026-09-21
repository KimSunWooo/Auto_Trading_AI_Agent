from __future__ import annotations

from ai_investment_agent.domain.enums import ModelHealthStatus
from ai_investment_agent.domain.evaluation import ModelHealthMetrics


def health(model_health: ModelHealthMetrics | None = None) -> dict[str, object]:
    metrics = model_health or ModelHealthMetrics.unknown()
    return {
        "status": "ok",
        "mode": "judgment_only",
        "terminalArtifact": "TradeProposal",
        "ordersEnabled": False,
        "brokerConnected": False,
        "autoTradingSystemConnected": False,
        "liveLlmConnected": False,
        "liveMarketDataConnected": False,
        "modelHealth": metrics.status.value,
        "modelHealthTreatedAsHealthy": metrics.treated_as_healthy,
        "unknownIsHealthy": False,
    }
