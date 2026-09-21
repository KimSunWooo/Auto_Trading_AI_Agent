"""Future-integration contract. This package does not talk to Auto-Trading-system."""

from ai_investment_agent.contracts.compatibility import (
    POLICY,
    CompatibilityPolicy,
    parse_consumer_envelope,
    parse_producer_envelope,
)
from ai_investment_agent.contracts.encode import envelope_from_proposal
from ai_investment_agent.contracts.schema_loader import load_schema
from ai_investment_agent.contracts.versioning import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_FAMILY,
    SUPPORTED_SCHEMA_VERSIONS,
    is_supported_schema,
)
from ai_investment_agent.domain.envelope import (
    ConsumerTradeProposalEnvelope,
    EnvelopeInvalidation,
    EnvelopeThesis,
    TradeProposalEnvelope,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "POLICY",
    "SCHEMA_FAMILY",
    "SUPPORTED_SCHEMA_VERSIONS",
    "CompatibilityPolicy",
    "ConsumerTradeProposalEnvelope",
    "EnvelopeInvalidation",
    "EnvelopeThesis",
    "TradeProposalEnvelope",
    "envelope_from_proposal",
    "is_supported_schema",
    "load_schema",
    "parse_consumer_envelope",
    "parse_producer_envelope",
]
