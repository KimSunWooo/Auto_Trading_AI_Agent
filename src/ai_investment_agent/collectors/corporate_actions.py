from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ai_investment_agent.collectors.loading import DATA_DIR, corporate_action_from_dict
from ai_investment_agent.collectors.query import collect_accessible
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.corporate_action import CorporateAction
from ai_investment_agent.domain.enums import CollectionStatus


class FixtureCorporateActionSource:
    """Fixture-only corporate actions. There is no live feed in this project."""

    def __init__(
        self,
        actions: Sequence[CorporateAction] | None = None,
        *,
        unavailable: bool = False,
        unavailable_reason: str = "fixture corporate action source failure",
    ) -> None:
        self._actions = list(actions or [])
        self._unavailable = unavailable
        self._unavailable_reason = unavailable_reason

    @classmethod
    def from_file(cls, name: str = "corporate_actions.json") -> FixtureCorporateActionSource:
        path = DATA_DIR / name
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        return cls([corporate_action_from_dict(item) for item in raw.get("actions", [])])

    @classmethod
    def from_path(cls, path: Path) -> FixtureCorporateActionSource:
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        return cls([corporate_action_from_dict(item) for item in raw.get("actions", [])])

    def all_actions(self) -> list[CorporateAction]:
        return list(self._actions)

    def list_for(self, ticker: str, as_of: datetime) -> CollectionResult[CorporateAction]:
        return collect_accessible(
            self._actions,
            as_of=as_of,
            unavailable=self._unavailable,
            unavailable_reason=self._unavailable_reason,
            match=lambda action: action.ticker == ticker,
            timestamps_of=lambda action: action.timestamps,
            freshness_of=lambda action: action.freshness_class,
            id_of=lambda action: action.action_id,
            empty_status=CollectionStatus.NO_EVENT,
        )
