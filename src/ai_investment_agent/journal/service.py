from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.ids import new_journal_id
from ai_investment_agent.domain.journal import DecisionJournalEntry, DecisionRecord
from ai_investment_agent.domain.enums import JournalStage
from ai_investment_agent.ports.repository import DecisionRepository


class JournalService:
    """Persists every judgment, including NO_TRADE and TACTICAL_WAIT."""

    def __init__(
        self,
        repository: DecisionRepository,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    def record(
        self,
        decision_id: str,
        stage: JournalStage,
        message: str,
        reason_codes: list[str] | None = None,
        payload: dict | None = None,
    ) -> DecisionJournalEntry:
        entry = DecisionJournalEntry(
            journal_id=new_journal_id(),
            decision_id=decision_id,
            stage=stage,
            message=message,
            reason_codes=reason_codes or [],
            payload=payload or {},
            recorded_at=self._now(),
        )
        self._repository.save_journal_entry(entry)
        return entry

    def to_record(self, snapshot: DecisionSnapshot) -> DecisionRecord:
        return snapshot.to_record()
