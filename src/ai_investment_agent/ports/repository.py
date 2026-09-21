from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.journal import DecisionJournalEntry


class DecisionRepository(Protocol):
    def save_snapshot(self, snapshot: DecisionSnapshot) -> None:
        ...

    def get_snapshot(self, decision_id: str) -> DecisionSnapshot | None:
        ...

    def save_journal_entry(self, entry: DecisionJournalEntry) -> None:
        ...

    def list_journal(self, decision_id: str) -> Sequence[DecisionJournalEntry]:
        ...
