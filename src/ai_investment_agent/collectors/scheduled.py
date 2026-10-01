"""Helpers for optional scheduled-event providers."""

from __future__ import annotations

from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus


def is_unconfigured_scheduled(result: CollectionResult) -> bool:
    if result.status is not CollectionStatus.DATA_UNAVAILABLE:
        return False
    return "NOT_CONFIGURED" in (result.error or "")
