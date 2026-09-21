"""Collectors for market data vs external intelligence.

Fixture implementations only. No live quotes, DART, news APIs, brokers,
Redis, or Kafka.
"""

from ai_investment_agent.collectors.corporate_actions import FixtureCorporateActionSource
from ai_investment_agent.collectors.intelligence import (
    FixtureDisclosureCollector,
    FixtureMacroCollector,
    FixtureNewsCollector,
    FixtureScheduledEventCollector,
)
from ai_investment_agent.collectors.market import FixtureMarketDataCollector
from ai_investment_agent.collectors.raw import InMemoryRawStore

__all__ = [
    "FixtureCorporateActionSource",
    "FixtureDisclosureCollector",
    "FixtureMacroCollector",
    "FixtureMarketDataCollector",
    "FixtureNewsCollector",
    "FixtureScheduledEventCollector",
    "InMemoryRawStore",
]
