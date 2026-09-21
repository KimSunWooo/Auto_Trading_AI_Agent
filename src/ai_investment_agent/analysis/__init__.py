"""Fixture-backed analysis pipeline that stops at TradeProposal."""

from ai_investment_agent.analysis.service import (
    PIPELINE_STAGES,
    AnalysisResult,
    AnalysisService,
)

__all__ = ["PIPELINE_STAGES", "AnalysisResult", "AnalysisService"]
