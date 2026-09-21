"""Judgment-only HTTP API. Order and broker routes are not defined."""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import Field

from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import ModelHealthStatus
from ai_investment_agent.domain.errors import DecisionNotFoundError
from ai_investment_agent.health.report import collect_health

FORBIDDEN_ORDER_PATHS = (
    "/orders",
    "/buy",
    "/sell",
    "/cancel",
    "/broker",
)


class EvaluateRequest(DomainModel):
    ticker: str = Field(min_length=1, default="005930")
    as_of: datetime | None = None


def create_app(service: AnalysisService | None = None) -> FastAPI:
    analysis = service or AnalysisService()
    app = FastAPI(
        title="AI Investment Judgment Agent",
        description=(
            "Standalone analysis API. Terminal artifact is TradeProposal. "
            "This service does not place, cancel, or route broker orders."
        ),
        version="0.1.0",
    )
    app.state.analysis = analysis

    @app.get("/")
    def root() -> dict[str, object]:
        return {
            "name": "ai-investment-agent",
            "mode": "judgment_only",
            "terminalArtifact": "TradeProposal",
            "ordersEnabled": False,
            "brokerConnected": False,
            "autoTradingSystemConnected": False,
        }

    @app.post("/analysis/evaluate")
    def evaluate(body: EvaluateRequest) -> JSONResponse:
        result = analysis.evaluate(body.ticker, as_of=body.as_of)
        return JSONResponse(result.model_dump(mode="json"))

    @app.get("/decisions")
    def list_decisions() -> JSONResponse:
        items = [record.model_dump(mode="json") for record in analysis.list_decisions()]
        return JSONResponse({"items": items, "count": len(items)})

    @app.get("/decisions/{decision_id}")
    def get_decision(decision_id: str) -> JSONResponse:
        snapshot = analysis.get_decision(decision_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="decision not found")
        return JSONResponse(snapshot.to_record().model_dump(mode="json"))

    @app.post("/decisions/{decision_id}/replay")
    def replay_decision(decision_id: str) -> JSONResponse:
        try:
            bundle = analysis.replay_decision(decision_id)
        except DecisionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(bundle.model_dump(mode="json"))

    @app.get("/health")
    def health_endpoint() -> JSONResponse:
        report = collect_health(analysis)
        payload = report.model_dump(mode="json")
        payload["modelHealthTreatedAsHealthy"] = (
            report.model_health.status is ModelHealthStatus.HEALTHY
        )
        payload["unknownIsHealthy"] = False
        payload["status"] = report.status.value
        return JSONResponse(payload)

    return app


app = create_app()


def run(host: str = "0.0.0.0", port: int = 43187) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)
