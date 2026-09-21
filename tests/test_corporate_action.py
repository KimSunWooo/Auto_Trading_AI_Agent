from ai_investment_agent.collectors.corporate_actions import FixtureCorporateActionSource
from ai_investment_agent.domain.corporate_action import CorporateAction
from ai_investment_agent.domain.enums import CollectionStatus, CorporateActionType
from ai_investment_agent.domain.serialization import from_json, to_json
from tests.collection_support import FIXED_AS_OF

REQUIRED_TYPES = {
    CorporateActionType.DIVIDEND,
    CorporateActionType.EX_DIVIDEND,
    CorporateActionType.SPLIT,
    CorporateActionType.REVERSE_SPLIT,
    CorporateActionType.MERGE,
    CorporateActionType.RIGHTS_ISSUE,
    CorporateActionType.BONUS_ISSUE,
    CorporateActionType.RIGHTS_OFF,
    CorporateActionType.TRADING_HALT,
    CorporateActionType.DELISTING,
    CorporateActionType.MERGER,
    CorporateActionType.TICKER_CHANGE,
}


def test_fixture_contains_every_corporate_action_type():
    source = FixtureCorporateActionSource.from_file()
    types = {action.action_type for action in source.all_actions()}
    assert types == REQUIRED_TYPES


def test_corporate_action_json_roundtrip_uses_camel_case():
    source = FixtureCorporateActionSource.from_file()
    original = next(
        action for action in source.all_actions() if action.action_type is CorporateActionType.DIVIDEND
    )
    raw = to_json(original)
    assert '"actionId"' in raw
    assert '"actionType"' in raw
    assert '"exDate"' in raw
    assert '"cashAmount"' in raw
    assert '"eventOccurredAt"' in raw
    assert '"publishedAt"' in raw
    assert '"sourceReceivedAt"' in raw
    assert '"collectedAt"' in raw
    assert '"normalizedAt"' in raw
    assert '"analyzedAt"' in raw
    assert '"tradableAt"' in raw
    restored = from_json(CorporateAction, raw)
    assert restored == original


def test_every_fixture_action_roundtrips():
    source = FixtureCorporateActionSource.from_file()
    for action in source.all_actions():
        assert from_json(CorporateAction, to_json(action)) == action


def test_corporate_actions_are_fixture_only_and_as_of_filtered():
    source = FixtureCorporateActionSource.from_file()
    listed = source.list_for("005930", FIXED_AS_OF)
    assert listed.status is CollectionStatus.OK
    assert all(item.source == "fixture-corporate-action" for item in listed.items)
    assert all(item.timestamps.tradable_at <= FIXED_AS_OF for item in listed.items)

    empty = source.list_for("NO_SUCH", FIXED_AS_OF)
    assert empty.status is CollectionStatus.NO_EVENT
    assert empty.items == []
