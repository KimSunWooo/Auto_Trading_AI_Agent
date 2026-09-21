"""Schema identity for TradeProposalEnvelope. Independent of modelVersion."""

from __future__ import annotations

from ai_investment_agent.domain.versions import TRADE_PROPOSAL_SCHEMA_VERSION

SCHEMA_FAMILY = "ai.trade-proposal"
CURRENT_SCHEMA_VERSION = TRADE_PROPOSAL_SCHEMA_VERSION
SUPPORTED_SCHEMA_VERSIONS = (TRADE_PROPOSAL_SCHEMA_VERSION,)


def schema_major(version: str) -> int | None:
    prefix = f"{SCHEMA_FAMILY}.v"
    if not version.startswith(prefix):
        return None
    suffix = version[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def is_supported_schema(version: str) -> bool:
    return version in SUPPORTED_SCHEMA_VERSIONS
