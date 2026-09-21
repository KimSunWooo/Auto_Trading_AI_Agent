"""Compatibility rules for a future consumer. No runtime ATS session."""

from __future__ import annotations

from typing import Literal

from ai_investment_agent.contracts.versioning import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    is_supported_schema,
)
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.envelope import (
    ConsumerTradeProposalEnvelope,
    TradeProposalEnvelope,
)
from ai_investment_agent.domain.errors import SerializationError
from ai_investment_agent.domain.serialization import from_json


class CompatibilityPolicy(DomainModel):
    """Frozen rules. Changing them requires a new schemaVersion."""

    current_schema: Literal["ai.trade-proposal.v1"] = CURRENT_SCHEMA_VERSION
    supported_schemas: tuple[str, ...] = SUPPORTED_SCHEMA_VERSIONS
    additive_optional_fields_compatible: Literal[True] = True
    field_rename_or_type_change_is_breaking: Literal[True] = True
    unknown_schema_rejected: Literal[True] = True
    idempotency_key: Literal["proposalId"] = "proposalId"
    producer_role: Literal["TradeProposal Producer"] = "TradeProposal Producer"
    consumer_role: Literal["TradeProposal Consumer"] = "TradeProposal Consumer"
    auto_trading_system_connected: Literal[False] = False
    live_order_path_defined: Literal[False] = False


POLICY = CompatibilityPolicy()


def assert_supported_schema(version: str) -> None:
    if not is_supported_schema(version):
        raise SerializationError(f"unsupported schemaVersion={version}")


def parse_producer_envelope(raw: str) -> TradeProposalEnvelope:
    envelope = from_json(TradeProposalEnvelope, raw)
    assert_supported_schema(envelope.schema_version)
    return envelope


def parse_consumer_envelope(raw: str) -> ConsumerTradeProposalEnvelope:
    """How a future ATS consumer should parse v1 (ignore additive extras)."""

    envelope = from_json(ConsumerTradeProposalEnvelope, raw)
    assert_supported_schema(envelope.schema_version)
    return envelope
